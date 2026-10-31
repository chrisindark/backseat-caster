"use client";

import {
  batchStageHighlights,
  deleteHighlightCandidates,
  detectHighlights,
  fetchChannelProfile,
  fetchHighlightCandidates,
  getHighlightStatus,
  getHighlightThumbnailUrl,
} from "@/lib/api";
import { useScrollLock } from "@/lib/useScrollLock";
import {
  HighlightCandidateItem,
  HighlightStatusResponse,
} from "@/types/video";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Award,
  Check,
  CheckSquare,
  ChevronRight,
  Clock,
  Copy,
  Crown,
  ExternalLink,
  Film,
  Flame,
  Layers,
  Loader2,
  Play,
  RotateCcw,
  Scissors,
  Sparkles,
  Square,
  Swords,
  Trash2,
  Trophy,
  X,
  Zap,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface HighlightCandidatesDrawerProps {
  isOpen: boolean;
  videoId: string;
  videoTitle?: string;
  onClose: () => void;
  onApplyToStudio: (candidate: HighlightCandidateItem) => void;
  onQuickRender?: (candidate: HighlightCandidateItem) => void;
  onCandidatesCountChange?: (count: number) => void;
}

type FilterCategory =
  | "all"
  | "team_wipe"
  | "multi_ko"
  | "clutch"
  | "crown_victory"
  | "round_qualified"
  | "eliminated"
  | "high_score";

