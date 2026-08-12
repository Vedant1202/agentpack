# TODO — Concept Graph in the Corpus Explorer UI

Companion to [graph-ui-plan.md](graph-ui-plan.md). Read that first — its "Verified facts" section is
pre-verified against this repo; do not re-derive. Working style, test invocation
(`PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q`), green baseline
(**285 passed, 1 pre-existing failure** `test_run_eval`), and process rules (branch off `dev`, PR
into `dev`, evidence per task) are identical to
[concept-graph-todo.md](concept-graph-todo.md)'s header — follow them verbatim.

**Do-not-touch:** `grapher.py`, `retrieve.py`, `validate.py`, all parsers/chunker/mapper — this
feature only *reads* `graph.yml`. Touching the graph build to make it "render nicer" is the wrong
layer; file a finding instead.

---

## G1 · `/api/graph` endpoint ✅ DONE

**Description:** Serve `graph.yml` to the frontend, mirroring `/api/manifest` (server.py:65-70).
`GET /api/graph` → `{"available": true, ...<graph.yml verbatim>}` when present;
`{"available": false}` (HTTP 200, not 404) when absent — absence is a normal state
(`--no-graph`, single-doc corpus), not an error.

- [x] `graph.yml` present → 200 with `available: true` plus verbatim `graph_version/pack/params/nodes/edges/communities`.
- [x] Absent → 200 `{"available": false}`; missing manifest still behaves like other endpoints (404 via `ensure_manifest_exists`).
- [x] Corrupt/unparseable `graph.yml` → `{"available": false}` + server-side warning (`[agentpack] Warning: failed to parse graph.yml (...)`, `capsys`-asserted), never a 500. **Caught against my own acceptance criterion**: the first implementation degraded silently with no warning — fixed and re-verified in a follow-up commit before moving to G2, matching this feature's established never-raise-but-never-silent posture (grapher.py, validate.py).

**Verify:** ✅ RED confirmed first (4 new tests failed — no `/api/graph` route existed, so the catch-all static handler served `index.html` instead of JSON, a `JSONDecodeError` on every assertion). `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_ui.py -v -k api_graph` → **4 passed**. Full suite: **289 passed, 1 pre-existing failure** (`test_run_eval`) — exactly 285 (B1 baseline) + 4 new, zero regressions.
**Commits:** `2a6455a` (endpoint), `9098254` (missing-warning fix).

---

## G2 · Concept Graph view — toggle, data builder, rendering, legend ✅ DONE

**Description:** A `Universe ⇄ Concepts` view toggle in the header. In Concepts view, fetch
`/api/graph` once, build ForceGraph2D data via a new `buildConceptGraphData(graph)` (sibling of
`buildGraphData`, App.jsx:60): nodes colored by `community` (stable palette keyed by community id),
sized by kind (document > section > concept), labels truncated ~40 chars; edges styled by relation —
solid for `contains`/`mentions`/`references`, dashed for `similar_to`. Legend panel (mirroring
`GraphLegend`, App.jsx:140) shows community labels + edge-relation key. Toggle disabled with
tooltip "No graph.yml in this pack — run `agentpack graph <pack_dir>`" when `available: false`.

