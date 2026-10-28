"use client";

import { PreflightReportItem } from "@/types/video";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  HardDrive,
  RefreshCw,
  Terminal,
  Video,
  X,
  Zap,
} from "lucide-react";
import React from "react";

interface PreflightModalProps {
  isOpen: boolean;
  onClose: () => void;
  report: PreflightReportItem | null;
  isLoading?: boolean;
  onRefresh?: () => void;
}

export const PreflightModal: React.FC<PreflightModalProps> = ({
  isOpen,
  onClose,
  report,
  isLoading = false,
  onRefresh,
}) => {
  if (!isOpen) return null;

  const checks = report?.checks;
  const ffmpeg = checks?.ffmpeg;
  const ffprobe = checks?.ffprobe;
  const ytdlp = checks?.yt_dlp;
  const disk = checks?.disk_space;

  const isHealthy = report?.ready && report.status === "healthy";
  const isDegraded = report?.ready && report.status === "degraded";
  const isUnhealthy = !report?.ready;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="w-full max-w-xl bg-[#0f111a] border border-white/10 rounded-2xl shadow-2xl shadow-black/80 overflow-hidden flex flex-col max-h-[90vh]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preflight-modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <h2 id="preflight-modal-title" className="text-sm font-bold text-white tracking-wide">
                System Preflight Diagnostics
              </h2>
              <p className="text-[11px] text-slate-400">
                Core CLI engines, media probes, and local disk verification
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={isLoading}
                title="Re-run preflight checks"
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50 cursor-pointer"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Status Pill Overview */}
        <div className="px-6 py-3 bg-black/40 border-b border-white/5 flex items-center justify-between text-xs">
          <span className="text-slate-400 font-medium">Overall System Readiness:</span>
          {isHealthy && (
            <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-bold">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>All Systems Operational</span>
            </span>
          )}
          {isDegraded && (
            <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 font-bold">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              <span>Degraded (Low Storage Warning)</span>
            </span>
          )}
          {isUnhealthy && (
            <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-300 font-bold">
              <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
              <span>Action Required (Missing Dependencies)</span>
            </span>
          )}
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4 overflow-y-auto">
          {/* FFmpeg & FFprobe Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* FFmpeg */}
            <div className="p-3.5 rounded-xl bg-slate-900/50 border border-white/5 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Video className="w-4 h-4 text-slate-400" />
                  <span className="text-xs font-bold text-white">FFmpeg</span>
                </div>
                {ffmpeg?.installed ? (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                    OK
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/10 text-rose-300 border border-rose-500/20">
                    MISSING
                  </span>
                )}
              </div>
              <p className="text-[11px] font-mono text-slate-400 truncate">
                {ffmpeg?.installed
                  ? `v${ffmpeg.version || "detected"} • ${ffmpeg.path || ""}`
                  : "Not found on system PATH"}
              </p>
              {ffmpeg?.remedy && !ffmpeg.installed && (
                <div className="p-2 rounded bg-black/60 border border-rose-500/20 text-[10px] text-rose-300">
                  <p className="font-semibold mb-0.5">Remedy:</p>
                  <code className="text-[10px] text-slate-300 select-all font-mono">
                    {ffmpeg.remedy}
                  </code>
                </div>
              )}
            </div>

            {/* FFprobe */}
            <div className="p-3.5 rounded-xl bg-slate-900/50 border border-white/5 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-slate-400" />
                  <span className="text-xs font-bold text-white">FFprobe</span>
                </div>
                {ffprobe?.installed ? (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                    OK
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/10 text-rose-300 border border-rose-500/20">
                    MISSING
                  </span>
                )}
              </div>
              <p className="text-[11px] font-mono text-slate-400 truncate">
                {ffprobe?.installed
                  ? `v${ffprobe.version || "detected"} • ${ffprobe.path || ""}`
                  : "Not found on system PATH"}
              </p>
              {ffprobe?.remedy && !ffprobe.installed && (
                <div className="p-2 rounded bg-black/60 border border-rose-500/20 text-[10px] text-rose-300">
                  <p className="font-semibold mb-0.5">Remedy:</p>
                  <code className="text-[10px] text-slate-300 select-all font-mono">
                    {ffprobe.remedy}
                  </code>
                </div>
              )}
            </div>
          </div>

          {/* yt-dlp */}
          <div className="p-3.5 rounded-xl bg-slate-900/50 border border-white/5 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-slate-400" />
                <span className="text-xs font-bold text-white">yt-dlp Ingestion Engine</span>
              </div>
              {ytdlp?.installed ? (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                  OK
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/10 text-rose-300 border border-rose-500/20">
                  MISSING
                </span>
              )}
            </div>
            <p className="text-[11px] font-mono text-slate-400 truncate">
              {ytdlp?.installed
                ? `v${ytdlp.version || "detected"} (${ytdlp.path || "module"})`
                : "Neither Python module nor CLI found"}
            </p>
            {ytdlp?.remedy && !ytdlp.installed && (
              <div className="p-2 rounded bg-black/60 border border-rose-500/20 text-[10px] text-rose-300">
                <p className="font-semibold mb-0.5">Remedy:</p>
                <code className="text-[10px] text-slate-300 select-all font-mono">
                  {ytdlp.remedy}
                </code>
              </div>
            )}
          </div>

          {/* Local Disk Storage Check */}
          <div className="p-4 rounded-xl bg-slate-900/50 border border-white/5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-slate-400" />
                <span className="text-xs font-bold text-white">Local Storage Partition</span>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                  disk?.status === "ok"
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
                    : disk?.status === "warning"
                    ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                    : "bg-rose-500/10 text-rose-300 border-rose-500/20"
                }`}
              >
                {disk?.free_gb !== undefined ? `${disk.free_gb} GB FREE` : "UNKNOWN"}
              </span>
            </div>

            {/* Storage Bar */}
            {disk?.total_gb ? (
              <div className="space-y-1.5">
                <div className="w-full h-2 rounded-full bg-black/60 overflow-hidden border border-white/5">
                  <div
                    className={`h-full transition-all duration-500 ${
                      disk.status === "error"
                        ? "bg-rose-500"
                        : disk.status === "warning"
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`}
                    style={{ width: `${Math.min(100, disk.percent_used || 0)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>Used: {disk.used_gb} GB ({disk.percent_used}%)</span>
                  <span>Total: {disk.total_gb} GB</span>
                </div>
              </div>
            ) : null}

            <p className="text-[10px] text-slate-400 font-mono truncate">
              Target directory: {disk?.path || "./data"}
            </p>

            {disk?.error && (
              <div className="p-2.5 rounded-lg bg-black/60 border border-amber-500/20 text-[11px] text-amber-300 space-y-1">
                <p>{disk.error}</p>
                {disk.remedy && <p className="text-[10px] text-slate-300">{disk.remedy}</p>}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-white/10 bg-slate-900/60 flex items-center justify-between text-xs">
          <span className="text-[11px] text-slate-500">
            BackseatCaster Local-First Pipeline
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-semibold transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
