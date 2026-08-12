"""
Ingestion trust layer: deterministic, no-ML checks over ingested files.

Implements docs/specs/0002-ingestion-trust-layer.md. Every public function here
degrades to an empty/None result on internal failure rather than raising —
malformed or adversarial input must never crash the pack pipeline (mirrors the
"cache writes must never crash the main pipeline" posture in cache.py).
"""
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import defusedxml.ElementTree as DET
import fitz

from agentpack.models import DocumentBlock, ExtractionWarning

_DOCX_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_DOCX_DOCUMENT_PART = "word/document.xml"

_PPTX_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
_PPTX_SLIDE_RE = re.compile(r"ppt/slides/slide(\d+)\.xml$")
# DrawingML expresses font size in hundredths of a point (sz="1800" = 18pt) —
# verified against a real python-pptx-generated file — unlike PDF/DOCX's
# whole/half points. 200 = 2pt, the same sub-legible-size concept as T1.4.
_PPTX_MIN_FONT_SIZE_HUNDREDTHS = 200

# SpreadsheetML uses one namespace (no separate "run container" vs "run"
# namespace split like DOCX/PPTX). Verified against real files from BOTH
# openpyxl (which defaults to inline strings, t="inlineStr", written directly
# in each worksheet part — xl/sharedStrings.xml isn't even produced) and
# xlsxwriter (which does use xl/sharedStrings.xml) — a plan that checked only
# sharedStrings.xml would silently miss every openpyxl-produced file.
_XLSX_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_XLSX_SHARED_STRINGS_PART = "xl/sharedStrings.xml"
_XLSX_SHEET_RE = re.compile(r"xl/worksheets/sheet(\d+)\.xml$")

# PDF text-rendering mode 3 ("3 Tr") always renders invisibly — the mechanism
# OCR pipelines use to lay a searchable text layer over a scanned image. It's
# also the simplest way to hide an instruction from a human skim while
# leaving it fully readable to a text-extraction pipeline.
_INVISIBLE_RENDER_MODE = 3

# Additional PDF concealment signals from the same get_texttrace() pass — no
# extra rendering cost. Real, human-authored content in these formats sits
# nowhere near these thresholds (default fill_opacity=1.0, default
# fontsize=11 in every producer we've checked), so false positives on
# ordinary documents are not expected at these levels.
_MIN_OPACITY = 0.05    # near-zero; genuinely visible text is opacity 1.0
_MIN_FONT_SIZE = 2.0   # points; below this is sub-legible to a human reader

# The sub-2pt check alone false-positived on demo_corpus/3M_2018_10K.pdf — a
# real SEC filing — on a bare space (page 39/131) and a 3-character fragment
# "low" (page 1), both almost certainly PDF-generation artifacts (kerning/
# anchor glyphs, fine-print fragments), not concealed instructions. A hidden
# instruction needs enough characters to actually say something; render mode
# and opacity are unambiguous, deliberate signals with no such artifact class
# and are left ungated. Gate applies to the size condition only.
_MIN_SUSPICIOUS_TEXT_LENGTH = 4  # non-whitespace chars

# Unicode smuggling: codepoints that let readable text pass a human skim
# invisibly while remaining fully readable to a text-extraction pipeline.
_UNICODE_TAG_RANGE = (0xE0000, 0xE007F)          # "tag characters" smuggling
_ZERO_WIDTH_CODEPOINTS = {0x200B, 0x200C, 0x200D, 0xFEFF}
_DEPRECATED_FORMAT_RANGE = (0x206A, 0x206F)