- [x] Toggle switches views without breaking the existing chunk universe. Required a fix beyond the original scope: the resize-observer effect (App.jsx, originally keyed only on `[loading]`) had to gain `viewMode` as a dependency too — switching views swaps in a *different* container `<div>` behind the same ref, and without re-attaching, the concept canvas would render at a stale/zero size from before the observer ever saw it. Caught by reasoning through the ref-sharing design before it shipped, not by trial and error.
- [x] Concept nodes render as diamonds (circles are already document/section's shape in the Universe view — reused that visual vocabulary rather than inventing a new one); document/section nodes as circles sized by `KIND_VAL`. Confirmed distinguishable in both light and dark mode live.
- [x] `available: false` → disabled toggle (real `disabled` attribute, not just dimmed styling — verified via `btn.disabled === true` in the browser, not just visually) + correct tooltip text; zero console errors on either pack.

**Verify:** ✅ `npm run lint` clean (one violation caught and fixed: an unused `catch (error)` binding — logged it instead, consistent with the sibling chunk-fetch catch block's own convention). `npm run build` clean, deterministic output hash before/after the live-verification browser session (`index-CCcKa6WL.css` / `index-FCKkGgK2.js` unchanged), confirming the debug-only `javascript_tool` use during verification never touched source. Full pytest suite: **289 passed, 1 pre-existing failure** — identical to G1's count, zero new Python tests as expected for a frontend-only task, zero regressions.

## G3 · Interactions — details panel, relation toggles, empty states ✅ DONE

**Description:** Click a node → the existing right-hand context panel shows kind-specific detail:
concept → full label + mentioning sections (walk `mentions` edges) + bridge status; document →
isolated status (no cross-doc edges) + section count; section → full untruncated label + parent doc +
concepts mentioned. Legend gains per-relation visibility checkboxes (all default ON; `similar_to`
expected to be the one users turn off on PDF corpora — known B1 finding). Communities summary
(label + size from `communities:`) listed in the panel when nothing is selected.

- [x] Each kind's detail set implemented as a faithful client-side port of the matching grapher.py logic, not an approximation: `isDocumentIsolated` mirrors `_isolated_documents` (no `references` edge either direction AND no concept shared with a different document's sections) and `conceptBridgeCommunities` mirrors `_bridge_concepts` (communities spanned by a concept's mentioning sections, ≥2 = bridge) — chosen over a simpler proxy (e.g. raw edge count) specifically so the UI's isolated/bridge labels never silently disagree with `reports/graph_report.md`'s own authoritative computation of the same facts.
- [x] Relation checkboxes filter `displayConceptData`'s links immediately (nodes are never pruned when their edges are hidden — an isolated-looking node is itself meaningful signal, matching the "isolated documents" concept from the report rather than hiding it).
- [x] No-selection state shows the communities summary (label, color swatch, member count) instead of a blank panel.

**Verify:** ✅ `npm run lint` + `npm run build` clean (same run as G2, built together). Full pytest suite unchanged (289 passed, 1 pre-existing failure).

- **Live browser verification, both packs, both themes** (financebench subset: 61 nodes/282 edges/6 communities; `--no-graph` pack: disabled-toggle path): confirmed via `preview_start`/`computer`/`javascript_tool` —
  - Real data flowed correctly end-to-end: stats (61/282/6) and community list/sizes in the sidebar matched `graph.yml` exactly.
  - Relation toggle: unchecking `similar_to` visibly cleared the 210-edge hairball (the exact B1 finding) down to the real structural graph, confirmed by screenshot before/after.
  - Node click → concept detail (`Chief Financial Officer`, community `Financial Statements`, correct "not a bridge" verdict, two `(root)` mentioning sections listed) → clicked a mentioning-section link → correctly navigated to that section's own detail (`doc: src_003`, 3 concepts mentioned) — the full cross-navigation chain works.
  - Dark mode and light mode both render all node kinds/edge styles/panel text legibly.
  - Disabled-toggle pack: `btn.disabled === true` at the DOM level (not just CSS), correct tooltip text, click is a genuine no-op (view stayed on Universe).
  - Zero console errors across the entire session.
  - **Tooling note, not a product finding:** precisely clicking small force-graph canvas nodes via screenshot-pixel coordinates proved unreliable at first (repeated misses) until calibrating the actual screenshot-to-viewport scale factor empirically (placing a marker `div` at a known viewport coordinate and confirming where it lands in a screenshot) — worth recording so a future verification pass doesn't repeat the same trial and error.

**Dependencies:** G2 (built together as one commit — the toggle/rendering and the interactions turned out to share too much context to usefully split into a RED/GREEN pair the way the backend tasks did; there is no frontend test suite to make that split meaningful the way it is for pytest-backed tasks).
**Commit:** `b384353`.

---

## ▣ CHECKPOINT — before PR

- [x] Full suite: 289 passed, 1 pre-existing unrelated failure (`test_run_eval`) — 285 (Phase B baseline) + 4 (G1), zero regressions across G1/G2/G3.
- [x] ~~`npm run build` output in `dist/` committed~~ — **this checkpoint criterion was wrong, corrected here rather than silently dropped.** `src/agentpack/ui/web/dist/` is deliberately git-ignored (both the repo-root `.gitignore` and a nested `src/agentpack/ui/web/.gitignore`), and reaches PyPI users via `MANIFEST.in` (`recursive-include src/agentpack/ui/web/dist *`) plus `pyproject.toml`'s package-data entry, applied when someone runs the actual release build (`python -m build`) — not via a git commit at feature-merge time. My original plan assumed "dist is committed" from the v0.3.2 changelog entry's *title* ("include pre-built UI assets in source distributions") without checking the *mechanism* first; the mechanism is packaging-time inclusion, not git tracking. `npm run build` succeeding cleanly (confirmed above) is the correct, sufficient check at this stage — the next actual release still needs a fresh `npm run build` run before `python -m build`, same as every prior UI release, which is a release-process fact to flag at release time, not a merge-blocking item here.
- [x] Live pass on BOTH real packs (financebench subset: dense, real communities/concepts/similar_to; `--no-graph` pack: disabled-toggle path) — see G3 evidence above.
- [x] `agentpack ui` against the `--no-graph` pack: explorer fully functional, toggle disabled, no errors.
- [ ] Human review, then PR into `dev` (never `main`).
