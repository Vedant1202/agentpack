# Spec 0004: Engineering Hardening — fixes for the 2026-08 audit

> Status: **APPROVED — ready for implementation** (all §9 open questions resolved 2026-08-12; recommendations accepted verbatim)
> Owner: Vedant
> Created: 2026-08-12
> Source: engineering audit of 2026-08-12 (three parallel subsystem audits + release/packaging pass; full record in `.plans/engineering-audit-2026-08.md` — background only, THIS SPEC IS SELF-CONTAINED)
> Baseline commit: `489dbe4` on `dev` (v0.5.0). Line numbers cited below are as of this commit.

---

## 0. READ THIS FIRST (handoff rules for the implementing agent)

This spec is written for an implementer with **no prior context**. Everything needed is inlined.

**Hard process rules (non-negotiable):**

1. **Test invocation, this exact form, always:**
   ```bash
   PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q
   ```
   Bare `python -m pytest` hits the wrong environment (anaconda base) and fails spuriously.
2. **Green baseline:** `296 passed, 1 failed` today. The 1 failure is `tests/test_eval.py::test_run_eval` — **T0.1 below fixes it**. After T0.1 the baseline is **fully green** and stays fully green after every task. Any new failure = you broke something; stop and fix before proceeding.
3. **TDD every task:** write the failing test first, run it, confirm it fails FOR THE RIGHT REASON (read the failure output), then implement, then confirm green, then run the FULL suite.
4. **Line numbers drift.** Before editing any cited location, `grep` for the quoted code to find its current line. If the code at a cited location does not match what this spec describes, **STOP and report the mismatch** — do not improvise a fix for code that has changed.
5. **Branch `fix/engineering-hardening` off `dev`. PR into `dev`, never `main`.** Commit per task or per coherent pair (conventional commits: `fix(chunker): …`, `test(eval): …`).
6. **One task at a time, in order.** Each phase ends with a checkpoint. **Stop at each ▣ CHECKPOINT and wait for human review before the next phase.**
7. Keep a running todo file `tasks/hardening-todo.md` (same style as `tasks/concept-graph-todo.md`: check off with evidence — test counts, commands run, findings).
8. **Verify library behavior live before relying on it.** Where a task says "verify:", run the snippet in `./venv/bin/python` first and record the output in the todo.

**Do-not-touch list (out of scope for every task):**
- `src/agentpack/grapher.py`, `src/agentpack/trust.py`, `src/agentpack/enrich.py` internals (except the single call-site cap in T0.4), `src/agentpack/mapper.py` tree-building logic (only the enrichment call sites in T0.4), parser *extraction logic* (only error boundaries/encoding wrappers change), `manifest.yml`/`map.yml`/`graph.yml` schemas (no new/renamed fields anywhere), retrieval *ranking* behavior (RRF, FTS query construction — verified correct, leave alone), `.github/workflows/publish.yml` and `agentpack.spec` (release plumbing is descoped, §8).

**Success criteria for the whole spec:** every listed task's new test fails before its fix and passes after; full suite fully green after every task; no schema changes; no retrieval-ranking changes (proven by T-B0's snapshot test).

---

## 1. Objective

Fix the verified engineering bugs from the 2026-08 audit — wrong citations, run-killing error paths, stale-cache/stale-index serving, eval-integrity holes, and CLI hygiene — **without adding features and without changing any output schema or retrieval ranking**. Users: everyone running `agentpack pack/retrieve/eval` today; the benchmark numbers in the README depend on Phase C.

---

## 2. Verified facts (do not re-derive; each was reproduced during the audit)