# Bidi *embedding/override* characters only (LRE RLE PDF LRO RLO,
# U+202A-U+202E) — deliberately excludes the newer *isolate* characters
# (LRI RLI FSI PDI, U+2066-U+2069). Verified empirically before choosing this
# split, not assumed from the spec's "Medium confidence" framing alone:
#   - Plain single-language RTL prose (tested: Hebrew, Arabic) contains
#     characters from NEITHER range — ordinary text doesn't need explicit
#     bidi controls at all, the Unicode bidi algorithm handles direction
#     automatically from each character's inherent script.
#   - Legitimate mixed-direction text (an English brand name embedded in an
#     Arabic sentence) written per W3C's *recommended* best practice — wrap
#     the embedded run in FSI...PDI — DOES trip the isolate range. Isolates
#     are the modern, actively-encouraged mechanism for exactly this case.
#   - A Trojan-Source-class attack (CVE-2021-42574) using RLO to visually
#     reorder text trips ONLY the embedding/override range, cleanly.
# So the embedding/override range is high-signal (deprecated by Unicode,
# associated with a disclosed real-world attack, clean on every legitimate
# fixture tested) while the isolate range would false-positive on correctly
# authored bilingual content — excluded for that reason, not overlooked.
_BIDI_EMBED_OVERRIDE_RANGE = (0x202A, 0x202E)

# Zip-bomb guard thresholds (tunable constants, not spec-locked). 100:1 and
# 200MB comfortably clear any real office document while catching the exploit
# shape — a synthetic 200KB-of-zeros entry hits ~950:1 in testing.
_MAX_COMPRESSION_RATIO = 100
_MAX_TOTAL_UNCOMPRESSED_SIZE = 200 * 1024 * 1024  # 200MB


def check_zip_safety(file_path: Path, source_id: str) -> Optional[ExtractionWarning]:
    """Pre-flight guard for zip-based office formats (.docx/.pptx/.xlsx).

    Reads only zip *metadata* (compress_size/file_size per entry, from the
    central directory) — never decompresses — so it's safe to run even
    against an adversarial file. Returns an ExtractionWarning naming the
    rejection reason if the file should be rejected, else None.
    """
    try:
        with zipfile.ZipFile(file_path) as zf:
            total_uncompressed = 0
            for info in zf.infolist():
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > _MAX_COMPRESSION_RATIO:
                    return ExtractionWarning(
                        source_id=source_id,
                        type="parse_error",
                        message=(
                            f"Rejected {file_path.name}: entry '{info.filename}' has a "
                            f"{ratio:.0f}:1 compression ratio, exceeding the safety "
                            f"threshold ({_MAX_COMPRESSION_RATIO}:1) — possible zip bomb."
                        ),
                    )
                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_TOTAL_UNCOMPRESSED_SIZE:
                    return ExtractionWarning(
                        source_id=source_id,
                        type="parse_error",
                        message=(
                            f"Rejected {file_path.name}: total uncompressed size exceeds "
                            f"the safety threshold "
                            f"({_MAX_TOTAL_UNCOMPRESSED_SIZE // (1024 * 1024)}MB) — "
                            f"possible zip bomb."
                        ),
                    )
    except Exception as e:
        return ExtractionWarning(
            source_id=source_id,
            type="parse_error",
            message=f"Rejected {file_path.name}: not a valid zip archive ({e}).",
        )
    return None


def scan_for_hidden_content(
    file_path: Path,
    doc_type: str,
    source_id: str,
    blocks: List[DocumentBlock],
) -> List[ExtractionWarning]:
    """Deterministic scan for content-concealment techniques (hidden-content
    warnings) — a prompt-injection defense, not a content filter. This never
    interprets or acts on concealed text, only reports that concealment exists.

    The entire body runs inside one outer try/except: on any internal failure
    this returns [] rather than a partial result, so a bug or an adversarial
    file degrades to "no trust signal available," never a crashed pack.
    """
    try:
        warnings: List[ExtractionWarning] = []

        if doc_type == "pdf":
            warnings.extend(_scan_pdf_hidden_text(file_path, source_id))
        elif doc_type == "docx":
            warnings.extend(_scan_docx_hidden_text(file_path, source_id))
        elif doc_type == "pptx":
            warnings.extend(_scan_pptx_hidden_text(file_path, source_id))
        elif doc_type == "xlsx":
            warnings.extend(_scan_xlsx_hidden_text(file_path, source_id))

        warnings.extend(_scan_unicode_smuggling(blocks, source_id))

        return warnings
    except Exception:
        return []


