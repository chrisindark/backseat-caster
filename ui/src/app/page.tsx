"use client";

import { Navbar } from "@/components/Navbar";
import { OBSUploadDropzone } from "@/components/OBSUploadDropzone";
import { Pagination } from "@/components/Pagination";
import { StatsBar } from "@/components/StatsBar";
import { VideoCard } from "@/components/VideoCard";
import {
  batchTagVideos,
  checkBackendHealth,
  deleteVideoDownload,
  downloadVideo,
  fetchVideos,
  syncChannel,
  updateVideo,
} from "@/lib/api";
import { getQueryParam, setQueryParams } from "@/lib/modalHistory";
import { VideoItem } from "@/types/video";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Compass,
  EyeOff,
  Film,
  RefreshCw,
  Sparkles,
  Tv,
  X,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useRef, useState } from "react";

function HomeContent() {
  const searchParams = useSearchParams();
  const initialFilter = searchParams.get("filter") || "all";
  const initialPage = parseInt(searchParams.get("page") || "1", 10) || 1;
  const initialSearch = searchParams.get("q") || "";

  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [channelTitle, setChannelTitle] = useState<string>("");
  const [channelInput, setChannelInput] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>(initialSearch);
  const [activeFilter, setActiveFilter] = useState<string>(initialFilter);
  const [page, setPage] = useState<number>(initialPage);
  const [limit, setLimit] = useState<number>(20);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);
  const [downloadingIds, setDownloadingIds] = useState<Set<string>>(new Set());
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const loadIdRef = useRef(0);
  const [downloadedTotal, setDownloadedTotal] = useState<number>(0);
  const [cataloguedTotal, setCataloguedTotal] = useState<number>(0);
  const [downloadingTotal, setDownloadingTotal] = useState<number>(0);
  const [highlightsMinedTotal, setHighlightsMinedTotal] = useState<number>(0);
  const [uploadedTotal, setUploadedTotal] = useState<number>(0);
  const [cleanupReadyTotal, setCleanupReadyTotal] = useState<number>(0);
  const [ignoredTotal, setIgnoredTotal] = useState<number>(0);

  // Selection & Batch Tagging
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isTagModalOpen, setIsTagModalOpen] = useState<boolean>(false);
  const [selectedReasonPreset, setSelectedReasonPreset] = useState<string>("Too old or low quality");
  const [customReasonText, setCustomReasonText] = useState<string>("");
  const [isBatchUpdating, setIsBatchUpdating] = useState<boolean>(false);

  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
      if (syncTimeoutRef.current) clearTimeout(syncTimeoutRef.current);
    };
  }, []);

  const refreshCounts = useCallback(async () => {
    try {
      const [dlData, allData, ingData, hlData, upData, clData, ignData] = await Promise.all([
        fetchVideos({ status: "downloaded", limit: 1 }),
        fetchVideos({ status: "all", limit: 1 }),
        fetchVideos({ status: "downloading", limit: 1 }),
        fetchVideos({ status: "highlights_mined", limit: 1 }),
        fetchVideos({ status: "uploaded", limit: 1 }),
        fetchVideos({ status: "cleanup_ready", limit: 1 }),
        fetchVideos({ status: "ignored", limit: 1 }),
      ]);
      setDownloadedTotal(dlData.total);
      setCataloguedTotal(allData.total);
      setDownloadingTotal(ingData.total);
      setHighlightsMinedTotal(hlData.total);
      setUploadedTotal(upData.total);
      setCleanupReadyTotal(clData.total);
      setIgnoredTotal(ignData.total);
    } catch {
      // ignore
    }
  }, []);

  // Load videos from backend
  const loadVideos = useCallback(
    async (
      currentPage = page,
      currentLimit = limit,
      currentFilter = activeFilter,
      currentSearch = searchQuery
    ) => {
      const loadId = ++loadIdRef.current;
      setIsLoading(true);
      setLoadError(null);
      try {
        const data = await fetchVideos({
          page: currentPage,
          limit: currentLimit,
          status: currentFilter,
          search: currentSearch,
        });

        if (loadId !== loadIdRef.current) return data;
        setVideos(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        if (data.channel_title) {
          setChannelTitle(data.channel_title);
        }

        if (currentFilter === "all" && !currentSearch) {
          setCataloguedTotal(data.total);
        } else if (currentFilter === "downloaded" && !currentSearch) {
          setDownloadedTotal(data.total);
        } else if (currentFilter === "downloading" && !currentSearch) {
          setDownloadingTotal(data.total);
        } else if (currentFilter === "highlights_mined" && !currentSearch) {
          setHighlightsMinedTotal(data.total);
        } else if (currentFilter === "uploaded" && !currentSearch) {
          setUploadedTotal(data.total);
        } else if (currentFilter === "cleanup_ready" && !currentSearch) {
          setCleanupReadyTotal(data.total);
        } else if (currentFilter === "ignored" && !currentSearch) {
          setIgnoredTotal(data.total);
        }

        // Check if any video is actively downloading
        const inProgress = new Set<string>();
        data.items.forEach((v) => {
          if (v.download_status === "downloading" || v.download_status === "pending") {
            inProgress.add(v.id);
          }
        });
        setDownloadingIds(inProgress);

        return data;
      } catch (err) {
        console.error("Error loading videos:", err);
        if (loadId === loadIdRef.current) {
          setLoadError(err instanceof Error ? err.message : "Failed to load videos");
        }
      } finally {
        if (loadId === loadIdRef.current) setIsLoading(false);
      }
    },
    [page, limit, activeFilter, searchQuery]
  );

  // Handle Sync channel action
  const handleSync = useCallback(async () => {
    setIsSyncing(true);
    setSyncMessage(null);
    try {
      const offset = limit * (page - 1);
      const res = await syncChannel(channelInput || "", limit, offset);
      setSyncMessage(res.message);
      if (res.channel_title) {
        setChannelTitle(res.channel_title);
      }
      await loadVideos(1, limit, activeFilter, searchQuery);
      setPage(1);
      refreshCounts();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setSyncMessage(`Sync failed: ${message}`);
    } finally {
      setIsSyncing(false);
      if (syncTimeoutRef.current) clearTimeout(syncTimeoutRef.current);
      syncTimeoutRef.current = setTimeout(() => setSyncMessage(null), 5000);
    }
  }, [channelInput, limit, page, activeFilter, searchQuery, loadVideos, refreshCounts]);

  // Initial check & load library videos (runs once on mount)
  useEffect(() => {
    let mounted = true;

    async function init() {
      const healthy = await checkBackendHealth();
      if (!mounted) return;
      setBackendHealthy(healthy);

      if (healthy) {
        await loadVideos(initialPage, limit, initialFilter, initialSearch);
        refreshCounts();
      } else {
        setIsLoading(false);
      }
    }

    init();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle popstate for browser Back/Forward tab and page navigation
  useEffect(() => {
    const handlePopState = () => {
      const f = getQueryParam("filter") || "all";
      const p = parseInt(getQueryParam("page") || "1", 10) || 1;
      const q = getQueryParam("q") || "";
      setActiveFilter(f);
      setPage(p);
      setSearchQuery(q);
      loadVideos(p, limit, f, q);
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [limit, loadVideos]);

  // Polling loop when videos are downloading (pauses when tab is hidden)
  useEffect(() => {
    const hasActiveDownloads =
      downloadingTotal > 0 ||
      downloadingIds.size > 0 ||
      videos.some(
        (v) =>
          v.download_status === "downloading" ||
          v.download_status === "pending"
      );

    if (!hasActiveDownloads) return;

    let interval: NodeJS.Timeout | null = null;

    const tick = () => {
      loadVideos(page, limit, activeFilter, searchQuery);
      refreshCounts();
    };

    const startPolling = () => {
      if (!interval && document.visibilityState === "visible") {
        interval = setInterval(tick, 2500);
      }
    };

    const stopPolling = () => {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        tick();
        startPolling();
      } else {
        stopPolling();
      }
    };

    startPolling();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [
    downloadingTotal,
    downloadingIds,
    videos,
    page,
    limit,
    activeFilter,
    searchQuery,
    loadVideos,
    refreshCounts,
  ]);

  // Handle video download trigger
  const handleDownload = async (videoId: string) => {
    setDownloadingIds((prev) => new Set(prev).add(videoId));
    try {
      await downloadVideo(videoId);
      await loadVideos(page, limit, activeFilter, searchQuery);
      refreshCounts();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      alert(`Could not start download: ${message}`);
      setDownloadingIds((prev) => {
        const next = new Set(prev);
        next.delete(videoId);
        return next;
      });
    }
  };

  // Handle deleting downloaded file
  const handleDeleteDownload = async (videoId: string) => {
    if (!confirm("Are you sure you want to delete this downloaded video file?")) return;
    try {
      await deleteVideoDownload(videoId);
      await loadVideos(page, limit, activeFilter, searchQuery);
      refreshCounts();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      alert(`Could not delete: ${message}`);
    }
  };

  // Selection Handlers
  const handleToggleSelect = useCallback((videoId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(videoId)) next.delete(videoId);
      else next.add(videoId);
      return next;
    });
  }, []);

  const handleSelectAllOnPage = useCallback(() => {
    setSelectedIds(new Set(videos.map((v) => v.id)));
  }, [videos]);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  // Batch Tag Videos
  const handleBatchTag = useCallback(
    async (isIgnored: boolean, reason?: string) => {
      if (selectedIds.size === 0) return;
      setIsBatchUpdating(true);
      try {
        const ids = Array.from(selectedIds);
        const res = await batchTagVideos(ids, isIgnored, reason);
        setSyncMessage(res.message);
        setSelectedIds(new Set());
        setIsTagModalOpen(false);
        await loadVideos(page, limit, activeFilter, searchQuery);
        await refreshCounts();
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        setLoadError(message);
      } finally {
        setIsBatchUpdating(false);
      }
    },
    [selectedIds, page, limit, activeFilter, searchQuery, loadVideos, refreshCounts]
  );

  // Single video quick toggle ignore
  const handleToggleIgnoreSingle = useCallback(
    async (video: VideoItem) => {
      try {
        const targetIgnored = !video.is_ignored;
        const reason = targetIgnored ? "Too old or low quality" : undefined;
        await updateVideo(video.id, {
          is_ignored: targetIgnored,
          ignore_reason: reason,
        });
        setSyncMessage(
          targetIgnored
            ? `Tagged "${video.title.slice(0, 40)}..." as Do Not Process`
            : `Marked "${video.title.slice(0, 40)}..." as active`
        );
        await loadVideos(page, limit, activeFilter, searchQuery);
        await refreshCounts();
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        setLoadError(message);
      }
    },
    [page, limit, activeFilter, searchQuery, loadVideos, refreshCounts]
  );

  // Filter change
  const handleFilterChange = (filter: string) => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
      searchTimeoutRef.current = null;
    }
    setActiveFilter(filter);
    setPage(1);
    setQueryParams(
      { filter: filter === "all" ? null : filter, page: null },
      { replace: true }
    );
    loadVideos(1, limit, filter, searchQuery);
  };

  // Search change with 300ms debounce
  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
    setPage(1);
    setQueryParams(
      { q: query.trim() ? query.trim() : null, page: null },
      { replace: true }
    );
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      loadVideos(1, limit, activeFilter, query);
    }, 300);
  };

  // Page change
  const handlePageChange = (newPage: number) => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
      searchTimeoutRef.current = null;
    }
    setPage(newPage);
    setQueryParams(
      { page: newPage <= 1 ? null : String(newPage) },
      { replace: true }
    );
    loadVideos(newPage, limit, activeFilter, searchQuery);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleUploadSuccess = useCallback(async () => {
    await loadVideos(1, limit, activeFilter, searchQuery);
    refreshCounts();
  }, [limit, activeFilter, searchQuery, loadVideos, refreshCounts]);

  return (
    <div className="min-h-screen bg-[#090a0f] flex flex-col">
      {/* Top Navigation */}
      <Navbar
        channelInput={channelInput}
        onChannelInputChange={setChannelInput}
        onSync={handleSync}
        isSyncing={isSyncing}
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        backendHealthy={backendHealthy}
      />

      <main className="flex-1 w-full max-w-[1280px] xl:max-w-[1440px] 2xl:max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Offline Warning Banner */}
        {!backendHealthy && (
          <div className="mb-6 p-4 rounded-xl bg-amber-950/40 border border-amber-500/30 text-amber-200 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-sm">
              <AlertCircle className="w-5 h-5 text-amber-400 shrink-0" />
              <div>
                <span className="font-bold">FastAPI backend is not reachable.</span> Start the server in another terminal:
                <code className="ml-2 px-2 py-0.5 bg-black/50 rounded text-amber-300 font-mono text-xs">
                  uv run uvicorn app.main:app --reload
                </code>
              </div>
            </div>
            <button
              onClick={async () => {
                await checkBackendHealth().then(setBackendHealthy);
                setLoadError(null);
                await loadVideos();
                await refreshCounts();
              }}
              className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-xs font-semibold rounded-lg border border-amber-500/40 cursor-pointer"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Sync message banner */}
        {syncMessage && (
          <div className="mb-6 p-3.5 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-200 text-sm flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{syncMessage}</span>
          </div>
        )}

        {/* Load error banner */}
        {loadError && (
          <div className="mb-6 p-4 rounded-xl bg-red-950/40 border border-red-500/30 text-red-200 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-sm">
              <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
              <div>
                <span className="font-bold">Error loading videos:</span> {loadError}
              </div>
            </div>
            <button
              onClick={() => {
                setLoadError(null);
                loadVideos();
                refreshCounts();
              }}
              className="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-xs font-semibold rounded-lg border border-red-500/40 cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}

        {/* OBS & Local Video Drag-and-Drop Ingestion */}
        <OBSUploadDropzone onUploadSuccess={handleUploadSuccess} />

        {/* Channel and Filter Header */}
        <StatsBar
          channelTitle={channelTitle}
          totalVideos={cataloguedTotal || total}
          downloadedCount={downloadedTotal}
          downloadingCount={Math.max(downloadingTotal, downloadingIds.size)}
          highlightsMinedCount={highlightsMinedTotal}
          uploadedCount={uploadedTotal}
          cleanupReadyCount={cleanupReadyTotal}
          ignoredCount={ignoredTotal}
          activeFilter={activeFilter}
          onFilterChange={handleFilterChange}
        />

        {/* Video Grid Section */}
        <section className="mt-6 relative" aria-label="YouTube Gameplay Videos">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-lg font-bold text-white flex items-center gap-2">
              <Film className="w-5 h-5 text-rose-500" />
              <span>
                {activeFilter === "downloaded"
                  ? "Downloaded Local VODs"
                  : activeFilter === "downloading"
                  ? "Currently Downloading Videos"
                  : activeFilter === "highlights_mined"
                  ? "Videos with Mined Highlights"
                  : activeFilter === "uploaded"
                  ? "Videos with Published YouTube Shorts"
                  : activeFilter === "cleanup_ready"
                  ? "Videos Ready for Disk Cleanup"
                  : activeFilter === "not_downloaded"
                  ? "Videos Ready to Download"
                  : activeFilter === "ignored"
                  ? "Videos Tagged as Do Not Process (Ignored)"
                  : "Channel Gameplay Videos"}
              </span>
              <span className="text-xs font-normal text-slate-400 ml-1">
                ({total} items)
              </span>
            </h1>

            {/* Selection Quick Info if any selected */}
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-rose-300 font-semibold bg-rose-950/40 border border-rose-500/30 px-2.5 py-1 rounded-lg">
                  {selectedIds.size} selected
                </span>
                <button
                  type="button"
                  onClick={handleClearSelection}
                  className="text-xs text-slate-400 hover:text-white underline cursor-pointer"
                >
                  Clear
                </button>
              </div>
            )}
          </div>

          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 sm:gap-5 py-12">
              {Array.from({ length: 8 }).map((_, idx) => (
                <div
                  key={idx}
                  className="bg-[#12141c] border border-white/5 rounded-2xl overflow-hidden animate-pulse flex flex-col"
                >
                  <div className="aspect-video bg-slate-800/60 w-full" />
                  <div className="p-4 flex flex-col gap-3">
                    <div className="h-4 bg-slate-800/80 rounded w-5/6" />
                    <div className="h-3 bg-slate-800/40 rounded w-1/2" />
                    <div className="h-8 bg-slate-800/30 rounded mt-2" />
                  </div>
                </div>
              ))}
            </div>
          ) : videos.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 sm:gap-5">
              {videos.map((video, idx) => (
                <VideoCard
                  key={video.id}
                  video={video}
                  index={idx}
                  onDownload={handleDownload}
                  onDeleteDownload={handleDeleteDownload}
                  isDownloadingThis={downloadingIds.has(video.id)}
                  isSelected={selectedIds.has(video.id)}
                  onToggleSelect={handleToggleSelect}
                  onToggleIgnore={handleToggleIgnoreSingle}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 px-4 text-center bg-[#12141c]/50 border border-white/5 rounded-2xl my-4">
              <div className="w-16 h-16 rounded-2xl bg-rose-950/40 border border-rose-500/20 flex items-center justify-center mb-4">
                <Tv className="w-8 h-8 text-rose-400" />
              </div>
              <h2 className="text-lg font-bold text-white mb-1">No videos found</h2>
              <p className="text-sm text-slate-400 max-w-md mb-6">
                {searchQuery
                  ? `No videos match "${searchQuery}". Try a different keyword.`
                  : activeFilter === "downloaded"
                  ? "No videos have been downloaded locally yet. Download a video from the library to start clipping."
                  : activeFilter === "downloading"
                  ? "No videos are currently being downloaded."
                  : activeFilter === "not_downloaded"
                  ? "All catalogued videos are already downloaded locally."
                  : activeFilter === "ignored"
                  ? "No videos are tagged as Do Not Process. You can select videos in your library and tag them to keep them in your archive without processing clips."
                  : "No videos catalogued yet. Sync your YouTube channel to browse and download gameplay VODs."}
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <Link
                  href="/setup"
                  className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-sm font-bold rounded-lg shadow-lg shadow-rose-900/40 transition-all cursor-pointer"
                >
                  <Sparkles className="w-4 h-4 text-amber-300" />
                  <span>Try a Demo (Instant 3 Shorts)</span>
                </Link>
                <Link
                  href="/youtube"
                  className="flex items-center gap-2 px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold rounded-lg border border-white/10 transition-all cursor-pointer"
                >
                  <Compass className="w-4 h-4" />
                  <span>Browse YouTube Channel</span>
                </Link>
                <button
                  onClick={handleSync}
                  disabled={isSyncing}
                  className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-slate-300 text-sm font-semibold rounded-lg border border-white/5 transition-all cursor-pointer"
                >
                  <RefreshCw className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`} />
                  <span>{isSyncing ? "Syncing Videos..." : "Sync Default Channel"}</span>
                </button>
              </div>
            </div>
          )}

          {/* Floating Batch Action Toolbar */}
          {selectedIds.size > 0 && (
            <div className="fixed bottom-4 sm:bottom-6 left-1/2 -translate-x-1/2 z-40 w-[calc(100%-2rem)] max-w-[640px] bg-[#161a29]/95 backdrop-blur-md border border-rose-500/40 rounded-2xl px-4 sm:px-5 py-3 shadow-2xl shadow-black/80 flex flex-wrap items-center justify-center gap-3.5 animate-in fade-in slide-in-from-bottom-4 duration-200">
              <div className="flex items-center gap-2 text-sm font-bold text-white">
                <span className="w-6 h-6 rounded-full bg-rose-600 text-xs flex items-center justify-center font-mono">
                  {selectedIds.size}
                </span>
                <span className="hidden sm:inline">selected</span>
              </div>

              <div className="h-4 w-px bg-white/15" />

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsTagModalOpen(true)}
                  disabled={isBatchUpdating}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 text-xs font-bold rounded-lg cursor-pointer transition-all disabled:opacity-50"
                >
                  <EyeOff className="w-3.5 h-3.5 text-amber-400" />
                  <span>Tag: Do Not Process</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleBatchTag(false)}
                  disabled={isBatchUpdating}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-white/10 text-xs font-semibold rounded-lg cursor-pointer transition-all disabled:opacity-50"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Mark Active</span>
                </button>

                <button
                  type="button"
                  onClick={handleSelectAllOnPage}
                  className="hidden md:inline-block px-2.5 py-1.5 text-xs text-slate-400 hover:text-white transition-colors cursor-pointer"
                >
                  Select Page ({videos.length})
                </button>

                <button
                  type="button"
                  onClick={handleClearSelection}
                  className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
                  title="Deselect all"
                  aria-label="Deselect all"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* Reason Selection Modal when tagging as Do Not Process */}
          {isTagModalOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
              <div className="bg-[#12141c] border border-amber-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-white/10">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400">
                      <EyeOff className="w-4 h-4" />
                    </div>
                    <div>
                      <h2 className="text-sm font-bold text-white">Tag as Do Not Process</h2>
                      <p className="text-xs text-slate-400">
                        {selectedIds.size} video{selectedIds.size === 1 ? "" : "s"} selected
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsTagModalOpen(false)}
                    className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <p className="text-xs text-slate-300 leading-relaxed">
                  Tagged videos will be tracked in your library archive, but skipped from
                  downloads and AI highlight clipping.
                </p>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300">
                    Select a reason (optional):
                  </label>
                  <div className="space-y-1.5">
                    {[
                      "Too old or obsolete VOD",
                      "Low gameplay action / not worth clipping",
                      "Wrong game or off-topic recording",
                      "Bad audio or technical issues",
                      "Other (custom reason)",
                    ].map((reason) => (
                      <button
                        key={reason}
                        type="button"
                        onClick={() => setSelectedReasonPreset(reason)}
                        className={`w-full text-left px-3 py-2 rounded-xl text-xs flex items-center justify-between transition-all cursor-pointer ${
                          selectedReasonPreset === reason
                            ? "bg-amber-500/20 border border-amber-500/40 text-amber-200 font-semibold"
                            : "bg-slate-900/60 border border-white/5 text-slate-300 hover:bg-slate-800"
                        }`}
                      >
                        <span>{reason}</span>
                        {selectedReasonPreset === reason && (
                          <Check className="w-3.5 h-3.5 text-amber-400" />
                        )}
                      </button>
                    ))}
                  </div>

                  {selectedReasonPreset === "Other (custom reason)" && (
                    <input
                      type="text"
                      value={customReasonText}
                      onChange={(e) => setCustomReasonText(e.target.value)}
                      placeholder="e.g. Unusable resolution, practice match..."
                      className="mt-2 w-full px-3 py-2 bg-slate-900 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                  )}
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-white/10">
                  <button
                    type="button"
                    onClick={() => setIsTagModalOpen(false)}
                    className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white rounded-xl cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const reason =
                        selectedReasonPreset === "Other (custom reason)"
                          ? customReasonText.trim() || "Do not process"
                          : selectedReasonPreset;
                      handleBatchTag(true, reason);
                    }}
                    disabled={isBatchUpdating}
                    className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-amber-950/40 cursor-pointer transition-all active:scale-95 disabled:opacity-50"
                  >
                    {isBatchUpdating
                      ? "Tagging..."
                      : `Tag ${selectedIds.size} Video${selectedIds.size === 1 ? "" : "s"}`}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Pagination */}
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            totalItems={total}
            itemsPerPage={limit}
            onPageChange={handlePageChange}
            onItemsPerPageChange={(newLimit) => {
              setLimit(newLimit);
              setPage(1);
              loadVideos(1, newLimit, activeFilter, searchQuery);
            }}
          />
        </section>
      </main>
    </div>
  );
}

export default function HomePage() {
  return (
    <React.Suspense fallback={<div className="min-h-screen bg-[#090a0f]" />}>
      <HomeContent />
    </React.Suspense>
  );
}