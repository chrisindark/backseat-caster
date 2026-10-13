"use client";

import { Navbar } from "@/components/Navbar";
import {
  checkBackendHealth,
  deleteVideoDownload,
  downloadVideo,
  fetchRenders,
  fetchVideo,
  getDownloadedVideoStreamUrl,
  getVideoStatus,
} from "@/lib/api";
import { RenderManifest, VideoItem } from "@/types/video";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  Download,
  Eye,
  ExternalLink,
  Film,
  HardDrive,
  Loader2,
  Play,
  Scissors,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import React, { useCallback, useEffect, useRef, useState } from "react";

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "N/A";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${mb.toFixed(1)} MB`;
}

function formatSeconds(sec: number): string {
  if (isNaN(sec) || sec < 0) return "0:00";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  if (h > 0) {
    return `${h}:${m < 10 ? "0" : ""}${m}:${s < 10 ? "0" : ""}${s}`;
  }
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

function parseSeconds(val: string): number {
  if (!val) return 0;
  if (val.includes(":")) {
    const parts = val.split(":").map((p) => parseFloat(p) || 0);
    if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    }
  }
  return parseFloat(val) || 0;
}

function VideoDetailContent() {
  const params = useParams();
  const videoId = typeof params?.id === "string" ? params.id : Array.isArray(params?.id) ? params.id[0] : "";

  const [video, setVideo] = useState<VideoItem | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);

  // Playhead & clip start time
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [clipStartTime, setClipStartTime] = useState<number>(0);
  const [startTimeInput, setStartTimeInput] = useState<string>("0:00");
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Downloads & renders
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [renders, setRenders] = useState<RenderManifest[]>([]);

  // Reload video after user actions
  const reloadVideo = useCallback(async () => {
    if (!videoId) return;
    try {
      const data = await fetchVideo(videoId);
      setVideo(data);
      setIsDownloading(
        data.download_status === "downloading" || data.download_status === "pending"
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    }
  }, [videoId]);

  // Initial data load via effects with async callback settling
  useEffect(() => {
    let mounted = true;
    checkBackendHealth().then((h) => {
      if (mounted) setBackendHealthy(h);
    });

    if (!videoId) return;

    fetchVideo(videoId)
      .then((data) => {
        if (!mounted) return;
        setVideo(data);
        setIsDownloading(
          data.download_status === "downloading" || data.download_status === "pending"
        );
        setIsLoading(false);
      })
      .catch((err) => {
        if (!mounted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setIsLoading(false);
      });

    fetchRenders({ video_id: videoId })
      .then((data) => {
        if (!mounted) return;
        setRenders(data.items || []);
      })
      .catch((err) => {
        console.warn("Could not load renders:", err);
      });

    return () => {
      mounted = false;
    };
  }, [videoId]);

  // Polling when download is in progress
  useEffect(() => {
    if (!isDownloading || !videoId) return;

    const interval = setInterval(async () => {
      try {
        const status = await getVideoStatus(videoId);
        setVideo((prev) =>
          prev
            ? {
                ...prev,
                is_downloaded: status.is_downloaded,
                download_status: status.download_status as VideoItem["download_status"],
                download_progress: status.download_progress,
                local_file_path: status.local_file_path,
                file_size_bytes: status.file_size_bytes,
                error_message: status.error_message,
              }
            : null
        );

        if (status.download_status === "completed" || status.download_status === "failed") {
          setIsDownloading(false);
        }
      } catch {
        // ignore polling error
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [isDownloading, videoId]);

  const handleDownload = async () => {
    if (!videoId) return;
    setIsDownloading(true);
    try {
      await downloadVideo(videoId);
      await reloadVideo();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Could not start download: ${msg}`);
      setIsDownloading(false);
    }
  };

  const handleDelete = async () => {
    if (!videoId) return;
    if (!confirm("Are you sure you want to delete this downloaded video file?")) return;
    try {
      await deleteVideoDownload(videoId);
      await reloadVideo();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Could not delete: ${msg}`);
    }
  };

  const handleSetCurrentAsStart = () => {
    const sec = Math.floor(currentTime);
    setClipStartTime(sec);
    setStartTimeInput(formatSeconds(sec));
  };

  const handleManualTimeChange = (val: string) => {
    setStartTimeInput(val);
    const parsed = parseSeconds(val);
    setClipStartTime(parsed);
  };

  const handleSeekToStart = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = clipStartTime;
    }
  };

  const handleNudge = (delta: number) => {
    const maxDuration = video?.duration || 999999;
    const next = Math.max(0, Math.min(maxDuration, clipStartTime + delta));
    setClipStartTime(next);
    setStartTimeInput(formatSeconds(next));
    if (videoRef.current) {
      videoRef.current.currentTime = next;
    }
  };

  const isDownloaded = video?.is_downloaded;
  const isProcessing =
    video?.download_status === "downloading" ||
    video?.download_status === "pending" ||
    isDownloading;

  return (
    <div className="min-h-screen bg-[#090a0f] flex flex-col">
      <Navbar backendHealthy={backendHealthy} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center justify-between mb-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors group cursor-pointer"
          >
            <div className="p-1.5 rounded-lg bg-slate-900 border border-white/5 group-hover:border-rose-500/40 group-hover:bg-rose-950/30 transition-colors">
              <ArrowLeft className="w-4 h-4 text-slate-400 group-hover:text-rose-400" />
            </div>
            <span>Back to Library</span>
          </Link>

          <div className="flex items-center gap-2">
            {video?.webpage_url && (
              <a
                href={video.webpage_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold rounded-lg border border-white/10 transition-colors"
              >
                <span>YouTube</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
            {isDownloaded && (
              <Link
                href={`/studio/${videoId}${clipStartTime > 0 ? `?start=${clipStartTime}` : ""}`}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg shadow-md shadow-rose-950/40 transition-all cursor-pointer"
              >
                <Scissors className="w-3.5 h-3.5" />
                <span>Open in Clip Studio</span>
              </Link>
            )}
          </div>
        </div>

        {/* Loading state */}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <Loader2 className="w-10 h-10 text-rose-500 animate-spin mb-4" />
            <h2 className="text-base font-semibold text-white">Loading video details...</h2>
            <p className="text-xs text-slate-400 mt-1">Fetching metadata and stream state</p>
          </div>
        ) : error || !video ? (
          <div className="p-8 rounded-2xl bg-[#12141c] border border-white/10 text-center max-w-lg mx-auto my-12">
            <AlertCircle className="w-12 h-12 text-rose-500 mx-auto mb-3" />
            <h2 className="text-lg font-bold text-white mb-2">Video Not Found</h2>
            <p className="text-xs text-slate-400 mb-6">{error || `No video found with ID "${videoId}".`}</p>
            <Link
              href="/"
              className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-md"
            >
              Return to Library
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Left Column: Player & Clip Cue Selector */}
            <div className="lg:col-span-8 flex flex-col gap-6">
              {/* Media Player Container */}
              <div className="relative aspect-video w-full bg-black rounded-2xl overflow-hidden border border-white/10 shadow-2xl">
                {isDownloaded ? (
                  <video
                    ref={videoRef}
                    src={getDownloadedVideoStreamUrl(video.id)}
                    poster={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
                    controls
                    playsInline
                    preload="metadata"
                    onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                    className="w-full h-full object-contain bg-black"
                  />
                ) : (
                  <div className="relative w-full h-full bg-slate-950 overflow-hidden flex items-center justify-center">
                    <img
                      src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
                      alt={video.title}
                      className="w-full h-full object-cover opacity-60"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-black/60 flex flex-col items-center justify-center p-6 text-center">
                      <div className="w-16 h-16 rounded-full bg-rose-600/90 text-white flex items-center justify-center shadow-lg shadow-rose-950/60 mb-4">
                        <Play className="w-7 h-7 ml-1 fill-current" />
                      </div>
                      <h3 className="text-lg font-bold text-white mb-2 max-w-md">{video.title}</h3>
                      <p className="text-xs text-slate-300 max-w-sm mb-6">
                        Download this gameplay VOD to enable frame-accurate clipping, vertical cropping, and multi-format rendering.
                      </p>
                      {isProcessing ? (
                        <div className="flex items-center gap-2 px-4 py-2 bg-amber-500/20 border border-amber-500/40 text-amber-300 rounded-xl text-xs font-semibold">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Downloading VOD... ({Math.round(video.download_progress)}%)</span>
                        </div>
                      ) : (
                        <button
                          onClick={handleDownload}
                          className="flex items-center gap-2 px-6 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-900/40 cursor-pointer transition-transform active:scale-95"
                        >
                          <Download className="w-4 h-4" />
                          <span>Download Gameplay VOD</span>
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Clip Start Selector (if downloaded) */}
              {isDownloaded && (
                <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl flex flex-col gap-4 shadow-xl">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/5">
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl bg-rose-600/20 border border-rose-500/30 text-rose-400">
                        <Scissors className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="text-sm font-bold text-white flex items-center gap-2">
                          <span>Set Clip Cue Start Point</span>
                          <span className="font-mono text-rose-300 text-xs font-bold bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/30">
                            {formatSeconds(clipStartTime)} ({clipStartTime}s)
                          </span>
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5">
                          Playhead is at: <span className="font-mono text-slate-200">{formatSeconds(currentTime)}</span> • Scrub in player or set timestamp
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleSetCurrentAsStart}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-sm cursor-pointer transition-all active:scale-95"
                      >
                        <Clock className="w-3.5 h-3.5" />
                        <span>Set to Current Playhead</span>
                      </button>
                      <button
                        type="button"
                        onClick={handleSeekToStart}
                        className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg border border-white/10 cursor-pointer transition-colors"
                      >
                        Seek
                      </button>
                    </div>
                  </div>

                  {/* Nudge & Fine-tuning */}
                  <div className="flex flex-wrap items-center justify-between gap-4 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400">Start Time:</span>
                      <input
                        type="text"
                        value={startTimeInput}
                        onChange={(e) => handleManualTimeChange(e.target.value)}
                        placeholder="MM:SS"
                        className="w-24 px-2.5 py-1 bg-black/60 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500"
                      />
                      <span className="text-[11px] text-slate-500 font-mono">MM:SS or seconds</span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 text-xs">Nudge:</span>
                      <div className="flex items-center bg-black/50 rounded-lg border border-white/10 p-0.5 font-mono text-xs">
                        {[-5, -1, 1, 5].map((delta) => (
                          <button
                            key={delta}
                            type="button"
                            onClick={() => handleNudge(delta)}
                            className="px-2.5 py-1 text-slate-400 hover:text-white hover:bg-white/5 rounded cursor-pointer transition-colors"
                          >
                            {delta > 0 ? `+${delta}s` : `${delta}s`}
                          </button>
                        ))}
                      </div>
                    </div>

                    <Link
                      href={`/studio/${videoId}?start=${clipStartTime}`}
                      className="flex items-center gap-2 px-5 py-2 bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-950/50 cursor-pointer transition-transform active:scale-95"
                    >
                      <Scissors className="w-4 h-4" />
                      <span>Launch Studio at {formatSeconds(clipStartTime)}</span>
                    </Link>
                  </div>
                </div>
              )}

              {/* Existing Renders for this video */}
              {renders.length > 0 && (
                <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <Film className="w-4 h-4 text-rose-500" />
                      <span>Rendered Clips for this Video</span>
                      <span className="text-xs text-slate-400 font-normal">({renders.length})</span>
                    </h3>
                    <Link
                      href="/renders"
                      className="text-xs text-rose-400 hover:text-rose-300 font-semibold"
                    >
                      View All in Renders →
                    </Link>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {renders.slice(0, 4).map((r) => (
                      <div
                        key={r.clip_id}
                        className="p-3 bg-black/40 border border-white/5 rounded-xl flex items-center justify-between gap-3 hover:border-rose-500/30 transition-colors"
                      >
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-white truncate font-mono">
                            {r.clip_id}
                          </div>
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            Start: {formatSeconds(r.clip?.start_seconds || 0)} • {r.clip?.duration_seconds || 15}s
                          </div>
                        </div>
                        <Link
                          href={`/renders?manifest=${r.clip_id}`}
                          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-white/10 shrink-0"
                        >
                          Inspect
                        </Link>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right Column: Video Metadata & Pipeline Actions */}
            <div className="lg:col-span-4 flex flex-col gap-6">
              {/* Header card */}
              <div className="p-6 bg-[#12141c] border border-white/10 rounded-2xl flex flex-col gap-4 shadow-xl">
                <div>
                  <span className="text-xs font-bold text-rose-500 uppercase tracking-wider">
                    {video.channel_name || "Gameplay VOD"}
                  </span>
                  <h1 className="text-lg font-bold text-white mt-1 leading-snug">
                    {video.title}
                  </h1>
                </div>

                {/* Status Badges */}
                <div className="flex flex-wrap items-center gap-2">
                  {isDownloaded ? (
                    <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-lg text-xs font-semibold">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Downloaded Local MP4</span>
                    </span>
                  ) : isProcessing ? (
                    <span className="flex items-center gap-1.5 px-3 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg text-xs font-semibold animate-pulse">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Downloading ({Math.round(video.download_progress)}%)</span>
                    </span>
                  ) : (
                    <span className="px-3 py-1 bg-slate-800 text-slate-400 rounded-lg text-xs font-semibold">
                      Remote VOD (Not Downloaded)
                    </span>
                  )}
                  <span className="px-2.5 py-1 bg-black/50 text-slate-300 rounded-lg text-xs font-mono">
                    {video.duration_formatted}
                  </span>
                </div>

                {/* Primary Action Button */}
                {isDownloaded ? (
                  <div className="flex flex-col gap-2 pt-2">
                    <Link
                      href={`/studio/${videoId}${clipStartTime > 0 ? `?start=${clipStartTime}` : ""}`}
                      className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-950/60 cursor-pointer transition-transform active:scale-95"
                    >
                      <Scissors className="w-4 h-4" />
                      <span>Open in Clip Studio</span>
                    </Link>
                    <button
                      onClick={handleDelete}
                      className="w-full flex items-center justify-center gap-1.5 py-2 bg-slate-900 hover:bg-rose-950/30 text-slate-400 hover:text-rose-400 text-xs font-semibold rounded-lg border border-white/5 cursor-pointer transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Delete Local File</span>
                    </button>
                  </div>
                ) : (
                  <div className="pt-2">
                    <button
                      onClick={handleDownload}
                      disabled={isProcessing}
                      className="w-full flex items-center justify-center gap-2 py-3 bg-rose-600 hover:bg-rose-500 disabled:opacity-70 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-950/60 cursor-pointer transition-transform active:scale-95"
                    >
                      <Download className="w-4 h-4" />
                      <span>{isProcessing ? "Download in progress..." : "Download Gameplay VOD"}</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Metadata Details */}
              <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl flex flex-col gap-3 text-xs shadow-xl">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 pb-2 border-b border-white/5">
                  Video Specifications
                </h3>

                <div className="flex items-center justify-between py-1 text-slate-300">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5" /> Duration
                  </span>
                  <span className="font-semibold text-white">{video.duration_formatted}</span>
                </div>

                <div className="flex items-center justify-between py-1 text-slate-300">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Eye className="w-3.5 h-3.5" /> Views
                  </span>
                  <span className="font-semibold text-white">{video.view_count.toLocaleString()}</span>
                </div>

                <div className="flex items-center justify-between py-1 text-slate-300">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5" /> Published
                  </span>
                  <span className="font-semibold text-white">{video.published_at || "Recent"}</span>
                </div>

                {isDownloaded && (
                  <div className="flex items-center justify-between py-1 text-slate-300">
                    <span className="text-slate-400 flex items-center gap-1.5">
                      <HardDrive className="w-3.5 h-3.5" /> Local Size
                    </span>
                    <span className="font-semibold text-emerald-400">{formatBytes(video.file_size_bytes)}</span>
                  </div>
                )}

                {video.local_file_path && (
                  <div className="pt-2 border-t border-white/5">
                    <span className="text-slate-400 block mb-1">Local Storage Path:</span>
                    <code className="text-[11px] text-slate-300 bg-black/50 p-2 rounded block break-all font-mono">
                      {video.local_file_path}
                    </code>
                  </div>
                )}
              </div>

              {/* Description box */}
              {video.description && (
                <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl flex flex-col gap-2 text-xs shadow-xl">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Description
                  </h3>
                  <div className="text-slate-400 leading-relaxed max-h-48 overflow-y-auto whitespace-pre-line pr-1">
                    {video.description}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function VideoDetailPage() {
  return (
    <React.Suspense
      fallback={
        <div className="min-h-screen bg-[#090a0f] flex flex-col items-center justify-center">
          <Loader2 className="w-8 h-8 text-rose-500 animate-spin mb-3" />
          <p className="text-xs text-slate-400 font-medium">Loading Video Details...</p>
        </div>
      }
    >
      <VideoDetailContent />
    </React.Suspense>
  );
}