def _pdf_hidden_reasons(trace: dict) -> List[str]:
    """Which concealment condition(s) this get_texttrace() run trips, if any.
    A run can trip more than one (e.g. invisible render mode AND sub-2pt) —
    callers must count the run once regardless of how many reasons apply."""
    reasons = []
    if trace.get("type") == _INVISIBLE_RENDER_MODE:
        reasons.append("invisible render mode")
    opacity = trace.get("opacity")
    if opacity is not None and opacity <= _MIN_OPACITY:
        reasons.append("near-zero opacity")
    size = trace.get("size")
    if size is not None and size < _MIN_FONT_SIZE:
        run_text = "".join(chr(c[0]) for c in trace.get("chars", ()))
        if len(run_text.strip()) >= _MIN_SUSPICIOUS_TEXT_LENGTH:
            reasons.append("sub-2pt font size")
    return reasons


def _scan_pdf_hidden_text(file_path: Path, source_id: str) -> List[ExtractionWarning]:
    """One hidden_text warning per page carrying concealed text — invisible
    render mode, near-zero opacity, or sub-2pt font size, all from the same
    get_texttrace() pass (no extra page rendering). Never one warning per
    run: a page with many hidden runs still gets one warning, and a single
    run tripping multiple conditions at once is counted once, not per
    condition — the message's per-reason breakdown is descriptive detail,
    not a second/third warning."""
    warnings: List[ExtractionWarning] = []
    doc = fitz.open(file_path)
    try:
        for page_num in range(doc.page_count):
            page = doc[page_num]
            hidden_run_count = 0
            reason_counts: Dict[str, int] = {}
            for trace in page.get_texttrace():
                reasons = _pdf_hidden_reasons(trace)
                if reasons:
                    hidden_run_count += 1
                    for reason in reasons:
                        reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if hidden_run_count:
                detail = ", ".join(f"{n} {reason}" for reason, n in reason_counts.items())
                warnings.append(ExtractionWarning(
                    source_id=source_id,
                    page=page_num + 1,
                    type="hidden_text",
                    message=(
                        f"Page {page_num + 1} contains {hidden_run_count} text "
                        f"run(s) with concealed content ({detail}) — readable "
                        f"to the parser but not visible to a human reader."
                    ),
                ))
    finally:
        doc.close()
    return warnings


def _docx_is_white_on_white(rpr, ns: dict) -> bool:
    """Explicit run-level w:color val=FFFFFF with no contrasting highlight or
    shading. Direct run-level only — does not resolve style-inherited colors
    against styles.xml (Medium confidence, narrower scope by design; see
    docs/specs/0002-ingestion-trust-layer.md §3)."""
    color = rpr.find("w:color", ns)
    if color is None:
        return False
    w_ns = ns["w"]
    val = (color.get(f"{{{w_ns}}}val") or "").upper()
    if val != "FFFFFF":
        return False
    # A highlight or non-white shading is contrast — a deliberate style choice
    # (e.g. white text on a dark highlight block), not concealment.
    highlight = rpr.find("w:highlight", ns)
    if highlight is not None:
        hval = (highlight.get(f"{{{w_ns}}}val") or "none").lower()
        if hval != "none":
            return False
    shd = rpr.find("w:shd", ns)
    if shd is not None:
        fill = (shd.get(f"{{{w_ns}}}fill") or "auto").lower()
        if fill not in ("auto", "ffffff", "none"):
            return False
    return True


def _docx_run_hidden_reasons(run, ns: dict) -> List[str]:
    """Which concealment condition(s) this w:r run trips, if any. Mirrors
    _pdf_hidden_reasons: a run can trip more than one condition (e.g. vanish
    AND white-on-white) — callers must count the run once regardless."""
    reasons = []
    rpr = run.find("w:rPr", ns)
    if rpr is None:
        return reasons
    if rpr.find("w:vanish", ns) is not None:
        reasons.append("w:vanish hidden run")
    if _docx_is_white_on_white(rpr, ns):
        reasons.append("white-on-white run color")
    return reasons


