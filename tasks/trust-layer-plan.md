# Plan — Ingestion Trust Layer v1

> Implements [docs/specs/0002-ingestion-trust-layer.md](../docs/specs/0002-ingestion-trust-layer.md). Vertical slicing: ship high-confidence detection end-to-end first, then deepen technique-by-technique — never build all of `trust.py` in isolation before wiring any of it in. Mirrors the slicing philosophy of [plan.md](plan.md) (Hierarchical Knowledge Map).

## Dependency graph

```
pyproject.toml ─────────────────────────────────────────────── (independent, no code edges)
  (pymupdf floor, defusedxml direct dep)

           (leaf — imports only agentpack.models + stdlib zipfile/fitz + defusedxml)
  trust.py ────────────────────────────►  pack.py  (hub: _parse_one())
  check_zip_safety()                        │  check_zip_safety() pre-parse, .docx/.pptx/.xlsx only
  scan_for_hidden_content()                 │  scan_for_hidden_content() AFTER cache_get/cache_set block
                                             │  (never before/inside — no cache-key change needed)
                                             ├──►  tests/test_pack.py  (+1 cache-hit regression test)
                                             │
  tests/test_trust.py  ◄────────────────────┘  (one test per technique, zip-bomb, never-raises,
                                                  false-positive guard)

  ⋯ gated on spec §10 Q2 ⋯──►  audit.py  (group warnings by type+count) — reads only the existing
                                            ExtractionWarning.type field, no dependency on trust.py
  ⋯ gated on spec §10 Q1 ⋯──►  cli.py    (opt-in/out flag) — only if human diverges from default-on
```

**Ordering implications**
- `trust.py` is a **pure leaf**: it imports only `agentpack.models` plus stdlib (`zipfile`, `re`) and `fitz`/`defusedxml` (both already present, one now a direct dep). It never imports `pack.py` or anything under `parsers/`.
- `pack.py`'s `_parse_one()` is the **integration hub** — the only place that calls into `trust.py`, at two distinct points: `check_zip_safety()` *before* the existing cache block (for zip-based formats only), and `scan_for_hidden_content()` *after* it (unconditionally, for every format).
- `audit.py` and `cli.py` are optional branches off the stable `ExtractionWarning` schema, not off `trust.py` itself — they can be built independently, any time, contingent only on the two open questions being answered. They do not gate anything upstream.
- `models.py` is untouched. Zero schema change.

## Verified technical grounding (checked against the actual installed libraries, not assumed)

- `page.get_texttrace()` on the installed `pymupdf` (1.27.2.3) returns a list of per-run dicts with `type` (render mode — live-tested: `page.insert_text(pt, text, render_mode=3)` round-trips to `type: 3`; normal text is `type: 0`), plus `opacity`, `size`, `color`, `bbox`, `layer`, `seqno`, `chars`. This is the complete PDF detection surface — no page rendering required for any v1 check.
- `defusedxml.ElementTree.fromstring()` mirrors stdlib `ElementTree.fromstring`, already installed transitively via `docling-core`. **Gotcha found during verification:** predicate-with-path XPath (`.//w:r[w:rPr/w:vanish]`) raises `SyntaxError: invalid predicate` — the stdlib subset defusedxml wraps doesn't support it. Working pattern instead, live-verified: `root.findall('.//w:r', ns)` then per-run `run.find('w:rPr/w:vanish', ns) is not None`.
- `zipfile.ZipFile(path).infolist()` exposes `.compress_size`/`.file_size` per entry **without decompressing** — exactly the zip-bomb ratio guard needs (`file_size / compress_size`, plus a cumulative cap). `defusedxml` does not provide this; it guards entity expansion, a different attack class.
- The spec's illustrative sketch shows `scan_for_hidden_content(file_path, doc_type, source_id)`. The real signature needs a fourth parameter, `blocks: List[DocumentBlock]`, since the Unicode-smuggling check runs over already-extracted `DocumentBlock.text` and warning messages must name a `block_id`/page a human can act on.

