"use client";

import { motion } from "framer-motion";
import {
  Check,
  CheckCircle2,
  Download,
  ExternalLink,
  EyeOff,
  HardDrive,
  Loader2,
  Play,
  Radio,
  Scissors,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import React from "react";
import { YoutubeIcon } from "./icons";
import { Tooltip, TruncatedText } from "./Tooltip";

import { VideoItem } from "@/types/video";

interface VideoCardProps {
  video: VideoItem;
  index: number;
  onSelect?: (video: VideoItem) => void;
  onDownload: (videoId: string) => void;
  onDeleteDownload: (videoId: string) => void;
  isDownloadingThis: boolean;
  isSelected?: boolean;
  onToggleSelect?: (videoId: string) => void;
  onToggleIgnore?: (video: VideoItem) => void;
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
  isSelected = false,
  onToggleSelect,
  onToggleIgnore,
}) => {
  const isHighPriority = index < 2;
  const isDownloaded = video.is_downloaded || video.download_status === "completed";
  const isProcessing =
    (video.download_status === "downloading" ||
      video.download_status === "pending" ||
      isDownloadingThis) &&
    !isDownloaded;

  const handleClickCard = () => {
    if (onSelect) onSelect(video);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.4) }}
      className={`group relative flex flex-col bg-[#12141c] hover:bg-[#181b26] rounded-2xl overflow-hidden shadow-lg transition-all duration-300 hover:shadow-2xl hover:shadow-rose-950/20 ${
        isSelected
          ? "ring-2 ring-rose-500 border border-rose-500/50 bg-[#161a29]"
          : video.is_ignored
          ? "border border-dashed border-slate-700/80 opacity-80 hover:opacity-100"
          : "border border-white/5 hover:border-rose-500/30"
      }`}
    >
      {/* Thumbnail Container (16:9 YouTube aspect ratio) */}
      <Link
        href={`/videos/${video.id}`}
        onClick={handleClickCard}
        className="relative aspect-video w-full bg-slate-900 cursor-pointer overflow-hidden block"
      >
        <img
          src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
          alt={video.title}
          fetchPriority={isHighPriority ? "high" : undefined}
          loading={isHighPriority ? "eager" : "lazy"}
          className={`w-full h-full object-cover transition-transform duration-500 group-hover:scale-105 ${
            video.is_ignored ? "grayscale-[35%]" : ""
          }`}
        />

        {/* Hover play and quick clip gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center gap-2">
          <div className="w-10 h-10 rounded-full bg-slate-900/90 text-white flex items-center justify-center shadow-lg transform scale-90 group-hover:scale-100 transition-transform border border-white/10 hover:border-white/30">
            <Play className="w-4 h-4 ml-0.5 fill-current" />
          </div>
          {isDownloaded && !video.is_ignored && (
            <Link
              href={`/studio/${video.id}`}
              onClick={(e) => e.stopPropagation()}
              className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 text-white text-xs font-bold flex items-center gap-1.5 shadow-xl hover:scale-105 transition-transform border border-rose-400/30"
              title="Quick Clip in Studio"
            >
              <Scissors className="w-3.5 h-3.5" />
              <span>Quick Clip</span>
            </Link>
          )}
        </div>

        {/* Selection Checkbox (bottom-left of thumbnail) */}
        {onToggleSelect && (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onToggleSelect(video.id);
            }}
            className={`absolute bottom-2.5 left-2.5 z-20 w-6 h-6 rounded-lg flex items-center justify-center transition-all cursor-pointer ${
              isSelected
                ? "bg-rose-600 text-white shadow-md shadow-rose-950/60 ring-2 ring-white/30 opacity-100"
                : "bg-black/70 text-transparent hover:text-white/80 border border-white/20 opacity-0 group-hover:opacity-100"
            }`}
            title={isSelected ? "Deselect video" : "Select video to tag or manage"}
            aria-label={isSelected ? "Deselect video" : "Select video to tag or manage"}
          >
            <Check className="w-3.5 h-3.5 stroke-[3]" />
          </button>
        )}

        {/* Duration badge */}
        <div className="absolute bottom-2.5 right-2.5 yt-badge shadow-md">
          {video.duration_formatted}
        </div>

        {/* Download / OBS Status Badge on Thumbnail */}
        {video.id.startsWith("obs_") || video.channel_name === "OBS Studio" ? (
          <div className="absolute top-2.5 left-2.5 flex items-center gap-1 px-2 py-0.5 rounded-md bg-gradient-to-r from-rose-600 to-amber-600 text-white text-xs font-semibold backdrop-blur-md shadow-md border border-rose-400/30">
            <Radio className="w-3 h-3 text-white animate-pulse" />
            <span>OBS / Local VOD</span>
          </div>
        ) : isDownloaded ? (
          <div className="absolute top-2.5 left-2.5 flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/90 text-white text-xs font-semibold backdrop-blur-md shadow-md">
            <CheckCircle2 className="w-3 h-3" />
            <span>Local MP4</span>
          </div>
        ) : null}

        {/* Top-Right Badges Container (Shorts Uploaded & Do Not Process Tag) */}
        <div className="absolute top-2.5 right-2.5 flex flex-col items-end gap-1 z-10 pointer-events-none">
          {video.uploaded_clip_count !== undefined && video.uploaded_clip_count > 0 && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-600/90 text-white text-xs font-bold backdrop-blur-md shadow-md border border-red-400/40">
              <YoutubeIcon className="w-3 h-3 text-white" />
              <span>{video.uploaded_clip_count} {video.uploaded_clip_count === 1 ? "Short" : "Shorts"} Uploaded</span>
            </div>
          )}
          {video.is_ignored && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-900/95 text-amber-300 text-[11px] font-bold backdrop-blur-md shadow-md border border-amber-500/40">
              <EyeOff className="w-3 h-3 text-amber-400" />
              <span>Do Not Process</span>
            </div>
          )}
        </div>

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
      </Link>

      {/* Card Content */}
      <div className="p-4 flex-1 flex flex-col justify-between gap-3">
        <div>
          {/* Video Title */}
          <Link
            href={`/videos/${video.id}`}
            onClick={handleClickCard}
            className="cursor-pointer block"
          >
            <TruncatedText
              text={video.title}
              lines={2}
              className="text-sm font-semibold text-slate-100 group-hover:text-rose-400 leading-snug transition-colors"
              tooltipTitle="Full VOD Title"
            />
          </Link>

          {/* Channel Name & Meta */}
          <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
            <Tooltip content={`Channel / Uploader: ${video.channel_name || "Gameplay VOD"}`}>
              <span className="font-medium text-slate-300 truncate max-w-[160px] cursor-help">
                {video.channel_name || "Gameplay VOD"}
              </span>
            </Tooltip>
            <div className="flex items-center gap-2">
              {video.view_count > 0 && (
                <Tooltip content={`Total views: ${video.view_count.toLocaleString()}`}>
                  <span className="cursor-help">{formatViews(video.view_count)}</span>
                </Tooltip>
              )}
              {video.published_at && (
                <>
                  <span>•</span>
                  <span>{video.published_at}</span>
                </>
              )}
            </div>
          </div>

          {/* Processing Lifecycle Badges (Highlights, YouTube Uploads, Cleanup Ready) */}
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {video.highlight_candidate_count !== undefined && video.highlight_candidate_count > 0 && (
              <Tooltip content={`${video.highlight_candidate_count} AI-mined gameplay highlight candidates ready for clipping`}>
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-purple-500/15 text-purple-300 border border-purple-500/30 flex items-center gap-1 cursor-help">
                  <Sparkles className="w-3 h-3 text-purple-400" />
                  <span>{video.highlight_candidate_count} Highlights</span>
                </span>
              </Tooltip>
            )}

            {video.uploaded_clip_count !== undefined && video.uploaded_clip_count > 0 && (
              <Tooltip content={`${video.uploaded_clip_count} highlight clip(s) rendered and published to YouTube Shorts`}>
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-red-600/15 text-red-300 border border-red-500/30 flex items-center gap-1 cursor-help">
                  <YoutubeIcon className="w-3 h-3 text-red-400" />
                  <span>{video.uploaded_clip_count} Uploaded</span>
                </span>
              </Tooltip>
            )}

            {video.can_cleanup_vod && (
              <Tooltip content="All highlights have been published to YouTube. It is safe to delete this source VOD to free up disk space while preserving your clips.">
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1 cursor-help">
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                  <span>Safe to Clean VOD</span>
                </span>
              </Tooltip>
            )}

            {video.is_ignored && (
              <Tooltip
                content={
                  video.ignore_reason
                    ? `Tagged as Do Not Process: ${video.ignore_reason}`
                    : "Tagged as Do Not Process: video is tracked but skipped from downloads and clip processing"
                }
              >
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-slate-800 text-amber-300 border border-amber-500/30 flex items-center gap-1 cursor-help">
                  <EyeOff className="w-3 h-3 text-amber-400" />
                  <span>Do Not Process</span>
                </span>
              </Tooltip>
            )}
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
              <Tooltip
                content={
                  video.can_cleanup_vod
                    ? "Highlights uploaded: safe to delete source VOD to free up disk space"
                    : `Downloaded local MP4 (${formatBytes(video.file_size_bytes) || "Saved"})`
                }
              >
                <div
                  className={`flex items-center gap-1.5 text-xs font-medium cursor-help ${
                    video.can_cleanup_vod ? "text-emerald-300" : "text-emerald-400"
                  }`}
                >
                  <HardDrive className="w-3.5 h-3.5" />
                  <span>
                    {formatBytes(video.file_size_bytes) || "Saved"}
                    {video.can_cleanup_vod && " • Clean Ready"}
                  </span>
                </div>
              </Tooltip>
              <div className="flex items-center gap-1.5">
                {onToggleIgnore && (
                  <Tooltip
                    content={
                      video.is_ignored
                        ? "Remove 'Do Not Process' tag (mark active)"
                        : "Tag as Do Not Process (skip downloads & clips)"
                    }
                  >
                    <button
                      type="button"
                      onClick={() => onToggleIgnore(video)}
                      className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                        video.is_ignored
                          ? "text-amber-400 hover:text-amber-300 bg-amber-500/10 border border-amber-500/30"
                          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                      }`}
                      title={video.is_ignored ? "Remove 'Do Not Process' tag" : "Tag as Do Not Process"}
                    >
                      <EyeOff className="w-3.5 h-3.5" />
                    </button>
                  </Tooltip>
                )}

                {!video.is_ignored && (
                  <Tooltip content="Launch Clip Studio to frame and render vertical highlights">
                    <Link
                      href={`/studio/${video.id}`}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold rounded-lg shadow-md shadow-rose-950/30 transition-all cursor-pointer active:scale-95"
                    >
                      <Scissors className="w-3.5 h-3.5" />
                      <span>Create Clips</span>
                    </Link>
                  </Tooltip>
                )}

                <Tooltip
                  content={
                    video.can_cleanup_vod
                      ? "Reclaim disk space: Delete source VOD file (keeps rendered clips & YouTube links)"
                      : "Delete downloaded local video file"
                  }
                >
                  <button
                    onClick={() => {
                      if (video.can_cleanup_vod) {
                        if (
                          confirm(
                            `Highlights for "${video.title}" have already been uploaded to YouTube Shorts.\n\nDeleting the local source VOD (${formatBytes(video.file_size_bytes) || "file"}) will free up disk space while preserving all highlights, clips, and YouTube links.\n\nProceed to delete local file?`
                          )
                        ) {
                          onDeleteDownload(video.id);
                        }
                      } else {
                        onDeleteDownload(video.id);
                      }
                    }}
                    className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                      video.can_cleanup_vod
                        ? "text-emerald-400 hover:text-emerald-300 hover:bg-emerald-950/40 border border-emerald-500/20"
                        : "text-slate-400 hover:text-rose-400 hover:bg-slate-800"
                    }`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </Tooltip>
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
              <div className="flex items-center gap-1.5">
                {onToggleIgnore && (
                  <Tooltip
                    content={
                      video.is_ignored
                        ? "Remove 'Do Not Process' tag (mark active)"
                        : "Tag as Do Not Process (skip downloads & clips)"
                    }
                  >
                    <button
                      type="button"
                      onClick={() => onToggleIgnore(video)}
                      className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                        video.is_ignored
                          ? "text-amber-400 hover:text-amber-300 bg-amber-500/10 border border-amber-500/30"
                          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                      }`}
                      title={video.is_ignored ? "Remove 'Do Not Process' tag" : "Tag as Do Not Process"}
                    >
                      <EyeOff className="w-3.5 h-3.5" />
                    </button>
                  </Tooltip>
                )}

                {video.is_ignored ? (
                  <Tooltip content="Video is tagged as Do Not Process. Remove tag to enable downloading.">
                    <span className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/80 text-slate-500 text-xs font-semibold rounded-lg border border-white/5 cursor-not-allowed">
                      <EyeOff className="w-3.5 h-3.5" />
                      <span>Ignored</span>
                    </span>
                  </Tooltip>
                ) : (
                  <button
                    onClick={() => onDownload(video.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600/90 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-sm shadow-rose-900/30 transition-all cursor-pointer active:scale-95"
                    title="Download VOD to enable clipping"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download VOD</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};