def _scan_docx_hidden_text(file_path: Path, source_id: str) -> List[ExtractionWarning]:
    """One hidden_text warning for the whole word/document.xml part, naming
    the count of concealed runs found (w:vanish and/or white-on-white color)
    — never one warning per run, and a run tripping both conditions at once
    is counted once, not twice (mirrors _scan_pdf_hidden_text's dedup).

    No local try/except: any failure here (corrupt zip, malformed XML)
    propagates to scan_for_hidden_content's single outer try/except, which
    is the intended "whole result degrades to []" behavior — not caught
    and suppressed locally, which would silently give partial results.

    NOTE: predicate-with-path XPath (e.g. ".//w:r[w:rPr/w:vanish]") raises
    SyntaxError on the stdlib ElementTree subset defusedxml wraps — findall()
    every run, then check conditions per run.
    """
    warnings: List[ExtractionWarning] = []
    with zipfile.ZipFile(file_path) as zf:
        if _DOCX_DOCUMENT_PART not in zf.namelist():
            return warnings
        with zf.open(_DOCX_DOCUMENT_PART) as f:
            root = DET.fromstring(f.read())

    runs = root.findall(".//w:r", _DOCX_WORD_NS)
    hidden_run_count = 0
    reason_counts: Dict[str, int] = {}
    for run in runs:
        reasons = _docx_run_hidden_reasons(run, _DOCX_WORD_NS)
        if reasons:
            hidden_run_count += 1
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    if hidden_run_count:
        detail = ", ".join(f"{n} {reason}" for reason, n in reason_counts.items())
        warnings.append(ExtractionWarning(
            source_id=source_id,
            type="hidden_text",
            message=(
                f"{_DOCX_DOCUMENT_PART} contains {hidden_run_count} run(s) with "
                f"concealed content ({detail}) — readable to the parser but "
                f"not visible in Word."
            ),
        ))
    return warnings


def _pptx_slide_parts(namelist: List[str]) -> List[str]:
    """ppt/slides/slideN.xml parts only (excludes ppt/slides/_rels/*), sorted
    numerically by N — zip entry order isn't guaranteed to match slide order,
    and slide10 must not sort before slide2."""
    numbered = []
    for name in namelist:
        m = _PPTX_SLIDE_RE.match(name)
        if m:
            numbered.append((int(m.group(1)), name))
    numbered.sort(key=lambda pair: pair[0])
    return [name for _, name in numbered]


def _pptx_run_text(run, ns: dict) -> str:
    t = run.find("a:t", ns)
    return (t.text or "") if t is not None else ""


def _pptx_run_hidden_reasons(run, ns: dict) -> List[str]:
    """Which concealment condition(s) this a:r run trips, if any.

    Narrower than the DOCX check by design (Medium confidence, per
    docs/specs/0002-ingestion-trust-layer.md §3): PPTX has no w:vanish
    equivalent, and there's no cheap run-level contrast signal analogous to
    DOCX's w:highlight/w:shd — a shape's background fill lives on the
    enclosing p:sp's p:spPr, not the run, and resolving it is out of scope
    for v1 (mirrors DOCX's exclusion of style-inherited colors: same class
    of "would need to walk outside this run" complexity). So a white
    a:srgbClr run flags unconditionally, with no contrast override. Theme
    colors (a:schemeClr referencing a customizable theme palette, e.g.
    "bg1") are also out of scope — only direct a:srgbClr RGB values are
    checked.
    """
    reasons = []
    rpr = run.find("a:rPr", ns)
    if rpr is None:
        return reasons

    fill = rpr.find("a:solidFill/a:srgbClr", ns)
    if fill is not None:
        val = (fill.get("val") or "").upper()
        if val == "FFFFFF":
            reasons.append("white text fill")

    sz = rpr.get("sz")
    if sz is not None and sz.isdigit() and int(sz) < _PPTX_MIN_FONT_SIZE_HUNDREDTHS:
        if len(_pptx_run_text(run, ns).strip()) >= _MIN_SUSPICIOUS_TEXT_LENGTH:
            reasons.append("sub-2pt font size")

    return reasons


