"use client";

import { RenderJobResponse } from "@/types/video";
import { YoutubeIcon } from "./icons";
import { Tooltip, TruncatedText } from "./Tooltip";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clock,
  Film,
  Loader2,
  RotateCcw,
  Smartphone,
  Star,
  Trash2,
} from "lucide-react";
import React, { useState } from "react";

interface RenderJobRowProps {
  job: RenderJobResponse;
  onRetry: (jobId: string) => Promise<void>;
  onDelete: (clipId: string) => Promise<void>;
  onViewRender?: (clipId: string) => void;
  isJobSelected?: boolean;
  onToggleJobSelect?: (clipId: string) => void;
}

export const RenderJobRow: React.FC<RenderJobRowProps> = ({
  job,
  onRetry,
  onDelete,
  onViewRender,
  isJobSelected = false,
  onToggleJobSelect,
}) => {
  const [isRetrying, setIsRetrying] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<boolean>(false);
  const [showErrorDetails, setShowErrorDetails] = useState<boolean>(false);

  const handleRetry = async () => {
    setIsRetrying(true);
    try {
      await onRetry(job.job_id);
    } finally {
      setIsRetrying(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(job.clip_id);
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const getStatusBadge = () => {
    switch (job.status) {
      case "completed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>Completed</span>
          </span>
        );
      case "rendering":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30 animate-pulse">
            <Loader2 className="w-3.5 h-3.5 text-sky-400 animate-spin" />
            <span>Rendering {Math.round(job.progress)}%</span>
          </span>
        );
      case "pending":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span>Queued</span>
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
            <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
            <span>Failed</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300">
            <span>{job.status}</span>
          </span>
        );
    }
  };

  const formatSeconds = (sec: number): string => {
    if (isNaN(sec) || sec < 0) return "0:00";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h > 0) {
      return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    }
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const startFormatted = formatSeconds(job.start_seconds);

  return (
    <div
      className={`p-4 sm:p-5 rounded-2xl transition-all space-y-3 ${
        isJobSelected
          ? "bg-slate-900/95 border-2 border-rose-500 shadow-xl shadow-rose-950/30 ring-2 ring-rose-500/50"
          : "bg-slate-900/80 border border-white/10 hover:border-white/20"
      }`}
    >
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 min-w-0">
        <div className="flex items-center gap-3">
          {onToggleJobSelect && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleJobSelect(job.clip_id);
              }}
              className={`w-8 h-8 min-w-[32px] min-h-[32px] rounded-lg border flex items-center justify-center transition-all shrink-0 cursor-pointer ${
                isJobSelected
                  ? "bg-rose-600 border-rose-500 text-white shadow-sm shadow-rose-900/50"
                  : "bg-slate-950/80 border-white/20 hover:border-white/40 text-transparent hover:text-slate-600"
              }`}
              title={isJobSelected ? "Deselect job" : "Select job"}
            >
              <Check className="w-3.5 h-3.5 stroke-[3]" />
            </button>
          )}

          {/* Status Badge */}
          {getStatusBadge()}

          {/* Short candidate indicator */}
          {job.duration_seconds <= 60.5 && job.crop_preset !== "landscape" && (
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-purple-500/15 text-purple-300 border border-purple-500/30 flex items-center gap-1">
              <Smartphone className="w-3 h-3 text-purple-400" />
              <span>Short (≤60s)</span>
            </span>
          )}

          {/* Staged for upload indicator */}
          {job.is_selected_for_upload && (
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-rose-500/15 text-rose-300 border border-rose-500/30 flex items-center gap-1">
              <Star className="w-3 h-3 text-rose-400 fill-rose-400" />
              <span>Staged</span>
            </span>
          )}

          {/* Published YouTube Link */}
          {(job.youtube_upload_url || job.youtube_upload_status === "completed") && (
            <a
              href={job.youtube_upload_url || `https://youtube.com/shorts/${job.youtube_video_id}`}
              target="_blank"
              rel="noreferrer"
              className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-red-600/20 text-red-300 border border-red-500/40 flex items-center gap-1 hover:bg-red-600/30 transition-colors"
              title="View on YouTube"
            >
              <YoutubeIcon className="w-3 h-3 text-red-500" />
              <span>Published</span>
            </a>
          )}

          {/* Preset Pill */}
          <Tooltip content={`Framing Crop Preset: ${job.crop_preset || "third_person"}`}>
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-slate-800 text-slate-300 border border-white/5 cursor-help">
              {job.crop_preset || "third_person"}
            </span>
          </Tooltip>

          <Tooltip content={`Background Job ID: ${job.job_id}`}>
            <span className="text-xs text-slate-400 font-mono hidden sm:inline cursor-help">
              {job.job_id}
            </span>
          </Tooltip>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 self-end sm:self-auto">
          {job.status === "completed" && onViewRender && (
            <Tooltip content="Switch to gallery and inspect rendered formats">
              <button
                type="button"
                onClick={() => onViewRender(job.clip_id)}
                className="flex items-center gap-1.5 px-3.5 py-2.5 min-h-[40px] rounded-lg bg-rose-600/20 text-rose-300 hover:bg-rose-600/30 border border-rose-500/30 text-xs font-medium transition-colors cursor-pointer"
              >
                <Film className="w-3.5 h-3.5" />
                <span>View Renders</span>
              </button>
            </Tooltip>
          )}

          {job.status === "failed" && (
            <Tooltip content="Re-run the FFmpeg rendering pipeline for this highlight">
              <button
                type="button"
                onClick={handleRetry}
                disabled={isRetrying}
                className="flex items-center gap-1.5 px-3.5 py-2.5 min-h-[40px] rounded-lg bg-white/5 hover:bg-white/10 text-slate-200 border border-white/10 text-xs font-medium transition-colors cursor-pointer"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${isRetrying ? "animate-spin" : ""}`} />
                <span>Retry</span>
              </button>
            </Tooltip>
          )}

          {showDeleteConfirm ? (
            <div className="flex items-center gap-1.5 animate-in fade-in">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="px-2 py-1 rounded-lg text-slate-400 hover:text-white text-xs cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={isDeleting}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold transition-colors cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{isDeleting ? "Deleting..." : "Confirm"}</span>
              </button>
            </div>
          ) : (
            <Tooltip content="Permanently delete job and associated rendered files">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="p-2.5 min-w-[40px] min-h-[40px] flex items-center justify-center rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </Tooltip>
          )}
        </div>
      </div>

      {/* Progress Bar (when rendering) */}
      {job.status === "rendering" && (
        <div className="space-y-1">
          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-sky-500 to-rose-500 rounded-full transition-all duration-300"
              style={{ width: `${Math.max(5, Math.min(100, job.progress))}%` }}
            />
          </div>
          <div className="flex justify-between text-[11px] text-slate-400">
            <span>Rendering landscape, vertical blur & crop outputs...</span>
            <span>{Math.round(job.progress)}%</span>
          </div>
        </div>
      )}

      {/* Details Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1 text-xs">
        <div className="space-y-1 min-w-0 flex-1">
          <TruncatedText
            text={job.video_title || `Video ${job.video_id}`}
            lines={1}
            className="font-semibold text-slate-100"
            tooltipTitle="VOD Title"
          />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-slate-400 font-mono text-[11px]">
            <Tooltip content={`Full Clip ID: ${job.clip_id}`}>
              <span className="cursor-help">Clip: {job.clip_id}</span>
            </Tooltip>
            <span>•</span>
            <span>
              Start: {startFormatted} ({Math.round(job.duration_seconds)}s)
            </span>
            {job.encoder && (
              <>
                <span>•</span>
                <Tooltip content={`FFmpeg hardware/software encoder used: ${job.encoder}`}>
                  <span className="cursor-help">Encoder: {job.encoder}</span>
                </Tooltip>
              </>
            )}
            {job.render_duration_seconds && (
              <>
                <span>•</span>
                <Tooltip content="Total render elapsed time">
                  <span className="text-emerald-400 font-medium cursor-help">
                    {job.render_duration_seconds.toFixed(1)}s elapsed
                  </span>
                </Tooltip>
              </>
            )}
          </div>
        </div>

        {job.created_at && (
          <Tooltip content={`Job queued at ${new Date(job.created_at).toLocaleString()}`}>
            <div className="text-right text-[11px] text-slate-500 shrink-0 cursor-help">
              <span>{new Date(job.created_at).toLocaleString()}</span>
            </div>
          </Tooltip>
        )}
      </div>

      {/* Error Message Box */}
      {job.status === "failed" && job.error_message && (
        <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/20 text-xs text-rose-300 space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-semibold flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
              <span>Failure Reason</span>
            </span>
            <button
              type="button"
              onClick={() => setShowErrorDetails((v) => !v)}
              className="text-[11px] underline text-rose-400 cursor-pointer"
            >
              {showErrorDetails ? "Collapse" : "Expand"}
            </button>
          </div>
          <Tooltip content={showErrorDetails ? undefined : job.error_message} disabled={showErrorDetails}>
            <p
              className={`font-mono text-[11px] text-rose-200/90 ${
                showErrorDetails ? "whitespace-pre-wrap" : "line-clamp-2 cursor-help"
              }`}
            >
              {job.error_message}
            </p>
          </Tooltip>
        </div>
      )}
    </div>
  );
};