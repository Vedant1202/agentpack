# Spec: Ingestion Trust Layer v1

> Status: **DRAFT — awaiting sign-off** (per project convention: open questions must be resolved before implementation)
> Owner: Vedant
> Created: 2026-08-09
> Source: `agentpack-directions-1-2-implementation.md`, Direction 1 (sub-parts 1a + 1c only — see Descoped)
> Relates to: `SPEC.md` (Knowledge Map — unaffected, no overlap), `docs/specs/0001-parsing-and-retrieval-overhaul.md` §G-G3 (secret/PII redaction — this spec does not absorb it; see Open Question 3)

## 1. Objective

AgentPack's own manifest tells the consuming agent to trust the corpus: every pack ships with
`agent.instructions: ["Use citations when answering.", "Prefer raw chunks over summaries.", ...]`
([`pack.py:216-220`](../../src/agentpack/pack.py)). That trust is currently unconditional — nothing
in the pipeline distinguishes a paragraph a human wrote from a paragraph a human can't see. Content
concealment techniques (white-on-white text, PDF invisible render mode, Office `w:vanish` runs,
Unicode "tag character" smuggling) let an attacker plant instructions in a source document that are
invisible on a human skim but fully readable to the extraction pipeline and, downstream, to the
agent. This is not hypothetical: it's the exact technique class an existing open-source scanner
(`wppoland/hidden-text-detector`) is built around, and the March 2026 "Reverse CAPTCHA" paper
measures how reliably LLMs act on instructions hidden this way.

AgentPack today has zero visibility into this. Docling's structured-tree output — what
`_parse_semantic` in [`pdf_parser.py`](../../src/agentpack/parsers/pdf_parser.py) and all of
[`docling_parser.py`](../../src/agentpack/parsers/docling_parser.py) consume — discards render-level
detail (color, opacity, OCG visibility) before it ever reaches a `DocumentBlock`. Concealed content
and normal content are indistinguishable by the time a pack exists.

This spec adds a deterministic, dependency-light scanning pass that surfaces concealment techniques
as `ExtractionWarning`s — the same mechanism already used for `parse_error` / `import_error` /
`low_text_density` — so a human reviewing `agentpack audit` output sees them. It also bundles two
small, unrelated hardening items (§1c of the source doc) because both touch the same ingestion
boundary: a `pymupdf` floor bump closing a disclosed CVE, and a zip-bomb guard for the
office-document formats that are all zip+XML under the hood.

