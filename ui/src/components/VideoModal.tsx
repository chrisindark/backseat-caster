"use client";

import { getDownloadedVideoStreamUrl } from "@/lib/api";
import { VideoItem } from "@/types/video";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  Clock,
  Download,
  ExternalLink,
  Loader2,
  Scissors,
  Trash2,
  X
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

interface VideoModalProps {
  video: VideoItem | null;
  onClose: () => void;
  onDownload: (videoId: string) => void;
  onDeleteDownload: (videoId: string) => void;
  onOpenClipStudio?: (video: VideoItem, initialStartTime?: number) => void;
  isDownloading: boolean;
}

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "N/A";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${mb.toFixed(1)} MB`;
}

function formatSeconds(sec: number): string {
  if (isNaN(sec) || sec < 0) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

function parseSeconds(val: string): number {
  if (!val) return 0;
  if (val.includes(":")) {
    const parts = val.split(":");
    if (parts.length === 2) {
      const min = parseFloat(parts[0]) || 0;
      const sec = parseFloat(parts[1]) || 0;
      return min * 60 + sec;
    }
  }
  return parseFloat(val) || 0;
}

export const VideoModal: React.FC<VideoModalProps> = ({
  video,
  onClose,
  onDownload,
  onDeleteDownload,
  onOpenClipStudio,
  isDownloading,
}) => {
  const isDownloaded = video?.is_downloaded;
  const isProcessing =
    video?.download_status === "downloading" ||
    video?.download_status === "pending" ||
    isDownloading;

  const [currentTime, setCurrentTime] = useState<number>(0);
  const [clipStartTime, setClipStartTime] = useState<number>(0);
  const [startTimeInput, setStartTimeInput] = useState<string>("0:00");
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    setCurrentTime(0);
    setClipStartTime(0);
    setStartTimeInput("0:00");
  }, [video?.id]);

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

  return (
    <AnimatePresence>
      {video && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/80 backdrop-blur-md"
        />

        {/* Modal Container */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.2 }}
          className="relative w-full max-w-3xl bg-[#12141c] border border-white/10 rounded-2xl shadow-2xl overflow-hidden z-10 my-8"
        >
          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 z-20 p-2 rounded-full bg-black/60 hover:bg-black text-slate-300 hover:text-white backdrop-blur-md transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Media Header Preview */}
          {isDownloaded ? (
            <div className="relative aspect-video w-full bg-black overflow-hidden group">
              <video
                ref={videoRef}
                src={getDownloadedVideoStreamUrl(video.id)}
                poster={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
                controls
                playsInline
                preload="metadata"
                onTimeUpdate={(e) => {
                  setCurrentTime(e.currentTarget.currentTime);
                }}
                className="w-full h-full object-contain bg-black"
              />
              {/* Badges on video player */}
              <div className="absolute top-4 left-4 z-10 flex items-center gap-2 pointer-events-none">
                <span className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/90 text-white text-xs font-semibold backdrop-blur-md shadow-md">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Downloaded MP4 ({formatBytes(video.file_size_bytes)})
                </span>
              </div>
              <div className="absolute top-4 right-14 z-20">
                <a
                  href={video.webpage_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1 bg-black/70 hover:bg-black text-white text-xs font-semibold rounded-lg backdrop-blur-md transition-colors"
                >
                  <span>YouTube</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            </div>
          ) : (
            <div className="relative aspect-video w-full bg-slate-950 overflow-hidden">
              <img
                src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
                alt={video.title}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-[#12141c] via-transparent to-black/40" />

              {/* Badges on preview */}
              <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="yt-badge text-sm">{video.duration_formatted}</span>
                </div>
                <a
                  href={video.webpage_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-black/70 hover:bg-black text-white text-xs font-semibold rounded-lg backdrop-blur-md transition-colors"
                >
                  <span>Watch on YouTube</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            </div>
          )}

          {/* Modal Body */}
          <div className="p-6 flex flex-col gap-5">
            <div>
              <span className="text-xs font-semibold text-rose-500 uppercase tracking-wider">
                {video.channel_name || "Gameplay VOD"}
              </span>
              <h2 className="text-xl font-bold text-white mt-1 leading-snug">
                {video.title}
              </h2>
            </div>

            {/* Interactive Clip Start Time Selector for Downloaded Videos */}
            {isDownloaded && (
              <div className="p-4 bg-gradient-to-r from-rose-950/40 via-purple-950/20 to-slate-900/60 border border-rose-500/20 rounded-xl flex flex-col gap-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-rose-600/20 border border-rose-500/30 text-rose-400">
                      <Scissors className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-white flex items-center gap-2">
                        <span>Select Clip Start Time</span>
                        <span className="font-mono text-rose-300 font-bold bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/30">
                          {formatSeconds(clipStartTime)} ({clipStartTime}s)
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-400">
                        Playhead: <span className="font-mono text-slate-200">{formatSeconds(currentTime)}</span> • Scrub or play the video to find the moment
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleSetCurrentAsStart}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-md shadow-rose-950/40 transition-all cursor-pointer active:scale-95"
                    >
                      <Clock className="w-3.5 h-3.5" />
                      <span>Set to Playhead ({formatSeconds(currentTime)})</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleSeekToStart}
                      className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg border border-white/10 transition-colors cursor-pointer"
                      title="Seek player to selected start time"
                    >
                      Seek to Start
                    </button>
                  </div>
                </div>

                {/* Fine-tune controls & manual input */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t border-white/5 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400 text-xs">Start Time:</span>
                    <input
                      type="text"
                      value={startTimeInput}
                      onChange={(e) => handleManualTimeChange(e.target.value)}
                      placeholder="e.g. 01:30"
                      className="w-24 px-2.5 py-1 bg-black/50 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500"
                    />
                    <span className="text-[11px] text-slate-400 font-mono">MM:SS or sec</span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-400 text-[11px]">Nudge:</span>
                    <div className="flex items-center bg-black/40 rounded-lg border border-white/10 p-0.5 font-mono text-xs">
                      <button
                        type="button"
                        onClick={() => handleNudge(-5)}
                        className="px-2 py-1 text-slate-400 hover:text-white hover:bg-white/5 rounded cursor-pointer transition-colors"
                        title="Rewind 5s"
                      >
                        -5s
                      </button>
                      <button
                        type="button"
                        onClick={() => handleNudge(-1)}
                        className="px-2 py-1 text-slate-400 hover:text-white hover:bg-white/5 rounded cursor-pointer transition-colors"
                        title="Rewind 1s"
                      >
                        -1s
                      </button>
                      <button
                        type="button"
                        onClick={() => handleNudge(1)}
                        className="px-2 py-1 text-slate-400 hover:text-white hover:bg-white/5 rounded cursor-pointer transition-colors"
                        title="Forward 1s"
                      >
                        +1s
                      </button>
                      <button
                        type="button"
                        onClick={() => handleNudge(5)}
                        className="px-2 py-1 text-slate-400 hover:text-white hover:bg-white/5 rounded cursor-pointer transition-colors"
                        title="Forward 5s"
                      >
                        +5s
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Metadata Pills */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 bg-slate-900/80 rounded-xl border border-white/5 text-xs">
              <div>
                <span className="text-slate-400 block">Duration</span>
                <span className="font-semibold text-white">{video.duration_formatted}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Views</span>
                <span className="font-semibold text-white">{video.view_count.toLocaleString()}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Published</span>
                <span className="font-semibold text-white">{video.published_at || "Recent"}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Status</span>
                <span
                  className={`font-semibold ${
                    isDownloaded
                      ? "text-emerald-400"
                      : isProcessing
                      ? "text-amber-400"
                      : "text-slate-300"
                  }`}
                >
                  {isDownloaded
                    ? "Ready Locally"
                    : isProcessing
                    ? `Downloading (${Math.round(video.download_progress)}%)`
                    : "Not Downloaded"}
                </span>
              </div>
            </div>

            {/* Local file details if downloaded */}
            {isDownloaded && video.local_file_path && (
              <div className="p-3.5 bg-emerald-950/20 border border-emerald-500/20 rounded-xl text-xs flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-emerald-400 font-semibold">
                  <span className="flex items-center gap-1.5">
                    <Scissors className="w-4 h-4" />
                    <span>Ready for Phase 1 Clip Rendering Engine</span>
                  </span>
                  <span>{formatBytes(video.file_size_bytes)}</span>
                </div>
                <div className="text-slate-400 break-all font-mono text-[11px]">
                  File: {video.local_file_path}
                </div>
              </div>
            )}

            {/* Error message if failed */}
            {video.error_message && (
              <div className="p-3 bg-rose-950/30 border border-rose-500/30 rounded-xl text-xs text-rose-300">
                <span className="font-semibold block mb-0.5">Download Error:</span>
                {video.error_message}
              </div>
            )}

            {/* Description (collapsible/scrollable) */}
            {video.description && (
              <div className="text-xs text-slate-400 bg-slate-900/40 p-3 rounded-xl border border-white/5 max-h-32 overflow-y-auto leading-relaxed">
                <span className="font-semibold text-slate-300 block mb-1">Description</span>
                {video.description}
              </div>
            )}

            {/* Footer Action Buttons */}
            <div className="flex items-center justify-between pt-4 border-t border-white/5">
              {isDownloaded ? (
                <>
                  <button
                    onClick={() => onDeleteDownload(video.id)}
                    className="flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 text-xs font-semibold rounded-lg border border-white/10 transition-colors cursor-pointer"
                  >
                    <Trash2 className="w-4 h-4" />
                    <span>Delete Local File</span>
                  </button>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        onClose();
                        if (onOpenClipStudio) onOpenClipStudio(video, clipStartTime);
                      }}
                      className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white text-xs font-bold rounded-lg shadow-lg shadow-rose-950/50 transition-all cursor-pointer active:scale-95"
                    >
                      <Scissors className="w-4 h-4" />
                      <span>
                        {clipStartTime > 0
                          ? `Create Clip from ${formatSeconds(clipStartTime)}`
                          : "Create Clip"}
                      </span>
                    </button>
                  </div>
                </>
              ) : isProcessing ? (
                <div className="flex items-center gap-3 w-full justify-between">
                  <div className="flex items-center gap-2 text-xs text-amber-400 font-semibold">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Downloading to data/downloads/... ({Math.round(video.download_progress)}%)</span>
                  </div>
                  <button
                    onClick={onClose}
                    className="px-4 py-2 bg-slate-800 text-slate-300 text-xs rounded-lg hover:bg-slate-700 cursor-pointer"
                  >
                    Close
                  </button>
                </div>
              ) : (
                <>
                  <button
                    onClick={onClose}
                    className="px-4 py-2 bg-slate-900 text-slate-300 text-xs font-semibold rounded-lg border border-white/10 hover:bg-slate-800 cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => onDownload(video.id)}
                    className="flex items-center gap-2 px-6 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg shadow-lg shadow-rose-900/50 transition-all cursor-pointer active:scale-95"
                  >
                    <Download className="w-4 h-4" />
                    <span>Download Gameplay Video</span>
                  </button>
                </>
              )}
            </div>
          </div>
        </motion.div>
      </div>
      )}
    </AnimatePresence>
  );
};