def _scan_pptx_hidden_text(file_path: Path, source_id: str) -> List[ExtractionWarning]:
    """One hidden_text warning per slide carrying concealed text — never one
    per run, and a run tripping both conditions counts once. Mirrors
    _scan_docx_hidden_text's structure; see _pptx_run_hidden_reasons for the
    narrower-than-DOCX scope note.

    No local try/except: propagates to scan_for_hidden_content's single
    outer one — same "whole result -> []" design as the PDF/DOCX branches.
    """
    warnings: List[ExtractionWarning] = []
    with zipfile.ZipFile(file_path) as zf:
        for slide_part in _pptx_slide_parts(zf.namelist()):
            with zf.open(slide_part) as f:
                root = DET.fromstring(f.read())

            hidden_run_count = 0
            reason_counts: Dict[str, int] = {}
            for run in root.findall(".//a:r", _PPTX_NS):
                reasons = _pptx_run_hidden_reasons(run, _PPTX_NS)
                if reasons:
                    hidden_run_count += 1
                    for reason in reasons:
                        reason_counts[reason] = reason_counts.get(reason, 0) + 1

            if hidden_run_count:
                detail = ", ".join(f"{n} {reason}" for reason, n in reason_counts.items())
                warnings.append(ExtractionWarning(
                    source_id=source_id,
                    type="hidden_text",
                    message=(
                        f"{slide_part} contains {hidden_run_count} run(s) with "
                        f"concealed content ({detail}) — readable to the "
                        f"parser but not visible in the presentation."
                    ),
                ))
    return warnings


def _xlsx_run_is_white(run, ns: dict) -> bool:
    """Direct rgb="..FFFFFF" only. SpreadsheetML's <color> can also carry a
    theme+tint or indexed-palette reference instead of rgb — those require
    resolving xl/theme/themeN.xml or the legacy indexed-color table and are
    out of scope, mirroring this module's DOCX/PPTX precedent of excluding
    theme/scheme colors and style resolution."""
    rpr = run.find("s:rPr", ns)
    if rpr is None:
        return False
    color = rpr.find("s:color", ns)
    if color is None:
        return False
    rgb = color.get("rgb")
    if not rgb:
        return False
    # SpreadsheetML uses ARGB (8 hex: alpha + RGB) — verified against a real
    # xlsxwriter-generated file (white came back as "FFFFFFFF"). Also accept
    # a bare 6-hex RGB in case some producer omits the alpha channel.
    return len(rgb) in (6, 8) and rgb.upper().endswith("FFFFFF")


def _xlsx_hidden_run_count(container, ns: dict) -> int:
    """Count of white rich-text runs directly under one <si> (shared-string
    pool entry) or <is> (inline-string cell) container."""
    return sum(1 for run in container.findall("s:r", ns) if _xlsx_run_is_white(run, ns))


def _xlsx_sheet_parts(namelist: List[str]) -> List[str]:
    """xl/worksheets/sheetN.xml parts only, sorted numerically by N — same
    reasoning as _pptx_slide_parts (zip entry order isn't guaranteed, and
    sheet10 must not sort before sheet2)."""
    numbered = []
    for name in namelist:
        m = _XLSX_SHEET_RE.match(name)
        if m:
            numbered.append((int(m.group(1)), name))
    numbered.sort(key=lambda pair: pair[0])
    return [name for _, name in numbered]