## Phase 0 — Hygiene + zip-bomb guard (independent, land first)

| # | Task | Touches |
|---|------|---------|
| T0.1 | `pymupdf` floor `>=1.23.0` → `>=1.26.7`; declare `defusedxml` as a direct dependency | `pyproject.toml` |
| T0.2 | `check_zip_safety(file_path, source_id)` — zip metadata-only ratio + cumulative-size guard; wired as an early-return branch in `_parse_one()` for `.docx`/`.pptx`/`.xlsx`, reusing `type="parse_error"` so `pack.py:174-176`'s status logic needs no changes | `trust.py` (new), `pack.py` |

## Phase 1 — Walking skeleton: high-confidence techniques, wired end-to-end

| # | Task | Touches |
|---|------|---------|
| T1.1 | `scan_for_hidden_content()` skeleton + PDF render-mode-3 branch; wired into `_parse_one()` after the cache block; whole-function try/except → `[]` | `trust.py`, `pack.py` |
| T1.2 | Unicode-smuggling sub-check: tag chars, zero-width, deprecated-format ranges, over `blocks` in document order | `trust.py` |
| T1.3 | DOCX `w:vanish` detection via `zipfile` + `defusedxml` | `trust.py` |
| T1.4 | Deepen PDF branch: near-zero opacity + sub-2pt font size, deduped per run | `trust.py` |
| T1.5 | False-positive guard (`demo_corpus/` + in-test-built benign office fixtures) + cache-hit regression test | `tests/test_trust.py`, `tests/test_pack.py` |

**Gate:** `pytest tests/ -q` fully green.

**▣ CHECKPOINT** — run `agentpack pack` + `agentpack audit` on a real corpus (`benchmarks/financebench_sample`); confirm zero false positives at this tier. Sanity-check T0.2's thresholds against a real office file if one becomes available. Go/no-go on Phase 2.

## Phase 2 — Medium-confidence techniques (gated by checkpoint)

| # | Task | Touches |
|---|------|---------|
| T2.1 | DOCX explicit white-on-white color (`w:color[@w:val='FFFFFF']`, no contrasting highlight) — direct run-level only | `trust.py` |
| T2.2 | PPTX white-fill/zero-size heuristic over `ppt/slides/slide*.xml` — narrower than DOCX (no `w:vanish` equivalent exists in PPTX) | `trust.py` |
| T2.3 | XLSX white-font heuristic over `sharedStrings.xml` — same narrower-scope caveat | `trust.py` |
| T2.4 | Bidi control chars, gated on a real RTL (Arabic/Hebrew) fixture test passing (spec Open Question 4's resolved answer) | `trust.py`, `tests/test_trust.py` |

**Gate:** `pytest tests/ -q`; re-run T1.5's false-positive guard to confirm Phase 2 didn't introduce a flood.

## Phase 3 — Open-question-dependent, independently droppable

| # | Task | Touches | Contingent on |
|---|------|---------|---|
| T3.1 | CLI flag for scan on/off — **skip entirely if default-on is confirmed** | `cli.py`, `pack.py` | spec §10 Q1 |
| T3.2 | `audit.py` grouping by warning type + counts | `audit.py`, `tests/test_audit.py` (new) | spec §10 Q2 |

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| PPTX/XLSX Medium-confidence checks fire on legitimate decorative white text | Checkpoint before Phase 2; each gets its own synthetic fixture, scoped narrower than DOCX by design |
| Bidi chars false-positive on real RTL documents | T2.4 explicitly gated on an RTL fixture test — not "ship now, tune later" |
| Single try/except in `scan_for_hidden_content` could swallow a real bug, not just malicious input | Accepted per spec §2/§8's resolved decision — a code-review concern, not something to relax here |
| Zip-bomb thresholds picked with no real-world office-file baseline in-repo | Sanity-check at the Phase-1 checkpoint if a real file becomes available; thresholds are tunable constants, not a spec-locked decision |
