import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search, RefreshCw, X, Info, LayoutTemplate, Link as LinkIcon, FileText, Moon, Sun, Network } from "lucide-react";
import ForceGraph2D from "react-force-graph-2d";
import Shepherd from 'shepherd.js';
import 'shepherd.js/dist/css/shepherd.css';

// ==========================================
// UTILS
// ==========================================
const fetchJson = async (url, options = {}) => {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
  return res.json();
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function getFileType(filename) {
  const normalized = (filename || "").toLowerCase();
  if (normalized.endsWith(".md")) return "md";
  if (normalized.endsWith(".pdf")) return "pdf";
  if (normalized.endsWith(".csv")) return "csv";
  if (normalized.endsWith(".py")) return "py";
  if (normalized.endsWith(".docx")) return "docx";
  if (normalized.endsWith(".pptx")) return "pptx";
  if (normalized.endsWith(".xlsx")) return "xlsx";
  if (normalized.endsWith(".html") || normalized.endsWith(".htm")) return "html";
  return "other";
}

function palette(type) {
  if (type === "md") return { fill: "#0ea5e9", soft: "#e0f2fe", border: "#7dd3fc", text: "#075985" }; // sky
  if (type === "pdf") return { fill: "#f59e0b", soft: "#fef3c7", border: "#fde68a", text: "#92400e" }; // amber
  if (type === "csv") return { fill: "#10b981", soft: "#d1fae5", border: "#a7f3d0", text: "#065f46" }; // emerald
  if (type === "py") return { fill: "#f43f5e", soft: "#fce7f3", border: "#fbcfe8", text: "#9d174d" }; // rose
  if (type === "docx") return { fill: "#6366f1", soft: "#eef2ff", border: "#c7d2fe", text: "#3730a3" }; // indigo
  if (type === "pptx") return { fill: "#f97316", soft: "#fff7ed", border: "#fed7aa", text: "#9a3412" }; // orange
  if (type === "xlsx") return { fill: "#22c55e", soft: "#f0fdf4", border: "#bbf7d0", text: "#14532d" }; // green
  if (type === "html") return { fill: "#a855f7", soft: "#faf5ff", border: "#e9d5ff", text: "#581c87" }; // purple
  return { fill: "#64748b", soft: "#f1f5f9", border: "#e2e8f0", text: "#334155" }; // slate
}

function getSourceName(chunk) {
  return chunk?.citation?.source_path || chunk?.source || "unknown";
}

function getChunkTitle(chunk) {
  return chunk?.title || chunk?.id || "Unknown chunk";
}

function getResultTitle(result, fallbackChunk) {
  return result?.title || fallbackChunk?.title || result?.id || fallbackChunk?.id || "Unknown chunk";
}

// ==========================================
// GRAPH DATA BUILDER
// ==========================================
function buildGraphData(chunks) {
  const nodes = [];
  const links = [];
  const docs = new Set();
  
  chunks.forEach(chunk => {
      const source = getSourceName(chunk);
      const type = getFileType(source);
      
      // Virtual Doc Node
      if (!docs.has(source)) {
          docs.add(source);
          nodes.push({
              id: `doc_${source}`,
              isDoc: true,
              label: source.split(/[\\/]/).pop(),
              group: type,
              val: 45,
              color: palette(type).fill,
          });
      }
      
      // Chunk Node
      nodes.push({
          id: chunk.id,
          isDoc: false,
          label: chunk.id.split('_').pop(),
          group: type,
          val: clamp(8 + (chunk.tokens || 0) / 50, 5, 20),
          color: palette(type).fill,
          chunk: chunk
      });
      
      // Link chunk to doc
      links.push({
          source: `doc_${source}`,
          target: chunk.id,
          isDocLink: true,
          width: 1
      });
  });

  // Sequential Links (Tape)
  const bySource = new Map();
  chunks.forEach((chunk) => {
    const source = getSourceName(chunk);
    if (!bySource.has(source)) bySource.set(source, []);
    bySource.get(source).push(chunk);
  });
  
  bySource.forEach((sourceChunks) => {
    sourceChunks.forEach((chunk, index, ordered) => {
      const next = ordered[index + 1];
      if (next) {
        links.push({ 
            source: chunk.id, 
            target: next.id, 
            isSequential: true,
            width: 1.5
        });
      }
    });
  });

  return { nodes, links };
}

// ==========================================
// CONCEPT GRAPH DATA BUILDER (graph.yml)
// ==========================================
const COMMUNITY_PALETTE = [
  "#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#f43f5e",
  "#a855f7", "#22c55e", "#f97316", "#14b8a6", "#eab308",
];

function communityColor(communityId) {
  if (communityId === null || communityId === undefined) return "#94a3b8";
  return COMMUNITY_PALETTE[communityId % COMMUNITY_PALETTE.length];
}

const KIND_VAL = { document: 40, section: 18, concept: 12 };

function truncateLabel(label, max = 40) {
  if (!label) return "";
  const oneLine = String(label).replace(/\s+/g, " ").trim();
  return oneLine.length > max ? oneLine.slice(0, max - 1) + "…" : oneLine;
}

const RELATION_STYLE = {
  contains: { dash: null, label: "Contains" },
  mentions: { dash: null, label: "Mentions" },
  references: { dash: null, label: "References" },
  similar_to: { dash: [4, 3], label: "Similar To (embedding)" },
};

function buildConceptGraphData(graphInfo) {
  if (!graphInfo || !graphInfo.available) return { nodes: [], links: [] };
  const nodes = (graphInfo.nodes || []).map(n => ({
    id: n.id,
    kind: n.kind,
    label: n.label,
    doc: n.doc,
    community: n.community,
    color: communityColor(n.community),
    val: KIND_VAL[n.kind] || 15,
  }));
  const links = (graphInfo.edges || []).map(e => ({
    source: e.source,
    target: e.target,
    relation: e.relation,
    basis: e.basis,
  }));
  return { nodes, links };
}

function endpointId(nodeOrId) {
  return (nodeOrId && nodeOrId.id) || nodeOrId;
}

function mentioningSections(conceptId, conceptGraphData) {
  const nodeById = new Map(conceptGraphData.nodes.map(n => [n.id, n]));
  return conceptGraphData.links
    .filter(l => l.relation === "mentions" && endpointId(l.target) === conceptId)
    .map(l => nodeById.get(endpointId(l.source)))
    .filter(Boolean);
}

function sectionMentionsConcepts(sectionId, conceptGraphData) {
  const nodeById = new Map(conceptGraphData.nodes.map(n => [n.id, n]));
  return conceptGraphData.links
    .filter(l => l.relation === "mentions" && endpointId(l.source) === sectionId)
    .map(l => nodeById.get(endpointId(l.target)))
    .filter(Boolean);
}

function conceptBridgeCommunities(conceptId, conceptGraphData) {
  const nodeById = new Map(conceptGraphData.nodes.map(n => [n.id, n]));
  const communities = new Set();
  conceptGraphData.links.forEach(l => {
    if (l.relation !== "mentions" || endpointId(l.target) !== conceptId) return;
    const section = nodeById.get(endpointId(l.source));
    if (section && section.community !== null && section.community !== undefined) {
      communities.add(section.community);
    }
  });
  return communities;
}

function isDocumentIsolated(docId, conceptGraphData) {
  // Mirrors grapher.py's _isolated_documents: no `references` edge in
  // either direction, AND no concept mentioned by this document's own
  // sections is ALSO mentioned by a section of a DIFFERENT document.
  const { nodes, links } = conceptGraphData;
  const nodeById = new Map(nodes.map(n => [n.id, n]));

  const referencedDocs = new Set();
  links.forEach(l => {
    if (l.relation === "references") {
      referencedDocs.add(endpointId(l.source));
      referencedDocs.add(endpointId(l.target));
    }
  });
  if (referencedDocs.has(docId)) return false;

  const ownConcepts = new Set();
  links.forEach(l => {
    if (l.relation !== "mentions") return;
    const section = nodeById.get(endpointId(l.source));
    if (section && section.doc === docId) ownConcepts.add(endpointId(l.target));
  });

  for (const l of links) {
    if (l.relation !== "mentions" || !ownConcepts.has(endpointId(l.target))) continue;
    const section = nodeById.get(endpointId(l.source));
    if (section && section.doc && section.doc !== docId) return false;
  }
  return true;
}

function documentSectionCount(docId, conceptGraphData) {
  return conceptGraphData.nodes.filter(n => n.kind === "section" && n.doc === docId).length;
}

// ==========================================
// COMPONENTS
// ==========================================

function Stat({ label, value }) {
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3 shadow-sm flex-1 min-w-[120px] transition-colors">
      <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-lg font-bold text-slate-900 dark:text-slate-50 truncate" title={String(value)}>{value}</div>
    </div>
  );
}

