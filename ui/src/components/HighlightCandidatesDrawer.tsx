"use client";

import {
  deleteHighlightCandidates,
  detectHighlights,
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
  ChevronRight,
  Clock,
  Copy,
  Crown,
  Flame,
  Layers,
  Loader2,
  Play,
  RotateCcw,
  Scissors,
  Sparkles,
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

type FilterCategory = "all" | "team_wipe" | "multi_ko" | "clutch" | "high_score";

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
  const [filterCategory, setFilterCategory] = useState<FilterCategory>("all");
  const [sortBy, setSortBy] = useState<"score" | "time">("score");

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
      await detectHighlights(videoId, {
        game: "marvel_rivals",
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

  // Filtered & Sorted candidates
  const filteredCandidates = useMemo(() => {
    let result = [...candidates];

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
    } else if (filterCategory === "high_score") {
      result = result.filter((c) => c.score >= 0.8);
    }

    if (sortBy === "score") {
      result.sort((a, b) => b.score - a.score);
    } else {
      result.sort((a, b) => a.start_seconds - b.start_seconds);
    }

    return result;
  }, [candidates, filterCategory, sortBy]);

  const teamWipeCount = useMemo(
    () =>
      candidates.filter(
        (c) => c.event_type === "team_wipe" || c.details?.is_team_wipe
      ).length,
    [candidates]
  );
  const multiKoCount = useMemo(
    () =>
      candidates.filter((c) =>
        ["triple_ko", "double_ko", "team_wipe", "mega_ko", "ultra_ko"].includes(
          c.event_type
        )
      ).length,
    [candidates]
  );
  const clutchCount = useMemo(
    () =>
      candidates.filter(
        (c) =>
          c.event_type === "objective_clutch" ||
          c.details?.game_phase === "overtime"
      ).length,
    [candidates]
  );
  const highScoreCount = useMemo(
    () => candidates.filter((c) => c.score >= 0.8).length,
    [candidates]
  );

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
              <div className="p-3 bg-black/30 border-b border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shrink-0">
                {/* Filter Chips */}
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
                  <button
                    type="button"
                    onClick={() => setFilterCategory("all")}
                    className={`px-2.5 py-1 rounded-lg font-semibold transition-colors cursor-pointer shrink-0 ${
                      filterCategory === "all"
                        ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                        : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                    }`}
                  >
                    All ({candidates.length})
                  </button>
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
                      Top Rated ({highScoreCount})
                    </button>
                  )}
                </div>

                {/* Sort Option */}
                <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                  <span className="text-slate-400">Sort:</span>
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as "score" | "time")}
                    aria-label="Sort highlight candidates"
                    className="px-2 py-1 bg-black/60 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500 cursor-pointer"
                  >
                    <option value="score">Highest Score</option>
                    <option value="time">Chronological</option>
                  </select>
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
                          : "bg-[#141620] border-white/10 hover:border-white/20 hover:bg-[#171926]"
                      }`}
                    >
                      {/* Top Header: Badge, Duration Chip & Score Pill */}
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span
                            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold border ${badge.classes}`}
                          >
                            <BadgeIcon className="w-3.5 h-3.5 shrink-0" />
                            <span>{badge.label}</span>
                          </span>

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
                          {onQuickRender && (
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