**Explicitly not in this spec:** the ML/semantic prompt-injection classifier (source doc's 1b) and
secret/PII detection (1d). See Descoped (§9) for why.

### Who is the user
Same as `docs/specs/0001-parsing-and-retrieval-overhaul.md`: engineers/AI builders packing a corpus
for agent retrieval. This spec is most load-bearing for teams packing third-party or
user-submitted documents (contracts, resumes, RFPs, scraped web content) where a planted hidden
instruction is a real adversarial input, not just noisy data.

### Success criteria (testable)
- A fixture PDF with PyMuPDF-inserted invisible text (`render_mode=3`) produces a `hidden_text`
  warning naming the correct page.
- A fixture `.docx` with a `<w:vanish/>` run produces a `hidden_text` warning.
- A fixture chunk containing Unicode tag characters (U+E0000–U+E007F) produces a `unicode_smuggling`
  warning.
- Re-packing `demo_corpus/` (no planted concealment) produces **zero** new warnings — no
  false-positive flood on ordinary documents.
- A synthetic zip-bomb `.docx` fails the pack gracefully (an `ExtractionWarning`, `status: failed`
  in the manifest) in bounded time — never a hang, never an unhandled exception.
- Re-packing an **unchanged** corpus (L1 cache hit path) still emits trust warnings identically to a
  cold pack — this is the regression guard for the caching design in §2.
- Zero new core dependencies. `defusedxml` (already present transitively via `docling-core`) becomes
  a direct declared dependency; no other package is added.
- Full existing test suite passes unchanged.

---

## 2. Resolved decisions

| Decision | Choice | Rationale |
|---|---|---|
| Where the scan hooks in | Call `scan_for_hidden_content()` from `_parse_one` in `pack.py`, **after** the `cache_get`/`cache_set` block — not inside it | The L1 parse cache pickles the whole `SourceDocument` ([`pack.py:47-53`](../../src/agentpack/pack.py)). If trust warnings were appended before caching, a cache hit on `--scan-hidden` toggled off (or a prior version of this code) would silently miss them, and there's no scan-related component in the cache key today. Running the scan *after* the cache block sidesteps needing a cache-key version bump entirely: it always re-runs, cache hit or miss, cheaply (see cost budget below). This also means trust warnings always carry the *current* `source_id`, which sidesteps `pack.py:55`'s existing behavior of reassigning `doc.source_id` on a cache hit without updating the `source_id` field embedded in the doc's warnings — a latent bug this design doesn't need to fix but must not inherit. |
| Zip-bomb guard placement | A pre-flight check in `trust.py`, called from `_parse_one` **before** `parser.parse()` for `.docx`/`.pptx`/`.xlsx`, gating both Docling's own conversion and the trust scanner's zip read | Docling opens office files as zip+XML internally; an unbounded read there is the actual DoS surface, not just the trust scanner's own zip access. One guard, one place, protects both call sites. |
| New dependency footprint | Zero new core deps. PDF checks via `fitz.get_texttrace()` (module already imported, [`pdf_parser.py:2`](../../src/agentpack/parsers/pdf_parser.py)); office checks via stdlib `zipfile` + `defusedxml` (confirmed already installed transitively via `docling-core`) | Matches this codebase's existing dependency conservatism (0001's Boundaries: "ask first before adding heavyweight deps"). `python-docx`/`python-pptx` are deliberately **not** added — raw XML part reads via `zipfile` cover the needed tags without a new dependency surface. `defusedxml` moves from implicit-transitive to an explicit `pyproject.toml` entry, since relying on an unpinned transitive dependency for a security-relevant XML parser is itself a small risk. |
| Failure mode | `scan_for_hidden_content()` never raises — blanket `try/except` returning `[]` on any internal failure | Mirrors the existing "cache writes must never crash the main pipeline" comment in [`cache.py:66`](../../src/agentpack/cache.py). A malformed or adversarially-crafted file degrades to "no trust signal available," never an aborted pack. |
| Zip-bomb rejection warning type | Reuse `type="parse_error"` (not a new `"zip_bomb"` type), with a message naming the rejection reason | `pack.py:174-176`'s failure/status logic already keys off `w.type == "parse_error"` to mark a source `"failed"` and surface the reason. Reusing the existing type means **zero changes** to that logic — the file already ends up with 0 blocks / 0 chunks either way, which alone would mark it failed. A new type would need that matcher extended for no behavioral gain. |
| PDF OCG `/OFF` layers | Descoped from v1 (§9) | PyMuPDF does not cleanly expose text-to-OCG association; needs dedicated investigation before it's a same-scope item. |
| Pixel-contrast detection | Descoped from v1 (§9) | Requires rendering every page — not free like a `get_texttrace()` pass. If ever added, it must move *inside* the L1 cache with a cache-key version bump, unlike everything else in this spec. Flagged explicitly so it is never casually added as a "small extension" of this scanner later. |
| 1b (ML prompt-injection classifier) | Rejected outright, not merely descoped (§9) | `protectai/llm-guard` and its underlying model repo are both archived/unmaintained; an independent evaluation (arXiv 2504.11168) measured the model at 67.87% attack success under adversarial ML evasion; the model card itself documents false positives on system-prompt/policy-like text, which describes a large share of real document corpora. |

---

## 3. Detection techniques (v1 scope)

