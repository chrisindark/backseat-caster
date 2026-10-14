"use client";

import { HighlightCandidatesDrawer } from "@/components/HighlightCandidatesDrawer";
import {
  createRender,
  fetchHighlightCandidates,
  fetchRenders,
  getDownloadedVideoStreamUrl,
  getRenderJobStatus,
  getStreamUrl,
} from "@/lib/api";
import {
  ClippingMode,
  HighlightCandidateItem,
  RenderClipResponse,
  RenderJobResponse,
  RenderManifest,
  VideoItem,
} from "@/types/video";

import { useScrollLock } from "@/lib/useScrollLock";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clock,
  Columns,
  Download,
  Eye,
  EyeOff,
  Layers,
  Loader2,
  Monitor,
  Play,
  Scissors,
  Sliders,
  Smartphone,
  Sparkles,
  Volume2,
  X
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

interface ClipStudioModalProps {
  video: VideoItem | null;
  initialStartTime?: number;
  onClose: () => void;
}

type AudioMode = "gameplay_only" | "voiceover";

interface ModeConfig {
  id: ClippingMode;
  title: string;
  badge: string;
  badgeColor: string;
  aspectRatio: "16:9" | "9:16";
  isVertical: boolean;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}

const CLIPPING_MODES: ModeConfig[] = [
  {
    id: "landscape",
    title: "16:9 Landscape Master",
    badge: "1920×1080 • Desktop",
    badgeColor: "bg-blue-500/10 text-blue-300 border-blue-500/20",
    aspectRatio: "16:9",
    isVertical: false,
    description: "Original 16:9 widescreen master without crop or blur padding. Standard for YouTube longform & desktop.",
    icon: Monitor,
  },
  {
    id: "vertical_blur",
    title: "Full Blurred Background",
    badge: "1080×1920 • 9:16 Shorts",
    badgeColor: "bg-purple-500/10 text-purple-300 border-purple-500/20",
    aspectRatio: "9:16",
    isVertical: true,
    description: "100% horizontal gameplay preserved in center with smooth blurred upper and lower background padding.",
    icon: Smartphone,
  },
  {
    id: "third_person",
    title: "Third-Person Wide Crop",
    badge: "Recommended • 33% Blur",
    badgeColor: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    aspectRatio: "9:16",
    isVertical: true,
    description: "Expanded 911px middle window (33.3% blur padding) tuned for third-person hero/character motion.",
    icon: Sparkles,
  },
  {
    id: "direct_crop",
    title: "Direct Center Crop",
    badge: "0% Blur • Full Bleed",
    badgeColor: "bg-amber-500/10 text-amber-300 border-amber-500/20",
    aspectRatio: "9:16",
    isVertical: true,
    description: "Tight 607px center crop filling the entire 9:16 canvas. No blurred padding; maximum screen immersion.",
    icon: Scissors,
  },
  {
    id: "cinematic",
    title: "Cinematic Balanced",
    badge: "25% Blur • 810px View",
    badgeColor: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
    aspectRatio: "9:16",
    isVertical: true,
    description: "Balanced 25% subtle top/bottom blur with an 810px center gameplay frame for cinematic perspective.",
    icon: Columns,
  },
  {
    id: "custom",
    title: "Custom Blur Padding",
    badge: "User Configured",
    badgeColor: "bg-cyan-500/10 text-cyan-300 border-cyan-500/20",
    aspectRatio: "9:16",
    isVertical: true,
    description: "Custom blur padding (0%–60%). Use interactive slider to calibrate framing for your exact HUD/game.",
    icon: Layers,
  },
];

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

function parseSeconds(val: string): number {
  if (!val) return 0;
  if (val.includes(":")) {
    const parts = val.split(":").map((p) => parseFloat(p) || 0);
    if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    }
  }
  return parseFloat(val) || 0;
}

