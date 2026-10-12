"use client";

import { motion } from "framer-motion";
import {
  CheckCircle2,
  Download,
  ExternalLink,
  HardDrive,
  Loader2,
  Play,
  Scissors,
  Trash2
} from "lucide-react";
import React from "react";

import { VideoItem } from "@/types/video";

interface VideoCardProps {
  video: VideoItem;
  index: number;
  onSelect: (video: VideoItem) => void;
  onDownload: (videoId: string) => void;
  onDeleteDownload: (videoId: string) => void;
  isDownloadingThis: boolean;
}

function formatViews(views: number): string {
  if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)}M views`;
  if (views >= 1_000) return `${(views / 1_000).toFixed(1)}K views`;
  return `${views} views`;
}

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${mb.toFixed(1)} MB`;
}

export const VideoCard: React.FC<VideoCardProps> = ({
  video,
  index,
  onSelect,
  onDownload,
  onDeleteDownload,
  isDownloadingThis,
}) => {
  const isHighPriority = index < 2;
  const isDownloaded = video.is_downloaded;
  const isProcessing =
    video.download_status === "downloading" ||
    video.download_status === "pending" ||
    isDownloadingThis;

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.4) }}
      className="group relative flex flex-col bg-[#12141c] hover:bg-[#181b26] border border-white/5 hover:border-rose-500/30 rounded-2xl overflow-hidden shadow-lg transition-all duration-300 hover:shadow-2xl hover:shadow-rose-950/20"
    >
      {/* Thumbnail Container (16:9 YouTube aspect ratio) */}
      <div
        className="relative aspect-video w-full bg-slate-900 cursor-pointer overflow-hidden"
        onClick={() => onSelect(video)}
      >
        <img
          src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
          alt={video.title}
          fetchPriority={isHighPriority ? "high" : undefined}
          loading={isHighPriority ? "eager" : "lazy"}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
        />

        {/* Hover play gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center">
          <div className="w-12 h-12 rounded-full bg-rose-600/90 text-white flex items-center justify-center shadow-lg transform scale-75 group-hover:scale-100 transition-transform">
            <Play className="w-5 h-5 ml-0.5 fill-current" />
          </div>
        </div>

        {/* Duration badge */}
        <div className="absolute bottom-2.5 right-2.5 yt-badge shadow-md">
          {video.duration_formatted}
        </div>

        {/* Download Status Badge on Thumbnail */}
        {isDownloaded && (
          <div className="absolute top-2.5 left-2.5 flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/90 text-white text-xs font-semibold backdrop-blur-md shadow-md">
            <CheckCircle2 className="w-3 h-3" />
            <span>Local MP4</span>
          </div>
        )}

        {isProcessing && (
          <div className="absolute top-2.5 left-2.5 flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-500/90 text-white text-xs font-semibold backdrop-blur-md shadow-md animate-pulse">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>
              {video.download_progress > 0
                ? `${Math.round(video.download_progress)}%`
                : "Queued"}
            </span>
          </div>
        )}
      </div>

      {/* Card Content */}
      <div className="p-4 flex-1 flex flex-col justify-between gap-3">
        <div>
          {/* Video Title */}
          <h3
            onClick={() => onSelect(video)}
            className="text-sm font-semibold text-slate-100 group-hover:text-rose-400 line-clamp-2 leading-snug cursor-pointer transition-colors"
            title={video.title}
          >
            {video.title}
          </h3>

          {/* Channel Name & Meta */}
          <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
            <span className="font-medium text-slate-300 truncate max-w-[160px]">
              {video.channel_name || "Gameplay VOD"}
            </span>
            <div className="flex items-center gap-2">
              {video.view_count > 0 && <span>{formatViews(video.view_count)}</span>}
              {video.published_at && (
                <>
                  <span>•</span>
                  <span>{video.published_at}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Download Progress Bar if in progress */}
        {isProcessing && (
          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-rose-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${Math.max(video.download_progress, 5)}%` }}
            />
          </div>
        )}

        {/* Card Footer Actions */}
        <div className="pt-2 border-t border-white/5 flex items-center justify-between gap-2">
          {isDownloaded ? (
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                <HardDrive className="w-3.5 h-3.5" />
                <span>{formatBytes(video.file_size_bytes) || "Saved"}</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => onSelect(video)}
                  title="Play video and create clip"
                  className="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors cursor-pointer flex items-center gap-1"
                >
                  <Scissors className="w-3 h-3" />
                  <span>Create Clip</span>
                </button>

                <button
                  onClick={() => onDeleteDownload(video.id)}
                  title="Delete local file"
                  className="p-1 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ) : isProcessing ? (
            <div className="flex items-center gap-2 text-xs text-amber-400 font-medium w-full justify-between">
              <span className="flex items-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Downloading video...</span>
              </span>
              <span>{Math.round(video.download_progress)}%</span>
            </div>
          ) : (
            <div className="flex items-center justify-between w-full">
              <a
                href={video.webpage_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <span>YouTube</span>
                <ExternalLink className="w-3 h-3" />
              </a>
              <button
                onClick={() => onDownload(video.id)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600/90 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-sm shadow-rose-900/30 transition-all cursor-pointer active:scale-95"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download VOD</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};
