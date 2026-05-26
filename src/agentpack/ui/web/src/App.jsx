import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search, RefreshCw, X, Info, LayoutTemplate, Link as LinkIcon, FileText, Moon, Sun } from "lucide-react";
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
  return "other";
}

function palette(type) {
  if (type === "md") return { fill: "#0ea5e9", soft: "#e0f2fe", border: "#7dd3fc", text: "#075985" }; // sky
  if (type === "pdf") return { fill: "#f59e0b", soft: "#fef3c7", border: "#fde68a", text: "#92400e" }; // amber
  if (type === "csv") return { fill: "#10b981", soft: "#d1fae5", border: "#a7f3d0", text: "#065f46" }; // emerald
  if (type === "py") return { fill: "#f43f5e", soft: "#fce7f3", border: "#fbcfe8", text: "#9d174d" }; // rose
  return { fill: "#64748b", soft: "#f1f5f9", border: "#e2e8f0", text: "#334155" }; // slate
}

function getSourceName(chunk) {
  return chunk?.citation?.source_path || chunk?.source || "unknown";
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
  const fileTypes = ["md", "pdf", "csv", "py", "other"];
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

// ==========================================
// MAIN APP COMPONENT
// ==========================================
export default function App() {
  const [chunks, setChunks] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const [baseGraphData, setBaseGraphData] = useState({ nodes: [], links: [] });
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  
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
        text: "Type any query here to search the vector database. We'll highlight matching chunks and draw hybrid trajectory paths between them.",
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
  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      setDim({ width: entries[0].contentRect.width, height: entries[0].contentRect.height });
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

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
      
      // Add temp trajectory links
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
                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Holistic Universe View</p>
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
                                <li><strong>Search</strong> to query the vector database and highlight matching topics.</li>
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
                                            <span className="truncate">{hit.id}</span>
                                        </h4>
                                        <span className="bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-400 text-[10px] font-bold px-2 py-0.5 rounded shrink-0">{score.toFixed(1)}%</span>
                                    </div>
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
                        
                        <div className="space-y-1">
                            <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Source File</div>
                            <div className="text-sm font-semibold text-slate-800 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 p-2 rounded-lg break-all">
                                {activeNode.isDoc ? activeNode.id.replace('doc_', '') : getSourceName(activeChunk)}
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
                                                <div className="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">{n.id}</div>
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
      </div>
    </main>
  );
}