| # | Fact | Where |
|---|------|-------|
| F1 | A chunk flushed at a block boundary is stamped with the NEXT block's page/section (chunk of pure page-1 text cited `page=2`) | `chunker.py` (metadata updated before flush decision) |
| F2 | A dangling symlink in the corpus aborts the entire pack with `FileNotFoundError`; nothing is written | `pack.py` (`future.result()` unguarded; `open()`s outside parser try blocks) |
| F3 | L1 cache hit remaps only `doc.source_id`; `doc.path` and block ids stay stale → citations name the old file; table files collide across sources | `pack.py:72-73` |
| F4 | Corrupt/truncated `lexical_index.db` raises `sqlite3.DatabaseError`, which the `except sqlite3.OperationalError` does NOT catch (it's the parent class) → permanent crash loop, self-heal never runs | `retrieve.py:76-81` |
| F5 | Section-level enrichment text is uncapped; `gist()` builds a dense O(N²) sentence graph; a `--fast` PDF = one root section = whole document → OOM on large filings (observed: 42-doc corpus, 8GB machine). Doc/corpus level already cap at `_ENRICH_TEXT_CAP = 8000` | `mapper.py:22,116,122-123,176,194`; `enrich.py:84-90` |
| F6 | `gen-eval` prints its error branch in red and exits **0** (`eval` correctly raises `typer.Exit(1)` at `cli.py:304-306`) | `cli.py:342-344` |
| F7 | `build_vector_index` early-returns on a zero-chunk manifest without writing the new hash or clearing old `vector_index.npy`/`vector_meta.json` → stale vectors served forever ("ghost results"); `tests/test_retrieve.py:125-159` (`test_search_hybrid`) **passes because of this bug** (mismatched hash + empty-chunk manifest → stale artifacts served) | `retrieve.py:141-142,175-176,309-322` |
| F8 | `_manifest_hash` fingerprints only sorted chunk ids + source checksums; chunk ids are positional (`{source_id}_chunk_{i:03d}`) → re-chunking that redistributes text across the SAME number of chunks keeps the hash identical → stale FTS/vector indexes AND stale L5 cached answers | `retrieve.py:62-73`; `chunker.py:30` |
| F9 | `cache_get`/`cache_set` swallow ALL exceptions; corrupt `cache.db` silently disables L1/L3/L5 forever and leaks the connection | `cache.py:39-51,54-66` |
| F10 | `hnsw_index.bin` is outside the staleness check and never deleted when hnswlib is absent at rebuild → a later hnswlib-capable env loads stale labels against new metadata | `retrieve.py:210-217,310-315,335-344` |
| F11 | L1 cache key = (file_hash, parser_version, fast_flag); `remove_empty_lines` missing → toggling the flag no-ops on cached corpora | `pack.py:65` |
| F12 | `TextEmbedding()` is instantiated with NO model argument while L3 keys hardcode `BAAI/bge-small-en-v1.5` (fastembed unpinned `>=0.2.7`) | `retrieve.py:21,58` |
| F13 | `scanner.py` uses `os.walk` with no `sorted()` → source_ids/chunk ids/manifest order are filesystem/platform-dependent | `scanner.py:64` |
| F14 | Oversized-block splitting: first sub-chunk is appended onto the retained overlap but `current_tokens = len(sub_tokens)` OVERWRITES the count → content 901 tokens, recorded `token_count=800`. Existing test passes only because it tests a LONE oversized block | `chunker.py:89-90` |
| F15 | Output dir inside input dir is scanned on re-run → the pack ingests its own chunks/report and grows every run (`write_pack('corpus','corpus/pack')` twice reproduced it) | `pack.py:132-137` |
| F16 | Non-UTF8 text/markdown files decode with `errors="replace"` → NUL-riddled mojibake chunks, status success, zero warnings. UTF-8 BOM (`utf-8` not `utf-8-sig`) turns `# Title` into a paragraph — structure silently lost | `text_parser.py:8`; `markdown_parser.py:82` |
| F17 | Judge failures in gen-eval record scores of 0 and increment `count` → averaged into headline numbers; generation failures produce answer text `"Error generating answer: …"` which is then judged as a real answer | `generation.py:112,128-130,143-147` |
| F18 | Dense-baseline disk cache is keyed `{strategy}_v{_CACHE_VERSION}` only — no corpus fingerprint → corpus edits silently reuse stale baseline embeddings while AgentPack's own modes rebuild | `baselines.py:287-302` |
| F19 | `_llm_generate` returns `""` on ANY failure → "HyDE"/"Contextual Retrieval" rows silently become plain vector search, still labeled as LLM baselines | `baselines.py:485-493,510,534` |
| F20 | `run_eval` has no per-query/per-mode error isolation and writes the report only at the end; same for `generation_results.json` → one flaky query loses an entire (paid) run | `runner.py:89,139`; `generation.py:163` |
| F21 | `_get_naive_conn` never sets `_last_corpus_dir` → with `--skip-raw-file` the naive FTS index is rebuilt from scratch on EVERY query; conversely can serve corpus A's index for corpus B | `baselines.py:75-102` |
| F22 | `test_run_eval` fails because commit `6a1e682` added a reranker baseline doing a **function-local** `from agentpack.retrieve import search_pack` (`baselines.py:445-447`) that the test's mock on `agentpack.eval.runner.search_pack` cannot intercept. Validated fix: additionally patch `agentpack.eval.runner._baselines.get_baselines` to return `[]` → passes in 1.9s | `tests/test_eval.py:65-67` |
| F23 | `/api/feedback`: bare `except: pass` turns a corrupt `eval_feedback.json` into `[]` and the next POST overwrites the whole file; write is non-atomic truncate-then-write | `ui/server.py:377-398` |
| F24 | `/api/umap` imports `umap` before the manifest check → missing manifest + no umap-learn = misleading 500; `tests/test_ui.py:158-162` documents this and `pytest.skip`s around it | `ui/server.py:214-220` |
| F25 | `cache_get` on a read path does `cache_dir.mkdir(parents=True)` → `agentpack retrieve <typo-dir> q` side-effect-creates `.cache/` and `indexes/` at the typo path, then tracebacks | `cache.py:19` |
| F26 | `agentpack index <missing-dir>` tracebacks (`mkdir` without `parents`, no manifest pre-check — `map`/`graph` at `cli.py:190-192,221-223` do it right); `audit` on an empty manifest tracebacks (`safe_load` → `None`, `audit.py:34`); `retrieve --top-k -1` reaches SQLite as `LIMIT -1` and dumps the ENTIRE corpus; `--top-k 0` returns nothing; `--mode` typos silently run hybrid (`retrieve.py:449-454`); `prep-benchmark --dataset tatqa\|qasper` are `pass` stubs that print "Preparation complete." and exit 0 (`benchmarks.py:226-236`) | `cli.py`, `audit.py`, `retrieve.py`, `benchmarks.py` |
| F27 | `search_fts` leaks its sqlite connection on the all-stopword early return and on any exception (no try/finally); `ensure_lexical_index` (`ui/server.py:44`) discards the LIVE connection `build_fts_index` returns. UI endpoints themselves are clean (try/finally verified) | `retrieve.py:237-281` |
| F28 | `agentpack map` rebuild hardcodes `enrich=False` (`mapper.py:261`) → rebuilt map has no keyphrases → a subsequent `agentpack graph` produces a zero-concept graph with no warning anywhere | `mapper.py:261`; `cli.py` graph_cmd |
| F29 | `fitz.open()` in the fast PDF path is never closed (success or exception) | `pdf_parser.py:41` |
| F30 | `search_hybrid(alpha=…)` is accepted and documented by signature but never read (dead parameter) | `retrieve.py:364` |

---

## 3. Design decisions (already made — do not relitigate)

| Decision | Choice | Why |
|---|---|---|
| Failure posture for per-file errors | Degrade to `parse_error` warning + `status: failed` source, never abort the pack | Matches the existing contract for errors inside parser try blocks; F2 just extends it to the escape paths |
| Eval failure accounting | **Exclude failed queries from averages; report `failures: N` per mode; never feed error strings to the judge** | Averaging zeros corrupts published numbers (F17); abort-on-first-error loses paid runs (F20) |
| Cache/index invalidation changes | Strengthen keys/fingerprints even though it one-time invalidates existing caches | Correctness over a one-time rebuild cost; see OQ2 |
| Scanner ordering | `sorted()` on both dirs and files in `os.walk` | Determinism; see OQ1 for the migration consequence |
| Corrupt-state self-heal | Corrupt `lexical_index.db` and corrupt `cache.db`: delete the file, warn on stderr once, rebuild/recreate | Matches trust.py/grapher.py "never crash, never silent" posture |
| Mode/typo handling | `--mode` becomes a validated choice; invalid `top_k` (< 1) is a clean CLI error | Silent fallback lies to users (F26) |
| Dead `alpha` param | Remove it from `search_hybrid`'s signature | Grep confirms no caller passes it (`cli.py`, `ui/server.py`, `eval/*` all call without it); removing is safe and honest |
| BOM/encoding | `utf-8-sig` for text/markdown; on decode errors emit an `ExtractionWarning(type="decode_error")` and continue with replacement chars | Same warning mechanism as everything else; no schema change (`type` is a free string) |
| What "atomic write" means here | Write to `<file>.tmp` in the same directory, then `os.replace()` | POSIX-atomic on same filesystem; pattern for F23 and the incremental eval writes |

---

## 4. Tasks

Uniform template per task: **Bug** (what's wrong) → **Fix** (exactly what to change) → **Test** (the RED test to write first) → **Verify** (commands). Acceptance for every task additionally includes: full suite green.

### Phase 0 — Independent quick wins (each is a small, self-contained commit)

#### T0.1 · Fix `test_run_eval` (the months-old red test)
- **Bug:** F22. The test mocks `agentpack.eval.runner.search_pack`/`write_pack`, but the reranker baseline added later imports `search_pack` function-locally from `agentpack.retrieve`, bypassing the mock; with `write_pack` mocked no pack exists → `FileNotFoundError`.
- **Fix:** in `tests/test_eval.py`, add a third patch so the test unit-tests the runner loop, not six real baselines:
  ```python
  @patch("agentpack.eval.runner._baselines.get_baselines", return_value=[])
  @patch("agentpack.eval.runner.search_pack")
  @patch("agentpack.eval.runner.write_pack")
  def test_run_eval(mock_write_pack, mock_search, mock_baselines, tmp_path):
  ```
  First **verify** the import shape: `grep -n "import baselines\|_baselines\|get_baselines" src/agentpack/eval/runner.py` — patch whatever name `run_eval` actually resolves `get_baselines` through (the audit found it reachable as `agentpack.eval.runner._baselines.get_baselines`; confirm before writing).
- **Test:** this IS a test change. RED = current failure (`FileNotFoundError`); GREEN = passes in ~2s.
- **Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_eval.py -v` then full suite → **fully green from here on**. Update rule 2's baseline in `tasks/hardening-todo.md`.

#### T0.2 · `gen-eval` exit code
- **Bug:** F6.
- **Fix:** in `cli.py`'s `gen_eval` error branch (currently `typer.secho(report, fg=typer.colors.RED)` with nothing after), add `raise typer.Exit(code=1)` — mirror the `eval` command's branch a few lines above.
- **Test (RED first):** in `tests/test_cli.py`, copy the existing `test_cli_eval_error` pattern: mock `run_generation_eval` to return a string starting with `"Error"`, invoke `["gen-eval", "fake_dir"]`, assert `result.exit_code == 1`.
- **Verify:** targeted test + full suite.

#### T0.3 · Corrupt `lexical_index.db` self-heal
- **Bug:** F4.
- **Fix:** in `retrieve.py` `_fts_stored_hash`, catch `sqlite3.DatabaseError` (parent of `OperationalError`) instead. In the caller (`search_fts`, around the hash-check at `:235-241`), when the stored hash is unreadable because the file is corrupt: `db_path.unlink(missing_ok=True)`, print one stderr warning (`[agentpack] Warning: corrupt lexical index, rebuilding.`), rebuild. Ensure the probe connection is closed on the error path (context-manage it).
- **Test (RED first):** build a real tiny FTS index (reuse `test_build_fts_index_and_search`'s setup), then truncate the db file (`db_path.write_bytes(b"garbage")`), then call `search_fts` → RED: raises `sqlite3.DatabaseError`. GREEN: returns results after transparent rebuild, and `capsys` captured a warning.
- **Verify:** live-verify first that `sqlite3.connect` + query on a garbage file raises `DatabaseError` and NOT `OperationalError`: the audit confirmed it, re-confirm in `./venv/bin/python`.

#### T0.4 · Cap section-level enrichment (the OOM)
- **Bug:** F5.
- **Fix:** two lines in `mapper.py::_to_section_node`: after `node_text = " ".join(tnode.own_text).strip()`, apply `node_text = node_text[:_ENRICH_TEXT_CAP]` before the `_keyphrases`/`_gist` calls — identical to the doc-level pattern at `:176`. Defense in depth (optional, same commit): in `enrich.py::gist`, cap `sentences = sentences[:400]` after `_sentences()` with a short comment; 400 sentences ≈ well past any 8000-char input, so it only guards future uncapped callers.
- **Test (RED first):** in `tests/test_mapper.py` (or wherever mapper tests live — find with `grep -rl "_to_section_node\|build_map" tests/`), build a doc whose single section has `own_text` > 8000 chars and assert the text reaching enrichment is capped — simplest observable: monkeypatch `agentpack.mapper._gist` to capture its argument, assert `len(arg) <= 8000`. RED first (captures full length today).
- **Verify:** targeted + full suite. Then the real-world check: `PYTHONPATH="$PWD/src" ./venv/bin/python -m agentpack.cli pack demo_corpus --out /tmp/hardening_t04 --fast --quiet` still succeeds and `map.yml` still has keyphrases/gists (cap must not blank them on normal docs).

#### T0.5 · Pin the embedding model name
- **Bug:** F12.
- **Fix:** `retrieve.py` — `TextEmbedding(model_name=_EMBED_MODEL_ID)` at the singleton construction site.
- **Test (RED first):** in `tests/test_retrieve.py`, patch `fastembed.TextEmbedding` with a `MagicMock`, call `_get_embedding_model()` (reset the module singleton first — check how it's cached, e.g. set the module global to `None`), assert it was called with `model_name="BAAI/bge-small-en-v1.5"`.
- **Verify:** targeted + full suite (mocked-embedding tests must be unaffected — they patch `_get_embedding_model` itself).

#### T0.6 · Warn when `agentpack graph` runs on a descriptor-less map
- **Bug:** F28.
- **Fix:** in `cli.py::graph_cmd`, after loading/confirming `map.yml` exists (or inside the flow before `write_graph`), read `map.yml` and if NO section anywhere in any document carries a non-empty `keyphrases` list, `typer.secho` a yellow warning: `"map.yml has no keyphrases (built by 'agentpack map'?) — the graph will contain no concepts; run 'agentpack pack' for a full-fidelity map."` Do not change behavior — warn only. Walk sections recursively (nested `nodes`).
- **Test (RED first):** in `tests/test_graph_cli.py`, pack a corpus, overwrite `map.yml` stripping all `keyphrases` (or run the real `agentpack map` rebuild to produce one honestly), run `["graph", str(out)]`, assert the warning text appears in output and exit code is 0. Second test: normal pack-time map → no warning.
- **Verify:** targeted + full suite.

#### T0.7 · Remove the dead `alpha` parameter
- **Bug:** F30.
- **Fix:** delete `alpha` from `search_hybrid`'s signature. First **verify** no callers: `grep -rn "search_hybrid(" src/ tests/` — if ANY call site passes `alpha`, STOP and report instead.
- **Test:** no new test; full suite is the test.

▣ **CHECKPOINT 0** — post the todo with evidence; wait for human go before Phase A.

### Phase A — Pack correctness (citations, error boundary, cache identity, determinism)

#### TA.1 · Chunk boundary metadata (THE citation bug)
- **Bug:** F1. In `chunker.py`, the loop updates `current_metadata` from the incoming block BEFORE deciding whether the accumulated chunk must flush; `create_chunk` then stamps the flushed chunk with the incoming block's page/section.
- **Fix:** reorder so the flush uses the metadata of the content actually IN the chunk: capture the would-be-flushed chunk's metadata before overwriting `current_metadata` (i.e., flush first with the OLD metadata, then update `current_metadata` for the new block). Read the whole loop before editing; also confirm the overlap-retention path (`:44-51`) stamps retained-overlap chunks with the metadata of where the overlap CAME FROM (acceptable) vs the new block (fix likewise if reachable).
- **Test (RED first):** two blocks, page 1 and page 2, sized so block 1 alone overflows into a flush exactly at the boundary (e.g., block1 ~700 tokens, block2 ~700 with `max_tokens=800`). Assert the FIRST chunk's citation page == 1. RED today: it reports 2. Add a section-path variant (block 2 in a different section; first chunk must carry block 1's section).
- **Verify:** targeted + full suite + re-pack `demo_corpus` and spot-check `manifest.yml` citations against a known page boundary.

#### TA.2 · Oversized-split token accounting
- **Bug:** F14. First sub-chunk = retained overlap + sub-block, but `current_tokens` is OVERWRITTEN with `len(sub_tokens)`.
- **Fix:** in `chunker.py:89-90` area: either add (`current_tokens += len(sub_tokens)`) so the flush threshold sees the true size, or flush the retained overlap before starting sub-block accumulation — choose whichever keeps every emitted chunk's real token count ≤ `max_tokens` AND `token_count` equal to the actual tokenized length of the chunk's text. The second property is the acceptance criterion; assert it directly.
- **Test (RED first):** normal block (~200 tokens) followed by an oversized block (~2000 tokens), `max_tokens=800`, overlap default. For EVERY emitted chunk: `len(enc.encode(chunk_text)) <= 800` and `manifest token_count == len(enc.encode(chunk_text))` (use the same `cl100k_base` encoder the chunker uses). RED today: one chunk is 901 tokens recorded as 800.
- **Verify:** targeted + full suite.

#### TA.3 · Per-file error boundary
- **Bug:** F2.
- **Fix:** in `pack.py`, wrap the per-file work so ANY exception from parsing one file (including the checksum/`open()` calls currently outside parser try blocks, and the `future.result()` at the gather point) degrades to: a `SourceDocument` with `status`-driving `ExtractionWarning(type="parse_error", detail=str(e))`, empty blocks, and the pack continuing. Implement at the submission-function level (the callable submitted to the executor catches everything and returns a failed-doc object) so `future.result()` can only raise on true executor faults. Preserve existing behavior for errors already handled inside parsers.
- **Test (RED first):** corpus of one good `.md` + one dangling symlink (`(dir / "ghost.md").symlink_to(dir / "nope.md")`). RED today: `write_pack` raises `FileNotFoundError`. GREEN: pack succeeds, manifest lists both sources, ghost has `status: failed` + a `parse_error` warning, good file's chunks exist. Second test: unreadable file via `chmod 0` (skip on platforms where root ignores permissions — guard with an effective-uid check like other tests do, or use monkeypatched `open` to raise `PermissionError` for that one path for determinism).
- **Verify:** targeted + full suite + `agentpack audit` on the produced pack shows the warning.

#### TA.4 · L1 cache-hit remap of path and block ids
- **Bug:** F3. Cache hit remaps `doc.source_id` only.
- **Fix:** at `pack.py:72-73`, after a hit also set `doc.path = file_path.name` (or the current path value used at parse time — match whatever a fresh parse would set) and rewrite block-level ids: for each block, re-derive its id under the CURRENT `source_id` (blocks carry ids like `src_000_table_0` — regenerate with the same formatting logic the parser uses; find it with `grep -rn "block_id\|_table_" src/agentpack/parsers/`). Follow the precedent of the trust-warning remap test (`tests/test_pack.py:192`) — this is the same bug class one field over.
- **Test (RED first):** pack corpus with `report_a.csv`; then rename the file to `report_b.csv` (same bytes) into a fresh input dir, pack again with the same cache dir. Assert manifest citations for the second pack say `report_b.csv` (RED: says `report_a.csv`) and any table block ids carry the second pack's source_id namespace.
- **Verify:** targeted + full suite. Also confirm cache HIT still happens (assert via the existing cache-hit counting pattern in `test_pack.py`) — the fix must remap, not bypass, the cache.

#### TA.5 · Deterministic scan order
- **Bug:** F13.
- **Fix:** in `scanner.py`'s `os.walk` loop: `dirs.sort()` (in-place, so traversal itself is ordered) and iterate `sorted(files)`.
- **Test (RED-ish):** monkeypatch `os.walk` to yield files in reversed order and assert `scan_directory` output is nonetheless sorted (this makes the test meaningful on any filesystem). Plus a straight determinism test: two scans → identical list.
- **Verify:** targeted + full suite. **Migration note for the PR description (OQ1):** existing packs re-packed after this may assign different `src_NNN` ids once.

#### TA.6 · Stop self-ingestion of the output dir
- **Bug:** F15.
- **Fix:** in `pack.py::write_pack`, resolve `out_path` and pass it to the scanner as an exclusion (add an `exclude_dirs` parameter to `scan_directory` or filter the scan result: any file whose resolved path is inside the resolved output dir is skipped). Do it by real path (`Path.resolve()`), not string prefix.
- **Test (RED first):** `write_pack(corpus, corpus/"pack")` twice; assert the second manifest's sources are exactly the original corpus files (RED today: includes `src_000_chunk_000.md`, `pack_report.md`).
- **Verify:** targeted + full suite.

#### TA.7 · Encoding: BOM + decode warnings
- **Bug:** F16.
- **Fix:** `text_parser.py` and `markdown_parser.py`: read with `encoding="utf-8-sig"`, `errors="replace"` retained, but AFTER decode, if `"�"` in the text, append `ExtractionWarning(type="decode_error", message=...)` to the doc (mirror how parsers attach warnings today — find the pattern with `grep -n "ExtractionWarning" src/agentpack/parsers/*.py`). Status stays success (content may still be partially useful) — the warning surfaces it in `audit`.
- **Test (RED first):** (a) UTF-8-BOM markdown `﻿# Title\n\nbody` → RED: first block is a paragraph titled literally `﻿# Title`; GREEN: parsed as heading, section structure present, no decode warning. (b) UTF-16-encoded `.txt` → GREEN: pack succeeds AND the source carries a `decode_error` warning (RED: no warning).
- **Verify:** targeted + full suite.

#### TA.8 · Close the fitz document
- **Bug:** F29.
- **Fix:** `pdf_parser.py:41` — `with fitz.open(...) as pdf_doc:` (pymupdf supports context manager; **verify live**: `import fitz; help(fitz.Document.__enter__)` or just try it on a demo PDF in `./venv/bin/python`).
- **Test:** no direct test (resource release); full suite + the e2e PDF test must stay green.

▣ **CHECKPOINT A** — evidence + human go.

### Phase B — Invalidation & retrieval robustness

#### TB.0 · Ranking snapshot guard (write FIRST, before any B change)
- **Purpose:** prove Phase B changes storage/invalidation only, never ranking.
- **Test:** build a small real pack (markdown corpus, mocked embeddings like `test_rrf_ordering` does), run `search_pack` hybrid for 2 fixed queries, snapshot the ordered chunk-id lists as literals in the test. This is the regression tripwire for the rest of Phase B.

#### TB.1 · Ghost results after degenerate rebuild
- **Bug:** F7.
- **Fix:** in `build_vector_index`, on the zero-chunks/zero-texts early paths: delete `vector_index.npy`, `vector_meta.json`, `hnsw_index.bin` if present, and WRITE the new manifest hash — so searches see "empty index" (return `[]`) rather than loading stale files. Adjust `search_vector` to return `[]` cleanly when index files are absent AND the hash says current-and-empty.
- **Test (RED first):** build a pack + vector index (mocked embeddings); then rewrite the manifest to zero chunks (keep sources) and call `search_vector` → RED: returns results for deleted chunks; GREEN: `[]`. **Also fix the entrenched test:** `test_search_hybrid` (`tests/test_retrieve.py:125-159`) currently passes BECAUSE of the bug — rewrite its fixture to a consistent manifest+index pair (it will fail against the fix as-is; that failure is expected and is the proof).
- **Verify:** targeted + TB.0 snapshot + full suite.

#### TB.2 · Content-aware manifest hash
- **Bug:** F8.
- **Fix:** in `_manifest_hash`, fold each chunk's `token_count` (present in the manifest today — verify with `grep -n "token_count" src/agentpack/pack.py`) into the fingerprint alongside its id, e.g. hash over sorted `f"{id}:{token_count}"` lines + source checksums. No schema change; redistribution of text across same-count chunks almost always shifts token counts.
- **Test (RED first):** two manifests, same chunk ids/sources, different token_counts → hashes must differ (RED: equal). Existing invalidation tests must stay green.
- **Verify:** targeted + TB.0 + full suite. Migration note (OQ2): one-time index rebuild + L5 cache invalidation for existing packs.

#### TB.3 · Corrupt `cache.db` self-heal + connection hygiene
- **Bug:** F9.
- **Fix:** in `cache.py`: wrap connections in try/finally (or context managers) so no path leaks; on `sqlite3.DatabaseError` in `_connect`/get/set, delete `cache.db`, emit ONE stderr warning per process (module-level flag), recreate, and continue (get returns miss). Keep the general never-crash posture.
- **Test (RED first):** write garbage to `cache.db`, call `cache_get` → RED: silent None forever with no heal (assert file unchanged); GREEN: warning emitted once (capsys), file recreated, subsequent `cache_set`/`cache_get` round-trips.
- **Verify:** targeted + full suite.

#### TB.4 · HNSW staleness
- **Bug:** F10.
- **Fix:** in `build_vector_index`: when hnswlib is unavailable (or embeddings empty), delete any existing `hnsw_index.bin`. In `search_vector`'s load path, wrap HNSW load+query in try/except → on failure (corrupt/mismatched bin) delete the bin, warn once, fall through to brute-force `np.dot`. Cheap consistency check before trusting it: `index.get_current_count() == len(embeddings)` (**verify live** that hnswlib exposes `get_current_count`; if not, rely on the try/except fallback alone).
- **Test (RED first):** build index with a REAL tiny hnsw bin (hnswlib is installed), then rewrite npy/meta to fewer rows while keeping the old bin and a matching hash → call `search_vector`: RED: wrong/erroring results from stale labels; GREEN: brute-force results, warning emitted, bin deleted.
- **Verify:** targeted + TB.0 + full suite.

#### TB.5 · `remove_empty_lines` in the L1 key
- **Bug:** F11.
- **Fix:** `pack.py:65` — add the flag to the key tuple/string (find exact key construction; extend consistently with how `fast_pdf` is included).
- **Test (RED first):** pack same corpus twice into fresh out dirs, same cache, second time with `remove_empty_lines=True` → assert the second pack's chunk text has no blank lines (RED: cached untransformed text served).
- **Verify:** targeted + full suite. (Old-key entries simply miss once — no migration needed.)

#### TB.6 · retrieve.py connection hygiene + no side-effect mkdir on reads
- **Bug:** F25, F27.
- **Fix:** (a) `search_fts` and `search_pack`'s content-attach block: try/finally around connections (mirror `ui/server.py:184-211`). (b) `ensure_lexical_index` in `ui/server.py`: `build_fts_index(...)` returns a live conn — close it. (c) `cache.py:19`: split read/write paths — `cache_get` must NOT `mkdir`; only `cache_set` creates the directory (verify `_db_path`/`_connect` structure first; simplest: pass a `create=False` flag from the get path and return a miss if the db file doesn't exist). (d) `search_pack`/CLI `retrieve`: check `manifest.yml` exists up front and produce the clean red-error/exit-1 pattern `map_cmd` uses.
- **Test (RED first):** `runner.invoke(app, ["retrieve", str(tmp/"nope"), "q"])` → RED: traceback + `.cache/` created at the typo path; GREEN: exit 1, red message, NO directories created (assert `not (tmp/"nope").exists()`).
- **Verify:** targeted + full suite.

#### TB.7 · UI: feedback atomicity + umap import order + chunks staleness
- **Bug:** F23, F24, and `/api/chunks` trusting existence over hash.
- **Fix:** (a) `/api/feedback`: replace bare `except: pass` with: on JSON parse failure, rename the corrupt file to `eval_feedback.json.corrupt-<epoch>` (preserve, don't wipe) and start fresh; write via tmp-file + `os.replace`; guard the read-modify-write with a module-level `threading.Lock`. (b) `/api/umap`: move `import umap` to AFTER `load_vector_artifacts` succeeds; then remove the now-unneeded `pytest.skip` guards in `tests/test_ui.py:158-176` region so the 404 path is actually tested everywhere (keep skips only where umap itself must run). (c) `ensure_lexical_index`: validate the stored hash like `search_fts` does (reuse/extract that check) and rebuild when stale.
- **Test (RED first):** (a) write corrupt `eval_feedback.json`, POST feedback twice → GREEN: both entries present in the new file AND the corrupt original preserved under `.corrupt-*` (RED: file wiped to 1 entry, original lost). (b) missing manifest + umap absent: currently skipped tests → after fix, `/api/umap` with no manifest returns 404 with umap not even installed (drop the skip). (c) build pack, load `/api/chunks`, re-pack different corpus into same dir, `/api/chunks` again → GREEN: new corpus's chunks (RED: old).
- **Verify:** targeted + full suite.

▣ **CHECKPOINT B** — evidence + human go.

### Phase C — Eval integrity (the published numbers)

#### TC.1 · Failed queries excluded from averages; failures reported
- **Bug:** F17 (+ policy from §3).
- **Fix:** `generation.py`: when generation raises → record the query as FAILED for that mode (do NOT call the judge, do NOT increment the scored count, do NOT synthesize an "Error generating answer" string as an answer); when the judge raises → same. Track `failures` per mode; the report table gains a `failures` column (report text only — no schema files involved) and averages divide by `count_scored`. If `count_scored == 0`, print `n/a` not 0.0. Mirror the same policy in `runner.py`'s retrieval metrics if a search_fn raises (see TC.2).
- **Test (RED first):** mock generation to raise on query 2 of 3 → GREEN: averages computed over 2, `failures: 1` visible in report (RED: averaged over 3 with zeros / error-string judged).
- **Verify:** targeted + full suite.

#### TC.2 · Per-query error isolation + incremental persistence
- **Bug:** F20.
- **Fix:** `runner.py`: wrap the per-query `search_fn` call in try/except → count as failure for that mode, continue. `generation.py`: after each query, write `generation_results.json` atomically (tmp + `os.replace`) so a crash at q99 preserves 98; same for the final report writes.
- **Test (RED first):** search_fn that raises on one query → run completes, other queries scored (RED: whole eval aborts). Persistence: mock generation to raise `KeyboardInterrupt` at q3 of 5 inside a `pytest.raises` guard → `generation_results.json` on disk contains q1-q2.
- **Verify:** targeted + full suite.

#### TC.3 · Baseline cache gets a corpus fingerprint
- **Bug:** F18.
- **Fix:** `baselines.py` cache filenames/keys: incorporate a corpus fingerprint = sha256 over sorted `(relative_path, size, mtime_ns)` of corpus files (cheap, no hashing of content; compute once per run). Bump `_CACHE_VERSION`.
- **Test (RED first):** populate cache, touch/modify a corpus file, rerun → GREEN: cache miss + rebuild (assert via a marker: the cache file name changes / a build-counter mock is called again). RED: stale reuse.
- **Verify:** targeted + full suite.

#### TC.4 · LLM-baseline degradation must be loud
- **Bug:** F19.
- **Fix:** `_llm_generate` failures: count them; if a mode's LLM call failed for >0 queries, its report row label gains an explicit marker, e.g. `HyDE [LLM UNAVAILABLE for N/M queries]`, and a stderr warning is printed once. Do NOT change the fallback behavior itself (still degrade gracefully) — just stop it being silent.
- **Test (RED first):** mock `_llm_generate` to return `""` (as on failure) → report contains the marker (RED: clean "HyDE" row).
- **Verify:** targeted + full suite.

#### TC.5 · `_get_naive_conn` cache correctness
- **Bug:** F21.
- **Fix:** set `_last_corpus_dir` (and include `chunk_size` in the identity check) in `_get_naive_conn` exactly as `_get_raw_conn` does — read both functions side by side first.
- **Test (RED first):** call `_get_naive_conn(corpusA)` twice → second call must NOT rebuild (mock/count the index-build function; RED: builds twice). Call with corpusB after A → MUST rebuild (guard the cross-corpus serving direction).
- **Verify:** targeted + full suite.

#### TC.6 · CLI/edge hygiene sweep
- **Bug:** F26 (+ audit/None guards).
- **Fix:** (a) `retrieve`: `top_k < 1` → clean typer error; `mode` validated against `{"hybrid","vector","fts"}` → clean error on anything else (keep free-text arg, validate in code — or use an Enum if typer version supports it cleanly; check how other choices are done in this cli.py). (b) `index`: add the manifest pre-check + red-exit-1 (copy `map_cmd`'s block). (c) `audit.py:34` + `runner.py:83` + `generation.py:86`: guard `safe_load(...) or {}` / empty-list access with clean error messages. (d) `benchmarks.py` tatqa/qasper stubs: `raise NotImplementedError("dataset slicing for X not implemented")` and `cli.py prep-benchmark` catches it → red message + exit 1 (RED test: currently prints "Preparation complete." and exits 0).
- **Test (RED first):** one test per branch above, all via `CliRunner` asserting exit codes and messages.
- **Verify:** targeted + full suite.

▣ **CHECKPOINT C (final)** — full-suite evidence, re-pack `demo_corpus` end-to-end (`pack`, `retrieve`, `audit`, `validate`, `ui` smoke), then PR into `dev`.

---

## 5. Commands

```bash
PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q            # full suite (always)
PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_X.py -v   # targeted
PYTHONPATH="$PWD/src" ./venv/bin/python -m agentpack.cli pack demo_corpus --out /tmp/hardening_smoke --fast --quiet   # real-corpus smoke
```

## 6. Project structure (files this spec touches)

`src/agentpack/`: `chunker.py`, `pack.py`, `scanner.py`, `retrieve.py`, `cache.py`, `mapper.py` (call-site caps only), `cli.py`, `audit.py`, `ui/server.py`, `parsers/text_parser.py`, `parsers/markdown_parser.py`, `parsers/pdf_parser.py` (close only), `eval/runner.py`, `eval/generation.py`, `eval/baselines.py`, `eval/benchmarks.py` (stub errors only).
`tests/`: the matching `test_*.py` files; `tasks/hardening-todo.md` (new).
**Nothing else.** If a fix seems to require touching a file outside this list, stop and report.

## 7. Code style

Match each file's existing conventions (this codebase is consistent): stderr warnings as `[agentpack] Warning: …` / `[agentpack] Note: …`; CLI errors as `typer.secho(..., fg=typer.colors.RED)` + `raise typer.Exit(code=1)`; never-crash wrappers follow `trust.py`/`grapher.py` (one outer try/except, degrade + one warning line); comments state constraints, not narration.

## 8. Descoped (deliberately NOT in this spec)

- **Release/packaging (audit #24/#25):** the never-succeeding `publish.yml`, the double-publish design, and the UI-less npm binary need a product decision (CI-canonical vs local-canonical publishing) — separate discussion, do not touch the workflow or `agentpack.spec`.
- **Manifest basename collisions (audit #16):** the fix changes `path` field semantics (relative paths) — a schema-adjacent behavior change; needs its own mini-spec.
- **Docling converter thread-safety (audit #34):** needs investigation of docling's actual guarantees; risky to "fix" blind.
- **`docs/docs/assets` Windows symlink (#36), nested-gitignore support, streaming file hashing, UMAP response caching:** noted in the audit, not worth the risk/effort ratio here.

## 9. Open Questions — RESOLVED 2026-08-12 (all recommendations accepted)

Resolutions: **OQ1** accepted (one-time src_NNN shift on re-pack is fine). **OQ2** accepted (one-time index rebuild + L5 invalidation is fine). **OQ3** confirmed (exclude-and-report). **OQ4** in scope, as its own PR after Checkpoint B. Original questions kept below for the record.

1. **OQ1 — scan-order migration.** TA.5 makes scanning sorted; re-packing an existing corpus may reassign `src_NNN` ids once (citations in NEW packs shift accordingly; old packs are untouched). Accept this one-time shift? **Recommendation: yes** — determinism across machines is worth it, and ids were never stable across platforms anyway (that's the bug).
2. **OQ2 — hash-strengthening migration.** TB.2 changes `_manifest_hash` → every existing pack's indexes rebuild once on next query and L5 query caches invalidate once. Accept? **Recommendation: yes** — the alternative is serving stale results.
3. **OQ3 — eval failure policy.** §3 chose exclude-and-report over abort-on-error and over average-as-zero. Confirm? **Recommendation: confirm** — it's the only option that neither corrupts numbers nor loses paid runs. (Failed-query counts remain visible so a mostly-failed run can't masquerade as a good one.)
4. **OQ4 — Phase C scope.** Eval integrity is the largest phase and touches the code producing README benchmark numbers. In scope now, or ship Phases 0/A/B first and do C as its own PR? **Recommendation: in scope, but as its own PR after Checkpoint B** (one branch per phase is fine; the spec's checkpoints already gate this).

## 10. Success criteria (rollup)

- Full suite **fully green** after T0.1 and after every subsequent task (no "1 pre-existing failure" allowance anymore).
- Every fix has a test that failed before it (recorded in `tasks/hardening-todo.md` with the RED output).
- TB.0's ranking snapshot is byte-identical before and after Phases B and C.
- `demo_corpus` end-to-end smoke (`pack` → `retrieve` → `audit` → `validate`) clean at the final checkpoint.
- No changes to `manifest.yml`/`map.yml`/`graph.yml` schemas, no changes to retrieval ranking, no new dependencies.
