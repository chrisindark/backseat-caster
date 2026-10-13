"use client";

import { getStreamUrl } from "@/lib/api";
import { RenderManifest } from "@/types/video";
import {
  Check,
  Clock,
  Columns,
  Download,
  FileCode,
  Play,
  Smartphone,
  Sparkles,
  Star,
  Trash2,
  Tv,
  Volume2,
} from "lucide-react";
import React, { useRef, useState } from "react";

interface RenderCardProps {
  render: RenderManifest;
  onToggleSelectForUpload: (
    clipId: string,
    isCurrentlySelected: boolean,
    preferredFormat: string
  ) => Promise<void>;
  onDelete: (clipId: string) => Promise<void>;
  onInspectManifest: (manifest: RenderManifest) => void;
  isCardSelected?: boolean;
  onToggleCardSelect?: (clipId: string) => void;
}

type PreviewTab = string;

const MODE_NAMES: Record<string, string> = {
  landscape: "16:9 Landscape",
  vertical_blur: "Vertical Blur",
  vertical_crop: "Direct Crop",
  third_person: "Third-Person Wide",
  direct_crop: "Direct Crop",
  cinematic: "Cinematic Balanced",
  custom: "Custom Blur Crop",
};

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return "N/A";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatSeconds(secs: number): string {
  if (isNaN(secs) || secs < 0) return "0:00";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export const RenderCard: React.FC<RenderCardProps> = ({
  render,
  onToggleSelectForUpload,
  onDelete,
  onInspectManifest,
  isCardSelected = false,
  onToggleCardSelect,
}) => {
  const availableModes = React.useMemo(() => {
    const list: string[] = [];
    if (render.outputs) {
      for (const k of Object.keys(render.outputs)) {
        if (render.outputs[k] && !list.includes(k)) {
          list.push(k);
        }
      }
    }
    if (render.modes) {
      for (const m of render.modes) {
        if (!list.includes(m)) list.push(m);
      }
    }
    const hasSpecialCrop = list.some((m) =>
      ["third_person", "direct_crop", "cinematic", "custom"].includes(m)
    );
    const filtered = hasSpecialCrop ? list.filter((m) => m !== "vertical_crop") : list;
    return filtered.length > 0 ? filtered : ["vertical_blur", "vertical_crop", "landscape"];
  }, [render]);

  const verticalModes = availableModes.filter((m) => m !== "landscape");

  const [activeTab, setActiveTab] = useState<PreviewTab>(() => availableModes[0] || "vertical_blur");
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<boolean>(false);
  const [isSelecting, setIsSelecting] = useState<boolean>(false);

  const blurVideoRef = useRef<HTMLVideoElement | null>(null);
  const cropVideoRef = useRef<HTMLVideoElement | null>(null);

  const startSec = render.clip?.start_seconds ?? render.request?.start_seconds ?? 0;
  const durationSec = render.clip?.duration_seconds ?? render.request?.duration_seconds ?? 0;
  const endSec = startSec + durationSec;

  const isSelected = Boolean(render.upload_selection?.is_selected);
  const preferredFormat = render.upload_selection?.preferred_format || availableModes[0] || "vertical_blur";

  const activeOutput = render.outputs?.[activeTab];

  // Synchronized playback controls for compare mode
  const handlePlayBoth = () => {
    if (blurVideoRef.current && cropVideoRef.current) {
      blurVideoRef.current.currentTime = 0;
      cropVideoRef.current.currentTime = 0;
      blurVideoRef.current.play().catch(() => {});
      cropVideoRef.current.play().catch(() => {});
    }
  };

  const handlePauseBoth = () => {
    if (blurVideoRef.current && cropVideoRef.current) {
      blurVideoRef.current.pause();
      cropVideoRef.current.pause();
    }
  };

  const handleToggleUpload = async (targetFormat?: string) => {
    setIsSelecting(true);
    try {
      await onToggleSelectForUpload(
        render.clip_id,
        isSelected,
        targetFormat || preferredFormat
      );
    } finally {
      setIsSelecting(false);
    }
  };

  const handleDeleteClick = async () => {
    setIsDeleting(true);
    try {
      await onDelete(render.clip_id);
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  return (
    <div
      className={`group relative rounded-2xl transition-all duration-300 overflow-hidden flex flex-col ${
        isCardSelected
          ? "bg-slate-900/95 border-2 border-rose-500 shadow-xl shadow-rose-950/30 ring-2 ring-rose-500/50"
          : isSelected
          ? "bg-slate-900/95 border-2 border-rose-500/60 shadow-xl shadow-rose-950/20"
          : "bg-slate-900/80 border border-white/10 hover:border-white/20 hover:shadow-xl hover:shadow-black/40"
      }`}
    >
      {/* Top Header: Video Title, Clip ID, Timestamp */}
      <div className="p-4 sm:p-5 border-b border-white/5 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            {onToggleCardSelect && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleCardSelect(render.clip_id);
                }}
                className={`mt-0.5 w-5 h-5 rounded-lg border flex items-center justify-center transition-all shrink-0 cursor-pointer ${
                  isCardSelected
                    ? "bg-rose-600 border-rose-500 text-white shadow-sm shadow-rose-900/50"
                    : "bg-slate-950/80 border-white/20 hover:border-white/40 text-transparent hover:text-slate-600"
                }`}
                title={isCardSelected ? "Deselect render" : "Select render"}
              >
                <Check className="w-3.5 h-3.5 stroke-[3]" />
              </button>
            )}
            <div className="space-y-1 min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-rose-500/15 text-rose-300 border border-rose-500/25">
                  {render.request?.crop_preset || "Highlight"}
                </span>
                <span className="text-xs text-slate-400 font-medium">
                  {render.channel_name || "VOD"}
                </span>
              </div>
              <h3 className="font-bold text-sm sm:text-base text-slate-100 line-clamp-1 group-hover:text-rose-200 transition-colors">
                {render.video_title || render.clip_id}
              </h3>
            </div>
          </div>

          {/* Upload Selection Star Badge */}
          <button
            type="button"
            onClick={() => handleToggleUpload()}
            disabled={isSelecting}
            title={isSelected ? "Remove from upload staging" : "Choose for upload"}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 cursor-pointer ${
              isSelected
                ? "bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-md shadow-emerald-950/40 hover:scale-105"
                : "bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-white/10 hover:border-rose-500/40"
            }`}
          >
            <Star
              className={`w-3.5 h-3.5 ${
                isSelected ? "fill-white text-white" : "text-amber-400"
              }`}
            />
            <span>{isSelected ? "Chosen for Upload" : "Choose for Upload"}</span>
          </button>
        </div>

        {/* Clip range metadata */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400 font-mono">
          <div className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span>
              {formatSeconds(startSec)} - {formatSeconds(endSec)} ({Math.round(durationSec)}s)
            </span>
          </div>
          <span>•</span>
          <span className="text-[11px] text-slate-500 truncate max-w-[200px]">
            {render.clip_id}
          </span>
          {render.created_at && (
            <>
              <span>•</span>
              <span className="text-[11px] text-slate-500">
                {new Date(render.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Format Selector Bar */}
      <div className="px-4 py-2 bg-slate-950/60 border-b border-white/5 flex items-center justify-between gap-2 overflow-x-auto">
        <div className="flex items-center gap-1">
          {availableModes.map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setActiveTab(mode)}
              className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg transition-all shrink-0 ${
                activeTab === mode
                  ? "bg-rose-600 text-white shadow-sm shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              {mode === "landscape" ? <Tv className="w-3 h-3" /> : <Smartphone className="w-3 h-3" />}
              <span>{MODE_NAMES[mode] || mode.replace("_", " ")}</span>
            </button>
          ))}
          {verticalModes.length >= 2 && (
            <button
              type="button"
              onClick={() => setActiveTab("compare")}
              className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg transition-all shrink-0 ${
                activeTab === "compare"
                  ? "bg-amber-600 text-white shadow-sm shadow-amber-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Columns className="w-3 h-3" />
              <span>Side-by-Side</span>
            </button>
          )}
        </div>

        {/* Quality / Resolution badge */}
        {activeTab !== "compare" && activeOutput && (
          <div className="hidden sm:flex items-center gap-1.5 text-[10px] text-slate-400 shrink-0 font-mono">
            <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
              {activeOutput.width}x{activeOutput.height}
            </span>
            <span>{formatBytes(activeOutput.size_bytes)}</span>
          </div>
        )}
      </div>

      {/* Video Preview Player Canvas */}
      <div className="relative bg-slate-950 p-3 sm:p-4 flex items-center justify-center min-h-[360px] overflow-hidden">
        {activeTab !== "compare" && (
          <div
            className={`w-full ${
              activeTab === "landscape" ? "max-w-[560px] aspect-video" : "max-w-[260px] aspect-[9/16]"
            } rounded-xl overflow-hidden bg-black shadow-2xl border border-white/10 relative`}
          >
            <video
              key={activeTab}
              src={getStreamUrl(render.clip_id, activeTab)}
              controls
              playsInline
              preload="metadata"
              className={`w-full h-full ${activeTab === "landscape" ? "object-contain" : "object-cover"}`}
            />
            <div className="absolute top-2 left-2 pointer-events-none">
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-black/70 backdrop-blur-md text-white border border-white/10">
                {MODE_NAMES[activeTab] || activeTab} ({activeTab === "landscape" ? "16:9" : "9:16"})
              </span>
            </div>
          </div>
        )}

        {activeTab === "compare" && verticalModes.length >= 2 && (
          <div className="w-full space-y-3">
            <div className="flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={handlePlayBoth}
                className="flex items-center gap-1.5 px-3 py-1 bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold rounded-lg shadow-md transition-all active:scale-95"
              >
                <Play className="w-3.5 h-3.5 fill-black" />
                <span>Play Both</span>
              </button>
              <button
                type="button"
                onClick={handlePauseBoth}
                className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg border border-white/10 transition-all"
              >
                <span>Pause</span>
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:gap-4 max-w-lg mx-auto">
              <div className="space-y-1.5">
                <div className="text-center">
                  <span className="text-[11px] font-semibold text-rose-300">
                    {MODE_NAMES[verticalModes[0]] || verticalModes[0]}
                  </span>
                </div>
                <div className="w-full aspect-[9/16] rounded-xl overflow-hidden bg-black shadow-xl border border-white/10">
                  <video
                    ref={blurVideoRef}
                    src={getStreamUrl(render.clip_id, verticalModes[0])}
                    controls
                    playsInline
                    preload="metadata"
                    className="w-full h-full object-contain"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="text-center">
                  <span className="text-[11px] font-semibold text-rose-300">
                    {MODE_NAMES[verticalModes[1]] || verticalModes[1]}
                  </span>
                </div>
                <div className="w-full aspect-[9/16] rounded-xl overflow-hidden bg-black shadow-xl border border-white/10">
                  <video
                    ref={cropVideoRef}
                    src={getStreamUrl(render.clip_id, verticalModes[1])}
                    controls
                    playsInline
                    preload="metadata"
                    className="w-full h-full object-contain"
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Format-specific upload selection bar */}
      <div className="px-4 py-3 bg-slate-950/80 border-t border-white/5 space-y-2">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2 text-slate-300">
            <span className="text-slate-400">Target for Upload:</span>
            <span className="font-semibold text-rose-300 capitalize">
              {(MODE_NAMES[preferredFormat] || preferredFormat).replace("_", " ")}
            </span>
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400">Format to publish:</span>
            {availableModes.map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => handleToggleUpload(mode)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  preferredFormat === mode && isSelected
                    ? "bg-rose-600 text-white font-bold"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                {mode.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>

        {/* Audio and engine tags */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-300 border border-white/5 flex items-center gap-1">
            <Volume2 className="w-3 h-3 text-slate-400" />
            <span>
              {render.audio_config?.has_narration ? "Voiceover Ducked" : "Original Game Audio"}
            </span>
          </span>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-300 border border-white/5 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-rose-400" />
            <span>{render.outputs?.landscape?.encoder || "Apple VideoToolbox"}</span>
          </span>
          {(render.render_stats?.total_render_seconds || render.render_duration_seconds) && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-950/60 text-emerald-400 border border-emerald-500/20">
              Rendered in{" "}
              {render.render_stats?.total_render_seconds ?? render.render_duration_seconds}s
            </span>
          )}
        </div>
      </div>

      {/* Card Footer: Downloads & Management */}
      <div className="p-4 border-t border-white/10 bg-slate-900/90 flex items-center justify-between gap-3 mt-auto">
        {/* Download links */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {availableModes.map((mode) => (
            <a
              key={mode}
              href={getStreamUrl(render.clip_id, mode)}
              download={`${render.clip_id}_${mode}.mp4`}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-200 border border-white/5 text-xs font-medium transition-colors"
            >
              <Download className="w-3 h-3 text-rose-400" />
              <span>{mode.replace("_", " ")} (.mp4)</span>
            </a>
          ))}
        </div>

        {/* Audit & Delete Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => onInspectManifest(render)}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-white/5 transition-colors cursor-pointer"
          >
            <FileCode className="w-3.5 h-3.5 text-slate-400" />
            <span>Manifest</span>
          </button>

          {showDeleteConfirm ? (
            <div className="flex items-center gap-1.5 animate-in fade-in">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="px-2 py-1.5 rounded-lg text-slate-400 hover:text-white text-xs cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteClick}
                disabled={isDeleting}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold transition-colors cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{isDeleting ? "Deleting..." : "Confirm"}</span>
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
              title="Delete rendered clip"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
