# Implementation Plan: Concept Graph in the Corpus Explorer UI (Phase C-c)

Companion todo: [graph-ui-todo.md](graph-ui-todo.md). Renders `graph.yml` (spec
[0003-corpus-concept-graph.md](../docs/specs/0003-corpus-concept-graph.md), shipped through Phase B)
in the existing Corpus Explorer. Descoped from 0003 as Phase C item (c); this plan specs only that item —
no retrieval changes, no LLM enrichment.

## Overview

The Corpus Explorer today renders one view: the "chunk universe" — a ForceGraph2D of every chunk,
clustered around virtual per-document nodes, built client-side from `/api/chunks`
([App.jsx:60-125](../src/agentpack/ui/web/src/App.jsx) `buildGraphData`). This feature adds a second,
toggleable view rendering the *concept* graph: documents, sections, and concepts from `graph.yml`,
colored by community, with `contains`/`mentions`/`references`/`similar_to` edges distinguished
visually. A pack without `graph.yml` shows the toggle disabled with a hint, never an error.

## Verified facts (grounds the design; do not re-derive)

- **Backend pattern:** `server.py` endpoints read pack files directly off `AGENTPACK_DIR`
  (`get_base_path()`); `/api/manifest` (server.py:65-70) is the exact shape to mirror — load YAML,
  return it. Errors are `HTTPException`; tests live in `tests/test_ui.py` using its `ASGITestClient`
  + `monkeypatch` of `server.PACK_DIR` (test_ui.py:47-88 pattern).
- **Frontend:** single-file React app (`src/agentpack/ui/web/src/App.jsx`, 706 lines),
  `react-force-graph-2d` already a dependency (used for the chunk universe), Tailwind for styling,
  `lucide-react` icons. **No frontend test infra exists** (no vitest/jest) — verification is
  `npm run lint` + `npm run build` + live browser check, matching how the UI shipped in v0.2.0–v0.4.x.
- **Dist ships via packaging, not git.** `src/agentpack/ui/web/dist/` is deliberately git-ignored
  (repo-root `.gitignore` plus a nested `web/.gitignore`) and reaches PyPI through `MANIFEST.in`
  (`recursive-include src/agentpack/ui/web/dist *`) and `pyproject.toml`'s package-data entry,
  applied when the release build (`python -m build`) runs — not by committing built output.
  **Correction, recorded 2026-08-11:** this bullet originally claimed dist was committed, inferred
  from the v0.3.2 changelog entry's title alone without checking the actual mechanism (MANIFEST.in).
  `npm run build` succeeding cleanly is the correct done-criterion for a frontend change; a fresh
  build still has to run before the next actual release, same as every prior UI release.
- **graph.yml shape** (from the shipped feature, not assumed): top-level `graph_version`, `pack`,
  `params`, `nodes` (`id/kind[document|section|concept]/label/doc/community`), `edges`
  (`source/target/relation[contains|mentions|references|similar_to]/basis`), `communities`
  (`id/label/size`). Section labels can be long or ugly (real finding: React README badge-wall,
  `(root)` for PDFs) — the UI must truncate defensively.
- **Scale envelope:** demo_corpus → 8 nodes; 21-doc financebench subset → 61 nodes / 282 edges.
  ForceGraph2D handles thousands; no virtualization needed at this scale. `similar_to` can be dense
  on PDF corpora (210/210 pairs, known B1 finding) — the legend/UI should let the user toggle that
  edge relation off.

## Architecture decisions

- **Separate toggled view, not an overlay** on the chunk universe. The two graphs share no node ids
  (chunk ids vs. section/concept ids), so overlaying would mean fake correlation; a clean
  view-switcher (Universe ⇄ Concepts) is simpler and matches the existing single-canvas layout.
- **Serve `graph.yml` verbatim** at `/api/graph` plus one computed field (`available`). No server-side
  reshaping — the client builds ForceGraph data the same way `buildGraphData` already does for chunks.
  Keeps the endpoint trivially testable and the transform in one language.
- **Community = node color, kind = node shape/size.** Community coloring is the whole point of
  Louvain; kind (document/section/concept) maps to size tiers + ring styling. Edge relation maps to
  line style (solid structural, dashed similar_to), with per-relation visibility toggles.
- **No new dependencies** — everything needed (force graph, icons, Tailwind) is already installed.

## Dependency graph

```
G1  /api/graph endpoint (server.py + test_ui.py)
 │
G2  Concept Graph view: toggle + data builder + rendering + legend (App.jsx)
 │
G3  Interactions: node details panel, edge-relation toggles, empty-state (App.jsx)
 │
CP  Checkpoint: lint + build + committed dist + live check on two real packs
```

Vertical slicing note: G2 is deliberately "render everything statically" and G3 is "make it
interactive" — each leaves a working, demoable UI.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| No frontend test infra | Med | Backend fully tested in pytest; frontend verified by lint + build + a scripted live browser pass on two real packs (steps in todo). Do not introduce a test framework as a side quest. |
| `similar_to` hairball on PDF corpora (known B1 finding) | Med | Relation toggles in G3 default `similar_to` ON but one click hides it; legend explains basis. |
| Long/ugly section labels (badge-wall, `(root)`) | Low | Truncate labels at ~40 chars with full text in the details panel. |
| dist drift (source edited, build not committed) | Med | Checkpoint explicitly diffs `dist/` and commits it; done-definition includes built assets. |
| Stale `graph.yml` vs manifest | Low | Out of scope — the CLI owns rebuilds (`agentpack graph`); UI renders what exists, and the empty-state hint names that command. |