function formatSeconds(sec: number): string {
  if (isNaN(sec) || sec < 0) return "0:00";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  if (h > 0) {
    return `${h}:${m < 10 ? "0" : ""}${m}:${s < 10 ? "0" : ""}${s}`;
  }
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

export const HighlightCandidatesDrawer: React.FC<HighlightCandidatesDrawerProps> = ({
  isOpen,
  videoId,
  videoTitle,
  onClose,
  onApplyToStudio,
  onQuickRender,
  onCandidatesCountChange,
}) => {
  useScrollLock(isOpen);

  const [candidates, setCandidates] = useState<HighlightCandidateItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanStatus, setScanStatus] = useState<HighlightStatusResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Filtering & Sorting
  const [lifecycleFilter, setLifecycleFilter] = useState<
    "all" | "left" | "rendered" | "uploaded"
  >("all");
  const [filterCategory, setFilterCategory] = useState<FilterCategory>("all");
  const [sortBy, setSortBy] = useState<"score" | "time">("score");

  // Selection & Batch Staging (Phase 8.5)
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(
    new Set()
  );
  const [isBatchStaging, setIsBatchStaging] = useState<boolean>(false);
  const [batchSuccessMessage, setBatchSuccessMessage] = useState<string | null>(
    null
  );
  const [batchMode, setBatchMode] = useState<string>("third_person");
  const [batchSchedule, setBatchSchedule] = useState<boolean>(true);

  useEffect(() => {
    fetchChannelProfile()
      .then((profile) => {
        if (profile.default_framing_preset) {
          setBatchMode(profile.default_framing_preset);
        }
      })
      .catch(() => {});
  }, []);

  // Interaction feedback states
  const [copiedTitleId, setCopiedTitleId] = useState<string | null>(null);
  const [appliedCandidateId, setAppliedCandidateId] = useState<string | null>(null);

  const isMountedRef = useRef<boolean>(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Close on ESC key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Load existing candidates
  const loadCandidates = useCallback(async () => {
    if (!videoId) return;
    try {
      const res = await fetchHighlightCandidates(videoId);
      if (!isMountedRef.current) return;
      const list = res.candidates || [];
      setCandidates(list);
      onCandidatesCountChange?.(list.length);
    } catch (err: unknown) {
      if (!isMountedRef.current) return;
      console.warn("Could not load candidates:", err);
    }
  }, [videoId, onCandidatesCountChange]);

  useEffect(() => {
    if (!isOpen || !videoId) return;
    let isCancelled = false;

    async function initDrawer() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const [candRes, statusRes] = await Promise.all([
          fetchHighlightCandidates(videoId),
          getHighlightStatus(videoId),
        ]);
        if (isCancelled || !isMountedRef.current) return;
        const list = candRes.candidates || [];
        setCandidates(list);
        onCandidatesCountChange?.(list.length);
        setScanStatus(statusRes);
        if (statusRes.status === "scanning" || statusRes.status === "pending") {
          setIsScanning(true);
        } else {
          setIsScanning(false);
        }
      } catch (err) {
        if (!isCancelled && isMountedRef.current) {
          console.warn("Failed to initialize highlight drawer:", err);
        }
      } finally {
        if (!isCancelled && isMountedRef.current) {
          setIsLoading(false);
        }
      }
    }

    initDrawer();

    return () => {
      isCancelled = true;
    };
  }, [isOpen, videoId, onCandidatesCountChange]);

  // Polling loop when scan is active
  useEffect(() => {
    if (!isScanning || !videoId) return;

    const interval = setInterval(async () => {
      try {
        const statusRes = await getHighlightStatus(videoId);
        if (!isMountedRef.current) return;
        setScanStatus(statusRes);

        if (statusRes.status === "completed") {
          setIsScanning(false);
          await loadCandidates();
        } else if (statusRes.status === "failed") {
          setIsScanning(false);
          setErrorMessage(statusRes.error || "Highlight detection failed. Please retry.");
        }
      } catch (err) {
        console.warn("Polling highlight status failed:", err);
      }
    }, 1800);

    return () => clearInterval(interval);
  }, [isScanning, videoId, loadCandidates]);

  // Trigger highlight scan
  const handleStartScan = async (forceRescan: boolean = false) => {
    if (!videoId) return;
    setErrorMessage(null);
    setIsScanning(true);
    try {
      const vtitle = videoTitle?.toLowerCase() || "";
      const detectedGame =
        vtitle.includes("fall guys") || vtitle.includes("fallguys")
          ? "fall_guys"
          : vtitle.includes("marvel rivals")
          ? "marvel_rivals"
          : undefined;

      await detectHighlights(videoId, {
        game: detectedGame,
        force_rescan: forceRescan,
        min_score: 0.5,
      });
      // Initial status check immediately
      const initialStatus = await getHighlightStatus(videoId);
      if (isMountedRef.current) {
        setScanStatus(initialStatus);
      }
    } catch (err: unknown) {
      if (!isMountedRef.current) return;
      setIsScanning(false);
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    }
  };

  // Clear candidates
  const handleClearCandidates = async () => {
    if (!videoId) return;
    if (!confirm("Are you sure you want to clear all detected highlights for this video?")) {
      return;
    }
    try {
      await deleteHighlightCandidates(videoId);
      setCandidates([]);
      onCandidatesCountChange?.(0);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to delete highlights: ${msg}`);
    }
  };

  const handleCopyTitle = (candidateId: string, title: string) => {
    navigator.clipboard.writeText(title);
    setCopiedTitleId(candidateId);
    setTimeout(() => {
      setCopiedTitleId(null);
    }, 2000);
  };

  const handleApply = (cand: HighlightCandidateItem) => {
    onApplyToStudio(cand);
    setAppliedCandidateId(cand.candidate_id);
    setTimeout(() => {
      setAppliedCandidateId(null);
    }, 2500);
  };

  // Phase 8.5: Lifecycle groupings
  const leftCandidates = useMemo(
    () =>
      candidates.filter(
        (c) => !c.processing_status || c.processing_status === "unprocessed"
      ),
    [candidates]
  );
  const renderedCandidates = useMemo(
    () => candidates.filter((c) => c.processing_status === "rendered"),
    [candidates]
  );
  const uploadedCandidates = useMemo(
    () => candidates.filter((c) => c.processing_status === "uploaded"),
    [candidates]
  );

  // Filtered & Sorted candidates
  const filteredCandidates = useMemo(() => {
    let result = [...candidates];

    // Tier 1: Lifecycle state filter
    if (lifecycleFilter === "left") {
      result = result.filter(
        (c) => !c.processing_status || c.processing_status === "unprocessed"
      );
    } else if (lifecycleFilter === "rendered") {
      result = result.filter((c) => c.processing_status === "rendered");
    } else if (lifecycleFilter === "uploaded") {
      result = result.filter((c) => c.processing_status === "uploaded");
    }

    // Tier 2: Event category filter
    if (filterCategory === "team_wipe") {
      result = result.filter(
        (c) => c.event_type === "team_wipe" || c.details?.is_team_wipe
      );
    } else if (filterCategory === "multi_ko") {
      result = result.filter((c) =>
        ["triple_ko", "double_ko", "team_wipe", "mega_ko", "ultra_ko"].includes(
          c.event_type
        )
      );
    } else if (filterCategory === "clutch") {
      result = result.filter(
        (c) =>
          c.event_type === "objective_clutch" ||
          c.details?.game_phase === "overtime"
      );
    } else if (filterCategory === "crown_victory") {
      result = result.filter((c) => c.event_type === "crown_victory");
    } else if (filterCategory === "round_qualified") {
      result = result.filter((c) => c.event_type === "round_qualified");
    } else if (filterCategory === "eliminated") {
      result = result.filter((c) => c.event_type === "eliminated");
    } else if (filterCategory === "high_score") {
      result = result.filter((c) => c.score >= 0.8);
    }

    if (sortBy === "score") {
      result.sort((a, b) => b.score - a.score);
    } else {
      result.sort((a, b) => a.start_seconds - b.start_seconds);
    }

    return result;
  }, [candidates, lifecycleFilter, filterCategory, sortBy]);

  const activePool = useMemo(() => {
    if (lifecycleFilter === "left") return leftCandidates;
    if (lifecycleFilter === "rendered") return renderedCandidates;
    if (lifecycleFilter === "uploaded") return uploadedCandidates;
    return candidates;
  }, [
    lifecycleFilter,
    leftCandidates,
    renderedCandidates,
    uploadedCandidates,
    candidates,
  ]);

  const teamWipeCount = useMemo(
    () =>
      activePool.filter(
        (c) => c.event_type === "team_wipe" || c.details?.is_team_wipe
      ).length,
    [activePool]
  );
  const multiKoCount = useMemo(
    () =>
      activePool.filter((c) =>
        ["triple_ko", "double_ko", "team_wipe", "mega_ko", "ultra_ko"].includes(
          c.event_type
        )
      ).length,
    [activePool]
  );
  const clutchCount = useMemo(
    () =>
      activePool.filter(
        (c) =>
          c.event_type === "objective_clutch" ||
          c.details?.game_phase === "overtime"
      ).length,
    [activePool]
  );
  const highScoreCount = useMemo(
    () => activePool.filter((c) => c.score >= 0.8).length,
    [activePool]
  );
  const crownCount = useMemo(
    () => activePool.filter((c) => c.event_type === "crown_victory").length,
    [activePool]
  );
  const qualifiedCount = useMemo(
    () => activePool.filter((c) => c.event_type === "round_qualified").length,
    [activePool]
  );
  const eliminatedCount = useMemo(
    () => activePool.filter((c) => c.event_type === "eliminated").length,
    [activePool]
  );

  const handleToggleSelect = (candidateId: string) => {
    setSelectedCandidateIds((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) {
        next.delete(candidateId);
      } else {
        next.add(candidateId);
      }
      return next;
    });
  };

  const handleSelectTopNLeft = (n: number) => {
    const leftSorted = [...leftCandidates].sort((a, b) => b.score - a.score);
    const topN = leftSorted.slice(0, n).map((c) => c.candidate_id);
    setSelectedCandidateIds(new Set(topN));
    setLifecycleFilter("left");
  };

  const handleExecuteBatchStage = async () => {
    if (selectedCandidateIds.size === 0 || !videoId) return;
    setIsBatchStaging(true);
    setErrorMessage(null);
    setBatchSuccessMessage(null);
    try {
      const res = await batchStageHighlights(videoId, {
        candidate_ids: Array.from(selectedCandidateIds),
        clipping_mode: batchMode,
        schedule: batchSchedule,
        same_day_catchup: true,
      });
      setSelectedCandidateIds(new Set());
      setBatchSuccessMessage(
        res.message || `Successfully enqueued ${res.staged_count} clips!`
      );
      setTimeout(() => setBatchSuccessMessage(null), 6000);
      await loadCandidates();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsBatchStaging(false);
    }
  };

  const getEventBadge = (cand: HighlightCandidateItem) => {
    const type = cand.event_type.toLowerCase();
    if (type === "team_wipe" || cand.details?.is_team_wipe) {
      return {
        label: "TEAM WIPE",
        icon: Crown,
        classes:
          "bg-gradient-to-r from-purple-500/25 via-fuchsia-500/20 to-purple-600/25 text-purple-200 border-purple-400/40 shadow-sm shadow-purple-950/50",
      };
    }
    if (type === "triple_ko" || type === "mega_ko" || type === "ultra_ko") {
      return {
        label: "TRIPLE KO",
        icon: Flame,
        classes:
          "bg-gradient-to-r from-rose-500/25 to-red-500/20 text-rose-200 border-rose-500/40 shadow-sm shadow-rose-950/50",
      };
    }
    if (type === "double_ko") {
      return {
        label: "DOUBLE KO",
        icon: Swords,
        classes:
          "bg-amber-500/20 text-amber-200 border-amber-500/40 shadow-sm shadow-amber-950/50",
      };
    }
    if (type === "objective_clutch" || cand.details?.game_phase === "overtime") {
      return {
        label: "CLUTCH VICTORY",
        icon: Trophy,
        classes:
          "bg-emerald-500/20 text-emerald-200 border-emerald-500/40 shadow-sm shadow-emerald-950/50",
      };
    }
    if (type === "crown_victory") {
      return {
        label: "CROWN VICTORY",
        icon: Crown,
        classes:
          "bg-gradient-to-r from-amber-500/30 via-yellow-500/25 to-amber-600/30 text-yellow-200 border-yellow-400/50 shadow-sm shadow-amber-950/50",
      };
    }
    if (type === "round_qualified") {
      return {
        label: "QUALIFIED!",
        icon: Zap,
        classes:
          "bg-gradient-to-r from-emerald-500/30 to-teal-500/25 text-emerald-200 border-emerald-400/50 shadow-sm shadow-emerald-950/50",
      };
    }
    if (type === "final_round") {
      return {
        label: "FINAL ROUND",
        icon: Flame,
        classes:
          "bg-gradient-to-r from-orange-500/30 to-rose-500/25 text-orange-200 border-orange-400/50 shadow-sm shadow-orange-950/50",
      };
    }
    if (type === "eliminated") {
      return {
        label: "ELIMINATED",
        icon: AlertCircle,
        classes:
          "bg-rose-950/40 text-rose-300 border-rose-800/60 shadow-sm shadow-black/50",
      };
    }
    if (type === "round_over") {
      return {
        label: "ROUND OVER",
        icon: Clock,
        classes:
          "bg-blue-900/30 text-blue-200 border-blue-500/40 shadow-sm shadow-blue-950/50",
      };
    }
    return {
      label: cand.event_type.replace("_", " ").toUpperCase(),
      icon: Zap,
      classes: "bg-blue-500/20 text-blue-200 border-blue-500/30",
    };
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.85) {
      return "text-emerald-400 border-emerald-500/40 bg-emerald-500/10";
    }
    if (score >= 0.7) {
      return "text-amber-300 border-amber-500/40 bg-amber-500/10";
    }
    return "text-purple-300 border-purple-500/40 bg-purple-500/10";
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity"
          />

          {/* Slide-over Drawer */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 260 }}
            className="relative w-full max-w-2xl bg-[#0e1017] border-l border-white/10 shadow-2xl flex flex-col h-full z-10"
          >
            {/* Header */}
            <div className="p-5 border-b border-white/10 bg-gradient-to-r from-rose-950/40 via-purple-950/20 to-black flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-gradient-to-br from-rose-600 to-purple-600 text-white shadow-lg shadow-rose-950/50">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-white tracking-tight">
                      AI Highlight Mining
                    </h2>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-mono bg-rose-500/20 text-rose-300 border border-rose-500/30">
                      Marvel Rivals Pass
                    </span>
                    {candidates.length > 0 && (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-bold font-mono bg-white/10 text-white border border-white/15">
                        {candidates.length} Mined
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 truncate max-w-sm">
                    {videoTitle || "Instant high-energy clips & killfeed chains"}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => handleStartScan(true)}
                  disabled={isScanning}
                  title="Force re-scan all action windows"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white rounded-lg border border-white/10 text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
                >
                  <RotateCcw className={`w-3.5 h-3.5 ${isScanning ? "animate-spin" : ""}`} />
                  <span className="hidden sm:inline">Re-scan</span>
                </button>

                {candidates.length > 0 && (
                  <button
                    type="button"
                    onClick={handleClearCandidates}
                    title="Clear mined highlights"
                    className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 rounded-lg transition-colors cursor-pointer"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}

                <button
                  type="button"
                  onClick={onClose}
                  className="p-2 rounded-full bg-black/40 hover:bg-white/10 text-slate-400 hover:text-white transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Live Progress Banner (if scanning) */}
            {isScanning && (
              <div className="p-4 bg-gradient-to-r from-rose-950/60 via-purple-950/40 to-black border-b border-rose-500/20 shrink-0">
                <div className="flex items-center justify-between text-xs mb-2">
                  <span className="flex items-center gap-2 text-rose-300 font-semibold">
                    <Loader2 className="w-4 h-4 animate-spin text-rose-400" />
                    <span>
                      {scanStatus?.stage || "Scanning audio excitement & HUD..."}
                    </span>
                  </span>
                  <span className="font-mono text-rose-400 font-bold">
                    {Math.round(scanStatus?.progress || 10)}%
                  </span>
                </div>
                <div className="w-full h-2 bg-black/60 rounded-full overflow-hidden border border-white/10">
                  <div
                    className="h-full bg-gradient-to-r from-rose-500 via-purple-500 to-amber-400 transition-all duration-300 rounded-full"
                    style={{
                      width: `${Math.max(8, Math.min(100, scanStatus?.progress || 10))}%`,
                    }}
                  />
                </div>
                <div className="mt-2 text-[11px] text-slate-400 flex items-center justify-between">
                  <span>
                    Pipeline: Audio Scanner → HUD ROI Extractor → OCR Matcher → Clustered Clips
                  </span>
                  {scanStatus?.candidate_count ? (
                    <span className="text-emerald-400 font-semibold font-mono">
                      {scanStatus.candidate_count} candidates found
                    </span>
                  ) : null}
                </div>
              </div>
            )}

            {/* Success Feedback Alert */}
            {batchSuccessMessage && (
              <div className="p-3 bg-emerald-950/60 border-b border-emerald-500/30 text-xs text-emerald-200 flex items-center justify-between gap-2 shrink-0">
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>{batchSuccessMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setBatchSuccessMessage(null)}
                  className="p-1 rounded text-emerald-400 hover:text-white cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Error Message Alert */}
            {errorMessage && (
              <div className="p-4 bg-rose-950/40 border-b border-rose-500/30 text-xs text-rose-300 flex items-center justify-between gap-2 shrink-0">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleStartScan(true)}
                  className="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded text-xs font-semibold cursor-pointer shrink-0"
                >
                  Retry Scan
                </button>
              </div>
            )}

            {/* Filter and Sorting Toolbar */}
            {candidates.length > 0 && (
              <div className="flex flex-col border-b border-white/5 shrink-0">
                {/* Tier 1: Lifecycle State Switcher + Quick Select Top N */}
                <div className="p-3 bg-black/40 border-b border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
                  <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
                    <button
                      type="button"
                      onClick={() => setLifecycleFilter("all")}
                      className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer shrink-0 flex items-center gap-1.5 ${
                        lifecycleFilter === "all"
                          ? "bg-white/20 text-white shadow"
                          : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                      }`}
                    >
                      <span>All</span>
                      <span className="px-1.5 py-0.5 rounded-full bg-black/40 text-[10px] font-mono">
                        {candidates.length}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setLifecycleFilter("left")}
                      className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer shrink-0 flex items-center gap-1.5 ${
                        lifecycleFilter === "left"
                          ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                          : "bg-white/5 hover:bg-white/10 text-rose-300/80 hover:text-rose-200"
                      }`}
                    >
                      <span>Left</span>
                      <span className="px-1.5 py-0.5 rounded-full bg-black/40 text-[10px] font-mono text-rose-200">
                        {leftCandidates.length}
                      </span>
                    </button>

                    {renderedCandidates.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setLifecycleFilter("rendered")}
                        className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer shrink-0 flex items-center gap-1.5 ${
                          lifecycleFilter === "rendered"
                            ? "bg-blue-600 text-white shadow-md shadow-blue-950"
                            : "bg-white/5 hover:bg-white/10 text-blue-300/80 hover:text-blue-200"
                        }`}
                      >
                        <span>Rendered</span>
                        <span className="px-1.5 py-0.5 rounded-full bg-black/40 text-[10px] font-mono text-blue-200">
                          {renderedCandidates.length}
                        </span>
                      </button>
                    )}

                    {uploadedCandidates.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setLifecycleFilter("uploaded")}
                        className={`px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer shrink-0 flex items-center gap-1.5 ${
                          lifecycleFilter === "uploaded"
                            ? "bg-emerald-600 text-white shadow-md shadow-emerald-950"
                            : "bg-white/5 hover:bg-white/10 text-emerald-300/80 hover:text-emerald-200"
                        }`}
                      >
                        <span>Uploaded</span>
                        <span className="px-1.5 py-0.5 rounded-full bg-black/40 text-[10px] font-mono text-emerald-200">
                          {uploadedCandidates.length}
                        </span>
                      </button>
                    )}
                  </div>

                  {/* Quick Select Left presets */}
                  {leftCandidates.length > 0 && (
                    <div className="flex items-center gap-1 self-end sm:self-auto shrink-0 text-[11px]">
                      <span className="text-slate-400 font-semibold mr-1">
                        Select Left:
                      </span>
                      {[3, 5, 6, 10].map((n) => (
                        <button
                          key={n}
                          type="button"
                          onClick={() => handleSelectTopNLeft(n)}
                          title={`Select top ${n} left candidates`}
                          className="px-2 py-0.5 rounded bg-white/5 hover:bg-rose-600 hover:text-white text-slate-300 font-mono text-[10px] font-bold border border-white/10 transition-colors cursor-pointer"
                        >
                          Top {n}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Tier 2: Category filter chips & Sort */}
                <div className="p-2.5 bg-black/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
                  <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
                    <button
                      type="button"
                      onClick={() => setFilterCategory("all")}
                      className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                        filterCategory === "all"
                          ? "bg-white/15 text-white"
                          : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                      }`}
                    >
                      All ({activePool.length})
                    </button>
                    {highScoreCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setFilterCategory("high_score")}
                        className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                          filterCategory === "high_score"
                            ? "bg-amber-600 text-white shadow-md shadow-amber-950"
                            : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                        }`}
                      >
                        Top Rated {lifecycleFilter === "left" ? "Left " : ""}({highScoreCount})
                      </button>
                    )}
                    {teamWipeCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setFilterCategory("team_wipe")}
                        className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                          filterCategory === "team_wipe"
                            ? "bg-purple-600 text-white shadow-md shadow-purple-950"
                            : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                        }`}
                      >
                        Team Wipes ({teamWipeCount})
                      </button>
                    )}
                    {multiKoCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setFilterCategory("multi_ko")}
                        className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                          filterCategory === "multi_ko"
                            ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                            : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                        }`}
                      >
                        Multi-KOs ({multiKoCount})
                      </button>
                    )}
                    {clutchCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setFilterCategory("clutch")}
                        className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                          filterCategory === "clutch"
                            ? "bg-emerald-600 text-white shadow-md shadow-emerald-950"
                            : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                        }`}
                      >
                        Clutch ({clutchCount})
                      </button>
                    )}
                    {crownCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setFilterCategory("crown_victory")}
                        className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                          filterCategory === "crown_victory"
                            ? "bg-amber-500 text-black font-bold shadow-md shadow-amber-950"
                            : "bg-white/5 hover:bg-white/10 text-amber-300 hover:text-white"
                        }`}
                      >
                        Crowns 👑 ({crownCount})
                      </button>
                    )}
                    {qualifiedCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setFilterCategory("round_qualified")}
                        className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                          filterCategory === "round_qualified"
                            ? "bg-teal-600 text-white shadow-md shadow-teal-950"
                            : "bg-white/5 hover:bg-white/10 text-teal-300 hover:text-white"
                        }`}
                      >
                        Qualified ⚡ ({qualifiedCount})
                      </button>
                    )}
                    {eliminatedCount > 0 && (
                      <button
                        type="button"
                        onClick={() => setFilterCategory("eliminated")}
                        className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                          filterCategory === "eliminated"
                            ? "bg-rose-900 text-white shadow-md shadow-rose-950"
                            : "bg-white/5 hover:bg-white/10 text-rose-400 hover:text-white"
                        }`}
                      >
                        Eliminated 💀 ({eliminatedCount})
                      </button>
                    )}
                  </div>

                  {/* Sort Option */}
                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                    <span className="text-slate-400">Sort:</span>
                    <select
                      value={sortBy}
                      onChange={(e) =>
                        setSortBy(e.target.value as "score" | "time")
                      }
                      aria-label="Sort highlight candidates"
                      className="px-2 py-1 bg-black/60 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500 cursor-pointer"
                    >
                      <option value="score">Highest Score</option>
                      <option value="time">Chronological</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* Scrollable Content: Candidate Cards */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4 overscroll-contain">
              {isLoading && candidates.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                  <Loader2 className="w-10 h-10 text-rose-500 animate-spin mb-3" />
                  <p className="text-sm font-semibold text-white">Loading Highlights...</p>
                  <p className="text-xs text-slate-400 mt-1">Retrieving candidate action clips</p>
                </div>
              ) : candidates.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center max-w-md mx-auto">
                  <div className="p-4 rounded-2xl bg-rose-600/10 border border-rose-500/20 text-rose-400 mb-4">
                    <Sparkles className="w-8 h-8" />
                  </div>
                  <h3 className="text-base font-bold text-white mb-1.5">
                    No Highlights Detected Yet
                  </h3>
                  <p className="text-xs text-slate-300 leading-relaxed mb-6">
                    Run the BackseatCaster automated AI pipeline to analyze Momentary Loudness energy spikes, extract Marvel Rivals HUD elimination events, and cluster ready-to-render Shorts candidates.
                  </p>
                  <button
                    type="button"
                    onClick={() => handleStartScan(false)}
                    disabled={isScanning}
                    className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-950/60 cursor-pointer transition-transform active:scale-95 disabled:opacity-50"
                  >
                    <Sparkles className="w-4 h-4" />
                    <span>{isScanning ? "Scanning Video..." : "Start AI Highlight Scan"}</span>
                  </button>
                  <div className="mt-8 grid grid-cols-2 gap-3 text-left w-full">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/5">
                      <span className="font-bold text-white text-xs block mb-1">
                        ⚡ 100x Audio Scan
                      </span>
                      <p className="text-[11px] text-slate-400 leading-tight">
                        EBU R128 loudness pass rapidly flags top 20% high-energy windows.
                      </p>
                    </div>
                    <div className="p-3 rounded-xl bg-black/40 border border-white/5">
                      <span className="font-bold text-white text-xs block mb-1">
                        🎯 HUD Elimination OCR
                      </span>
                      <p className="text-[11px] text-slate-400 leading-tight">
                        Color masks and scans Team Wipe, Multi-KO, and Overtime clutch events.
                      </p>
                    </div>
                  </div>
                </div>
              ) : filteredCandidates.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-xs">
                  No candidates match the selected filter category.
                </div>
              ) : (
                filteredCandidates.map((candidate, idx) => {
                  const badge = getEventBadge(candidate);
                  const BadgeIcon = badge.icon;
                  const thumbUrl =
                    candidate.thumbnail_url ||
                    getHighlightThumbnailUrl(videoId, candidate.candidate_id);
                  const isApplied = appliedCandidateId === candidate.candidate_id;

                  return (
                    <div
                      key={candidate.candidate_id}
                      className={`p-4 rounded-2xl border transition-all duration-200 flex flex-col gap-3.5 group relative ${
                        isApplied
                          ? "bg-rose-950/30 border-rose-500 shadow-lg shadow-rose-950/30"
                          : selectedCandidateIds.has(candidate.candidate_id)
                          ? "bg-rose-950/20 border-rose-500/50 shadow-md shadow-rose-950/20"
                          : "bg-[#141620] border-white/10 hover:border-white/20 hover:bg-[#171926]"
                      }`}
                    >
                      {/* Top Header: Checkbox, Badge, Lifecycle Status & Score Pill */}
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          {/* Selection Checkbox for unprocessed candidates */}
                          {(!candidate.processing_status ||
                            candidate.processing_status === "unprocessed") && (
                            <button
                              type="button"
                              onClick={() =>
                                handleToggleSelect(candidate.candidate_id)
                              }
                              aria-label="Select candidate for batch action"
                              className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors cursor-pointer"
                            >
                              {selectedCandidateIds.has(
                                candidate.candidate_id
                              ) ? (
                                <CheckSquare className="w-4 h-4 text-rose-500" />
                              ) : (
                                <Square className="w-4 h-4 text-slate-500" />
                              )}
                            </button>
                          )}

                          <span
                            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold border ${badge.classes}`}
                          >
                            <BadgeIcon className="w-3.5 h-3.5 shrink-0" />
                            <span>{badge.label}</span>
                          </span>

                          {/* Lifecycle Status Pill */}
                          {candidate.processing_status === "uploaded" && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                              <Check className="w-3 h-3 stroke-[3]" />
                              <span>Uploaded</span>
                            </span>
                          )}
                          {candidate.processing_status === "rendered" && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold font-mono bg-blue-500/20 text-blue-300 border border-blue-500/40">
                              <Film className="w-3 h-3" />
                              <span>Rendered</span>
                            </span>
                          )}
                          {candidate.processing_status === "staged" && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold font-mono bg-purple-500/20 text-purple-300 border border-purple-500/40">
                              <span>📅 Scheduled</span>
                            </span>
                          )}
                          {candidate.processing_status === "rendering" && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40">
                              <Loader2 className="w-3 h-3 animate-spin" />
                              <span>Rendering...</span>
                            </span>
                          )}

                          <span className="text-[11px] font-mono text-slate-400 bg-black/40 px-2 py-0.5 rounded border border-white/5">
                            #{idx + 1} • {candidate.game}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          <div
                            className={`px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border flex items-center gap-1 ${getScoreColor(
                              candidate.score
                            )}`}
                          >
                            <Award className="w-3 h-3" />
                            <span>{Math.round(candidate.score * 100)}% Match</span>
                          </div>
                        </div>
                      </div>

                      {/* Main Content Layout: Thumbnail + Highlights Metadata */}
                      <div className="grid grid-cols-1 sm:grid-cols-12 gap-4">
                        {/* Thumbnail Viewport (5 cols) */}
                        <div className="sm:col-span-5 relative aspect-video bg-black rounded-xl overflow-hidden border border-white/10 group-hover:border-rose-500/40 transition-colors shrink-0 shadow-inner">
                          <img
                            src={thumbUrl}
                            alt={candidate.suggested_title}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            onError={(e) => {
                              // If thumbnail fails to load, replace with styled fallback
                              (e.currentTarget as HTMLElement).style.display = "none";
                            }}
                          />
                          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/30 pointer-events-none" />

                          {/* Action Climax Pill */}
                          <div className="absolute bottom-1.5 left-1.5 right-1.5 flex items-center justify-between text-[10px] font-mono font-bold text-white z-10">
                            <span className="px-1.5 py-0.5 rounded bg-black/70 backdrop-blur-sm border border-white/10">
                              Peak: {formatSeconds(candidate.peak_timestamp)}
                            </span>
                            <span className="px-1.5 py-0.5 rounded bg-rose-600/80 backdrop-blur-sm">
                              {candidate.duration_seconds}s
                            </span>
                          </div>
                        </div>

                        {/* Metadata & Trigger Info (7 cols) */}
                        <div className="sm:col-span-7 flex flex-col justify-between gap-2.5">
                          <div>
                            {/* Suggested Shorts Title */}
                            <div className="flex items-start justify-between gap-1.5 mb-1.5">
                              <h4 className="text-xs font-bold text-white line-clamp-2 leading-snug">
                                {candidate.suggested_title || `${badge.label} Highlight`}
                              </h4>
                              {candidate.suggested_title && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    handleCopyTitle(
                                      candidate.candidate_id,
                                      candidate.suggested_title
                                    )
                                  }
                                  title="Copy suggested Shorts title"
                                  className="p-1 rounded bg-black/40 hover:bg-white/10 text-slate-400 hover:text-white transition-colors cursor-pointer shrink-0"
                                >
                                  {copiedTitleId === candidate.candidate_id ? (
                                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                                  ) : (
                                    <Copy className="w-3.5 h-3.5" />
                                  )}
                                </button>
                              )}
                            </div>

                            {/* Timing Specs */}
                            <div className="flex items-center gap-2 text-[11px] text-slate-300 font-mono mb-2">
                              <Clock className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                              <span>
                                {formatSeconds(candidate.start_seconds)} →{" "}
                                {formatSeconds(candidate.end_seconds)}
                              </span>
                              <span className="text-slate-500">•</span>
                              <span className="text-rose-400 font-bold">
                                {candidate.duration_seconds}s Duration
                              </span>
                            </div>

                            {/* Elimination & Ultimate Badges */}
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {candidate.details?.kill_count ? (
                                <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/20 text-[10px] font-bold font-mono">
                                  ⚔️ {candidate.details.kill_count} Kills
                                </span>
                              ) : null}
                              {candidate.details?.has_ultimate && (
                                <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 text-[10px] font-bold">
                                  ⚡ Ultimate Cast
                                </span>
                              )}
                              {candidate.details?.game_phase === "overtime" && (
                                <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 text-[10px] font-bold">
                                  ⏳ Overtime
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Trigger Events Mini Strip */}
                          {candidate.details?.trigger_events &&
                            candidate.details.trigger_events.length > 0 && (
                              <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-none">
                                {candidate.details.trigger_events
                                  .slice(0, 3)
                                  .map((ev, i) => (
                                    <span
                                      key={i}
                                      className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-black/40 border border-white/5 text-slate-400 shrink-0"
                                    >
                                      {formatSeconds(ev.time)}: {ev.label}
                                    </span>
                                  ))}
                              </div>
                            )}
                        </div>
                      </div>

                      {/* Action Buttons Footer */}
                      <div className="pt-2.5 border-t border-white/5 flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] text-slate-400">
                            Candidate ID:{" "}
                            <code className="text-slate-300 font-mono text-[10px]">
                              {candidate.candidate_id}
                            </code>
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          {/* Watch on YouTube button for uploaded clips */}
                          {candidate.processing_status === "uploaded" && (
                            <a
                              href={
                                candidate.youtube_upload_url ||
                                (candidate.youtube_video_id
                                  ? `https://youtube.com/shorts/${candidate.youtube_video_id}`
                                  : "#")
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-300 hover:text-white rounded-xl border border-emerald-500/40 text-xs font-semibold transition-colors cursor-pointer"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                              <span>Watch on YouTube</span>
                            </a>
                          )}

                          {onQuickRender &&
                            (!candidate.processing_status ||
                              candidate.processing_status === "unprocessed") && (
                              <button
                                type="button"
                                onClick={() => onQuickRender(candidate)}
                                title="Quick Render (Third-Person Wide Crop)"
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-black/40 hover:bg-black/80 text-slate-300 hover:text-white rounded-xl border border-white/10 text-xs font-semibold transition-colors cursor-pointer"
                              >
                                <Play className="w-3.5 h-3.5" />
                                <span>Quick Render</span>
                              </button>
                            )}

                          <button
                            type="button"
                            onClick={() => handleApply(candidate)}
                            className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold rounded-xl transition-all shadow-md active:scale-95 cursor-pointer ${
                              isApplied
                                ? "bg-emerald-600 text-white shadow-emerald-950"
                                : candidate.processing_status === "uploaded"
                                ? "bg-white/10 hover:bg-white/20 text-slate-300"
                                : "bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white shadow-rose-950"
                            }`}
                          >
                            {isApplied ? (
                              <>
                                <Check className="w-3.5 h-3.5 stroke-[3]" />
                                <span>Applied to Studio!</span>
                              </>
                            ) : (
                              <>
                                <Scissors className="w-3.5 h-3.5" />
                                <span>Apply to Studio</span>
                                <ChevronRight className="w-3.5 h-3.5 -mr-1" />
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Floating Batch Action Dock when items are selected */}
            <AnimatePresence>
              {selectedCandidateIds.size > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 30 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 30 }}
                  className="p-3 bg-[#13151f] border-t border-rose-500/30 shadow-2xl flex flex-wrap items-center justify-between gap-3 shrink-0 z-20"
                >
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 rounded-lg bg-rose-600/30 text-rose-300 font-bold text-xs border border-rose-500/40 font-mono">
                      {selectedCandidateIds.size} Selected
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedCandidateIds(new Set())}
                      className="text-xs text-slate-400 hover:text-white underline cursor-pointer"
                    >
                      Clear
                    </button>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <select
                      value={batchMode}
                      onChange={(e) => setBatchMode(e.target.value)}
                      aria-label="Batch crop preset"
                      className="px-2.5 py-1.5 bg-black/60 border border-white/15 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500 cursor-pointer"
                    >
                      <option value="third_person">
                        Third-Person Wide (9:16)
                      </option>
                      <option value="direct_crop">
                        Direct Center Crop (9:16)
                      </option>
                      <option value="vertical_blur">Vertical Blur (9:16)</option>
                      <option value="cinematic">Cinematic Crop (9:16)</option>
                    </select>

                    <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={batchSchedule}
                        onChange={(e) => setBatchSchedule(e.target.checked)}
                        className="rounded border-white/20 text-rose-600 focus:ring-0 cursor-pointer"
                      />
                      <span className="hidden sm:inline">
                        Same-Day Scheduling
                      </span>
                    </label>

                    <button
                      type="button"
                      onClick={handleExecuteBatchStage}
                      disabled={isBatchStaging}
                      className="flex items-center gap-1.5 px-4 py-1.5 bg-gradient-to-r from-rose-600 to-purple-600 hover:from-rose-500 hover:to-purple-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-rose-950/50 transition-all cursor-pointer active:scale-95 disabled:opacity-50"
                    >
                      {isBatchStaging ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Queueing...</span>
                        </>
                      ) : (
                        <>
                          <Zap className="w-3.5 h-3.5" />
                          <span>
                            Batch Render & Stage ({selectedCandidateIds.size})
                          </span>
                        </>
                      )}
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Footer Summary Strip */}
            <div className="p-4 bg-black/60 border-t border-white/5 flex items-center justify-between text-xs text-slate-400 shrink-0">
              <span className="flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-rose-400" />
                <span>
                  Showing {filteredCandidates.length} of {candidates.length} mined clips
                </span>
              </span>
              <span className="text-[11px] text-slate-400">
                1-Click Apply updates start timestamp and duration in Studio
              </span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