| Format | Technique | Check | Warning type | Confidence |
|---|---|---|---|---|
| PDF | Invisible render mode (`3 Tr`) | `page.get_texttrace()` — filter entries with text render mode `3` | `hidden_text` | High |
| PDF | Near-zero fill/stroke opacity | `page.get_texttrace()` opacity fields ≈ 0 | `hidden_text` | High |
| PDF | Sub-legible font size (< 2pt) | `page.get_texttrace()` font size | `hidden_text` | High |
| DOCX | `w:vanish` hidden run | `zipfile` read of `word/document.xml`, `defusedxml`-parsed, search `w:rPr/w:vanish` | `hidden_text` | High |
| DOCX | Explicit white-on-white run color | Same parse, `w:rPr/w:color[@w:val='FFFFFF']` with no contrasting highlight | `hidden_text` | Medium |
| PPTX | Explicit white/background-matched text fill or zero font size | `zipfile` read of `ppt/slides/slideN.xml` | `hidden_text` | **Medium** — PPTX has no direct `w:vanish` equivalent; v1 covers only explicit color-match and zero-size heuristics, narrower than DOCX coverage |
| XLSX | White font color in `sharedStrings.xml` / `sheetN.xml` cell styles | `zipfile` read of relevant parts | `hidden_text` | **Medium** — same narrower-than-DOCX caveat |
| Any extracted block text | Unicode tag characters (U+E0000–U+E007F) | Codepoint range scan over `DocumentBlock.text` | `unicode_smuggling` | High |
| Any extracted block text | Zero-width characters (U+200B–200D, U+FEFF) | Codepoint scan | `unicode_smuggling` | High |
| Any extracted block text | Deprecated Unicode format characters (U+206A–U+206F) | Codepoint scan | `unicode_smuggling` | High |
| Any extracted block text | Bidirectional control characters (U+202A–U+202E, U+2066–U+2069) | Codepoint scan | `unicode_smuggling` | Medium — legitimate RTL-language documents use some of these; needs the false-positive check against a real multilingual fixture before shipping default-on (see §8) |

The Unicode-smuggling scan runs over `DocumentBlock.text` post-extraction (format-agnostic, one
implementation for every source type). The render/structural checks are format-specific and run
against the original file bytes, since that detail is exactly what parsing already discards.

---

## 4. Commands (CLI surface)

| Command | Change |
|---|---|
| `agentpack pack <dir> --out <out>` | Scan runs automatically as part of parsing (see Open Question 1 on default-on vs. flag). No new required flag. |
| `agentpack audit <pack_dir>` | Warning section groups by `type` with per-type counts; `parse_error`/`import_error` remain listed first (see Open Question 2). |
| `agentpack validate <pack_dir>` | Unchanged — trust warnings use the existing `ExtractionWarning` schema, no new validation needed. |
| all others (`retrieve`, `map`, `index`, `ui`, `eval`) | Unchanged. |

---

## 5. Project structure

```
src/agentpack/
  trust.py            # NEW — scan_for_hidden_content(file_path, doc_type, source_id) -> List[ExtractionWarning]
                       #       check_zip_safety(file_path) -> Optional[ExtractionWarning]
                       #       Imports only agentpack.models; no dependency on pack.py/parsers/*.
  pack.py              # _parse_one(): call check_zip_safety() pre-parse for .docx/.pptx/.xlsx;
                       #   call scan_for_hidden_content() after the cache_get/cache_set block
  models.py            # unchanged — reuses ExtractionWarning as-is, zero schema change
  audit.py             # group the warnings section by type with per-type counts
pyproject.toml         # pymupdf floor >=1.23.0 -> >=1.26.7; defusedxml declared as a direct dep
tests/
  test_trust.py        # NEW — one test per technique in §3 (synthetic fixtures built in-test,
                       #   nothing committed as a binary); zip-bomb rejection test; never-raises
                       #   fuzz test on truncated/corrupt input; no-false-positive test on demo_corpus
  test_pack.py         # +1 regression test: cache hit still emits trust warnings, with correct
                       #   source_id, identical to a cold pack
```

---

## 6. Code style

Match the existing codebase (same conventions as `docs/specs/0001-...`):
- `ExtractionWarning` pydantic objects, not dicts, returned from `scan_for_hidden_content`.
- Blanket `try/except` at the function boundary — this module must never propagate an exception
  into `_parse_one`.
- No `print` from library code, ever (this module has no `verbose`/`quiet` context to check —
  findings surface only as warnings, never console output).
- Deterministic ordering: iterate pages/XML entries in file order; never let dict/set iteration
  order leak into warning ordering.
