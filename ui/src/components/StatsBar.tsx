"use client";

import { CheckCircle2, DownloadCloud, Film, HardDrive } from "lucide-react";
import React from "react";

interface StatsBarProps {
  channelTitle?: string | null;
  totalVideos: number;
  downloadedCount: number;
  downloadingCount?: number;
  activeFilter: string;
  onFilterChange: (filter: string) => void;
}

export const StatsBar: React.FC<StatsBarProps> = ({
  channelTitle,
  totalVideos,
  downloadedCount,
  downloadingCount = 0,
  activeFilter,
  onFilterChange,
}) => {
  const notDownloadedCount = Math.max(0, totalVideos - downloadedCount - downloadingCount);

  const filters = [
    { id: "all", label: "All Videos", icon: Film, count: totalVideos },
    { id: "downloaded", label: "Downloaded", icon: CheckCircle2, count: downloadedCount },
    { id: "downloading", label: "Downloading", icon: DownloadCloud, count: downloadingCount },
    { id: "not_downloaded", label: "Not Downloaded", icon: HardDrive, count: notDownloadedCount },
  ];

  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 py-4 border-b border-white/5">
      {/* Channel info */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400">Current Channel:</span>
          <span className="text-sm font-bold text-white bg-slate-800/80 px-2.5 py-1 rounded-md border border-white/10">
            {channelTitle || "No Channel Selected"}
          </span>
        </div>
        <div className="hidden md:flex items-center gap-2 text-xs text-slate-400">
          <span>•</span>
          <span>{totalVideos} catalogued</span>
          <span>•</span>
          <span className="text-emerald-400 font-semibold">{downloadedCount} local</span>
          {downloadingCount > 0 && (
            <>
              <span>•</span>
              <span className="text-amber-400 font-semibold">{downloadingCount} downloading</span>
            </>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 p-1 bg-slate-900/80 rounded-xl border border-white/10 overflow-x-auto w-full sm:w-auto">
        {filters.map((f) => {
          const Icon = f.icon;
          const isActive = activeFilter === f.id;
          return (
            <button
              key={f.id}
              onClick={() => onFilterChange(f.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all whitespace-nowrap cursor-pointer ${
                isActive
                  ? "bg-rose-600 text-white shadow-sm shadow-rose-900/50"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{f.label}</span>
              {f.count !== undefined && f.count > 0 && (
                <span
                  className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                    isActive
                      ? "bg-white/20 text-white font-bold"
                      : "bg-white/5 text-slate-400"
                  }`}
                >
                  {f.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
