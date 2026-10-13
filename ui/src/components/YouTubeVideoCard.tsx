"use client";

import { YouTubeChannelVideoItem } from "@/types/video";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  ExternalLink,
  Play,
  Tv,
} from "lucide-react";
import React from "react";

interface YouTubeVideoCardProps {
  video: YouTubeChannelVideoItem;
  index: number;
  isSelected: boolean;
  onToggleSelect: (video: YouTubeChannelVideoItem) => void;
  onPreview: (video: YouTubeChannelVideoItem) => void;
}

function formatViews(views: number): string {
  if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)}M views`;
  if (views >= 1_000) return `${(views / 1_000).toFixed(1)}K views`;
  return `${views} views`;
}

export const YouTubeVideoCard: React.FC<YouTubeVideoCardProps> = ({
  video,
  index,
  isSelected,
  onToggleSelect,
  onPreview,
}) => {
  const isInLibrary = video.is_in_database;

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.3) }}
      className={`group relative flex flex-col bg-[#12141c] rounded-2xl overflow-hidden shadow-lg transition-all duration-200 border ${
        isSelected
          ? "border-rose-500 ring-2 ring-rose-500/30 bg-[#171a26] shadow-rose-950/30"
          : isInLibrary
          ? "border-emerald-500/30 hover:border-emerald-500/60 hover:bg-[#151824]"
          : "border-white/5 hover:border-white/20 hover:bg-[#161824]"
      }`}
    >
      {/* Thumbnail Container */}
      <div className="relative aspect-video w-full bg-slate-900 overflow-hidden">
        <img
          src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
          alt={video.title}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105 cursor-pointer"
          onClick={() => onPreview(video)}
        />

        {/* Play Overlay */}
        <div
          onClick={() => onPreview(video)}
          className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center cursor-pointer"
        >
          <div className="w-11 h-11 rounded-full bg-rose-600/90 text-white flex items-center justify-center shadow-lg transform scale-75 group-hover:scale-100 transition-transform">
            <Play className="w-5 h-5 ml-0.5 fill-current" />
          </div>
        </div>

        {/* Duration badge */}
        <div className="absolute bottom-2.5 right-2.5 yt-badge shadow-md">
          {video.duration_formatted}
        </div>

        {/* In-Database Library Status Badge */}
        {isInLibrary ? (
          <div className="absolute top-2.5 left-2.5 flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/95 text-white text-[11px] font-semibold backdrop-blur-md shadow-md">
            <CheckCircle2 className="w-3 h-3" />
            <span>In Library</span>
          </div>
        ) : (
          <div className="absolute top-2.5 left-2.5 flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-900/80 text-slate-300 text-[11px] font-medium backdrop-blur-md border border-white/10">
            <Tv className="w-3 h-3 text-slate-400" />
            <span>Unsynced</span>
          </div>
        )}

        {/* Selection Checkbox */}
        <div
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect(video);
          }}
          className="absolute top-2.5 right-2.5 z-10 cursor-pointer"
        >
          <div
            className={`w-6 h-6 rounded-lg border flex items-center justify-center transition-all shadow-md ${
              isSelected
                ? "bg-rose-600 border-rose-500 text-white shadow-rose-900/50"
                : "bg-slate-900/85 hover:bg-slate-800 border-white/20 text-transparent"
            }`}
          >
            <CheckCircle2 className="w-4 h-4 text-white" />
          </div>
        </div>
      </div>

      {/* Card Content */}
      <div className="p-4 flex-1 flex flex-col justify-between gap-3">
        <div>
          {/* Video Title */}
          <h3
            onClick={() => onPreview(video)}
            className="text-sm font-semibold text-slate-100 group-hover:text-rose-400 line-clamp-2 leading-snug cursor-pointer transition-colors"
            title={video.title}
          >
            {video.title}
          </h3>

          {/* Channel Name & Meta */}
          <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
            <span className="font-medium text-slate-300 truncate max-w-[150px]">
              {video.channel_name || "YouTube VOD"}
            </span>
            <div className="flex items-center gap-2 shrink-0">
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

        {/* Card Footer Actions */}
        <div className="pt-2.5 border-t border-white/5 flex items-center justify-between gap-2 text-xs">
          <a
            href={video.webpage_url}
            target="_blank"
            rel="noreferrer"
            className="text-slate-400 hover:text-slate-200 flex items-center gap-1 transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <span>Watch on YouTube</span>
            <ExternalLink className="w-3 h-3" />
          </a>

          <button
            onClick={() => onToggleSelect(video)}
            className={`px-2.5 py-1 rounded-lg font-semibold text-xs transition-colors cursor-pointer flex items-center gap-1 ${
              isSelected
                ? "bg-rose-600/30 text-rose-300 border border-rose-500/40 hover:bg-rose-600/40"
                : isInLibrary
                ? "bg-slate-800/80 text-emerald-400 hover:bg-slate-700/80 border border-emerald-500/20"
                : "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-white/10"
            }`}
          >
            <span>{isSelected ? "Selected" : isInLibrary ? "Re-sync" : "Select"}</span>
          </button>
        </div>
      </div>
    </motion.div>
  );
};
