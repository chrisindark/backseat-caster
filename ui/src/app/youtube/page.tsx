"use client";

import { Navbar } from "@/components/Navbar";
import { YouTubePreviewModal } from "@/components/YouTubePreviewModal";
import { YouTubeVideoCard } from "@/components/YouTubeVideoCard";
import { checkBackendHealth, fetchVideo, fetchYouTubeChannelVideos, syncChannel } from "@/lib/api";
import { getQueryParam, setQueryParams } from "@/lib/modalHistory";
import { YouTubeChannelVideoItem } from "@/types/video";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Compass,
  HardDriveDownload,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Tv
} from "lucide-react";
import Link from "next/link";
import React, { useCallback, useEffect, useRef, useState } from "react";

export default function YouTubeChannelPage() {
  const [channelInput, setChannelInput] = useState<string>("@chrisindark");
  const [activeChannel, setActiveChannel] = useState<string>("@chrisindark");
  const [channelTitle, setChannelTitle] = useState<string>("chrisindark");
  const [channelUrl, setChannelUrl] = useState<string>("");

  const [videos, setVideos] = useState<YouTubeChannelVideoItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState<number>(20);
  const [searchFilter, setSearchFilter] = useState<string>("");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);

  const [previewVideo, setPreviewVideo] = useState<YouTubeChannelVideoItem | null>(null);
  const [syncFeedback, setSyncFeedback] = useState<{
    type: "success" | "error";
    message: string;
    newAdded?: number;
    skipped?: number;
  } | null>(null);

  const videosRef = useRef<YouTubeChannelVideoItem[]>(videos);
  useEffect(() => {
    videosRef.current = videos;
  }, [videos]);

  // Modal handlers with browser history tracking
  const openPreviewModal = useCallback((video: YouTubeChannelVideoItem) => {
    setPreviewVideo(video);
    setQueryParams({ preview: video.id });
  }, []);

  const closePreviewModal = useCallback(() => {
    setPreviewVideo(null);
    setQueryParams({ preview: null });
  }, []);

  const syncPreviewFromUrl = useCallback(
    async (currentVideos?: YouTubeChannelVideoItem[]) => {
      const previewId = getQueryParam("preview") || getQueryParam("videoId");
      if (!previewId) {
        setPreviewVideo(null);
        return;
      }

      const list = currentVideos || videosRef.current;
      const found = list.find((v) => v.id === previewId);
      if (found) {
        setPreviewVideo(found);
      } else {
        // Attempt to fetch from local database
        try {
          const dbVid = await fetchVideo(previewId);
          if (dbVid) {
            setPreviewVideo({
              id: dbVid.id,
              title: dbVid.title,
              description: dbVid.description,
              thumbnail_url: dbVid.thumbnail_url,
              duration: dbVid.duration,
              duration_formatted: dbVid.duration_formatted,
              channel_name: dbVid.channel_name,
              channel_id: dbVid.channel_id,
              channel_url: dbVid.channel_url,
              view_count: dbVid.view_count,
              published_at: dbVid.published_at,
              webpage_url: dbVid.webpage_url,
              is_in_database: true,
              is_downloaded: dbVid.is_downloaded,
              download_status: dbVid.download_status,
            });
            return;
          }
        } catch {
          // not found in local DB
        }

        // Fallback preview item so embedded player still functions
        setPreviewVideo({
          id: previewId,
          title: "YouTube Video Preview",
          description: null,
          thumbnail_url: `https://i.ytimg.com/vi/${previewId}/hqdefault.jpg`,
          duration: 0,
          duration_formatted: "00:00",
          channel_name: null,
          channel_id: null,
          channel_url: null,
          view_count: 0,
          published_at: null,
          webpage_url: `https://www.youtube.com/watch?v=${previewId}`,
          is_in_database: false,
          is_downloaded: false,
          download_status: "not_downloaded",
        });
      }
    },
    []
  );

  // Load initial channel videos
  const loadChannelVideos = useCallback(
    async (targetChannel: string, batchSize: number) => {
      setIsLoading(true);
      setSyncFeedback(null);
      setSelectedIds(new Set());
      try {
        const data = await fetchYouTubeChannelVideos({
          channel: targetChannel,
          limit: batchSize,
          offset: 0,
        });

        setVideos(data.videos);
        setChannelTitle(data.channel_title || targetChannel);
        setChannelUrl(data.channel_url || "");
        setActiveChannel(targetChannel);
        setHasMore(data.videos.length >= batchSize && data.has_more);
        return data.videos;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setSyncFeedback({
          type: "error",
          message: `Failed to load videos for ${targetChannel}: ${msg}`,
        });
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Initial check & load
  useEffect(() => {
    let mounted = true;
    async function init() {
      const healthy = await checkBackendHealth();
      if (!mounted) return;
      setBackendHealthy(healthy);
      if (healthy) {
        const loaded = await loadChannelVideos(channelInput, limit);
        if (mounted && loaded) {
          await syncPreviewFromUrl(loaded);
        }
      } else {
        setIsLoading(false);
      }
    }
    init();
    return () => {
      mounted = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Listen to browser Back/Forward navigation to sync modal states
  useEffect(() => {
    const onPopState = () => {
      syncPreviewFromUrl();
    };

    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
    };
  }, [syncPreviewFromUrl]);

  // Handle Fetch / Change Channel
  const handleFetchChannel = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!channelInput.trim()) return;
    loadChannelVideos(channelInput.trim(), limit);
  };

  // Handle Load More
  const handleLoadMore = async () => {
    if (isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    setSyncFeedback(null);
    try {
      const offset = videos.length;
      const data = await fetchYouTubeChannelVideos({
        channel: activeChannel,
        limit,
        offset,
      });

      if (!data.videos || data.videos.length === 0) {
        setHasMore(false);
      } else {
        // Deduplicate and append
        setVideos((prev) => {
          const existingIds = new Set(prev.map((v) => v.id));
          const fresh = data.videos.filter((v) => !existingIds.has(v.id));
          return [...prev, ...fresh];
        });
        setHasMore(data.videos.length >= limit && data.has_more);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setSyncFeedback({
        type: "error",
        message: `Failed to load more videos: ${msg}`,
      });
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Toggle selection for a single video
  const handleToggleSelect = (video: YouTubeChannelVideoItem) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(video.id)) {
        next.delete(video.id);
      } else {
        next.add(video.id);
      }
      return next;
    });
  };

  // Select all currently filtered/loaded videos
  const handleToggleSelectAll = () => {
    const visibleVideos = filteredVideos;
    const allSelected = visibleVideos.length > 0 && visibleVideos.every((v) => selectedIds.has(v.id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(visibleVideos.map((v) => v.id)));
    }
  };

  // Select only unsynced videos
  const handleSelectUnsynced = () => {
    const unsynced = videos.filter((v) => !v.is_in_database);
    setSelectedIds(new Set(unsynced.map((v) => v.id)));
  };

  // Clear all selections
  const handleClearSelection = () => {
    setSelectedIds(new Set());
  };

  // Perform Sync operation (either selected videos or all loaded videos)
  const handleSyncToLibrary = async (syncAll: boolean = false) => {
    const videosToSync =
      syncAll || selectedIds.size === 0
        ? videos
        : videos.filter((v) => selectedIds.has(v.id));

    if (videosToSync.length === 0) {
      alert("No videos available to sync.");
      return;
    }

    setIsSyncing(true);
    setSyncFeedback(null);
    try {
      const res = await syncChannel(activeChannel, limit, 0, videosToSync);

      setSyncFeedback({
        type: "success",
        message: res.message,
        newAdded: res.new_added,
        skipped: res.skipped,
      });

      // Update database status of synced videos locally
      const syncedIdSet = new Set(videosToSync.map((v) => v.id));
      setVideos((prev) =>
        prev.map((v) => (syncedIdSet.has(v.id) ? { ...v, is_in_database: true } : v))
      );

      // Clear selection after sync
      setSelectedIds(new Set());
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setSyncFeedback({
        type: "error",
        message: `Sync failed: ${msg}`,
      });
    } finally {
      setIsSyncing(false);
    }
  };

  // Filtered videos based on local search keyword
  const filteredVideos = videos.filter((v) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      v.title.toLowerCase().includes(q) ||
      (v.channel_name && v.channel_name.toLowerCase().includes(q))
    );
  });

  const inLibraryCount = videos.filter((v) => v.is_in_database).length;
  const unsyncedCount = videos.length - inLibraryCount;
  const isAllSelected =
    filteredVideos.length > 0 && filteredVideos.every((v) => selectedIds.has(v.id));

  return (
    <div className="min-h-screen bg-[#090a0f] flex flex-col">
      {/* Top Navigation */}
      <Navbar
        channelInput={channelInput}
        onChannelInputChange={setChannelInput}
        backendHealthy={backendHealthy}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6">
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
              onClick={() => checkBackendHealth().then(setBackendHealthy)}
              className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-xs font-semibold rounded-lg border border-amber-500/40 cursor-pointer"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Sync feedback notification banner */}
        {syncFeedback && (
          <div
            className={`mb-6 p-4 rounded-2xl border text-sm flex items-center justify-between gap-4 shadow-lg ${
              syncFeedback.type === "success"
                ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-200"
                : "bg-rose-950/40 border-rose-500/40 text-rose-200"
            }`}
          >
            <div className="flex items-center gap-3">
              {syncFeedback.type === "success" ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              ) : (
                <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
              )}
              <div>
                <p className="font-semibold">{syncFeedback.message}</p>
                {syncFeedback.type === "success" && (
                  <p className="text-xs text-emerald-300/80 mt-0.5">
                    Videos added to the catalog are ready for download and highlight rendering in Clip Studio.
                  </p>
                )}
              </div>
            </div>
            {syncFeedback.type === "success" && (
              <Link
                href="/"
                className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-500 text-black hover:bg-emerald-400 font-bold text-xs rounded-lg transition-colors shrink-0 shadow-md"
              >
                <span>View in Library</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            )}
          </div>
        )}

        {/* Header & Channel Control Panel */}
        <section
          aria-label="Channel Controls"
          className="bg-[#12141c]/90 border border-white/10 rounded-2xl p-5 shadow-xl backdrop-blur-md"
        >
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            {/* Channel info & URL input */}
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  <Compass className="w-3.5 h-3.5" />
                  <span>Channel Live Explorer</span>
                </span>
                <span className="text-xs text-slate-400">
                  Selective sync pipeline — avoid catalog overload
                </span>
              </div>

              <form onSubmit={handleFetchChannel} className="flex items-center gap-2 max-w-lg">
                <div className="relative flex-1">
                  <Tv className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    value={channelInput}
                    onChange={(e) => setChannelInput(e.target.value)}
                    placeholder="Enter @channel handle or URL"
                    className="w-full pl-9 pr-3 py-2 bg-slate-900 border border-white/10 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isLoading}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-white/10 transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                >
                  {isLoading ? "Fetching..." : "Fetch Channel"}
                </button>
              </form>
            </div>

            {/* Pagination settings & filter */}
            <div className="flex flex-wrap items-center gap-3">
              {/* Batch size selector */}
              <div className="flex items-center gap-2 bg-slate-900 border border-white/10 rounded-xl px-3 py-1.5 text-xs text-slate-300">
                <span>Load batch size:</span>
                <select
                  value={limit}
                  onChange={(e) => {
                    const newLimit = Number(e.target.value);
                    setLimit(newLimit);
                    loadChannelVideos(activeChannel, newLimit);
                  }}
                  className="bg-transparent font-bold text-white focus:outline-none cursor-pointer"
                >
                  <option value={10} className="bg-slate-900 text-white">
                    10 videos
                  </option>
                  <option value={20} className="bg-slate-900 text-white">
                    20 videos (default)
                  </option>
                  <option value={30} className="bg-slate-900 text-white">
                    30 videos
                  </option>
                  <option value={50} className="bg-slate-900 text-white">
                    50 videos
                  </option>
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400 pointer-events-none -ml-1" />
              </div>

              {/* Local search within loaded */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  placeholder="Filter loaded..."
                  className="w-40 pl-8 pr-3 py-1.5 bg-slate-900 border border-white/10 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
                />
              </div>
            </div>
          </div>

          {/* Stats Bar & Channel Summary */}
          <div className="mt-4 pt-4 border-t border-white/5 flex flex-wrap items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-4">
              <span className="text-slate-400">
                Channel:{" "}
                <span className="text-white font-bold">{channelTitle}</span>
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-slate-400">
                Loaded on page:{" "}
                <span className="text-white font-semibold">{videos.length} videos</span>
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-emerald-400 font-medium">
                {inLibraryCount} in library
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-slate-300">
                {unsyncedCount} unsynced
              </span>
            </div>

            {channelUrl && (
              <a
                href={channelUrl}
                target="_blank"
                rel="noreferrer"
                className="text-rose-400 hover:text-rose-300 font-medium flex items-center gap-1"
              >
                <span>View Channel on YouTube</span>
                <ArrowRight className="w-3 h-3" />
              </a>
            )}
          </div>
        </section>

        {/* Action & Sync Controls Bar */}
        <section
          aria-label="Sync Action Bar"
          className="mt-6 p-4 bg-[#12141c]/95 border border-white/10 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-4 sticky top-16 z-30 shadow-2xl backdrop-blur-xl"
        >
          {/* Selection controls */}
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={handleToggleSelectAll}
              disabled={filteredVideos.length === 0}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer flex items-center gap-1.5 ${
                isAllSelected
                  ? "bg-rose-600 text-white border-rose-500"
                  : "bg-slate-900 hover:bg-slate-800 text-slate-300 border-white/10"
              }`}
            >
              <Check className="w-3.5 h-3.5" />
              <span>{isAllSelected ? "Deselect All" : "Select All Loaded"}</span>
            </button>

            <button
              onClick={handleSelectUnsynced}
              disabled={unsyncedCount === 0}
              className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-slate-300 text-xs font-semibold rounded-lg border border-white/10 transition-colors cursor-pointer"
            >
              Select Unsynced ({unsyncedCount})
            </button>

            {selectedIds.size > 0 && (
              <button
                onClick={handleClearSelection}
                className="px-2.5 py-1.5 text-xs text-slate-400 hover:text-rose-400 transition-colors cursor-pointer"
              >
                Clear ({selectedIds.size})
              </button>
            )}
          </div>

          {/* Sync Buttons */}
          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
            <div className="text-xs text-slate-400 mr-1 hidden sm:block">
              {selectedIds.size > 0 ? (
                <span className="text-rose-300 font-medium">
                  {selectedIds.size} of {videos.length} selected
                </span>
              ) : (
                <span>All {videos.length} loaded videos</span>
              )}
            </div>

            {selectedIds.size > 0 ? (
              <>
                <button
                  onClick={() => handleSyncToLibrary(false)}
                  disabled={isSyncing}
                  className="flex items-center gap-2 px-5 py-2 bg-rose-600 hover:bg-rose-500 disabled:bg-rose-800 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-900/40 transition-all cursor-pointer whitespace-nowrap active:scale-95"
                >
                  <HardDriveDownload className={`w-4 h-4 ${isSyncing ? "animate-bounce" : ""}`} />
                  <span>
                    {isSyncing
                      ? "Syncing Selected..."
                      : `Sync Selected (${selectedIds.size}) to Library`}
                  </span>
                </button>

                <button
                  onClick={() => handleSyncToLibrary(true)}
                  disabled={isSyncing}
                  className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl border border-white/10 transition-colors cursor-pointer whitespace-nowrap"
                  title="Add all loaded videos to library"
                >
                  <span>Sync All ({videos.length})</span>
                </button>
              </>
            ) : (
              <button
                onClick={() => handleSyncToLibrary(true)}
                disabled={isSyncing || videos.length === 0}
                className="flex items-center gap-2 px-5 py-2 bg-rose-600 hover:bg-rose-500 disabled:bg-slate-800 disabled:text-slate-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-900/40 transition-all cursor-pointer whitespace-nowrap active:scale-95"
              >
                <RefreshCw className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`} />
                <span>
                  {isSyncing
                    ? "Syncing Loaded Videos..."
                    : `Sync Channel (${videos.length} Loaded Videos)`}
                </span>
              </button>
            )}
          </div>
        </section>

        {/* Video Grid Section */}
        <section className="mt-6" aria-label="YouTube Channel Videos">
          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6 py-8">
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
          ) : filteredVideos.length > 0 ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                {filteredVideos.map((video, idx) => (
                  <YouTubeVideoCard
                    key={video.id}
                    video={video}
                    index={idx}
                    isSelected={selectedIds.has(video.id)}
                    onToggleSelect={handleToggleSelect}
                    onPreview={openPreviewModal}
                  />
                ))}
              </div>

              {/* Load More Button Section */}
              <div className="mt-10 mb-8 flex flex-col items-center justify-center gap-3">
                {hasMore ? (
                  <button
                    onClick={handleLoadMore}
                    disabled={isLoadingMore}
                    className="flex items-center gap-2 px-6 py-3 bg-[#181b26] hover:bg-rose-600 border border-white/10 hover:border-rose-500 text-white text-sm font-bold rounded-2xl shadow-xl transition-all cursor-pointer active:scale-95 disabled:opacity-60"
                  >
                    {isLoadingMore ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin text-rose-400" />
                        <span>Loading next {limit} videos from YouTube...</span>
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4 text-rose-500 group-hover:text-white" />
                        <span>Load More ({limit} more videos)</span>
                      </>
                    )}
                  </button>
                ) : (
                  <div className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900/60 border border-white/5 text-slate-400 text-xs">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>All videos currently available from this channel have been loaded.</span>
                  </div>
                )}

                <p className="text-xs text-slate-500">
                  Showing {videos.length} videos according to page size setting ({limit} per batch)
                </p>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 px-4 text-center bg-[#12141c]/50 border border-white/5 rounded-2xl my-4">
              <div className="w-16 h-16 rounded-2xl bg-rose-950/40 border border-rose-500/20 flex items-center justify-center mb-4">
                <Tv className="w-8 h-8 text-rose-400" />
              </div>
              <h2 className="text-lg font-bold text-white mb-1">No YouTube videos found</h2>
              <p className="text-sm text-slate-400 max-w-md mb-6">
                {searchFilter
                  ? `No loaded videos match "${searchFilter}". Try clearing your filter keyword.`
                  : `Could not retrieve videos from channel "${activeChannel}". Please check the channel handle and ensure it has public videos.`}
              </p>
              <button
                onClick={() => loadChannelVideos(activeChannel, limit)}
                disabled={isLoading}
                className="flex items-center gap-2 px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-sm font-semibold rounded-lg shadow-lg shadow-rose-900/40 cursor-pointer"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                <span>Retry Fetching Channel</span>
              </button>
            </div>
          )}
        </section>
      </main>

      {/* Video Preview Modal with embedded YouTube Player */}
      <YouTubePreviewModal
        video={previewVideo}
        isSelected={previewVideo ? selectedIds.has(previewVideo.id) : false}
        onToggleSelect={handleToggleSelect}
        onClose={closePreviewModal}
      />
    </div>
  );
}