- `block_id`/`page` references in warning messages should point at something a human can act on
  (page number, XML part name) — mirror the existing message style in `pdf_parser.py`
  (`f"Page {page_num + 1} has little or no text."`).

Sketch of the integration point in `pack.py`:

```python
def _parse_one(file_path, source_id, fast_pdf, remove_empty_lines, cache_dir):
    parser = get_parser(file_path.suffix, fast_pdf=fast_pdf)
    if parser is None:
        return None

    if file_path.suffix.lower() in {".docx", ".pptx", ".xlsx"}:
        zip_warning = check_zip_safety(file_path, source_id)
        if zip_warning is not None:
            return SourceDocument(
                source_id=source_id, path=file_path.name,
                type=file_path.suffix.lstrip(".").lower(),
                checksum=_sha256(file_path), blocks=[], warnings=[zip_warning],
            )

    # ... existing cache_get / parser.parse / cache_set block, unchanged ...

    doc.warnings.extend(scan_for_hidden_content(file_path, doc.type, source_id))
    return doc
```

---

## 7. Testing strategy

- **Unit, per technique:** each row in §3 gets a synthetic fixture built at test time, not a
  committed binary — e.g. `fitz` PDFs constructed via `page.insert_text(point, text, render_mode=3)`
  (the real API OCR pipelines use to write invisible text layers); minimal `.docx`/`.pptx`/`.xlsx`
  built as an in-memory `zipfile.ZipFile` with a hand-written XML part containing the target tag.
- **Zip-bomb test:** construct a highly-compressible zip at test time (never commit an actual
  exploit-shaped binary to the repo); assert `pack()` marks the source `"failed"` with a
  `parse_error` warning naming the rejection, and assert wall-clock stays bounded.
- **Never-raises test:** feed `scan_for_hidden_content` a truncated/corrupted `.docx` and a
  corrupted PDF; assert it returns `[]`, not an exception.
- **False-positive guard:** re-pack `demo_corpus/` (and any other existing fixture corpus with no
  planted concealment) and assert zero new `hidden_text`/`unicode_smuggling` warnings appear.
  Include at least one fixture with legitimate RTL (Arabic/Hebrew) text to validate the
  bidi-control-character check doesn't fire on ordinary multilingual content (flagged as Medium
  confidence in §3 for exactly this reason).
- **Cache-interaction regression test:** pack the same corpus twice. Assert the second (cache-hit)
  run's manifest carries the same trust warnings as the first, each with `source_id` matching its
  actual source — this is the direct regression guard for the caching design decision in §2.
- **Determinism:** two packs of the same corpus produce identical trust warnings (order and
  content), matching the existing determinism guarantee for `map.yml` in `SPEC.md`.

---

## 8. Boundaries

**Always**
- `scan_for_hidden_content` never raises; on any internal failure it returns `[]`.
- Stay additive: no existing `ExtractionWarning` field, manifest key, or warning type is removed or
  renamed.
- Trust warnings are computed fresh every pack (never pickled into the L1 cache) — see §2.
- Zero new core dependencies beyond declaring `defusedxml` directly.

**Ask first**
- Adding `python-docx`/`python-pptx` (or any dependency beyond stdlib `zipfile` + `defusedxml`) for
  office-format parsing convenience — that would be a real new footprint, unlike `defusedxml`.
- Changing the scan from default-on to opt-in (or vice versa) after ship, once real false-positive
  data exists — that's a behavior change, not a bug fix.
- Any change that causes a trust finding to modify, redact, or drop chunk content — this spec is
  **flag-only**.

**Never**
- Block or fail a pack solely because hidden content was found. This is a signal for the human
  running `agentpack audit`, never an enforcement gate.
- Extract, interpret, or act on any instruction found inside concealed content. The scanner's job
  is to report that concealment *exists* — nothing in this pipeline should read a hidden
  instruction's semantic content and behave differently because of it.
