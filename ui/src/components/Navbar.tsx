"use client";

import { Badge } from "@radix-ui/themes";
import {
  AlertCircle,
  Compass,
  Film,
  Layers,
  Palette,
  Radio,
  RefreshCw,
  Scissors,
  Search,
  Sliders,
  UploadCloud,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { useEffect, useState } from "react";
import { fetchRenderJobs, fetchSystemHealth } from "@/lib/api";
import { PreflightReportItem } from "@/types/video";
import { PreflightModal } from "./PreflightModal";

interface NavbarProps {
  channelInput?: string;
  onChannelInputChange?: (val: string) => void;
  onSync?: () => void;
  isSyncing?: boolean;
  searchQuery?: string;
  onSearchChange?: (val: string) => void;
  backendHealthy?: boolean;
  activeJobsCount?: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  channelInput = "",
  onChannelInputChange,
  onSync,
  isSyncing = false,
  searchQuery,
  onSearchChange,
  backendHealthy = true,
  activeJobsCount: controlledJobsCount,
}) => {
  const pathname = usePathname();
  const [internalActiveJobs, setInternalActiveJobs] = useState<number>(0);
  const [preflightReport, setPreflightReport] = useState<PreflightReportItem | null>(null);
  const [isPreflightModalOpen, setIsPreflightModalOpen] = useState<boolean>(false);
  const [isPreflightLoading, setIsPreflightLoading] = useState<boolean>(false);
  const [bannerDismissed, setBannerDismissed] = useState<boolean>(false);

  // Load preflight status on mount
  const loadPreflight = async () => {
    setIsPreflightLoading(true);
    try {
      const health = await fetchSystemHealth();
      if (health?.preflight) {
        setPreflightReport(health.preflight);
      }
    } catch {
      // quiet fallback
    } finally {
      setIsPreflightLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const health = await fetchSystemHealth();
        if (mounted && health?.preflight) {
          setPreflightReport(health.preflight);
        }
      } catch {
        // quiet fallback
      }
    })();
    return () => {
      mounted = false;
    };
  }, [backendHealthy]);

  // Poll for active jobs if not controlled via props
  useEffect(() => {
    if (controlledJobsCount !== undefined || !backendHealthy) return;

    let mounted = true;
    const checkActiveJobs = async () => {
      try {
        const res = await fetchRenderJobs({ limit: 20 });
        if (mounted && res?.items) {
          const active = res.items.filter(
            (j) => j.status === "rendering" || j.status === "pending"
          ).length;
          setInternalActiveJobs(active);
        }
      } catch {
        // quiet failure
      }
    };

    checkActiveJobs();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") {
        checkActiveJobs();
      }
    }, 10000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [controlledJobsCount, backendHealthy]);

  const activeJobs = controlledJobsCount !== undefined ? controlledJobsCount : internalActiveJobs;

  return (
    <header className="sticky top-0 z-50 glass-nav border-b border-white/10 px-4 lg:px-8 py-3 backdrop-blur-xl">
      {/* Preflight Dependency Failure Alert Banner */}
      {preflightReport && !preflightReport.ready && !bannerDismissed && (
        <div className="max-w-7xl mx-auto mb-2 p-2 rounded-xl bg-rose-950/80 border border-rose-500/40 flex items-center justify-between text-xs text-rose-200 gap-3 animate-in fade-in">
          <div className="flex items-center gap-2 min-w-0">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span className="truncate">
              <strong>Preflight System Alert:</strong> Critical dependencies missing (
              {preflightReport.errors.length} issue{preflightReport.errors.length > 1 ? "s" : ""}). Video clipping/rendering cannot run.
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setIsPreflightModalOpen(true)}
              className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold text-[11px] transition-colors cursor-pointer"
            >
              View Instructions
            </button>
            <button
              type="button"
              onClick={() => setBannerDismissed(true)}
              className="text-rose-400 hover:text-white text-[11px] px-1.5 py-1"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand & Nav Links */}
        <div className="flex items-center gap-6 w-full md:w-auto justify-between md:justify-start">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/30 group-hover:scale-105 transition-transform">
              <Radio className="w-4 h-4 text-white animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400">
                  BackseatCaster
                </span>
                <Badge color="crimson" variant="surface" size="1">
                  AI Clip Engine
                </Badge>
              </div>
              <p className="text-[11px] text-slate-400">Gameplay Highlight Pipeline</p>
            </div>
          </Link>

          {/* Navigation Tabs - Refined Information Architecture */}
          <nav className="flex items-center p-1 bg-slate-900/90 border border-white/10 rounded-xl" aria-label="Main Navigation">
            <Link
              href="/"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname === "/" || pathname?.startsWith("/videos")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Film className="w-3.5 h-3.5" />
              <span>Library</span>
            </Link>

            <Link
              href="/studio"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname?.startsWith("/studio")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Scissors className="w-3.5 h-3.5" />
              <span>Create</span>
            </Link>

            <Link
              href="/renders"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname === "/renders" || (pathname?.startsWith("/renders") && !pathname?.startsWith("/renders/staging"))
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Renders & Jobs</span>
              {activeJobs > 0 && (
                <span className="ml-0.5 px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-400/30 animate-pulse">
                  {activeJobs}
                </span>
              )}
            </Link>

            <Link
              href="/staging"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname?.startsWith("/staging")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <UploadCloud className="w-3.5 h-3.5" />
              <span>Staging</span>
            </Link>

            <Link
              href="/channel"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname?.startsWith("/channel")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Palette className="w-3.5 h-3.5" />
              <span>Brand</span>
            </Link>

            <Link
              href="/youtube"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname?.startsWith("/youtube")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>Publish / YouTube</span>
            </Link>

            <Link
              href="/setup"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname?.startsWith("/setup")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Setup</span>
            </Link>
          </nav>

          {/* Backend & Preflight Status indicator */}
          <button
            type="button"
            onClick={() => setIsPreflightModalOpen(true)}
            title="Click to view system preflight checks & storage diagnostics"
            className="hidden xl:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/80 hover:bg-slate-800 border border-white/10 text-xs text-slate-300 transition-colors cursor-pointer"
          >
            <span
              className={`w-2 h-2 rounded-full ${
                !backendHealthy
                  ? "bg-rose-500 shadow-sm shadow-rose-500"
                  : preflightReport && !preflightReport.ready
                  ? "bg-rose-500 shadow-sm shadow-rose-500 animate-pulse"
                  : preflightReport?.status === "degraded"
                  ? "bg-amber-400 shadow-sm shadow-amber-400"
                  : "bg-emerald-400 shadow-sm shadow-emerald-400"
              }`}
            />
            <span className="font-medium">
              {!backendHealthy
                ? "API Offline"
                : preflightReport && !preflightReport.ready
                ? "Preflight Error"
                : preflightReport?.status === "degraded"
                ? "Low Storage"
                : "API Ready"}
            </span>
            <Zap className="w-3 h-3 text-slate-500 hover:text-slate-300 ml-0.5" />
          </button>
        </div>

        {/* Search Input (if callback provided) */}
        {onSearchChange && (
          <div className="flex-1 max-w-sm w-full">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery ?? ""}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Search video titles or keywords..."
                className="w-full pl-9 pr-4 py-1.5 bg-slate-900/90 border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
              />
            </div>
          </div>
        )}

        {/* Channel Selector & Sync Button (if provided) */}
        {onChannelInputChange && (
          <div className="flex items-center gap-2 w-full md:w-auto">
            <div className="relative flex-1 md:w-48">
              <input
                type="text"
                value={channelInput}
                onChange={(e) => onChannelInputChange(e.target.value)}
                placeholder="@Channel or URL"
                className="w-full pl-3 pr-2.5 py-1.5 bg-slate-900/90 border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
              />
            </div>
            {onSync && (
              <button
                onClick={onSync}
                disabled={isSyncing}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 disabled:bg-rose-800 disabled:opacity-70 text-white text-xs font-semibold rounded-lg shadow-md shadow-rose-900/40 transition-all cursor-pointer whitespace-nowrap active:scale-95"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                <span>{isSyncing ? "Syncing..." : "Sync"}</span>
              </button>
            )}
          </div>
        )}
      </div>

      <PreflightModal
        isOpen={isPreflightModalOpen}
        onClose={() => setIsPreflightModalOpen(false)}
        report={preflightReport}
        isLoading={isPreflightLoading}
        onRefresh={loadPreflight}
      />
    </header>
  );
};