function GraphLegend() {
  const fileTypes = ["md", "pdf", "csv", "py", "docx", "pptx", "xlsx", "html", "other"];
  return (
    <div className="tour-legend absolute bottom-6 left-6 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xl z-20 w-64 pointer-events-auto transition-colors">
      <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wide mb-3 flex items-center gap-2">
        <LayoutTemplate size={14} className="text-indigo-500 dark:text-indigo-400" />
        Map Legend
      </h4>
      <div className="space-y-3">
        <div>
          <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Node Colors (Source Type)</div>
          <div className="flex flex-wrap gap-2">
            {fileTypes.map(type => (
              <span key={type} className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-700 dark:text-slate-300">
                <span className="w-2.5 h-2.5 rounded-full shadow-sm" style={{ backgroundColor: palette(type).fill }}></span>
                {type}
              </span>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Edge Types</div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400">
              <div className="w-4 h-0.5 bg-slate-300 dark:bg-slate-600"></div> Document Parent
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400">
              <div className="w-4 h-0.5 bg-slate-400 dark:bg-slate-500"></div> Sequential Chunk
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400">
              <div className="w-4 h-0.5 bg-amber-500 border-dashed border-t-2"></div> Hybrid Search Path
            </div>
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-[10px] text-slate-500 dark:text-slate-400 leading-relaxed">
          <p><strong>Scroll</strong> to zoom. <strong>Drag</strong> to pan.</p>
          <p><strong>Click</strong> a node to highlight its connected network.</p>
        </div>
      </div>
    </div>
  );
}

function ConceptGraphLegend({ communities, relationVisibility, onToggleRelation }) {
  return (
    <div className="absolute bottom-6 left-6 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-xl z-20 w-64 pointer-events-auto transition-colors">
      <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wide mb-3 flex items-center gap-2">
        <Network size={14} className="text-indigo-500 dark:text-indigo-400" />
        Concept Graph Legend
      </h4>
      <div className="space-y-3">
        <div>
          <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Communities (node color)</div>
          <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto">
            {communities.length === 0 && (
              <span className="text-[11px] text-slate-400 dark:text-slate-500 italic">None.</span>
            )}
            {communities.map(c => (
              <span key={c.id} className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 max-w-full">
                <span className="w-2.5 h-2.5 rounded-full shadow-sm shrink-0" style={{ backgroundColor: communityColor(c.id) }}></span>
                <span className="truncate max-w-[150px]" title={c.label}>{c.label}</span>
              </span>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Edge relations (click to hide)</div>
          <div className="space-y-1.5">
            {Object.entries(RELATION_STYLE).map(([relation, style]) => (
              <label key={relation} className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={relationVisibility[relation] !== false}
                  onChange={() => onToggleRelation(relation)}
                  className="w-3 h-3 accent-indigo-600 shrink-0"
                />
                <span className={`w-4 h-0.5 shrink-0 ${style.dash ? "border-t-2 border-dashed border-slate-400 dark:border-slate-500" : "bg-slate-400 dark:bg-slate-500"}`}></span>
                {style.label}
              </label>
            ))}
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-[10px] text-slate-500 dark:text-slate-400 leading-relaxed">
          <p>Node size: document &gt; section &gt; concept. Concepts render as diamonds.</p>
        </div>
      </div>
    </div>
  );
}

// ==========================================
// MAIN APP COMPONENT
// ==========================================
export default function App() {
  const [chunks, setChunks] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const [baseGraphData, setBaseGraphData] = useState({ nodes: [], links: [] });
  const [selectedNodeId, setSelectedNodeId] = useState(null);

  const [viewMode, setViewMode] = useState("universe"); // "universe" | "concepts"
  const [graphInfo, setGraphInfo] = useState({ available: false, nodes: [], edges: [], communities: [] });
  const [selectedConceptId, setSelectedConceptId] = useState(null);
  const [relationVisibility, setRelationVisibility] = useState({
    contains: true, mentions: true, references: true, similar_to: true,
  });
  const conceptFgRef = useRef();

  const [query, setQuery] = useState("");
  const [searchHits, setSearchHits] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  
  const [neighbors, setNeighbors] = useState([]);
  const [loadingNeighbors, setLoadingNeighbors] = useState(false);
  
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('theme');
      if (saved) return saved === 'dark';
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  });

  const fgRef = useRef();
  const containerRef = useRef();
  const [dim, setDim] = useState({ width: 800, height: 600 });

  // Handle Dark Mode Side Effects
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [darkMode]);

  // 1. Initial Data Fetch
  useEffect(() => {
    async function loadData() {
      try {
        const data = await fetchJson("/api/chunks");
        const nextChunks = data.chunks || [];
        setChunks(nextChunks);
        setBaseGraphData(buildGraphData(nextChunks));
      } catch (error) {
        console.error("Failed to load corpus data", error);
      } finally {
        setLoading(false);
      }
      // Isolated from the chunk-universe fetch above: a missing/failed
      // graph.yml must never block or error the Universe view.
      try {
        const graphData = await fetchJson("/api/graph");
        setGraphInfo(graphData);
      } catch (error) {
        console.error("Failed to load concept graph", error);
        setGraphInfo({ available: false, nodes: [], edges: [], communities: [] });
      }
    }
    loadData();
  }, []);

  // Tour Initialization
  useEffect(() => {
    if (!loading && chunks.length > 0 && !sessionStorage.getItem('tourComplete')) {
      const tour = new Shepherd.Tour({
        useModalOverlay: true,
        defaultStepOptions: {
          classes: 'shadow-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-2 font-sans dark:text-slate-100',
          scrollTo: true,
          cancelIcon: { enabled: true }
        }
      });

      const btnBack = { text: 'Back', action: tour.back, classes: 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-300 px-3 py-1.5 text-sm font-medium mr-2' };
      const btnNext = { text: 'Next', action: tour.next, classes: 'bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-indigo-700 transition shadow-sm' };
      const btnFinish = { text: 'Finish', action: tour.complete, classes: 'bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-emerald-700 transition shadow-sm' };

      tour.addStep({
        id: 'welcome',
        title: 'Welcome to Agentpack Corpus Explorer',
        text: "This is your holistic universe view. Every dot is a chunk of text from your corpus. You can drag to pan and scroll to zoom.",
        attachTo: { element: '.tour-graph', on: 'center' },
        buttons: [btnNext]
      });

      tour.addStep({
        id: 'search',
        title: 'Search the Corpus',
        text: "Type a query to search the corpus. Matching chunks glow amber, and dashed lines connect the ranked results so you can inspect the returned set quickly.",
        attachTo: { element: '.tour-search', on: 'bottom' },
        buttons: [btnBack, btnNext]
      });

      tour.addStep({
        id: 'sidebar',
        title: 'Context Panel',
        text: "When you click a chunk or run a search, this panel updates to show you the raw content, metadata, and nearest semantic neighbors.",
        attachTo: { element: '.tour-sidebar', on: 'left' },
        buttons: [btnBack, btnNext]
      });

      tour.addStep({
        id: 'legend',
        title: 'Map Legend',
        text: "Use this legend to understand what the colors and edges mean. You're ready to explore!",
        attachTo: { element: '.tour-legend', on: 'top-start' },
        buttons: [btnBack, btnFinish]
      });

      tour.on('complete', () => sessionStorage.setItem('tourComplete', 'true'));
      tour.on('cancel', () => sessionStorage.setItem('tourComplete', 'true'));

      const timer = setTimeout(() => tour.start(), 800);
      return () => {
        clearTimeout(timer);
        if (tour.isActive()) tour.complete();
      };
    }
  }, [loading, chunks.length]);

  // 2. Resize Observer for Graph Container
  // Depends on `loading`: while loading, the early-return spinner is rendered and
  // containerRef is null, so the observer has nothing to attach to. Once loading
  // flips to false the graph container mounts and this effect re-runs, attaching
  // the observer (which fires immediately with the real container dimensions).
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      setDim({ width: entries[0].contentRect.width, height: entries[0].contentRect.height });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
    // viewMode is a dependency, not just loading: switching views swaps in a
    // DIFFERENT container div (same ref object, new DOM node), so the
    // observer must detach from the old one and re-attach to the new one.
  }, [loading, viewMode]);

  // 3. Search Handler
  const handleSearch = useCallback(async () => {
    if (!query.trim()) {
        setSearchHits([]);
        return;
    }
    setIsSearching(true);
    setSelectedNodeId(null);
    try {
      const res = await fetchJson("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 10 }),
      });
      setSearchHits(res.results || []);
      
      // Auto zoom to hits
      if (fgRef.current && res.results?.length > 0) {
          const hitIds = new Set(res.results.map(r => r.id));
          fgRef.current.zoomToFit(1000, 100, node => hitIds.has(node.id));
      }
    } catch (error) {
      console.error(error);
    } finally {
      setIsSearching(false);
    }
  }, [query]);

  // 4. Fetch Neighbors when a chunk is selected
  useEffect(() => {
    if (!selectedNodeId || selectedNodeId.startsWith("doc_")) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setNeighbors([]);
        return;
    }
    let cancelled = false;
    setLoadingNeighbors(true);
    fetchJson("/api/neighbors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chunk_id: selectedNodeId, top_k: 5 }),
    })
    .then((res) => {
      if (!cancelled) setNeighbors(res.neighbors || []);
    })
    .catch(() => {
      if (!cancelled) setNeighbors([]);
    })
    .finally(() => {
      if (!cancelled) setLoadingNeighbors(false);
    });
    return () => { cancelled = true; };
  }, [selectedNodeId]);

  // 5. Dynamic Graph Data (Incorporate Search Temp Links)
  const displayData = useMemo(() => {
      if (searchHits.length === 0) return baseGraphData;
      
      const nodes = [...baseGraphData.nodes];
      const links = [...baseGraphData.links];
      
      // Add temporary links to show ranked-result ordering in the current search set.
      for(let i=1; i<searchHits.length; i++) {
          links.push({
              source: searchHits[i-1].id,
              target: searchHits[i].id,
              isSearchTemp: true,
              color: "#f59e0b",
              width: 2
          });
      }
      return { nodes, links };
  }, [baseGraphData, searchHits]);

  // 5b. Concept Graph Data (derived from graph.yml, filtered by relation toggles)
  const conceptGraphData = useMemo(() => buildConceptGraphData(graphInfo), [graphInfo]);
  const displayConceptData = useMemo(() => ({
    nodes: conceptGraphData.nodes,
    links: conceptGraphData.links.filter(l => relationVisibility[l.relation] !== false),
  }), [conceptGraphData, relationVisibility]);

  // 5c. Concept Node Paint Logic -- community color, kind-based size/shape
  const paintConceptNode = useCallback((node, ctx, globalScale) => {
    const isSelected = selectedConceptId === node.id;
    const r = isSelected ? Math.sqrt(node.val) * 1.6 : Math.sqrt(node.val);

    ctx.beginPath();
    if (node.kind === "concept") {
      // Diamond distinguishes concepts from document/section circles at a
      // glance -- concepts are the one kind with no `doc` anchor of its own.
      ctx.moveTo(node.x, node.y - r);
      ctx.lineTo(node.x + r, node.y);
      ctx.lineTo(node.x, node.y + r);
      ctx.lineTo(node.x - r, node.y);
      ctx.closePath();
    } else {
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
    }
    ctx.fillStyle = node.color;
    ctx.fill();

    if (isSelected) {
      ctx.lineWidth = 1.5 / globalScale;
      ctx.strokeStyle = darkMode ? "#f8fafc" : "#0f172a";
      ctx.stroke();
    } else if (node.kind === "document") {
      ctx.lineWidth = 1 / globalScale;
      ctx.strokeStyle = darkMode ? "rgba(248,250,252,0.5)" : "rgba(15,23,42,0.4)";
      ctx.stroke();
    }

    const showLabel = node.kind === "document" || isSelected || globalScale > 2.5;
    if (showLabel) {
      const label = truncateLabel(node.label, node.kind === "document" ? 30 : 24);
      const fontSize = node.kind === "document" ? 15 / globalScale : 10 / globalScale;
      ctx.font = `600 ${fontSize}px Inter, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = darkMode ? "#f1f5f9" : "#334155";
      ctx.fillText(label, node.x, node.y + r + (4 / globalScale) + fontSize / 2);
    }
  }, [selectedConceptId, darkMode]);

  // 6. Node Paint Logic
  const paintNode = useCallback((node, ctx, globalScale) => {
      const isSelected = selectedNodeId === node.id;
      const isSearchHit = searchHits.some(hit => hit.id === node.id);
      
      // Calculate connected network logic for dimming
      let isDimmed = false;
      if (searchHits.length > 0 && !isSearchHit) {
          isDimmed = true;
      } else if (selectedNodeId && !isSelected) {
          // Check if it's an immediate neighbor
          const isNeighbor = baseGraphData.links.some(l => {
              const sId = l.source.id || l.source;
              const tId = l.target.id || l.target;
              return (sId === selectedNodeId && tId === node.id) || (tId === selectedNodeId && sId === node.id);
          });
          if (!isNeighbor) isDimmed = true;
      }

      // Base radius
      const r = isSelected || isSearchHit ? Math.sqrt(node.val) * 1.5 : Math.sqrt(node.val);

      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
      const dimFill = darkMode ? "rgba(51, 65, 85, 0.4)" : "rgba(203, 213, 225, 0.4)";
      ctx.fillStyle = isDimmed ? dimFill : node.color; 
      
      if (isSearchHit) {
          ctx.fillStyle = "#f59e0b"; // Amber for search
          ctx.lineWidth = 1.5 / globalScale;
          ctx.strokeStyle = darkMode ? "#fbbf24" : "#b45309";
          ctx.stroke();
      } else if (isSelected) {
          ctx.lineWidth = 1.5 / globalScale;
          ctx.strokeStyle = darkMode ? "#f8fafc" : "#0f172a";
          ctx.stroke();
      }

      ctx.fill();

      // Dynamic hover labels
      const showLabel = node.isDoc || isSelected || (globalScale > 2.5 && !isDimmed);
      if (showLabel) {
          const label = node.label || node.id;
          const fontSize = node.isDoc ? 16 / globalScale : 11 / globalScale;
          ctx.font = `600 ${fontSize}px Inter, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          const textDim = darkMode ? "rgba(148, 163, 184, 0.5)" : "rgba(148, 163, 184, 0.5)";
          const textDoc = darkMode ? "#f1f5f9" : "#334155";
          const textNorm = darkMode ? "#f8fafc" : "#0f172a";
          ctx.fillStyle = isDimmed ? textDim : (node.isDoc ? textDoc : textNorm);
          ctx.fillText(label, node.x, node.y + r + (4/globalScale) + fontSize/2);
      }
  }, [selectedNodeId, searchHits, baseGraphData, darkMode]);

  // Loading Screen
  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center bg-slate-50 dark:bg-slate-950 text-slate-700 dark:text-slate-300 font-sans transition-colors">
        <div className="flex items-center gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-5 py-4 rounded-xl shadow-sm font-medium">
            <RefreshCw className="animate-spin text-indigo-500" size={20} />
            Loading corpus universe...
        </div>
      </div>
    );
  }

  // Active Context Models
  const activeNode = baseGraphData.nodes.find(n => n.id === selectedNodeId);
  const activeChunk = activeNode?.chunk;

  return (
    <main className="h-screen w-screen bg-slate-50 dark:bg-slate-950 flex flex-col font-sans overflow-hidden text-slate-900 dark:text-slate-100 transition-colors">
      
      {/* HEADER */}
      <header className="flex-none px-6 py-4 flex flex-col md:flex-row md:items-center justify-between bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 z-10 shadow-sm gap-4 transition-colors">
        <div className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg text-white">
                <LayoutTemplate size={20} />
            </div>
            <div>
                <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white leading-tight">Agentpack Corpus Explorer</h1>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Corpus Relationship Map</p>
            </div>
        </div>
        
        {/* SEARCH BAR & THEME TOGGLE */}
        <div className="flex items-center gap-3 w-full md:w-auto">
            <div className="tour-search flex items-center bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg overflow-hidden shadow-sm focus-within:ring-2 ring-indigo-500 transition-all w-full md:w-96">
                <Search className="w-4 h-4 text-slate-400 ml-3 shrink-0" />
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Query context (e.g. 'auth logic')"
                    className="px-3 py-2 text-sm outline-none w-full text-slate-700 dark:text-slate-200 bg-transparent placeholder:text-slate-400"
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
                {query && (
                    <button onClick={() => { setQuery(""); setSearchHits([]); }} className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                        <X size={14} />
                    </button>
                )}
                <button onClick={handleSearch} className="bg-slate-900 dark:bg-indigo-600 hover:bg-indigo-600 dark:hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2 transition border-l border-slate-700 dark:border-indigo-500 shrink-0 flex items-center gap-2">
                    {isSearching ? <RefreshCw size={14} className="animate-spin" /> : "Search"}
                </button>
            </div>

            <button
                onClick={() => {
                    if (!graphInfo.available) return;
                    setSelectedConceptId(null);
                    setViewMode(viewMode === "universe" ? "concepts" : "universe");
                }}
                disabled={!graphInfo.available}
                title={graphInfo.available ? "Switch between the chunk universe and the concept graph" : "No graph.yml in this pack — run `agentpack graph <pack_dir>` to build one"}
                aria-label="Toggle universe/concepts view"
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium border transition ${
                    !graphInfo.available
                        ? "opacity-40 cursor-not-allowed bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 border-transparent"
                        : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 border-transparent dark:border-slate-700"
                }`}
            >
                <Network size={16} />
                {viewMode === "universe" ? "Concepts" : "Universe"}
            </button>

            <button
                onClick={() => setDarkMode(!darkMode)}
                className="p-2.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 border border-transparent dark:border-slate-700 transition"
                aria-label="Toggle theme"
            >
                {darkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>
        </div>
      </header>

      {/* WORKSPACE */}
      <div className="flex-1 flex p-4 gap-4 overflow-hidden relative">
      {viewMode === "universe" ? (
      <>
        {/* GRAPH AREA */}
        <div className="tour-graph flex-1 relative rounded-2xl overflow-hidden shadow-lg border border-slate-200 dark:border-slate-800 bg-[#f8fafc] dark:bg-[#020617] transition-colors" ref={containerRef}>
            <ForceGraph2D
                ref={fgRef}
                width={dim.width}
                height={dim.height}
                graphData={displayData}
                nodeCanvasObject={paintNode}
                nodeId="id"
                backgroundColor={darkMode ? "#020617" : "#f8fafc"}
                onNodeClick={(node) => {
                    setSelectedNodeId(node.id);
                    setSearchHits([]); // Clear search if user clicks a specific node
                    setQuery("");
                    fgRef.current.centerAt(node.x, node.y, 800);
                    fgRef.current.zoom(3.5, 800);
                }}
                onBackgroundClick={() => {
                    setSelectedNodeId(null);
                    if (searchHits.length > 0) fgRef.current.zoomToFit(800, 50);
                }}
                linkColor={link => {
                    if (link.isSearchTemp) return "#f59e0b";

                    // Highlight logic
                    if (selectedNodeId) {
                        const sId = link.source.id || link.source;
                        const tId = link.target.id || link.target;
                        if (sId === selectedNodeId || tId === selectedNodeId) {
                            return darkMode ? "#f8fafc" : "#0f172a"; // Dark strong line for active connection
                        }
                        return darkMode ? "rgba(51, 65, 85, 0.4)" : "rgba(203, 213, 225, 0.2)"; // Dim rest
                    }
                    if (searchHits.length > 0) return darkMode ? "rgba(51, 65, 85, 0.4)" : "rgba(203, 213, 225, 0.2)"; // Dim rest during search

                    if (link.isSequential) return darkMode ? "rgba(148, 163, 184, 0.3)" : "rgba(148, 163, 184, 0.45)";
                    return darkMode ? "rgba(148, 163, 184, 0.15)" : "rgba(148, 163, 184, 0.2)";
                }}
                linkWidth={link => {
                    if (link.isSearchTemp) return 3;
                    if (selectedNodeId) {
                        const sId = link.source.id || link.source;
                        const tId = link.target.id || link.target;
                        if (sId === selectedNodeId || tId === selectedNodeId) return 2;
                    }
                    return link.width;
                }}
                linkLineDash={link => link.isSearchTemp ? [4, 4] : null}
            />

            <GraphLegend />
        </div>

        {/* CONTEXT SIDEBAR */}
        <aside className="tour-sidebar w-[380px] md:w-[420px] bg-white dark:bg-slate-900 rounded-2xl flex flex-col overflow-hidden transition-all duration-300 shadow-xl border border-slate-200 dark:border-slate-800 shrink-0 z-20">
            {/* Header */}
            <div className="p-5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50">
                <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center justify-between">
                    {searchHits.length > 0 ? "Retrieval Results" : (activeNode ? "Context Panel" : "Overview")}
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${searchHits.length > 0 ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800" : (activeNode ? "bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800" : "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800")}`}>
                        {searchHits.length > 0 ? "Query" : (activeNode ? "Selected" : "Ready")}
                    </span>
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {searchHits.length > 0 ? `Showing top ${searchHits.length} chunks.` : (activeNode ? `Viewing details for ${activeNode.id}` : "Interact with the map or run a query.")}
                </p>
            </div>

            <div className="flex-1 overflow-y-auto p-5 relative">
                
                {/* STATE 1: DEFAULT (Stats) */}
                {!activeNode && searchHits.length === 0 && (
                    <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-3">
                            <Stat label="Total Files" value={new Set(chunks.map(c => getSourceName(c))).size} />
                            <Stat label="Total Chunks" value={chunks.length} />
                        </div>
                        <div className="bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800 rounded-xl p-4 text-indigo-900 dark:text-indigo-200">
                            <h4 className="font-bold text-sm mb-2 flex items-center gap-2">
                                <Info size={16} /> How to explore
                            </h4>
                            <ul className="text-xs space-y-2 opacity-80 list-disc pl-4">
                                <li><strong>Pan & Zoom</strong> to explore the document corpus.</li>
                                <li><strong>Click</strong> a chunk to reveal its contents and semantic relations.</li>
                                <li><strong>Search</strong> to query the corpus and trace the ranked result set.</li>
                            </ul>
                        </div>
                    </div>
                )}

                {/* STATE 2: SEARCH RESULTS */}
                {searchHits.length > 0 && (
                    <div className="space-y-3">
                        {searchHits.map((hit, index) => {
                            const chunk = chunks.find(c => c.id === hit.id);
                            const score = (hit.hybrid || hit.score || 0) * 100;
                            const title = getResultTitle(hit, chunk);
                            const source = hit.source_file_path || chunk?.source_file_path || getSourceName(chunk);
                            return (
                                <div key={hit.id} 
                                     className="p-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm cursor-pointer hover:border-amber-400 dark:hover:border-amber-500 hover:shadow-md transition"
                                     onClick={() => {
                                         setSelectedNodeId(hit.id);
                                         setSearchHits([]); // Transition into inspection mode
                                         setQuery("");
                                         const n = baseGraphData.nodes.find(n => n.id === hit.id);
                                         if(n) { fgRef.current.centerAt(n.x, n.y, 800); fgRef.current.zoom(3.5, 800); }
                                     }}>
                                    <div className="flex justify-between items-start mb-2">
                                        <h4 className="font-bold text-sm text-slate-900 dark:text-slate-100 flex items-center gap-2 truncate">
                                            <span className="w-5 h-5 rounded flex items-center justify-center bg-slate-900 dark:bg-slate-700 text-white text-[10px] shrink-0">{index+1}</span>
                                            <span className="truncate">{title}</span>
                                        </h4>
                                        <span className="bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-400 text-[10px] font-bold px-2 py-0.5 rounded shrink-0">{score.toFixed(1)}%</span>
                                    </div>
                                    <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate mb-2">{source || "Source unavailable"}</p>
                                    <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-3 leading-relaxed">{hit.content || chunk?.content || "Content unavailable."}</p>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* STATE 3: NODE INSPECTOR */}
                {activeNode && (
                    <div className="space-y-6">
                        {/* Stats */}
                        <div className="grid grid-cols-2 gap-3">
                            <Stat label="Tokens" value={activeChunk?.tokens || 0} />
                            <Stat label="Source Type" value={getFileType(activeNode.isDoc ? activeNode.id.replace('doc_', '') : getSourceName(activeChunk))} />
                        </div>

                        {!activeNode.isDoc && activeChunk && (
                            <div className="space-y-1">
                                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Chunk Title</div>
                                <div className="text-sm font-semibold text-slate-800 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 p-2 rounded-lg break-words">
                                    {getChunkTitle(activeChunk)}
                                </div>
                            </div>
                        )}
                        
                        <div className="space-y-1">
                            <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Source File</div>
                            <div className="text-sm font-semibold text-slate-800 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 p-2 rounded-lg break-all">
                                {activeNode.isDoc ? activeNode.id.replace('doc_', '') : (activeChunk?.source_file_path || getSourceName(activeChunk))}
                            </div>
                        </div>

                        {/* Content */}
                        {!activeNode.isDoc && activeChunk && (
                            <div>
                                <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wide mb-2 flex items-center gap-2">
                                    <FileText size={14} className="text-slate-400 dark:text-slate-500" />
                                    Raw Content
                                </h4>
                                <div className="bg-slate-900 dark:bg-black rounded-xl p-4 shadow-inner border border-slate-800 dark:border-slate-800/50">
                                    <p className="text-[13px] text-slate-300 font-mono leading-relaxed break-words whitespace-pre-wrap">{activeChunk.content}</p>
                                </div>
                            </div>
                        )}

                        {/* Semantic Neighbors */}
                        {!activeNode.isDoc && (
                            <div>
                                <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 uppercase tracking-wide mb-2 flex items-center gap-2">
                                    <LinkIcon size={14} className="text-indigo-500 dark:text-indigo-400" />
                                    Semantic Neighbors
                                </h4>
                                <div className="bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/50 rounded-xl p-3 shadow-sm space-y-2">
                                    {loadingNeighbors && <p className="text-xs text-slate-500 dark:text-slate-400 italic">Finding neighbors...</p>}
                                    {!loadingNeighbors && neighbors.length === 0 && <p className="text-xs text-slate-500 dark:text-slate-400 italic">No semantic links found.</p>}
                                    {!loadingNeighbors && neighbors.map(n => (
                                        <div key={n.id} 
                                             className="flex items-center gap-3 p-2 bg-white dark:bg-slate-800 rounded-lg border border-slate-100 dark:border-slate-700 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500 transition shadow-sm"
                                             onClick={() => {
                                                 setSelectedNodeId(n.id);
                                                 const node = baseGraphData.nodes.find(x => x.id === n.id);
                                                 if(node) { fgRef.current.centerAt(node.x, node.y, 800); fgRef.current.zoom(3.5, 800); }
                                             }}>
                                            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: palette(getFileType(n.source)).fill }}></div>
                                            <div className="min-w-0 flex-1">
                                                <div className="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">{n.title || n.id}</div>
                                                <div className="text-[10px] text-slate-500 dark:text-slate-400">Match: {(n.score * 100).toFixed(1)}%</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </aside>
      </>
      ) : (
      <>
        {/* CONCEPT GRAPH AREA */}
        <div className="flex-1 relative rounded-2xl overflow-hidden shadow-lg border border-slate-200 dark:border-slate-800 bg-[#f8fafc] dark:bg-[#020617] transition-colors" ref={containerRef}>
            <ForceGraph2D
                ref={conceptFgRef}
                width={dim.width}
                height={dim.height}
                graphData={displayConceptData}
                nodeCanvasObject={paintConceptNode}
                nodeId="id"
                backgroundColor={darkMode ? "#020617" : "#f8fafc"}
                onNodeClick={(node) => {
                    setSelectedConceptId(node.id);
                    conceptFgRef.current.centerAt(node.x, node.y, 800);
                    conceptFgRef.current.zoom(3.5, 800);
                }}
                onBackgroundClick={() => setSelectedConceptId(null)}
                linkColor={link => {
                    if (selectedConceptId) {
                        const sId = link.source.id || link.source;
                        const tId = link.target.id || link.target;
                        if (sId === selectedConceptId || tId === selectedConceptId) {
                            return darkMode ? "#f8fafc" : "#0f172a";
                        }
                        return darkMode ? "rgba(51, 65, 85, 0.3)" : "rgba(203, 213, 225, 0.3)";
                    }
                    return darkMode ? "rgba(148, 163, 184, 0.25)" : "rgba(148, 163, 184, 0.35)";
                }}
                linkWidth={link => {
                    if (selectedConceptId) {
                        const sId = link.source.id || link.source;
                        const tId = link.target.id || link.target;
                        if (sId === selectedConceptId || tId === selectedConceptId) return 2;
                    }
                    return 1;
                }}
                linkLineDash={link => RELATION_STYLE[link.relation]?.dash || null}
            />

            <ConceptGraphLegend
                communities={graphInfo.communities || []}
                relationVisibility={relationVisibility}
                onToggleRelation={(relation) => setRelationVisibility(prev => ({ ...prev, [relation]: prev[relation] === false ? true : false }))}
            />
        </div>

        {/* CONCEPT CONTEXT SIDEBAR */}
        <aside className="w-[380px] md:w-[420px] bg-white dark:bg-slate-900 rounded-2xl flex flex-col overflow-hidden transition-all duration-300 shadow-xl border border-slate-200 dark:border-slate-800 shrink-0 z-20">
            {(() => {
                const activeConceptNode = conceptGraphData.nodes.find(n => n.id === selectedConceptId);
                const communityLabel = (communityId) => (graphInfo.communities || []).find(c => c.id === communityId)?.label || "Unassigned";
                return (
                    <>
                        <div className="p-5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center justify-between">
                                {activeConceptNode ? "Node Detail" : "Communities"}
                                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800">
                                    {activeConceptNode ? activeConceptNode.kind : "Overview"}
                                </span>
                            </h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                {activeConceptNode ? "Click the background to deselect." : `${conceptGraphData.nodes.length} nodes, ${(graphInfo.communities || []).length} communities.`}
                            </p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 relative">
                            {!activeConceptNode && (
                                <div className="space-y-4">
                                    <div className="grid grid-cols-2 gap-3">
                                        <Stat label="Nodes" value={conceptGraphData.nodes.length} />
                                        <Stat label="Edges" value={conceptGraphData.links.length} />
                                    </div>
                                    <div>
                                        <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Communities</div>
                                        <div className="space-y-1.5">
                                            {(graphInfo.communities || []).map(c => (
                                                <div key={c.id} className="flex items-center justify-between p-2 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-700/50">
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: communityColor(c.id) }}></span>
                                                        <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 truncate" title={c.label}>{c.label}</span>
                                                    </div>
                                                    <span className="text-[10px] text-slate-500 dark:text-slate-400 shrink-0 ml-2">{c.size} member(s)</span>
                                                </div>
                                            ))}
                                            {(graphInfo.communities || []).length === 0 && (
                                                <p className="text-xs text-slate-500 dark:text-slate-400 italic">No communities.</p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {activeConceptNode && (
                                <div className="space-y-4">
                                    <div>
                                        <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Label</div>
                                        <div className="text-sm font-semibold text-slate-800 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 p-2 rounded-lg break-words">
                                            {activeConceptNode.label}
                                        </div>
                                    </div>

                                    <div>
                                        <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Community</div>
                                        <div className="text-sm text-slate-700 dark:text-slate-300 flex items-center gap-2">
                                            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: communityColor(activeConceptNode.community) }}></span>
                                            {communityLabel(activeConceptNode.community)}
                                        </div>
                                    </div>

                                    {activeConceptNode.kind === "document" && (
                                        <>
                                            <div>
                                                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Sections</div>
                                                <div className="text-sm text-slate-700 dark:text-slate-300">{documentSectionCount(activeConceptNode.id, conceptGraphData)}</div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Cross-Document Status</div>
                                                <div className="text-sm text-slate-700 dark:text-slate-300">
                                                    {isDocumentIsolated(activeConceptNode.id, conceptGraphData)
                                                        ? "Isolated — no references or shared concepts with any other document."
                                                        : "Connected — shares a reference or concept with another document."}
                                                </div>
                                            </div>
                                        </>
                                    )}

                                    {activeConceptNode.kind === "section" && (
                                        <>
                                            <div>
                                                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Document</div>
                                                <div className="text-sm text-slate-700 dark:text-slate-300 break-all">{activeConceptNode.doc || "—"}</div>
                                            </div>
                                            <div>
                                                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Concepts Mentioned</div>
                                                <div className="space-y-1.5">
                                                    {sectionMentionsConcepts(activeConceptNode.id, conceptGraphData).map(c => (
                                                        <div key={c.id}
                                                             className="text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-800/50 p-2 rounded-lg truncate cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500 border border-transparent transition"
                                                             onClick={() => setSelectedConceptId(c.id)}
                                                             title={c.label}>
                                                            {c.label}
                                                        </div>
                                                    ))}
                                                    {sectionMentionsConcepts(activeConceptNode.id, conceptGraphData).length === 0 && (
                                                        <p className="text-xs text-slate-500 dark:text-slate-400 italic">No promoted concepts.</p>
                                                    )}
                                                </div>
                                            </div>
                                        </>
                                    )}

                                    {activeConceptNode.kind === "concept" && (
                                        <>
                                            <div>
                                                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Bridge Status</div>
                                                {(() => {
                                                    const spanned = conceptBridgeCommunities(activeConceptNode.id, conceptGraphData);
                                                    return (
                                                        <div className="text-sm text-slate-700 dark:text-slate-300">
                                                            {spanned.size >= 2
                                                                ? `Bridge — mentioned by sections in ${spanned.size} different communities.`
                                                                : "Not a bridge — mentioning sections stay within one community."}
                                                        </div>
                                                    );
                                                })()}
                                            </div>
                                            <div>
                                                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Mentioned By</div>
                                                <div className="space-y-1.5">
                                                    {mentioningSections(activeConceptNode.id, conceptGraphData).map(s => (
                                                        <div key={s.id}
                                                             className="text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-800/50 p-2 rounded-lg truncate cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500 border border-transparent transition"
                                                             onClick={() => setSelectedConceptId(s.id)}
                                                             title={s.label}>
                                                            {s.label}
                                                        </div>
                                                    ))}
                                                    {mentioningSections(activeConceptNode.id, conceptGraphData).length === 0 && (
                                                        <p className="text-xs text-slate-500 dark:text-slate-400 italic">No mentioning sections.</p>
                                                    )}
                                                </div>
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </>
                );
            })()}
        </aside>
      </>
      )}
      </div>
    </main>
  );
}
