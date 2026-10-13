"use client";

import { YouTubeChannelVideoItem } from "@/types/video";
import { useScrollLock } from "@/lib/useScrollLock";
import { CheckCircle2, ExternalLink, X } from "lucide-react";
import React, { useEffect } from "react";

interface YouTubePreviewModalProps {
  video: YouTubeChannelVideoItem | null;
  isSelected: boolean;
  onToggleSelect: (video: YouTubeChannelVideoItem) => void;
  onClose: () => void;
}

export const YouTubePreviewModal: React.FC<YouTubePreviewModalProps> = ({
  video,
  isSelected,
  onToggleSelect,
  onClose,
}) => {
  useScrollLock(Boolean(video));

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!video) return null;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in overflow-y-auto overscroll-contain"
    >
      <div
        className="relative w-full max-w-4xl bg-[#12141c] border border-white/10 rounded-2xl overflow-hidden shadow-2xl flex flex-col max-h-[calc(100vh-2rem)] my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="p-4 border-b border-white/10 flex items-center justify-between gap-4 shrink-0">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-bold text-white truncate">{video.title}</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {video.channel_name || "YouTube VOD"} • {video.duration_formatted}
              {video.published_at ? ` • ${video.published_at}` : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Video Player (16:9) */}
        <div className="relative aspect-video w-full bg-black">
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${video.id}?autoplay=1`}
            title={video.title}
            className="w-full h-full border-0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-white/10 flex items-center justify-between gap-3 bg-[#0d0f17] shrink-0">
          <div className="flex items-center gap-2">
            {video.is_in_database ? (
              <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Already in Local Library</span>
              </span>
            ) : (
              <span className="text-xs text-slate-400">
                Not yet added to local library
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <a
              href={video.webpage_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg border border-white/10 transition-colors cursor-pointer"
            >
              <span>Open on YouTube</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>

            <button
              onClick={() => onToggleSelect(video)}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold shadow-md transition-all cursor-pointer ${
                isSelected
                  ? "bg-rose-600/30 text-rose-300 border border-rose-500/40 hover:bg-rose-600/40 shadow-rose-950/30"
                  : "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-900/40"
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{isSelected ? "Deselect Video" : "Select for Sync"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