export const ClipStudioModal: React.FC<ClipStudioModalProps> = ({ video, initialStartTime, onClose }) => {
  useScrollLock(Boolean(video));

  // Clip parameters
  const [startSecondsInput, setStartSecondsInput] = useState<string>(() =>
    initialStartTime !== undefined && initialStartTime !== null && initialStartTime > 0
      ? formatSeconds(initialStartTime)
      : "0"
  );
  const [durationPreset, setDurationPreset] = useState<number>(15);
  const [customDuration, setCustomDuration] = useState<string>("15");
  const [isCustomDuration, setIsCustomDuration] = useState<boolean>(false);

  // Source video preview & playback
  const [showSourcePreview, setShowSourcePreview] = useState<boolean>(false);
  const [sourceCurrentTime, setSourceCurrentTime] = useState<number>(() =>
    initialStartTime !== undefined && initialStartTime !== null && initialStartTime > 0
      ? initialStartTime
      : 0
  );
  const sourceVideoRef = useRef<HTMLVideoElement | null>(null);
  const isMountedRef = useRef<boolean>(true);

  // Comparison playback element refs
  const compareLeftVideoRef = useRef<HTMLVideoElement | null>(null);
  const compareRightVideoRef = useRef<HTMLVideoElement | null>(null);
  const standaloneVideoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      sourceVideoRef.current?.pause();
      compareLeftVideoRef.current?.pause();
      compareRightVideoRef.current?.pause();
      standaloneVideoRef.current?.pause();
    };
  }, []);

  // Pause playback when modal closes or video becomes null
  useEffect(() => {
    if (!video) {
      sourceVideoRef.current?.pause();
      compareLeftVideoRef.current?.pause();
      compareRightVideoRef.current?.pause();
      standaloneVideoRef.current?.pause();
    }
  }, [video]);

  // Listen to Escape key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Sync initialStartTime when prop changes using state comparison during render
  const currentInitKey = `${video?.id ?? ""}:${initialStartTime ?? 0}`;
  const [prevInitKey, setPrevInitKey] = useState<string>(currentInitKey);
  if (prevInitKey !== currentInitKey) {
    setPrevInitKey(currentInitKey);
    const formatted =
      initialStartTime !== undefined && initialStartTime !== null && initialStartTime > 0
        ? formatSeconds(initialStartTime)
        : "0";
    if (startSecondsInput !== formatted) {
      setStartSecondsInput(formatted);
    }
  }

  // Audio mode & normalization
  const [audioMode, setAudioMode] = useState<AudioMode>("gameplay_only");
  const [narrationPath, setNarrationPath] = useState<string>("");
  const [normalizeAudio, setNormalizeAudio] = useState<boolean>(true);
  const [targetLufs, setTargetLufs] = useState<number>(-14.0);

  // Clipping modes multi-select
  const [selectedModes, setSelectedModes] = useState<ClippingMode[]>([
    "landscape",
    "vertical_blur",
    "third_person",
  ]);
  const [customBlurPadding, setCustomBlurPadding] = useState<number>(0.33);

  // Rendering state
  const [isRendering, setIsRendering] = useState<boolean>(false);
  const [renderProgress, setRenderProgress] = useState<number>(0);
  const [renderStatusStage, setRenderStatusStage] = useState<string>("Queuing render job...");
  const [renderError, setRenderError] = useState<string | null>(null);
  const [renderResult, setRenderResult] = useState<RenderClipResponse | null>(null);

  // Rendered outputs map: mode -> stream URL
  const [renderedOutputs, setRenderedOutputs] = useState<Record<string, string>>({});

  // Active view tab for results
  const [activeTab, setActiveTab] = useState<string>("comparison");
  const [leftCompareMode, setLeftCompareMode] = useState<string>("vertical_blur");
  const [rightCompareMode, setRightCompareMode] = useState<string>("third_person");

  // Pause output preview players when switching output tabs
  useEffect(() => {
    compareLeftVideoRef.current?.pause();
    compareRightVideoRef.current?.pause();
    standaloneVideoRef.current?.pause();
  }, [activeTab]);

  // Previous completed renders for this video
  const [existingRenders, setExistingRenders] = useState<RenderManifest[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);

  // AI Highlights Drawer
  const [isHighlightDrawerOpen, setIsHighlightDrawerOpen] = useState<boolean>(false);
  const [highlightCount, setHighlightCount] = useState<number>(0);

  useEffect(() => {
    if (!video?.id) return;
    fetchHighlightCandidates(video.id)
      .then((res) => {
        if (res.candidates) setHighlightCount(res.candidates.length);
      })
      .catch(() => {});
  }, [video?.id]);

  const handleApplyHighlightFromModal = (cand: HighlightCandidateItem) => {
    setStartSecondsInput(formatSeconds(cand.start_seconds));
    const dur = Math.round(cand.duration_seconds);
    const isPreset = [10, 15, 30, 60].includes(dur);
    setDurationPreset(isPreset ? dur : 15);
    setIsCustomDuration(!isPreset);
    setCustomDuration(String(dur));
    setSourceCurrentTime(cand.start_seconds);
    if (sourceVideoRef.current) {
      sourceVideoRef.current.currentTime = cand.start_seconds;
    }
  };

  const toggleMode = (mode: ClippingMode) => {
    setSelectedModes((prev) =>
      prev.includes(mode) ? prev.filter((m) => m !== mode) : [...prev, mode]
    );
  };

  const handleSelectAllModes = () => {
    setSelectedModes(["landscape", "vertical_blur", "third_person", "direct_crop", "cinematic", "custom"]);
  };

  const handleSelectAllShorts = () => {
    setSelectedModes(["vertical_blur", "third_person", "direct_crop", "cinematic", "custom"]);
  };

  const handleSelectDefaultTriple = () => {
    setSelectedModes(["landscape", "vertical_blur", "third_person"]);
  };

  // Synchronized playback controls for compare mode
  const handlePlayBoth = () => {
    if (compareLeftVideoRef.current && compareRightVideoRef.current) {
      compareLeftVideoRef.current.currentTime = 0;
      compareRightVideoRef.current.currentTime = 0;
      compareLeftVideoRef.current.play().catch(() => {});
      compareRightVideoRef.current.play().catch(() => {});
    }
  };

  const handlePauseBoth = () => {
    if (compareLeftVideoRef.current && compareRightVideoRef.current) {
      compareLeftVideoRef.current.pause();
      compareRightVideoRef.current.pause();
    }
  };

  // Load existing renders for this video on mount
  useEffect(() => {
    if (!video) return;
    let isCancelled = false;

    async function checkExisting() {
      if (!video) return;
      setIsLoadingHistory(true);
      try {
        const data = await fetchRenders();
        if (isCancelled) return;
        const matched = data.items.filter(
          (item) => (item.source?.path || "").includes(video.id) || item.clip_id.includes(video.id)
        );
        setExistingRenders(matched);
        if (matched.length > 0) {
          const latest = matched[0];
          const newOutputs: Record<string, string> = {};
          if (latest.outputs) {
            for (const [m, out] of Object.entries(latest.outputs)) {
              if (out && typeof out === "object" && out.path) {
                newOutputs[m] = getStreamUrl(latest.clip_id, m);
              }
            }
          }
          if (latest.modes && latest.modes.length > 0) {
            for (const m of latest.modes) {
              newOutputs[m] = getStreamUrl(latest.clip_id, m);
            }
          }
          if (latest.vertical_blur_path && !newOutputs.vertical_blur) {
            newOutputs.vertical_blur = getStreamUrl(latest.clip_id, "vertical_blur");
          }
          if (latest.vertical_crop_path && !newOutputs.vertical_crop && !newOutputs.third_person && !newOutputs.direct_crop && !newOutputs.cinematic && !newOutputs.custom) {
            const cropPreset = latest.request?.crop_preset || "third_person";
            newOutputs[cropPreset] = getStreamUrl(latest.clip_id, cropPreset);
            newOutputs.vertical_crop = getStreamUrl(latest.clip_id, "vertical_crop");
          }
          if (latest.landscape_path && !newOutputs.landscape) {
            newOutputs.landscape = getStreamUrl(latest.clip_id, "landscape");
          }

          setRenderedOutputs(newOutputs);

          const vertKeys = Object.keys(newOutputs).filter((k) => k !== "landscape");
          if (vertKeys.length >= 2) {
            setActiveTab("comparison");
            setLeftCompareMode(vertKeys[0]);
            setRightCompareMode(vertKeys[1]);
          } else if (vertKeys.length === 1) {
            setActiveTab(vertKeys[0]);
          } else if (newOutputs.landscape) {
            setActiveTab("landscape");
          }
        } else {
          setRenderedOutputs({});
        }
      } catch (err: unknown) {
        if (!isCancelled) console.warn("Could not load render history:", err);
      } finally {
        if (!isCancelled) setIsLoadingHistory(false);
      }
    }
    checkExisting();

    return () => {
      isCancelled = true;
    };
  }, [video]);

  const activeDuration = Math.max(
    1,
    isCustomDuration ? parseSeconds(customDuration) || 15 : durationPreset
  );

  const currentStartSec = Math.max(0, parseSeconds(startSecondsInput) || 0);
  const remainingVideoSeconds =
    video && video.duration > 0 ? Math.max(0, video.duration - currentStartSec) : null;
  const isDurationClamped =
    remainingVideoSeconds !== null && activeDuration > remainingVideoSeconds;
  const effectiveDuration = isDurationClamped
    ? Math.max(1, remainingVideoSeconds)
    : activeDuration;

  const handleStartRender = async () => {
    if (!video) return;
    if (selectedModes.length === 0) {
      setRenderError("Please select at least 1 clipping mode to render.");
      return;
    }
    setRenderError(null);

    const rawStartSec = parseSeconds(startSecondsInput);
    const startSec = Math.max(0, rawStartSec);

    if (video.duration > 0 && startSec >= video.duration) {
      setRenderError(`Start time (${formatSeconds(startSec)}) exceeds video duration (${video.duration_formatted}).`);
      return;
    }

    setIsRendering(true);
    setRenderProgress(5);
    setRenderStatusStage(`Queuing render job for ${selectedModes.length} modes...`);

    try {
      const cropPresetForCompat =
        selectedModes.find((m) =>
          ["third_person", "direct_crop", "cinematic", "custom"].includes(m)
        ) || "third_person";

      const res = await createRender({
        video_id: video.id,
        start_seconds: startSec,
        duration_seconds: effectiveDuration,
        narration_path: audioMode === "voiceover" && narrationPath.trim() ? narrationPath.trim() : null,
        encoder: "auto",
        overwrite: true,
        crop_preset: cropPresetForCompat,
        crop_blur_padding: selectedModes.includes("custom") ? customBlurPadding : undefined,
        modes: selectedModes,
        normalize_audio: normalizeAudio,
        target_lufs: targetLufs,
      });

      if (!isMountedRef.current) return;

      let completedJob: RenderJobResponse | RenderClipResponse = res;

      // If render job is asynchronous (pending/rendering), poll status endpoint until completion
      if (res.status !== "completed") {
        const targetId = res.job_id || res.clip_id;
        const startTime = Date.now();
        const timeoutMs = 10 * 60 * 1000; // 10 minutes max
        const pollIntervalMs = 1200; // 1.2s poll interval

        while (isMountedRef.current) {
          if (Date.now() - startTime > timeoutMs) {
            throw new Error("Render job timed out. Check server logs or worker status.");
          }

          await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
          if (!isMountedRef.current) return;

          const jobStatus = await getRenderJobStatus(targetId);
          if (!isMountedRef.current) return;

          const prog = jobStatus.progress || 0;
          setRenderProgress(prog);

          if (prog < 20) {
            setRenderStatusStage("Analyzing source video & extracting frames...");
          } else if (prog < 75) {
            setRenderStatusStage(`Rendering ${selectedModes.length} clipping modes in single pass...`);
          } else if (prog < 100) {
            setRenderStatusStage("Writing manifest and final media outputs...");
          }

          if (jobStatus.status === "completed") {
            setRenderProgress(100);
            setRenderStatusStage("Render complete!");
            completedJob = jobStatus;
            break;
          }

          if (jobStatus.status === "failed") {
            throw new Error(jobStatus.error_message || "Render job failed during background processing.");
          }
        }
      }

      if (!isMountedRef.current) return;

      setRenderResult(completedJob as RenderClipResponse);

      const newOutputs: Record<string, string> = {};
      if (completedJob.outputs) {
        for (const m of Object.keys(completedJob.outputs)) {
          newOutputs[m] = getStreamUrl(completedJob.clip_id, m);
        }
      }
      if (completedJob.modes && completedJob.modes.length > 0) {
        for (const m of completedJob.modes) {
          newOutputs[m] = getStreamUrl(completedJob.clip_id, m);
        }
      }
      if (completedJob.vertical_blur_path && !newOutputs.vertical_blur) {
        newOutputs.vertical_blur = getStreamUrl(completedJob.clip_id, "vertical_blur");
      }
      if (completedJob.vertical_crop_path && !newOutputs.vertical_crop) {
        newOutputs.vertical_crop = getStreamUrl(completedJob.clip_id, "vertical_crop");
      }
      if (completedJob.landscape_path && !newOutputs.landscape) {
        newOutputs.landscape = getStreamUrl(completedJob.clip_id, "landscape");
      }

      setRenderedOutputs(newOutputs);

      const vertKeys = Object.keys(newOutputs).filter((k) => k !== "landscape");
      if (vertKeys.length >= 2) {
        setActiveTab("comparison");
        setLeftCompareMode(vertKeys[0]);
        setRightCompareMode(vertKeys[1]);
      } else if (vertKeys.length === 1) {
        setActiveTab(vertKeys[0]);
      } else if (newOutputs.landscape) {
        setActiveTab("landscape");
      }

      // Refresh history
      const histData = await fetchRenders();
      if (!isMountedRef.current) return;
      setExistingRenders(
        histData.items.filter(
          (item) => (item.source?.path || "").includes(video.id) || item.clip_id.includes(video.id)
        )
      );
    } catch (err: unknown) {
      if (!isMountedRef.current) return;
      console.error("Render failed:", err);
      const message = err instanceof Error ? err.message : "Failed to render clip. Check server logs.";
      setRenderError(message);
    } finally {
      if (isMountedRef.current) {
        setIsRendering(false);
      }
    }
  };

  const hasOutputs = Object.keys(renderedOutputs).length > 0;
  const availableOutputKeys = Object.keys(renderedOutputs);
  const verticalOutputKeys = availableOutputKeys.filter((k) => k !== "landscape");

  return (
    <AnimatePresence>
      {video && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto overscroll-contain">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/85 backdrop-blur-md touch-none"
          />

          {/* Modal Window */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 15 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 15 }}
            transition={{ duration: 0.2 }}
            className="relative w-full max-w-5xl bg-[#10121a] border border-rose-500/20 rounded-2xl shadow-2xl shadow-rose-950/20 overflow-hidden z-10 my-auto flex flex-col max-h-[calc(100vh-1.5rem)] sm:max-h-[calc(100vh-3rem)]"
          >
            {/* Header */}
            <div className="p-5 border-b border-white/10 flex items-center justify-between bg-gradient-to-r from-rose-950/40 via-purple-950/20 to-transparent shrink-0">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-rose-600/20 border border-rose-500/30 text-rose-400">
                  <Scissors className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-white tracking-tight">
                      Clip Studio • Multi-Format Renderer
                    </h2>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                      Phase 1 Studio Quality
                    </span>
                    {isLoadingHistory ? (
                      <span className="text-[10px] text-slate-500 flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" /> Checking history...
                      </span>
                    ) : existingRenders.length > 0 ? (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 text-slate-300 border border-white/10">
                        {existingRenders.length} render{existingRenders.length > 1 ? "s" : ""} cached
                      </span>
                    ) : null}

                    {video?.is_downloaded && (
                      <button
                        type="button"
                        onClick={() => setIsHighlightDrawerOpen(true)}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-gradient-to-r from-rose-600/30 to-purple-600/30 hover:from-rose-600/50 hover:to-purple-600/50 text-white border border-rose-500/40 text-[11px] font-bold shadow cursor-pointer active:scale-95 transition-all"
                      >
                        <Sparkles className="w-3 h-3 text-rose-400" />
                        <span>
                          AI Highlights
                          {highlightCount > 0 ? ` (${highlightCount})` : ""}
                        </span>
                      </button>
                    )}
                  </div>
                <p className="text-xs text-slate-400 truncate max-w-xl">
                  {video.title} ({video.duration_formatted})
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-2 rounded-full bg-black/40 hover:bg-black text-slate-400 hover:text-white transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Scrollable Content Body */}
          <div className="p-6 overflow-y-auto flex-1 min-h-0 flex flex-col gap-6 space-y-2 overscroll-contain">
            {/* Top Config Row: Settings Grid */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
              {/* Left Column: Timing & Presets (7 cols) */}
              <div className="md:col-span-7 bg-[#141724] border border-white/5 rounded-xl p-4 flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-rose-400" />
                    <span>Clip Timing & Duration</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-slate-400 font-mono">
                      Total VOD: {video.duration_formatted}
                    </span>
                    {video.is_downloaded && (
                      <button
                        type="button"
                        onClick={() => setShowSourcePreview((p) => !p)}
                        className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 transition-colors cursor-pointer"
                      >
                        {showSourcePreview ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                        <span>{showSourcePreview ? "Hide Player" : "Preview Player"}</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Embedded Source Video Scrubber */}
                {video.is_downloaded && showSourcePreview && (
                  <div className="p-3 bg-black/60 rounded-xl border border-rose-500/20 flex flex-col gap-2">
                    <div className="relative aspect-video w-full bg-black rounded-lg overflow-hidden">
                      <video
                        ref={sourceVideoRef}
                        src={getDownloadedVideoStreamUrl(video.id)}
                        controls
                        playsInline
                        preload="metadata"
                        onLoadedMetadata={(e) => {
                          const target = sourceCurrentTime > 0 ? sourceCurrentTime : parseSeconds(startSecondsInput);
                          if (target > 0) {
                            e.currentTarget.currentTime = target;
                            setSourceCurrentTime(target);
                          }
                        }}
                        onTimeUpdate={(e) => setSourceCurrentTime(e.currentTarget.currentTime)}
                        onSeeked={(e) => setSourceCurrentTime(e.currentTarget.currentTime)}
                        className="w-full h-full object-contain"
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">
                        Current Playhead: <strong className="font-mono text-white">{formatSeconds(sourceCurrentTime)}</strong> ({Math.floor(sourceCurrentTime)}s)
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          const currentVal = sourceVideoRef.current ? sourceVideoRef.current.currentTime : sourceCurrentTime;
                          const sec = Math.floor(currentVal);
                          setStartSecondsInput(formatSeconds(sec));
                          setSourceCurrentTime(sec);
                        }}
                        className="flex items-center gap-1 px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded text-xs transition-colors cursor-pointer"
                      >
                        <Clock className="w-3 h-3" />
                        <span>Use Playhead as Start ({formatSeconds(sourceCurrentTime)})</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Start Time Input */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Start Time (sec or MM:SS)
                    </label>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        value={startSecondsInput}
                        onChange={(e) => setStartSecondsInput(e.target.value)}
                        placeholder="e.g. 0 or 01:30"
                        className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-rose-500 transition-colors"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const target = parseSeconds(startSecondsInput);
                          setSourceCurrentTime(target);
                          if (sourceVideoRef.current) {
                            sourceVideoRef.current.currentTime = target;
                          }
                        }}
                        className="px-2.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg border border-white/10 cursor-pointer shrink-0"
                      >
                        Seek
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Duration: {activeDuration}s
                      {isDurationClamped && (
                        <span className="text-amber-400 text-[11px] ml-1.5 font-normal">
                          (capped: {effectiveDuration}s)
                        </span>
                      )}
                    </label>
                    <div className="flex items-center gap-1.5">
                      {[10, 15, 30, 60].map((sec) => (
                        <button
                          key={sec}
                          type="button"
                          onClick={() => {
                            setDurationPreset(sec);
                            setIsCustomDuration(false);
                          }}
                          className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                            !isCustomDuration && durationPreset === sec
                              ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                              : "bg-black/30 hover:bg-black/60 text-slate-400 hover:text-white border border-white/5"
                          }`}
                        >
                          {sec}s
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => setIsCustomDuration((prev) => !prev)}
                        className={`px-2.5 py-2 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                          isCustomDuration
                            ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                            : "bg-black/30 hover:bg-black/60 text-slate-400 hover:text-white border border-white/5"
                        }`}
                      >
                        Custom
                      </button>
                    </div>
                    {isCustomDuration && (
                      <div className="mt-2 flex items-center gap-2">
                        <input
                          type="number"
                          min="1"
                          max="300"
                          value={customDuration}
                          onChange={(e) => setCustomDuration(e.target.value)}
                          placeholder="Duration in seconds"
                          className="w-full px-2.5 py-1.5 bg-black/40 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500"
                        />
                        <span className="text-xs text-slate-400 font-mono">sec</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Duration Slider / Info */}
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-black/25 text-xs text-slate-400">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span>
                      Clip Segment:{" "}
                      <strong className="text-white font-mono">
                        {startSecondsInput}s → {currentStartSec + effectiveDuration}s
                      </strong>
                    </span>
                    {isDurationClamped && (
                      <span className="text-[11px] font-semibold text-amber-400 bg-amber-950/60 border border-amber-500/30 px-1.5 py-0.5 rounded">
                        Capped at video end ({effectiveDuration}s)
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-emerald-400 font-semibold flex items-center gap-1">
                    <Sparkles className="w-3 h-3" />
                    Instant High-Fidelity Extraction
                  </span>
                </div>
              </div>

              {/* Right Column: Audio & Voiceover Mode (5 cols) */}
              <div className="md:col-span-5 bg-[#141724] border border-white/5 rounded-xl p-4 flex flex-col gap-3">
                <span className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                  <Volume2 className="w-3.5 h-3.5 text-rose-400" />
                  <span>Audio & Ducking Options</span>
                </span>

                <div className="flex flex-col gap-2">
                  {/* Mode 1: Pure Game Audio (Unducked) */}
                  <button
                    type="button"
                    onClick={() => setAudioMode("gameplay_only")}
                    className={`p-3 rounded-lg border text-left transition-all cursor-pointer flex flex-col gap-1 ${
                      audioMode === "gameplay_only"
                        ? "bg-rose-950/30 border-rose-500/50 text-white"
                        : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50"
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs font-bold">
                      <span className="flex items-center gap-1.5 text-emerald-400">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Pure Game Audio (No Ducking)</span>
                      </span>
                      <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">
                        100% Vol
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-400 leading-tight">
                      Preserves raw game sound without voiceover. Zero ducking or volume reduction.
                    </span>
                  </button>

                  {/* Mode 2: Voiceover / Narration with Auto Ducking */}
                  <button
                    type="button"
                    onClick={() => setAudioMode("voiceover")}
                    className={`p-3 rounded-lg border text-left transition-all cursor-pointer flex flex-col gap-1 ${
                      audioMode === "voiceover"
                        ? "bg-purple-950/30 border-purple-500/50 text-white"
                        : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50"
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs font-bold">
                      <span className="flex items-center gap-1.5 text-purple-400">
                        <span>🎙️ Add Narration / Voiceover</span>
                      </span>
                      <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300">
                        Ducked (30%)
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-400 leading-tight">
                      Ducks background game audio to 30% and mixes with commentary audio track.
                    </span>
                  </button>

                  {audioMode === "voiceover" && (
                    <div className="mt-1">
                      <label className="block text-[11px] font-medium text-slate-300 mb-1">
                        Narration File Path (.wav / .mp3)
                      </label>
                      <input
                        type="text"
                        value={narrationPath}
                        onChange={(e) => setNarrationPath(e.target.value)}
                        placeholder="/path/to/narration.wav"
                        className="w-full px-2.5 py-1.5 bg-black/40 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-purple-500"
                      />
                    </div>
                  )}

                  {/* Audio Normalization (EBU R128 -14 LUFS) */}
                  <div className="mt-2 pt-2.5 border-t border-white/10 flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Volume2 className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="text-xs font-semibold text-slate-200">EBU R128 Loudness Normalization</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setNormalizeAudio(!normalizeAudio)}
                        className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                          normalizeAudio ? "bg-cyan-500" : "bg-white/10"
                        }`}
                      >
                        <span
                          className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                            normalizeAudio ? "translate-x-4" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span>YouTube Shorts Standard:</span>
                      <span className="font-mono font-bold text-cyan-400">
                        {normalizeAudio ? `${targetLufs.toFixed(1)} LUFS` : "Disabled"}
                      </span>
                    </div>
                    {normalizeAudio && (
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] font-mono text-slate-500">-24</span>
                        <input
                          type="range"
                          min="-24"
                          max="-9"
                          step="0.5"
                          value={targetLufs}
                          onChange={(e) => setTargetLufs(parseFloat(e.target.value))}
                          className="flex-1 accent-cyan-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                        />
                        <span className="text-[10px] font-mono text-slate-500">-9</span>
                        <button
                          type="button"
                          onClick={() => setTargetLufs(-14.0)}
                          className="text-cyan-400 hover:text-cyan-300 text-[10px] underline ml-1 cursor-pointer"
                          title="Reset to YouTube Shorts standard (-14 LUFS)"
                        >
                          -14 (Reset)
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Clipping Modes & Framing Presets (Multi-Select 6 Options) */}
            <div className="bg-[#141724] border border-white/5 rounded-xl p-4 flex flex-col gap-3">
              {/* Section Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                      <Scissors className="w-3.5 h-3.5 text-rose-400" />
                      <span>Clipping Modes & Composition Presets</span>
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono border ${
                      selectedModes.length > 0
                        ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                        : "bg-red-500/20 text-red-300 border-red-500/40"
                    }`}>
                      {selectedModes.length} of 6 selected
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Select which formats to render simultaneously. Multiple modes are processed in a single fast FFmpeg pass.
                  </p>
                </div>

                {/* Quick Presets */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={handleSelectAllModes}
                    className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-black/40 hover:bg-black/70 text-slate-300 hover:text-white border border-white/5 hover:border-white/20 transition-all cursor-pointer"
                  >
                    All 6 Modes
                  </button>
                  <button
                    type="button"
                    onClick={handleSelectAllShorts}
                    className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-black/40 hover:bg-black/70 text-slate-300 hover:text-white border border-white/5 hover:border-white/20 transition-all cursor-pointer"
                  >
                    All Shorts (5)
                  </button>
                  <button
                    type="button"
                    onClick={handleSelectDefaultTriple}
                    className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-black/40 hover:bg-black/70 text-slate-300 hover:text-white border border-white/5 hover:border-white/20 transition-all cursor-pointer"
                  >
                    Default Triple (3)
                  </button>
                </div>
              </div>

              {/* 6 Modes Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {CLIPPING_MODES.map((mode) => {
                  const isSelected = selectedModes.includes(mode.id);
                  const Icon = mode.icon;
                  return (
                    <div
                      key={mode.id}
                      onClick={() => toggleMode(mode.id)}
                      className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between gap-2.5 select-none ${
                        isSelected
                          ? "bg-rose-950/30 border-rose-500/60 text-white shadow-lg shadow-rose-950/20"
                          : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50 hover:border-white/10"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <div className={`p-1.5 rounded-lg border ${
                            isSelected
                              ? "bg-rose-500/20 border-rose-500/40 text-rose-300"
                              : "bg-white/5 border-white/5 text-slate-400"
                          }`}>
                            <Icon className="w-4 h-4" />
                          </div>
                          <div>
                            <span className={`text-xs font-bold block ${isSelected ? "text-white" : "text-slate-300"}`}>
                              {mode.title}
                            </span>
                            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border inline-block mt-0.5 ${mode.badgeColor}`}>
                              {mode.id === "custom" ? `${Math.round(customBlurPadding * 100)}% Blur Padding` : mode.badge}
                            </span>
                          </div>
                        </div>

                        <div className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 transition-colors ${
                          isSelected
                            ? "bg-rose-600 border-rose-500 text-white"
                            : "border-white/20 bg-black/40 text-transparent"
                        }`}>
                          <Check className="w-3.5 h-3.5 stroke-[3]" />
                        </div>
                      </div>

                      <p className="text-[11px] text-slate-400 leading-snug line-clamp-3">
                        {mode.description}
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* Custom Blur Padding Slider (Visible when custom is selected) */}
              {selectedModes.includes("custom") && (
                <div className="mt-1 p-3.5 bg-black/40 border border-cyan-500/25 rounded-xl flex flex-col gap-2.5 animate-in fade-in slide-in-from-top-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sliders className="w-4 h-4 text-cyan-400" />
                      <span className="text-xs font-bold text-white">
                        Custom Blur Padding Calibration
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                        {Math.round(customBlurPadding * 100)}% ({customBlurPadding.toFixed(2)})
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono">
                      Gameplay Width:{" "}
                      <strong className="text-cyan-300">
                        {Math.round(607 / (1 - customBlurPadding))}px
                      </strong>{" "}
                      / 1080px
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-[10px] font-mono text-slate-400">0% (Tight)</span>
                    <input
                      type="range"
                      min="0"
                      max="0.60"
                      step="0.01"
                      value={customBlurPadding}
                      onChange={(e) => setCustomBlurPadding(parseFloat(e.target.value))}
                      className="flex-1 accent-cyan-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                    />
                    <span className="text-[10px] font-mono text-slate-400">60% (Wide)</span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>
                      A higher percentage displays more horizontal width of your original gameplay by adding blurred padding at top and bottom.
                    </span>
                    <button
                      type="button"
                      onClick={() => setCustomBlurPadding(0.33)}
                      className="text-cyan-400 hover:text-cyan-300 text-[10px] underline ml-2 shrink-0 cursor-pointer"
                    >
                      Reset to 33%
                    </button>
                  </div>
                </div>
              )}

              {selectedModes.length === 0 && (
                <div className="p-2.5 bg-red-950/30 border border-red-500/30 rounded-lg text-xs text-red-300 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                  <span>Select at least 1 clipping mode above to enable rendering.</span>
                </div>
              )}
            </div>

            {/* Quality & Output Guarantee Banner */}
            <div className="p-3.5 bg-gradient-to-r from-slate-900 via-rose-950/20 to-slate-900 border border-white/5 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-rose-400" />
                <span className="text-slate-300">
                  <strong className="text-white">Single-Pass Multi-Export:</strong> Renders{" "}
                  <span className="text-rose-400">{selectedModes.length} chosen format{selectedModes.length !== 1 ? "s" : ""}</span> in a consolidated FFmpeg filtergraph pipeline.
                </span>
              </div>
              <div className="flex items-center gap-2 font-mono text-[11px] text-slate-400">
                <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                  CRF 17 Master Quality
                </span>
                <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">
                  Lanczos Scaling
                </span>
              </div>
            </div>

            {/* Live Render Progress & Stage Bar */}
            {isRendering && (
              <div className="w-full bg-[#111422] border border-rose-500/20 rounded-xl p-3.5 flex flex-col gap-2.5 shadow-lg shadow-black/40">
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-2 text-rose-300 font-semibold">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-400" />
                    <span>{renderStatusStage}</span>
                  </span>
                  <span className="font-mono text-rose-400 font-bold">
                    {Math.round(renderProgress)}%
                  </span>
                </div>
                <div className="w-full h-2 bg-black/60 rounded-full overflow-hidden border border-white/5">
                  <div
                    className="h-full bg-gradient-to-r from-rose-600 via-rose-500 to-amber-400 rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${Math.max(5, Math.min(100, renderProgress))}%` }}
                  />
                </div>
              </div>
            )}

            {/* Action Trigger Button */}
            <div className="flex items-center justify-between pt-2">
              <div className="text-xs text-slate-400">
                {isRendering ? (
                  <span className="flex items-center gap-2 text-rose-400 font-semibold animate-pulse">
                    <Clock className="w-3.5 h-3.5 text-rose-400" />
                    Background worker active ({Math.round(renderProgress)}%)
                  </span>
                ) : renderResult ? (
                  <span className="flex items-center gap-1.5 text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-4 h-4" />
                    Render finished in {renderResult.render_duration_seconds?.toFixed(1)}s using{" "}
                    {renderResult.encoder_used}! ({renderResult.modes?.length || selectedModes.length} modes ready)
                  </span>
                ) : selectedModes.length === 0 ? (
                  <span className="text-rose-400 font-medium">
                    Choose at least 1 mode to begin render.
                  </span>
                ) : (
                  <span>Ready to render {selectedModes.length} mode{selectedModes.length > 1 ? "s" : ""} from source video.</span>
                )}
              </div>

              <button
                type="button"
                onClick={handleStartRender}
                disabled={isRendering || selectedModes.length === 0}
                className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-950/60 transition-all cursor-pointer active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isRendering ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Rendering ({Math.round(renderProgress)}%)...</span>
                  </>
                ) : selectedModes.length === 0 ? (
                  <>
                    <Scissors className="w-4 h-4" />
                    <span>Select Modes to Render</span>
                  </>
                ) : (
                  <>
                    <Scissors className="w-4 h-4" />
                    <span>Render {selectedModes.length} Selected Mode{selectedModes.length > 1 ? "s" : ""}</span>
                  </>
                )}
              </button>
            </div>

            {renderError && (
              <div className="p-3 bg-rose-950/40 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{renderError}</span>
              </div>
            )}

            {/* Render Preview & Comparison Section */}
            {hasOutputs && (
              <div className="mt-4 pt-4 border-t border-white/10 flex flex-col gap-4">
                {/* View Tabs */}
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-1 p-1 bg-black/40 border border-white/5 rounded-xl overflow-x-auto max-w-full">
                    {/* If 2 or more vertical formats exist, offer side-by-side comparison */}
                    {verticalOutputKeys.length >= 2 && (
                      <button
                        type="button"
                        onClick={() => setActiveTab("comparison")}
                        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer shrink-0 ${
                          activeTab === "comparison"
                            ? "bg-rose-600 text-white shadow-sm"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        <Columns className="w-3.5 h-3.5" />
                        <span>Side-by-Side Comparison</span>
                      </button>
                    )}

                    {/* Dynamic tabs for each rendered output */}
                    {availableOutputKeys.map((modeKey) => {
                      const detail = CLIPPING_MODES.find((m) => m.id === modeKey);
                      const title = detail?.title || modeKey.replace("_", " ");
                      const Icon = detail?.icon || (modeKey === "landscape" ? Monitor : Smartphone);

                      return (
                        <button
                          key={modeKey}
                          type="button"
                          onClick={() => setActiveTab(modeKey)}
                          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer shrink-0 ${
                            activeTab === modeKey
                              ? "bg-rose-600 text-white shadow-sm"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5" />
                          <span>{title}</span>
                        </button>
                      );
                    })}
                  </div>

                  <span className="text-xs text-slate-400 font-mono">
                    {availableOutputKeys.length} output format{availableOutputKeys.length > 1 ? "s" : ""} ready
                  </span>
                </div>

                {/* Side-by-Side Comparison */}
                {activeTab === "comparison" && verticalOutputKeys.length >= 2 && (
                  <div className="bg-black/30 p-5 rounded-2xl border border-white/5 flex flex-col gap-4">
                    {/* Comparison selectors & Play controls */}
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pb-3 border-b border-white/5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-400">Compare:</span>
                        <select
                          value={leftCompareMode}
                          onChange={(e) => setLeftCompareMode(e.target.value)}
                          className="px-2.5 py-1 bg-black/60 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500 cursor-pointer"
                        >
                          {verticalOutputKeys.map((k) => (
                            <option key={k} value={k}>
                              Left: {CLIPPING_MODES.find((m) => m.id === k)?.title || k}
                            </option>
                          ))}
                        </select>
                        <span className="text-xs text-slate-400 font-bold">vs</span>
                        <select
                          value={rightCompareMode}
                          onChange={(e) => setRightCompareMode(e.target.value)}
                          className="px-2.5 py-1 bg-black/60 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500 cursor-pointer"
                        >
                          {verticalOutputKeys.map((k) => (
                            <option key={k} value={k}>
                              Right: {CLIPPING_MODES.find((m) => m.id === k)?.title || k}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handlePlayBoth}
                          className="flex items-center gap-1.5 px-3 py-1 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg shadow-md transition-all active:scale-95 cursor-pointer"
                        >
                          <Play className="w-3.5 h-3.5 fill-white" />
                          <span>Play Both</span>
                        </button>
                        <button
                          type="button"
                          onClick={handlePauseBoth}
                          className="px-3 py-1 bg-black/50 hover:bg-black/80 text-slate-300 text-xs font-medium rounded-lg border border-white/10 transition-colors cursor-pointer"
                        >
                          Pause
                        </button>
                      </div>
                    </div>

                    {/* Dual Players */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {/* Left Player */}
                      <div className="flex flex-col items-center gap-3">
                        <div className="flex items-center justify-between w-full max-w-[280px] text-xs">
                          <span className="font-bold text-white truncate max-w-[190px]">
                            {CLIPPING_MODES.find((m) => m.id === leftCompareMode)?.title || leftCompareMode}
                          </span>
                          {renderedOutputs[leftCompareMode] && (
                            <a
                              href={renderedOutputs[leftCompareMode]}
                              download={`${leftCompareMode}.mp4`}
                              className="flex items-center gap-1 text-slate-400 hover:text-white text-[11px]"
                            >
                              <Download className="w-3 h-3" />
                              <span>Save MP4</span>
                            </a>
                          )}
                        </div>
                        <div className="w-[280px] aspect-[9/16] bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl relative">
                          <video
                            ref={compareLeftVideoRef}
                            data-sync-group="modal-compare"
                            src={renderedOutputs[leftCompareMode]}
                            controls
                            playsInline
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <p className="text-[11px] text-slate-400 text-center max-w-[280px]">
                          {CLIPPING_MODES.find((m) => m.id === leftCompareMode)?.description || ""}
                        </p>
                      </div>

                      {/* Right Player */}
                      <div className="flex flex-col items-center gap-3">
                        <div className="flex items-center justify-between w-full max-w-[280px] text-xs">
                          <span className="font-bold text-white truncate max-w-[190px]">
                            {CLIPPING_MODES.find((m) => m.id === rightCompareMode)?.title || rightCompareMode}
                          </span>
                          {renderedOutputs[rightCompareMode] && (
                            <a
                              href={renderedOutputs[rightCompareMode]}
                              download={`${rightCompareMode}.mp4`}
                              className="flex items-center gap-1 text-slate-400 hover:text-white text-[11px]"
                            >
                              <Download className="w-3 h-3" />
                              <span>Save MP4</span>
                            </a>
                          )}
                        </div>
                        <div className="w-[280px] aspect-[9/16] bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl relative">
                          <video
                            ref={compareRightVideoRef}
                            data-sync-group="modal-compare"
                            src={renderedOutputs[rightCompareMode]}
                            controls
                            playsInline
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <p className="text-[11px] text-slate-400 text-center max-w-[280px]">
                          {CLIPPING_MODES.find((m) => m.id === rightCompareMode)?.description || ""}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Dedicated Single Player Tab for any selected mode */}
                {activeTab !== "comparison" && renderedOutputs[activeTab] && (
                  <div className="flex flex-col items-center justify-center p-6 bg-black/30 rounded-2xl border border-white/5 gap-3">
                    <div className={`bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl ${
                      activeTab === "landscape"
                        ? "w-full max-w-2xl aspect-video"
                        : "w-[320px] aspect-[9/16]"
                    }`}>
                      <video
                        ref={standaloneVideoRef}
                        src={renderedOutputs[activeTab]}
                        controls
                        playsInline
                        className={`w-full h-full ${activeTab === "landscape" ? "object-contain" : "object-cover"}`}
                      />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-300">
                      <span>
                        {activeTab === "landscape" ? "1920×1080 • Standard Landscape Master" : "1080×1920 • 9:16 Shorts Format"}
                      </span>
                      <a
                        href={renderedOutputs[activeTab]}
                        download={`${activeTab}.mp4`}
                        className="flex items-center gap-1 text-rose-400 hover:text-rose-300 font-semibold"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download {activeTab}.mp4</span>
                      </a>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>
      </div>
      )}

      {/* Highlight Mining Slide-over Drawer */}
      {video && (
        <HighlightCandidatesDrawer
          isOpen={isHighlightDrawerOpen}
          videoId={video.id}
          videoTitle={video.title}
          onClose={() => setIsHighlightDrawerOpen(false)}
          onApplyToStudio={handleApplyHighlightFromModal}
          onCandidatesCountChange={(count) => setHighlightCount(count)}
        />
      )}
    </AnimatePresence>
  );
};