- Render PDF pages to images as part of this scan (that's the descoped pixel-contrast tier,
  deliberately excluded from v1's performance envelope — see §2).
- Change `pack.py`'s existing `has_parse_error` / status-determination logic — the zip-bomb guard is
  designed to require zero changes there (§2).

---

## 9. Descoped / out of scope

- **PDF OCG `/OFF` layer detection** — needs dedicated investigation into PyMuPDF's OCG API before
  it's addable at this confidence level.
- **Pixel-rendering contrast detection** (the `wppoland/hidden-text-detector` technique of
  rendering pages and measuring text-region contrast) — the most robust single technique for
  catching white-on-white and colored-panel matches, but not free like `get_texttrace()`; requires
  moving inside the L1 cache with a key-version bump. Real future work, not this spec.
- **1b — ML/semantic prompt-injection classifier** — rejected for the reasons in §2, not merely
  deferred. Revisit only if a current, maintained, independently-well-evaluated alternative to
  `protectai/llm-guard` emerges (e.g. a non-archived successor to Meta Prompt Guard).
- **1d — secret/PII detection wiring** (`detect-secrets` is a declared but never-imported dependency
  today) — already tracked as `G-G3` in `docs/specs/0001-parsing-and-retrieval-overhaul.md` Phase 4,
  with its own open question there ("redact or only flag?"). Not absorbed into this spec — see Open
  Question 3 for whether that should change.

---

## 10. Open Questions

1. **Default-on or opt-in flag?** Proposed: **default-on**, no new flag. This is a warning-only
   signal — nothing is blocked, redacted, or altered — which matches the "safe/complete behavior is
   the default" pattern this codebase already uses for `map.yml` generation (`--no-map` is an
   *opt-out*, not opt-in). Contrast with `--fast`/`--enrich-llm`-style flags, which gate genuinely
   expensive or behavior-changing paths; this scan is neither. Open because it changes what shows up
   in every `manifest.yml`/`audit` output by default, including for users who have never heard of
   this feature.
2. **Does `agentpack audit` need warning grouping?** Proposed: group the existing flat warning list
   by `type` with per-type counts, `parse_error`/`import_error` listed first/most prominent. A
   corpus with many `hidden_text` findings (e.g. a batch of OCR'd PDFs with legitimate invisible
   text layers) would otherwise drown genuine parse failures in one undifferentiated list. Simpler
   than building a full severity-ranking system, which is overkill for v1.
3. **Bundle 1d (secret detection) into this spec, or leave it as `G-G3` fast-follow work under
   0001?** Proposed: **leave it separate.** It shares the `ExtractionWarning` mechanism but its
   optional `--redact-secrets` path mutates emitted chunk text, which nothing in this spec does —
   different risk profile, different review. `G-G3` in 0001 already tracks it with its own open
   redact-vs-flag question; duplicating that tracking here would fork the decision in two places.
4. **Bidi-control-character false positives (§3, last row):** is the Medium-confidence check
   ship-blocking pending the RTL fixture test in §7, or should it start out logged-but-not-surfaced
   (collected in warnings but excluded from `audit`'s summary count) until real corpus data confirms
   the false-positive rate? Proposed: ship it, gated by the RTL fixture test passing — no separate
   suppression mechanism, keep the warning model uniform.

---

## 11. Success criteria (rollup)

- [ ] `hidden_text` warnings fire correctly for PDF render-mode-3, DOCX `w:vanish`, and the
      Medium-confidence PPTX/XLSX color-match checks (§3).
- [ ] `unicode_smuggling` warnings fire correctly for tag characters, zero-width characters, and
      deprecated format characters; bidi-control-character check passes the RTL false-positive
      fixture (§7, Open Question 4).
- [ ] Zero new warnings on `demo_corpus/` and other existing fixtures (no false-positive flood).
- [ ] Zip-bomb `.docx` fails gracefully, bounded time, `parse_error` warning, zero changes to
      `pack.py`'s existing status logic (§2).
- [ ] Cache-hit regression test passes: trust warnings identical across cold and warm packs, correct
      `source_id` every time (§7).
- [ ] `pymupdf` floor bumped to `>=1.26.7`; `defusedxml` declared as a direct dependency.
- [ ] Zero new core dependencies beyond `defusedxml`.
- [ ] Full existing test suite passes unchanged.
- [ ] Open Questions 1–4 resolved and recorded here before implementation begins.
