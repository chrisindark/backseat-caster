"use client";

import { YoutubeIcon } from "@/components/icons";
import { ManifestModal } from "@/components/ManifestModal";
import { Navbar } from "@/components/Navbar";
import { RenderCard } from "@/components/RenderCard";
import { RenderJobRow } from "@/components/RenderJobRow";
import { UploadQueueModal } from "@/components/UploadQueueModal";
import {
  bulkDeleteRenders,
  checkBackendHealth,
  deleteRender,
  fetchRenderJobs,
  fetchRenders,
  getRender,
  retryRenderJob,
  updateUploadSelection,
} from "@/lib/api";
import { getQueryParam, setQueryParams } from "@/lib/modalHistory";
import {
  RenderJobResponse,
  RenderManifest,
  UploadSelectionPayload,
} from "@/types/video";
import {
  AlertTriangle,
  CheckCircle2,
  CheckSquare,
  Film,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Star,
  Trash2,
  Video,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

type ViewMode = "gallery" | "jobs";
type StatusFilter = "all" | "completed" | "active" | "failed" | "selected";

function RendersContent() {
  const searchParams = useSearchParams();
  const initialView = (searchParams.get("view") as ViewMode) || (getQueryParam("view") as ViewMode) || "gallery";
  const initialStatus = (searchParams.get("status") as StatusFilter) || (getQueryParam("status") as StatusFilter) || "all";
  const initialVideoId = searchParams.get("video_id") || getQueryParam("video_id") || "all";
  const initialSearch = searchParams.get("q") || getQueryParam("q") || "";

  const [renders, setRenders] = useState<RenderManifest[]>([]);
  const [jobs, setJobs] = useState<RenderJobResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);

  // View & Filters (synchronized with search parameters)
  const [viewMode, setViewModeState] = useState<ViewMode>(
    initialView === "jobs" ? "jobs" : "gallery"
  );
  const [selectedVideoId, setSelectedVideoIdState] = useState<string>(initialVideoId);
  const [statusFilter, setStatusFilterState] = useState<StatusFilter>(
    ["all", "completed", "active", "failed", "selected"].includes(initialStatus)
      ? initialStatus
      : "all"
  );
  const [searchQuery, setSearchQueryState] = useState<string>(initialSearch);

  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeState(mode);
    setQueryParams({ view: mode === "gallery" ? null : mode }, { replace: true });
  }, []);

  const setStatusFilter = useCallback((status: StatusFilter) => {
    setStatusFilterState(status);
    setQueryParams({ status: status === "all" ? null : status }, { replace: true });
  }, []);

  const setSelectedVideoId = useCallback((vid: string) => {
    setSelectedVideoIdState(vid);
    setQueryParams({ video_id: vid === "all" ? null : vid }, { replace: true });
  }, []);

  const setSearchQuery = useCallback((q: string) => {
    setSearchQueryState(q);
    setQueryParams({ q: q.trim() ? q.trim() : null }, { replace: true });
  }, []);

  // Bulk selection & deletion
  const [selectedClipIds, setSelectedClipIds] = useState<Set<string>>(new Set());
  const [isBulkDeleting, setIsBulkDeleting] = useState<boolean>(false);
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState<boolean>(false);

  // Modals with browser history tracking
  const [inspectingManifest, setInspectingManifest] = useState<RenderManifest | null>(null);
  const [showUploadQueueModal, setShowUploadQueueModal] = useState<boolean>(false);

  const openManifestModal = useCallback((manifest: RenderManifest) => {
    setInspectingManifest(manifest);
    setShowUploadQueueModal(false);
    setQueryParams({ manifest: manifest.clip_id, uploadQueue: null });
  }, []);

  const closeManifestModal = useCallback(() => {
    setInspectingManifest(null);
    setQueryParams({ manifest: null });
  }, []);

  const openUploadQueueModal = useCallback(() => {
    setShowUploadQueueModal(true);
    setInspectingManifest(null);
    setQueryParams({ uploadQueue: "true", manifest: null });
  }, []);

  const closeUploadQueueModal = useCallback(() => {
    setShowUploadQueueModal(false);
    setQueryParams({ uploadQueue: null });
  }, []);

  const rendersRef = useRef<RenderManifest[]>(renders);
  useEffect(() => {
    rendersRef.current = renders;
  }, [renders]);

  const syncModalsFromUrl = useCallback(
    async (currentRenders?: RenderManifest[]) => {
      const manifestId = getQueryParam("manifest") || getQueryParam("clipId");
      const isUploadQueue = getQueryParam("uploadQueue") === "true";

      if (manifestId) {
        setShowUploadQueueModal(false);
        const list: RenderManifest[] = currentRenders || rendersRef.current;
        const found = list.find((r: RenderManifest) => r.clip_id === manifestId);
        if (found) {
          setInspectingManifest(found);
        } else {
          try {
            const fetched = await getRender(manifestId);
            setInspectingManifest(fetched);
          } catch {
            setQueryParams({ manifest: null }, { replace: true });
          }
        }
      } else if (isUploadQueue) {
        setShowUploadQueueModal(true);
        setInspectingManifest(null);
      } else {
        setInspectingManifest(null);
        setShowUploadQueueModal(false);
      }
    },
    []
  );

  // Status notifications
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const showToast = useCallback((msg: string, durationMs = 3500) => {
    if (toastTimeoutRef.current) {
      clearTimeout(toastTimeoutRef.current);
    }
    setToastMessage(msg);
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
      toastTimeoutRef.current = null;
    }, durationMs);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) {
        clearTimeout(toastTimeoutRef.current);
      }
    };
  }, []);

  // Load all renders and jobs
  const loadData = useCallback(async () => {
    try {
      const [rendersRes, jobsRes, health] = await Promise.all([
        fetchRenders(),
        fetchRenderJobs({ limit: 100 }),
        checkBackendHealth(),
      ]);

      const items = rendersRes.items || [];
      setRenders(items);
      setJobs(jobsRes.items || []);
      setBackendHealthy(health);
    } catch (err) {
      console.error("Error loading renders and jobs:", err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  // Initial load and URL modal restoration
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const [rendersRes, jobsRes, health] = await Promise.all([
          fetchRenders(),
          fetchRenderJobs({ limit: 100 }),
          checkBackendHealth(),
        ]);
        if (!cancelled) {
          const items = rendersRes.items || [];
          setRenders(items);
          setJobs(jobsRes.items || []);
          setBackendHealthy(health);
          setIsLoading(false);
          await syncModalsFromUrl(items);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Error loading renders and jobs:", err);
          setIsLoading(false);
        }
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Listen to browser Back/Forward navigation to sync modal & tab filter states
  useEffect(() => {
    const onPopState = () => {
      syncModalsFromUrl();
      const v = (getQueryParam("view") as ViewMode) || "gallery";
      const s = (getQueryParam("status") as StatusFilter) || "all";
      const vid = getQueryParam("video_id") || "all";
      const q = getQueryParam("q") || "";
      setViewModeState(v === "jobs" ? "jobs" : "gallery");
      setStatusFilterState(
        ["all", "completed", "active", "failed", "selected"].includes(s) ? s : "all"
      );
      setSelectedVideoIdState(vid);
      setSearchQueryState(q);
    };

    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
    };
  }, [syncModalsFromUrl]);

  // Real-time polling when jobs are active
  const hasActiveJobs = useMemo(() => {
    return jobs.some((j) => j.status === "pending" || j.status === "rendering");
  }, [jobs]);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;

    const startPolling = () => {
      if (hasActiveJobs && !interval && document.visibilityState === "visible") {
        interval = setInterval(() => {
          loadData();
        }, 2500);
      }
    };

    const stopPolling = () => {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        startPolling();
        if (hasActiveJobs) loadData();
      } else {
        stopPolling();
      }
    };

    startPolling();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [hasActiveJobs, loadData]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await loadData();
  };

  // Upload selection toggle
  const handleToggleSelectForUpload = async (
    clipId: string,
    isCurrentlySelected: boolean,
    preferredFormat: string
  ) => {
    try {
      const newSelected = !isCurrentlySelected;
      await updateUploadSelection(clipId, {
        is_selected: newSelected,
        preferred_format: preferredFormat,
      });

      // Update local state optimistically
      setRenders((prev) =>
        prev.map((r) =>
          r.clip_id === clipId
            ? {
                ...r,
                upload_selection: {
                  ...(r.upload_selection || {}),
                  is_selected: newSelected,
                  preferred_format: preferredFormat,
                },
              }
            : r
        )
      );

      setJobs((prev) =>
        prev.map((j) =>
          j.clip_id === clipId
            ? {
                ...j,
                is_selected_for_upload: newSelected,
                selected_format: preferredFormat,
              }
            : j
        )
      );

      showToast(
        newSelected
          ? `Added ${clipId} to upload staging`
          : `Removed ${clipId} from upload staging`
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("Failed to update upload selection:", err);
      showToast(`Error: ${msg || "Failed to update"}`, 4000);
    }
  };

  // Update selection details from modal
  const handleUpdateSelectionFromModal = async (
    clipId: string,
    payload: UploadSelectionPayload
  ) => {
    await updateUploadSelection(clipId, payload);
    // Reload data to synchronize
    await loadData();
  };

  // Clear all selections
  const handleClearAllSelections = async () => {
    const selected = renders.filter((r) => r.upload_selection?.is_selected);
    await Promise.all(
      selected.map((r) =>
        updateUploadSelection(r.clip_id, {
          is_selected: false,
        })
      )
    );
    await loadData();
    showToast("Cleared all upload staging selections", 3000);
  };

  // Delete render
  const handleDeleteRender = async (clipId: string) => {
    try {
      await deleteRender(clipId);
      setRenders((prev) => prev.filter((r) => r.clip_id !== clipId));
      setJobs((prev) => prev.filter((j) => j.clip_id !== clipId && j.job_id !== clipId));
      setSelectedClipIds((prev) => {
        if (!prev.has(clipId)) return prev;
        const next = new Set(prev);
        next.delete(clipId);
        return next;
      });
      showToast(`Deleted render ${clipId}`, 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("Delete failed:", err);
      showToast(`Delete failed: ${msg}`, 4000);
    }
  };

  // Bulk selection handlers
  const handleToggleSelectClip = useCallback((clipId: string) => {
    setSelectedClipIds((prev) => {
      const next = new Set(prev);
      if (next.has(clipId)) {
        next.delete(clipId);
      } else {
        next.add(clipId);
      }
      return next;
    });
  }, []);

  const handleDeselectAll = useCallback(() => {
    setSelectedClipIds(new Set());
  }, []);

  const handleConfirmBulkDelete = async () => {
    if (selectedClipIds.size === 0) return;
    setIsBulkDeleting(true);
    try {
      const idsToDelete = Array.from(selectedClipIds);
      const res = await bulkDeleteRenders(idsToDelete, { sync: true });
      const deletedSet = new Set(res.deleted_clip_ids);

      setRenders((prev) => prev.filter((r) => !deletedSet.has(r.clip_id)));
      setJobs((prev) =>
        prev.filter((j) => !deletedSet.has(j.clip_id) && !deletedSet.has(j.job_id))
      );
      setSelectedClipIds(new Set());
      setShowBulkDeleteConfirm(false);
      showToast(res.message || `Deleted ${res.deleted_count} renders`, 3500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("Bulk delete failed:", err);
      showToast(`Bulk delete failed: ${msg}`, 4500);
    } finally {
      setIsBulkDeleting(false);
    }
  };

  // Retry job
  const handleRetryJob = async (jobId: string) => {
    try {
      await retryRenderJob(jobId);
      showToast(`Re-queued job ${jobId}`, 3000);
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("Retry failed:", err);
      showToast(`Retry failed: ${msg}`, 4000);
    }
  };

  // Unique videos list for filter dropdown
  const availableVideos = useMemo(() => {
    const map = new Map<string, string>();
    renders.forEach((r) => {
      const vidId = r.video_id || (r.source?.path ? r.source.path.split("/").pop()?.split(".")[0] : null);
      if (vidId) {
        map.set(vidId, r.video_title || `Video ${vidId}`);
      }
    });
    jobs.forEach((j) => {
      if (j.video_id) {
        map.set(j.video_id, j.video_title || `Video ${j.video_id}`);
      }
    });
    return Array.from(map.entries()).map(([id, title]) => ({ id, title }));
  }, [renders, jobs]);

  // Selected renders count
  const selectedForUploadList = useMemo(() => {
    return renders.filter((r) => r.upload_selection?.is_selected);
  }, [renders]);

  // Filtered renders
  const filteredRenders = useMemo(() => {
    return renders.filter((r) => {
      // Video filter
      if (selectedVideoId !== "all") {
        const vidId =
          r.video_id ||
          (r.source?.path ? r.source.path.split("/").pop()?.split(".")[0] : null) ||
          r.clip_id;
        if (vidId !== selectedVideoId && !vidId.includes(selectedVideoId)) return false;
      }

      // Status filter
      if (statusFilter === "selected" && !r.upload_selection?.is_selected) {
        return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = (r.video_title || "").toLowerCase().includes(q);
        const matchClip = r.clip_id.toLowerCase().includes(q);
        const matchPreset = (r.request?.crop_preset || "").toLowerCase().includes(q);
        if (!matchTitle && !matchClip && !matchPreset) return false;
      }

      return true;
    });
  }, [renders, selectedVideoId, statusFilter, searchQuery]);

  // Filtered jobs
  const filteredJobs = useMemo(() => {
    return jobs.filter((j) => {
      // Video filter
      if (selectedVideoId !== "all" && j.video_id !== selectedVideoId) {
        return false;
      }

      // Status filter
      if (statusFilter === "completed" && j.status !== "completed") return false;
      if (statusFilter === "active" && j.status !== "rendering" && j.status !== "pending") return false;
      if (statusFilter === "failed" && j.status !== "failed") return false;
      if (statusFilter === "selected" && !j.is_selected_for_upload) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = (j.video_title || "").toLowerCase().includes(q);
        const matchJob = j.job_id.toLowerCase().includes(q);
        const matchClip = j.clip_id.toLowerCase().includes(q);
        if (!matchTitle && !matchJob && !matchClip) return false;
      }

      return true;
    });
  }, [jobs, selectedVideoId, statusFilter, searchQuery]);

  const handleSelectAllCurrent = useCallback(() => {
    const ids =
      viewMode === "gallery"
        ? filteredRenders.map((r) => r.clip_id)
        : filteredJobs.map((j) => j.clip_id);
    setSelectedClipIds(new Set(ids));
  }, [viewMode, filteredRenders, filteredJobs]);

  // Jump from job to render
  const handleViewRender = (clipId: string) => {
    setViewMode("gallery");
    setSearchQuery(clipId);
  };

  return (
    <div className="min-h-screen bg-[#090a0f] text-slate-100 flex flex-col selection:bg-rose-500 selection:text-white">
      {/* Navbar */}
      <Navbar backendHealthy={backendHealthy} />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6 space-y-8">
        {/* Toast Alert Notice */}
        {toastMessage && (
          <div className="p-3 bg-slate-900 border border-rose-500/30 text-rose-300 rounded-xl text-xs flex items-center justify-between shadow-xl animate-in fade-in">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{toastMessage}</span>
            </div>
            <button
              onClick={() => setToastMessage(null)}
              className="text-slate-400 hover:text-white text-xs"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Hero Banner & KPI Stats */}
        <section className="relative rounded-3xl p-6 sm:p-8 bg-gradient-to-br from-slate-900/90 via-slate-900/60 to-rose-950/20 border border-white/10 shadow-2xl backdrop-blur-xl overflow-hidden">
          <div className="absolute top-0 right-0 -mt-12 -mr-12 w-96 h-96 bg-rose-600/10 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute bottom-0 left-1/3 -mb-12 w-64 h-64 bg-amber-500/5 rounded-full blur-2xl pointer-events-none" />

          <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs font-semibold">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Render Engine & Publishing Hub</span>
              </div>
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-white">
                Render Jobs & Multi-Format Studio
              </h1>
              <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
                Review rendered clips across your videos, compare landscape master and vertical formats, and choose which clips to upload to YouTube.
              </p>
            </div>

            {/* Quick KPI stats */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 shrink-0">
              <div className="p-3.5 rounded-2xl bg-slate-900/90 border border-white/10 shadow-lg">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                  Completed Renders
                </span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-2xl font-black text-white">{renders.length}</span>
                  <span className="text-[11px] text-emerald-400 font-semibold">
                    {renders.length * 3} exports
                  </span>
                </div>
              </div>

              <div className="p-3.5 rounded-2xl bg-slate-900/90 border border-white/10 shadow-lg">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                  Active Jobs
                </span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-2xl font-black text-sky-400">
                    {jobs.filter((j) => j.status === "rendering" || j.status === "pending").length}
                  </span>
                  {hasActiveJobs && (
                    <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping inline-block" />
                  )}
                </div>
              </div>

              <div
                onClick={openUploadQueueModal}
                className="col-span-2 sm:col-span-1 p-3.5 rounded-2xl bg-gradient-to-br from-rose-950/40 to-slate-900/90 border border-rose-500/30 shadow-lg hover:border-rose-500/60 transition-all cursor-pointer group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-rose-300 uppercase tracking-wider block">
                    Upload Staging
                  </span>
                  <Star className="w-3.5 h-3.5 fill-rose-400 text-rose-400 group-hover:scale-110 transition-transform" />
                </div>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="text-2xl font-black text-rose-400">
                    {selectedForUploadList.length}
                  </span>
                  <span className="text-[11px] text-slate-400 underline group-hover:text-white">
                    Review Queue →
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* View Mode & Filter Controls */}
        <section className="space-y-4">
          <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 p-2 bg-slate-900/70 border border-white/10 rounded-2xl backdrop-blur-md">
            {/* View Switcher: Gallery vs Jobs */}
            <div className="flex items-center gap-1 p-1 bg-slate-950/80 rounded-xl border border-white/5">
              <button
                type="button"
                onClick={() => setViewMode("gallery")}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                  viewMode === "gallery"
                    ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                }`}
              >
                <Film className="w-4 h-4" />
                <span>Renders Gallery ({renders.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setViewMode("jobs")}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                  viewMode === "jobs"
                    ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                }`}
              >
                <Layers className="w-4 h-4" />
                <span>Job Queue & Monitor ({jobs.length})</span>
                {hasActiveJobs && (
                  <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse" />
                )}
              </button>
            </div>

            {/* Video Selector Dropdown */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2 bg-slate-950/80 px-3 py-1.5 rounded-xl border border-white/5 text-xs text-slate-300">
                <Video className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <label className="text-[11px] text-slate-400 whitespace-nowrap">Filter Video:</label>
                <select
                  value={selectedVideoId}
                  onChange={(e) => setSelectedVideoId(e.target.value)}
                  className="bg-transparent text-slate-100 font-semibold focus:outline-none cursor-pointer max-w-[200px] truncate"
                >
                  <option value="all" className="bg-slate-900 text-slate-100">
                    All Source Videos ({availableVideos.length})
                  </option>
                  {availableVideos.map((v) => (
                    <option key={v.id} value={v.id} className="bg-slate-900 text-slate-100">
                      {v.title}
                    </option>
                  ))}
                </select>
              </div>

              {/* Refresh button */}
              <button
                type="button"
                onClick={handleManualRefresh}
                disabled={isRefreshing}
                className="p-2 rounded-xl bg-slate-950/80 hover:bg-slate-800 text-slate-300 hover:text-white border border-white/5 transition-all"
                title="Refresh Renders and Jobs"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
              </button>

              {/* Open Upload Queue Button */}
              <button
                type="button"
                onClick={openUploadQueueModal}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold shadow-md shadow-rose-900/30 transition-all cursor-pointer whitespace-nowrap"
              >
                <YoutubeIcon className="w-3.5 h-3.5" />
                <span>Upload Staging ({selectedForUploadList.length})</span>
              </button>
            </div>
          </div>

          {/* Secondary Filters Bar: Status Pills & Search */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            {/* Status Pills */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
              <button
                type="button"
                onClick={() => setStatusFilter("all")}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                  statusFilter === "all"
                    ? "bg-slate-800 text-white border border-white/20"
                    : "text-slate-400 hover:text-white hover:bg-slate-900"
                }`}
              >
                All
              </button>
              <button
                type="button"
                onClick={() => setStatusFilter("selected")}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                  statusFilter === "selected"
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                    : "text-slate-400 hover:text-white hover:bg-slate-900"
                }`}
              >
                <Star className="w-3 h-3 fill-rose-400 text-rose-400" />
                <span>Chosen for Upload ({selectedForUploadList.length})</span>
              </button>

              {/* Quick Select All Toggle Button */}
              {((viewMode === "gallery" && filteredRenders.length > 0) ||
                (viewMode === "jobs" && filteredJobs.length > 0)) && (
                <button
                  type="button"
                  onClick={
                    selectedClipIds.size ===
                    (viewMode === "gallery" ? filteredRenders.length : filteredJobs.length)
                      ? handleDeselectAll
                      : handleSelectAllCurrent
                  }
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900/90 hover:bg-slate-800 text-slate-300 hover:text-white border border-white/10 text-xs font-semibold transition-colors"
                >
                  <CheckSquare className="w-3 h-3 text-rose-500" />
                  <span>
                    {selectedClipIds.size ===
                    (viewMode === "gallery" ? filteredRenders.length : filteredJobs.length)
                      ? "Deselect All"
                      : `Select All (${viewMode === "gallery" ? filteredRenders.length : filteredJobs.length})`}
                  </span>
                </button>
              )}
              {viewMode === "jobs" && (
                <>
                  <button
                    type="button"
                    onClick={() => setStatusFilter("active")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                      statusFilter === "active"
                        ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                        : "text-slate-400 hover:text-white hover:bg-slate-900"
                    }`}
                  >
                    Active / Queued
                  </button>
                  <button
                    type="button"
                    onClick={() => setStatusFilter("completed")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                      statusFilter === "completed"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "text-slate-400 hover:text-white hover:bg-slate-900"
                    }`}
                  >
                    Completed
                  </button>
                  <button
                    type="button"
                    onClick={() => setStatusFilter("failed")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                      statusFilter === "failed"
                        ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                        : "text-slate-400 hover:text-white hover:bg-slate-900"
                    }`}
                  >
                    Failed
                  </button>
                </>
              )}
            </div>

            {/* Search Input */}
            <div className="relative max-w-xs w-full">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search clips or titles..."
                className="w-full pl-9 pr-3 py-1.5 bg-slate-900/90 border border-white/10 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
              />
            </div>
          </div>
        </section>

        {/* Content Area */}
        {isLoading ? (
          <div className="py-24 flex flex-col items-center justify-center space-y-3">
            <Loader2 className="w-8 h-8 text-rose-500 animate-spin" />
            <p className="text-sm font-semibold text-slate-400">Loading renders and jobs...</p>
          </div>
        ) : viewMode === "gallery" ? (
          /* Gallery of Completed Renders */
          filteredRenders.length === 0 ? (
            <div className="py-20 rounded-3xl bg-slate-900/40 border border-white/10 text-center space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-slate-800/80 flex items-center justify-center mx-auto text-slate-500">
                <Film className="w-8 h-8 text-rose-500" />
              </div>
              <div className="space-y-1 max-w-md mx-auto">
                <h3 className="text-base font-bold text-slate-200">
                  {searchQuery || statusFilter !== "all" || selectedVideoId !== "all"
                    ? "No Renders Match Filter"
                    : "No Rendered Clips Found"}
                </h3>
                <p className="text-xs text-slate-400">
                  {searchQuery || statusFilter !== "all" || selectedVideoId !== "all"
                    ? "Try resetting your search or filter options to see all rendered clips."
                    : "Render clips from your gameplay videos using Clip Studio in the Library."}
                </p>
              </div>
              <div>
                {searchQuery || statusFilter !== "all" || selectedVideoId !== "all" ? (
                  <button
                    onClick={() => {
                      setSearchQuery("");
                      setStatusFilter("all");
                      setSelectedVideoId("all");
                    }}
                    className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-xs font-semibold text-slate-200 transition-colors"
                  >
                    Reset Filters
                  </button>
                ) : (
                  <Link
                    href="/"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white shadow-lg shadow-rose-900/40 transition-all"
                  >
                    <Film className="w-3.5 h-3.5" />
                    <span>Go to Library to Render Clips</span>
                  </Link>
                )}
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6">
              {filteredRenders.map((render) => (
                <RenderCard
                  key={render.clip_id}
                  render={render}
                  isCardSelected={selectedClipIds.has(render.clip_id)}
                  onToggleCardSelect={handleToggleSelectClip}
                  onToggleSelectForUpload={(clipId, isSel, fmt) =>
                    handleToggleSelectForUpload(clipId, isSel, fmt)
                  }
                  onDelete={handleDeleteRender}
                  onInspectManifest={openManifestModal}
                />
              ))}
            </div>
          )
        ) : (
          /* Job Queue & Monitor View */
          filteredJobs.length === 0 ? (
            <div className="py-20 rounded-3xl bg-slate-900/40 border border-white/10 text-center space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-slate-800/80 flex items-center justify-center mx-auto text-slate-500">
                <Layers className="w-8 h-8 text-rose-500" />
              </div>
              <div className="space-y-1 max-w-md mx-auto">
                <h3 className="text-base font-bold text-slate-200">No Render Jobs in Queue</h3>
                <p className="text-xs text-slate-400">
                  Background and Celery jobs created for rendering clips will be monitored here.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredJobs.map((job) => (
                <RenderJobRow
                  key={job.job_id}
                  job={job}
                  isJobSelected={selectedClipIds.has(job.clip_id)}
                  onToggleJobSelect={handleToggleSelectClip}
                  onRetry={handleRetryJob}
                  onDelete={handleDeleteRender}
                  onViewRender={handleViewRender}
                />
              ))}
            </div>
          )
        )}
      </main>

      {/* Floating Bulk Action Bar */}
      {selectedClipIds.size > 0 && (
        <aside
          aria-label="Bulk actions"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 w-full max-w-xl px-4 animate-in slide-in-from-bottom-5 duration-200"
        >
          <div className="flex items-center justify-between gap-3 p-3 bg-slate-900/95 border border-rose-500/40 rounded-2xl shadow-2xl shadow-black/80 backdrop-blur-xl">
            <div className="flex items-center gap-2.5 pl-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
              <span className="text-xs font-bold text-white whitespace-nowrap">
                {selectedClipIds.size} {selectedClipIds.size === 1 ? "clip" : "clips"} selected
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleSelectAllCurrent}
                className="px-2.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white text-xs font-semibold transition-colors whitespace-nowrap"
              >
                Select All ({viewMode === "gallery" ? filteredRenders.length : filteredJobs.length})
              </button>

              <button
                type="button"
                onClick={handleDeselectAll}
                className="px-2.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white text-xs font-semibold transition-colors"
              >
                Clear
              </button>

              <button
                type="button"
                onClick={() => setShowBulkDeleteConfirm(true)}
                disabled={isBulkDeleting}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 text-white text-xs font-bold shadow-lg shadow-rose-950/50 transition-all cursor-pointer whitespace-nowrap"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Delete Selected ({selectedClipIds.size})</span>
              </button>
            </div>
          </div>
        </aside>
      )}

      {/* Bulk Delete Confirmation Modal */}
      {showBulkDeleteConfirm && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => !isBulkDeleting && setShowBulkDeleteConfirm(false)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-150"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md bg-slate-900 border border-rose-500/40 rounded-2xl p-6 shadow-2xl shadow-rose-950/30 space-y-5 animate-in zoom-in-95 duration-150"
          >
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 shrink-0">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h3 className="text-base font-bold text-white">
                  Delete {selectedClipIds.size} Render{selectedClipIds.size > 1 ? "s" : ""}?
                </h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  This will permanently delete all rendered MP4 files (landscape, vertical blur, crops) and job records for the selected clips from disk. This action cannot be undone.
                </p>
              </div>
            </div>

            <div className="p-3 bg-slate-950/70 rounded-xl border border-white/5 max-h-36 overflow-y-auto space-y-1 text-xs text-slate-400 font-mono">
              {Array.from(selectedClipIds).map((id) => (
                <div key={id} className="flex items-center gap-2 truncate">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" />
                  <span className="truncate">{id}</span>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowBulkDeleteConfirm(false)}
                disabled={isBulkDeleting}
                className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-slate-300 hover:text-white text-xs font-semibold transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmBulkDelete}
                disabled={isBulkDeleting}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold shadow-lg shadow-rose-900/40 transition-all cursor-pointer disabled:opacity-50"
              >
                {isBulkDeleting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Confirm Delete</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manifest Auditor Modal */}
      {inspectingManifest && (
        <ManifestModal
          manifest={inspectingManifest}
          onClose={closeManifestModal}
        />
      )}

      {/* Upload Queue Staging Modal */}
      {showUploadQueueModal && (
        <UploadQueueModal
          selectedRenders={selectedForUploadList}
          onUpdateSelection={handleUpdateSelectionFromModal}
          onClose={closeUploadQueueModal}
          onClearAll={handleClearAllSelections}
        />
      )}
    </div>
  );
}

export default function RendersPage() {
  return (
    <React.Suspense
      fallback={
        <div className="min-h-screen bg-[#090a0f] flex flex-col items-center justify-center">
          <Loader2 className="w-8 h-8 text-rose-500 animate-spin mb-3" />
          <p className="text-xs text-slate-400 font-medium">Loading Renders Dashboard...</p>
        </div>
      }
    >
      <RendersContent />
    </React.Suspense>
  );
}