def _scan_xlsx_hidden_text(file_path: Path, source_id: str) -> List[ExtractionWarning]:
    """Checks the two distinct storage mechanisms real xlsx files use for
    cell text — verified empirically against two different xlsx-writing
    libraries, not assumed: the traditional shared-string pool
    (xl/sharedStrings.xml) and inline strings written directly in each
    worksheet part (xl/worksheets/sheetN.xml, t="inlineStr" cells). The
    latter is openpyxl's DEFAULT output format — openpyxl never produced
    xl/sharedStrings.xml at all in testing, even for heavily repeated string
    values — so checking only sharedStrings.xml (this task's original,
    narrower scope) would have silently missed a large, realistic class of
    real xlsx files.

    IMPORTANT, empirically-confirmed limitation, more significant than the
    DOCX/PPTX equivalents: this only catches white text applied as a
    *rich-text run* — mixed per-character formatting within one cell
    (<r><rPr><color rgb=".."/></rPr><t>..</t></r>). The far more common way
    to set a cell's font color — selecting the whole cell and picking a
    color in the UI — is stored as a *cell-level style* (the cell's s="N"
    attribute indexing into styles.xml's cellXfs -> fonts), confirmed via
    both openpyxl's Font() API and xlsxwriter's add_format(): neither embeds
    color in the string content itself for whole-cell coloring. Resolving
    that is out of scope here, consistent with this module's DOCX/PPTX
    precedent of not resolving styles/themes — but it means XLSX's real-world
    coverage is narrower than DOCX's equivalent check by a wider margin than
    the "Medium confidence" framing alone would suggest.

    No local try/except — propagates to scan_for_hidden_content's outer one.
    """
    warnings: List[ExtractionWarning] = []
    with zipfile.ZipFile(file_path) as zf:
        namelist = zf.namelist()

        if _XLSX_SHARED_STRINGS_PART in namelist:
            with zf.open(_XLSX_SHARED_STRINGS_PART) as f:
                root = DET.fromstring(f.read())
            hidden_run_count = sum(
                _xlsx_hidden_run_count(si, _XLSX_NS)
                for si in root.findall("s:si", _XLSX_NS)
            )
            if hidden_run_count:
                warnings.append(ExtractionWarning(
                    source_id=source_id,
                    type="hidden_text",
                    message=(
                        f"{_XLSX_SHARED_STRINGS_PART} contains {hidden_run_count} "
                        f"rich-text run(s) with white font color — readable to "
                        f"the parser but not visible in Excel."
                    ),
                ))

        for sheet_part in _xlsx_sheet_parts(namelist):
            with zf.open(sheet_part) as f:
                root = DET.fromstring(f.read())
            hidden_run_count = sum(
                _xlsx_hidden_run_count(is_el, _XLSX_NS)
                for is_el in root.findall(".//s:is", _XLSX_NS)
            )
            if hidden_run_count:
                warnings.append(ExtractionWarning(
                    source_id=source_id,
                    type="hidden_text",
                    message=(
                        f"{sheet_part} contains {hidden_run_count} inline "
                        f"rich-text run(s) with white font color — readable "
                        f"to the parser but not visible in Excel."
                    ),
                ))

    return warnings


def _classify_smuggling_char(codepoint: int) -> Optional[str]:
    """Return a human-readable label if codepoint is a smuggling technique, else None."""
    if _UNICODE_TAG_RANGE[0] <= codepoint <= _UNICODE_TAG_RANGE[1]:
        return "Unicode tag character"
    if codepoint in _ZERO_WIDTH_CODEPOINTS:
        return "zero-width character"
    if _DEPRECATED_FORMAT_RANGE[0] <= codepoint <= _DEPRECATED_FORMAT_RANGE[1]:
        return "deprecated Unicode format character"
    if _BIDI_EMBED_OVERRIDE_RANGE[0] <= codepoint <= _BIDI_EMBED_OVERRIDE_RANGE[1]:
        return "bidi embedding/override character"
    return None


def _scan_unicode_smuggling(
    blocks: List[DocumentBlock],
    source_id: str,
) -> List[ExtractionWarning]:
    """Format-agnostic: runs over already-extracted block text, so it applies
    to every document type. One warning per offending block (never one per
    character), in document order (blocks is already in that order)."""
    warnings: List[ExtractionWarning] = []
    for block in blocks:
        if not block.text:
            continue
        counts: Dict[str, int] = {}
        for ch in block.text:
            label = _classify_smuggling_char(ord(ch))
            if label:
                counts[label] = counts.get(label, 0) + 1
        if counts:
            detail = ", ".join(f"{n} {label}(s)" for label, n in counts.items())
            warnings.append(ExtractionWarning(
                source_id=source_id,
                page=block.page,
                type="unicode_smuggling",
                message=(
                    f"Block {block.block_id} contains {detail} — characters that "
                    f"can hide readable text from a human skim while remaining "
                    f"fully readable to a text-extraction pipeline."
                ),
            ))
    return warnings
