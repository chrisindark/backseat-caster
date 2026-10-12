"use client";

import { ClipStudioModal } from "@/components/ClipStudioModal";
import { Navbar } from "@/components/Navbar";
import { Pagination } from "@/components/Pagination";
import { StatsBar } from "@/components/StatsBar";
import { VideoCard } from "@/components/VideoCard";
import { VideoModal } from "@/components/VideoModal";
import {
  checkBackendHealth,
  deleteVideoDownload,
  downloadVideo,
  fetchVideo,
  fetchVideos,
  syncChannel,
} from "@/lib/api";
import { getQueryParam, setQueryParams } from "@/lib/modalHistory";
import { VideoItem } from "@/types/video";
import {
  AlertCircle,
  CheckCircle2,
  Compass,
  Film,
  RefreshCw,
  Tv,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

export default function HomePage() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [channelTitle, setChannelTitle] = useState<string>("chrisindark");
  const [channelInput, setChannelInput] = useState<string>("@chrisindark");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [page, setPage] = useState<number>(1);
  const [limit, setLimit] = useState<number>(20);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);
  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  const [clipStudioVideo, setClipStudioVideo] = useState<VideoItem | null>(null);
  const [clipInitialStartTime, setClipInitialStartTime] = useState<number>(0);
  const [downloadingIds, setDownloadingIds] = useState<Set<string>>(new Set());
  const [syncMessage, setSyncMessage] = useState<string | null>(null);


  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Load videos from backend
  const loadVideos = useCallback(
    async (currentPage = page, currentLimit = limit, currentFilter = activeFilter, currentSearch = searchQuery) => {
      console.log("loadVideos");
      try {
        const data = await fetchVideos({
          page: currentPage,
          limit: currentLimit,
          status: currentFilter,
          search: currentSearch,
        });

        setVideos(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        if (data.channel_title) {
          setChannelTitle(data.channel_title);
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
      } finally {
        setIsLoading(false);
      }
    },
    [page, limit, activeFilter, searchQuery]
  );

  // Handle Sync channel action
  const handleSync = useCallback(async () => {
    console.log("handleSync");
    setIsSyncing(true);
    setSyncMessage(null);
    try {
      const offset = limit * (page - 1);
      const res = await syncChannel(channelInput || "@chrisindark", limit, offset);
      setSyncMessage(res.message);
      if (res.channel_title) {
        setChannelTitle(res.channel_title);
      }
      await loadVideos(1, limit, activeFilter, searchQuery);
      setPage(1);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setSyncMessage(`Sync failed: ${message}`);
    } finally {
      setIsSyncing(false);
      setTimeout(() => setSyncMessage(null), 5000);
    }
  }, [channelInput, limit, page, activeFilter, searchQuery, loadVideos]);

  // Modal handlers with browser history tracking
  const openVideoModal = useCallback((video: VideoItem) => {
    setSelectedVideo(video);
    setClipStudioVideo(null);
    setQueryParams({ video: video.id, clip: null, start: null });
  }, []);

  const closeVideoModal = useCallback(() => {
    setSelectedVideo(null);
    setQueryParams({ video: null });
  }, []);

  const openClipStudioModal = useCallback((video: VideoItem, initialStartTime = 0) => {
    setClipStudioVideo(video);
    setClipInitialStartTime(initialStartTime);
    setSelectedVideo(null);
    setQueryParams({
      clip: video.id,
      start: initialStartTime > 0 ? String(initialStartTime) : null,
      video: null,
    });
  }, []);

  const closeClipStudioModal = useCallback(() => {
    setClipStudioVideo(null);
    setQueryParams({ clip: null, start: null });
  }, []);

  const videosRef = useRef<VideoItem[]>(videos);
  useEffect(() => {
    videosRef.current = videos;
  }, [videos]);

  // Sync modal state from browser URL (e.g. on reload or Back/Forward navigation)
  const syncModalsFromUrl = useCallback(
    async (itemsList?: VideoItem[]) => {
      const clipId = getQueryParam("clip") || getQueryParam("clipVideoId");
      const startParam = getQueryParam("start") || getQueryParam("startTime");
      const videoId = getQueryParam("video") || getQueryParam("videoId");

      if (clipId) {
        const parsedStart = startParam ? parseFloat(startParam) || 0 : 0;
        setClipInitialStartTime(parsedStart);
        setSelectedVideo(null);

        const list = itemsList || videosRef.current;
        const found = list.find((v) => v.id === clipId);
        if (found) {
          setClipStudioVideo(found);
        } else {
          try {
            const fetched = await fetchVideo(clipId);
            setClipStudioVideo(fetched);
          } catch (err) {
            console.warn("Could not find video for clip modal:", err);
            setQueryParams({ clip: null, start: null }, { replace: true });
          }
        }
      } else if (videoId) {
        setClipStudioVideo(null);
        const list = itemsList || videosRef.current;
        const found = list.find((v) => v.id === videoId);
        if (found) {
          setSelectedVideo(found);
        } else {
          try {
            const fetched = await fetchVideo(videoId);
            setSelectedVideo(fetched);
          } catch (err) {
            console.warn("Could not find video for detail modal:", err);
            setQueryParams({ video: null }, { replace: true });
          }
        }
      } else {
        setSelectedVideo(null);
        setClipStudioVideo(null);
      }
    },
    []
  );

  // Initial check & load library videos, then restore any active modal from URL
  useEffect(() => {
    console.log("useEffect initial");
    let mounted = true;

    async function init() {
      if (!mounted) {
        return;
      }

      const healthy = await checkBackendHealth();
      if (!mounted) return;
      setBackendHealthy(healthy);

      if (healthy) {
        const data = await loadVideos(1, limit, "all", "");
        if (!mounted) return;
        if (data?.items) {
          await syncModalsFromUrl(data.items);
        } else {
          await syncModalsFromUrl();
        }
      } else {
        setIsLoading(false);
      }
    }

    init();
    return () => {
      mounted = false;
    };
  }, [limit]); // eslint-disable-line react-hooks/exhaustive-deps

  // Listen to browser Back/Forward navigation to sync modal states
  useEffect(() => {
    const onPopState = () => {
      syncModalsFromUrl();
    };

    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
    };
  }, [syncModalsFromUrl]);


  // Polling loop when videos are downloading
  useEffect(() => {
    console.log("useEffect polling");
    const hasActiveDownloads =
      downloadingIds.size > 0 ||
      videos.some(
        (v) =>
          v.download_status === "downloading" ||
          v.download_status === "pending"
      );

    if (hasActiveDownloads) {
      pollingRef.current = setInterval(() => {
        loadVideos();
      }, 2500);
    } else {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [downloadingIds, videos, loadVideos]);

  // Handle video download trigger
  const handleDownload = async (videoId: string) => {
    console.log("handleDownload");
    setDownloadingIds((prev) => new Set(prev).add(videoId));
    try {
      await downloadVideo(videoId);
      // await loadVideos();
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
      if (selectedVideo?.id === videoId) {
        setSelectedVideo(null);
      }
      await loadVideos();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      alert(`Could not delete: ${message}`);
    }
  };

  // Filter change
  const handleFilterChange = (filter: string) => {
    setActiveFilter(filter);
    setPage(1);
    loadVideos(1, limit, filter, searchQuery);
  };

  // Search change
  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
    setPage(1);
    loadVideos(1, limit, activeFilter, query);
  };

  // Page change
  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    loadVideos(newPage, limit, activeFilter, searchQuery);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const downloadedCount = videos.filter((v) => v.is_downloaded).length;

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

        {/* Sync message banner */}
        {syncMessage && (
          <div className="mb-6 p-3.5 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-200 text-sm flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{syncMessage}</span>
          </div>
        )}

        {/* Channel and Filter Header */}
        <StatsBar
          channelTitle={channelTitle}
          totalVideos={total}
          downloadedCount={downloadedCount}
          activeFilter={activeFilter}
          onFilterChange={handleFilterChange}
        />

        {/* Video Grid Section */}
        <section className="mt-6" aria-label="YouTube Gameplay Videos">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-lg font-bold text-white flex items-center gap-2">
              <Film className="w-5 h-5 text-rose-500" />
              <span>Channel Gameplay Videos</span>
              <span className="text-xs font-normal text-slate-400 ml-1">
                ({total} items)
              </span>
            </h1>
          </div>

          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6 py-12">
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
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {videos.map((video, idx) => (
                <VideoCard
                  key={video.id}
                  video={video}
                  index={idx}
                  onSelect={openVideoModal}
                  onDownload={handleDownload}
                  onDeleteDownload={handleDeleteDownload}
                  isDownloadingThis={downloadingIds.has(video.id)}
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
                  : activeFilter !== "all"
                  ? `No videos match the "${activeFilter}" filter.`
                  : "No videos catalogued yet. Sync your YouTube channel to browse and download gameplay VODs."}
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <Link
                  href="/youtube"
                  className="flex items-center gap-2 px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-sm font-semibold rounded-lg shadow-lg shadow-rose-900/40 transition-all cursor-pointer"
                >
                  <Compass className="w-4 h-4" />
                  <span>Browse YouTube Channel</span>
                </Link>
                <button
                  onClick={handleSync}
                  disabled={isSyncing}
                  className="flex items-center gap-2 px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold rounded-lg border border-white/10 transition-all cursor-pointer"
                >
                  <RefreshCw className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`} />
                  <span>{isSyncing ? "Syncing Videos..." : "Sync Default Channel"}</span>
                </button>
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

      {/* Video Detail Modal */}
      <VideoModal
        video={selectedVideo}
        onClose={closeVideoModal}
        onDownload={handleDownload}
        onDeleteDownload={handleDeleteDownload}
        onOpenClipStudio={(vid, startTime) => {
          openClipStudioModal(vid, startTime ?? 0);
        }}
        isDownloading={selectedVideo ? downloadingIds.has(selectedVideo.id) : false}
      />

      {/* Phase 1 Clip Studio & Comparison Modal */}
      <ClipStudioModal
        video={clipStudioVideo}
        initialStartTime={clipInitialStartTime}
        onClose={closeClipStudioModal}
      />
    </div>
  );

}
