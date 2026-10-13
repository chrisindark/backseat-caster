"use client";

import { Navbar } from "@/components/Navbar";
import {
  checkBackendHealth,
  createRender,
  fetchRenders,
  fetchVideo,
  getDownloadedVideoStreamUrl,
  getRenderJobStatus,
  getStreamUrl,
} from "@/lib/api";
import {
  ClippingMode,
  RenderClipResponse,
  RenderJobResponse,
  RenderManifest,
  VideoItem,
} from "@/types/video";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  Clock,
  Columns,
  Download,
  Eye,
  EyeOff,
  Film,
  HardDrive,
  Layers,
  Loader2,
  Monitor,
  Play,
  Scissors,
  Sliders,
  Smartphone,
  Sparkles,
  Volume2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useRef, useState } from "react";

type AudioMode = "gameplay_only" | "voiceover";
type ViewTab = "comparison" | "vertical_blur" | "vertical_crop" | "landscape";

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

function StudioWorkspace() {
  const params = useParams();
  const searchParams = useSearchParams();

  const videoId = typeof params?.id === "string" ? params.id : Array.isArray(params?.id) ? params.id[0] : "";
  const initialStartFromQuery = searchParams.get("start") ? parseFloat(searchParams.get("start")!) || 0 : 0;

  const [video, setVideo] = useState<VideoItem | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);

  // Timing controls
  const [startSecondsInput, setStartSecondsInput] = useState<string>(
    initialStartFromQuery > 0 ? formatSeconds(initialStartFromQuery) : "0"
  );
  const [durationPreset, setDurationPreset] = useState<number>(15);
  const [customDuration, setCustomDuration] = useState<string>("15");
  const [isCustomDuration, setIsCustomDuration] = useState<boolean>(false);

  // Source video playback & scrubber
  const [showSourcePreview, setShowSourcePreview] = useState<boolean>(true);
  const [sourceCurrentTime, setSourceCurrentTime] = useState<number>(0);
  const sourceVideoRef = useRef<HTMLVideoElement | null>(null);

  // Audio mode & normalization
  const [audioMode, setAudioMode] = useState<AudioMode>("gameplay_only");
  const [narrationPath, setNarrationPath] = useState<string>("");
  const [normalizeAudio, setNormalizeAudio] = useState<boolean>(true);
  const [targetLufs, setTargetLufs] = useState<number>(-14.0);

  // 6 Clipping modes multi-select
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

  // Active comparison tab & output streams
  const [activeTab, setActiveTab] = useState<string>("comparison");
  const [leftCompareMode, setLeftCompareMode] = useState<string>("vertical_blur");
  const [rightCompareMode, setRightCompareMode] = useState<string>("third_person");

  // Existing renders cache
  const [existingRenders, setExistingRenders] = useState<RenderManifest[]>([]);

  const compareLeftVideoRef = useRef<HTMLVideoElement | null>(null);
  const compareRightVideoRef = useRef<HTMLVideoElement | null>(null);

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

  const activeDuration = isCustomDuration
    ? Math.max(1, Math.min(300, parseInt(customDuration, 10) || 15))
    : durationPreset;

  const extractOutputs = useCallback((latest: RenderManifest) => {
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
  }, []);

  // Refresh existing renders after user actions
  const refreshExistingRenders = useCallback(async () => {
    if (!videoId) return;
    try {
      const data = await fetchRenders({ video_id: videoId });
      const matched = data.items || [];
      setExistingRenders(matched);
      if (matched.length > 0) {
        extractOutputs(matched[0]);
      }
    } catch (err) {
      console.warn("Could not load render history:", err);
    }
  }, [videoId, extractOutputs]);

  // Initial load
  useEffect(() => {
    let mounted = true;
    checkBackendHealth().then((h) => {
      if (mounted) setBackendHealthy(h);
    });

    if (!videoId) return;

    fetchVideo(videoId)
      .then((data) => {
        if (!mounted) return;
        setVideo(data);
        setIsLoading(false);
      })
      .catch((err) => {
        if (!mounted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setIsLoading(false);
      });

    fetchRenders({ video_id: videoId })
      .then((data) => {
        if (!mounted) return;
        const matched = data.items || [];
        setExistingRenders(matched);
        if (matched.length > 0) {
          extractOutputs(matched[0]);
        }
      })
      .catch((err) => {
        console.warn("Could not load render history:", err);
      });

    return () => {
      mounted = false;
    };
  }, [videoId, extractOutputs]);

  const handleStartRender = async () => {
    if (!video) return;
    if (selectedModes.length === 0) {
      setRenderError("Please select at least 1 clipping mode to render.");
      return;
    }
    setRenderError(null);
    const startSec = parseSeconds(startSecondsInput);

    if (startSec < 0) {
      setRenderError("Start time must be positive.");
      return;
    }
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
        duration_seconds: activeDuration,
        crop_preset: cropPresetForCompat,
        crop_blur_padding: selectedModes.includes("custom") ? customBlurPadding : undefined,
        modes: selectedModes,
        narration_path: audioMode === "voiceover" && narrationPath.trim() ? narrationPath.trim() : null,
        normalize_audio: normalizeAudio,
        target_lufs: targetLufs,
      });

      let completedJob: RenderJobResponse | RenderClipResponse = res;

      // Poll if async background job
      if (res.job_id && (res.status === "pending" || res.status === "rendering")) {
        const targetId = res.job_id;
        let isDone = false;
        let pollCount = 0;
        const maxPolls = 180;

        while (!isDone && pollCount < maxPolls) {
          await new Promise((r) => setTimeout(r, 1000));
          pollCount++;
          if (pollCount >= maxPolls) {
            throw new Error("Render job timed out. Check server logs or background worker.");
          }

          const jobStatus = await getRenderJobStatus(targetId);
          const prog = jobStatus.progress || 10;
          setRenderProgress(prog);

          if (prog < 25) {
            setRenderStatusStage("Analyzing source video & extracting frames...");
          } else if (prog < 75) {
            setRenderStatusStage(`Rendering ${selectedModes.length} clipping modes in single pass...`);
          } else {
            setRenderStatusStage("Generating audit manifest & outputs...");
          }

          if (jobStatus.status === "completed") {
            setRenderProgress(100);
            setRenderStatusStage("Render complete!");
            completedJob = jobStatus;
            isDone = true;
          } else if (jobStatus.status === "failed") {
            throw new Error(jobStatus.error_message || "Render job failed during background processing.");
          }
        }
      }

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

      await refreshExistingRenders();
    } catch (err: unknown) {
      console.error("Render failed:", err);
      const message = err instanceof Error ? err.message : "Failed to render clip. Check server logs.";
      setRenderError(message);
    } finally {
      setIsRendering(false);
    }
  };

  const hasOutputs = Object.keys(renderedOutputs).length > 0;
  const availableOutputKeys = Object.keys(renderedOutputs);
  const verticalOutputKeys = availableOutputKeys.filter((k) => k !== "landscape");

  return (
    <div className="min-h-screen bg-[#090a0f] flex flex-col">
      <Navbar backendHealthy={backendHealthy} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6">
        {/* Navigation Breadcrumbs & Top Info */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-white/5">
          <div className="flex items-center gap-3">
            <Link
              href={`/videos/${videoId}`}
              className="inline-flex items-center gap-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors group cursor-pointer"
            >
              <div className="p-1.5 rounded-lg bg-slate-900 border border-white/5 group-hover:border-rose-500/40 group-hover:bg-rose-950/30 transition-colors">
                <ArrowLeft className="w-4 h-4 text-slate-400 group-hover:text-rose-400" />
              </div>
              <span>Back to Video</span>
            </Link>

            <span className="text-slate-600">/</span>

            <div className="flex items-center gap-2">
              <div className="p-1 rounded-lg bg-rose-600/20 text-rose-400">
                <Scissors className="w-4 h-4" />
              </div>
              <h1 className="text-sm font-bold text-white tracking-tight">
                Clip Studio Workspace
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                Phase 1 Multi-Format
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs">
            {video && (
              <span className="text-slate-400 truncate max-w-sm">
                <strong className="text-slate-200">{video.title}</strong> ({video.duration_formatted})
              </span>
            )}
            <Link
              href="/renders"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white rounded-lg border border-white/10 transition-colors font-medium"
            >
              <Film className="w-3.5 h-3.5" />
              <span>All Renders & Jobs</span>
            </Link>
          </div>
        </div>

        {/* Loading state */}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <Loader2 className="w-10 h-10 text-rose-500 animate-spin mb-4" />
            <h2 className="text-base font-semibold text-white">Loading Clip Studio...</h2>
            <p className="text-xs text-slate-400 mt-1">Fetching video stream source and cached renders</p>
          </div>
        ) : error || !video ? (
          <div className="p-8 rounded-2xl bg-[#12141c] border border-white/10 text-center max-w-lg mx-auto my-12">
            <AlertCircle className="w-12 h-12 text-rose-500 mx-auto mb-3" />
            <h2 className="text-lg font-bold text-white mb-2">Video Not Available</h2>
            <p className="text-xs text-slate-400 mb-6">{error || `No video found with ID "${videoId}".`}</p>
            <Link
              href="/"
              className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-md"
            >
              Back to Library
            </Link>
          </div>
        ) : !video.is_downloaded ? (
          <div className="p-8 rounded-2xl bg-[#12141c] border border-amber-500/30 text-center max-w-xl mx-auto my-12">
            <HardDrive className="w-12 h-12 text-amber-400 mx-auto mb-3" />
            <h2 className="text-lg font-bold text-white mb-2">VOD Must Be Downloaded First</h2>
            <p className="text-xs text-slate-300 mb-6 leading-relaxed">
              Clip Studio requires frame-accurate local media access to render multi-format 16:9 masters and 9:16 vertical shorts without network buffering.
            </p>
            <div className="flex items-center justify-center gap-3">
              <Link
                href={`/videos/${videoId}`}
                className="px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-900/40"
              >
                Go to Video Details & Download
              </Link>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-8">
            {/* Main Studio Controls Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Video Scrubber & Playhead Timeline (7 cols) */}
              <div className="lg:col-span-7 flex flex-col gap-4">
                <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl shadow-xl flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                      <Clock className="w-4 h-4 text-rose-400" />
                      <span>Source Player & Playhead Scrubber</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowSourcePreview((p) => !p)}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 transition-colors cursor-pointer"
                    >
                      {showSourcePreview ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      <span>{showSourcePreview ? "Minimize Player" : "Expand Player"}</span>
                    </button>
                  </div>

                  {/* Video Player */}
                  {showSourcePreview && (
                    <div className="relative aspect-video w-full bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl">
                      <video
                        ref={sourceVideoRef}
                        src={getDownloadedVideoStreamUrl(video.id)}
                        controls
                        playsInline
                        preload="metadata"
                        onTimeUpdate={(e) => setSourceCurrentTime(e.currentTarget.currentTime)}
                        className="w-full h-full object-contain"
                      />
                    </div>
                  )}

                  {/* Playhead Sync Strip */}
                  <div className="p-3 bg-black/40 rounded-xl border border-white/5 flex flex-wrap items-center justify-between gap-3 text-xs">
                    <span className="text-slate-400">
                      Playhead: <strong className="font-mono text-rose-400 text-sm">{formatSeconds(sourceCurrentTime)}</strong> ({Math.floor(sourceCurrentTime)}s)
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const sec = Math.floor(sourceCurrentTime);
                          setStartSecondsInput(formatSeconds(sec));
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-lg text-xs transition-colors cursor-pointer active:scale-95 shadow-md shadow-rose-950/40"
                      >
                        <Clock className="w-3.5 h-3.5" />
                        <span>Set Current Playhead as Start</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (sourceVideoRef.current) {
                            sourceVideoRef.current.currentTime = parseSeconds(startSecondsInput);
                          }
                        }}
                        className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg border border-white/10 cursor-pointer"
                      >
                        Seek
                      </button>
                    </div>
                  </div>

                  {/* Start & Duration Selection Inputs */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                        Start Timestamp (MM:SS or seconds)
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={startSecondsInput}
                          onChange={(e) => setStartSecondsInput(e.target.value)}
                          placeholder="e.g. 01:30"
                          className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-xl text-white font-mono text-sm focus:outline-none focus:border-rose-500 transition-colors"
                        />
                        <div className="flex items-center bg-black/40 rounded-xl border border-white/10 p-0.5 font-mono text-xs shrink-0">
                          {[-5, 5].map((delta) => (
                            <button
                              key={delta}
                              type="button"
                              onClick={() => {
                                const current = parseSeconds(startSecondsInput);
                                const next = Math.max(0, current + delta);
                                setStartSecondsInput(formatSeconds(next));
                                if (sourceVideoRef.current) {
                                  sourceVideoRef.current.currentTime = next;
                                }
                              }}
                              className="px-2 py-1 text-slate-400 hover:text-white rounded cursor-pointer"
                            >
                              {delta > 0 ? `+${delta}s` : `${delta}s`}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                        Duration: <span className="text-rose-400 font-mono">{activeDuration}s</span>
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
                            className={`flex-1 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer ${
                              !isCustomDuration && durationPreset === sec
                                ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                                : "bg-black/40 hover:bg-black/60 text-slate-400 hover:text-white border border-white/5"
                            }`}
                          >
                            {sec}s
                          </button>
                        ))}
                        <button
                          type="button"
                          onClick={() => setIsCustomDuration((prev) => !prev)}
                          className={`px-3 py-2 text-xs font-bold rounded-xl transition-all cursor-pointer ${
                            isCustomDuration
                              ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                              : "bg-black/40 hover:bg-black/60 text-slate-400 hover:text-white border border-white/5"
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
                            className="w-full px-3 py-1.5 bg-black/50 border border-white/10 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-rose-500"
                          />
                          <span className="text-xs text-slate-400 font-mono">seconds</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Summary extraction banner */}
                  <div className="p-3 bg-black/30 rounded-xl border border-white/5 flex items-center justify-between text-xs text-slate-400">
                    <span>
                      Selected Range:{" "}
                      <strong className="text-white font-mono">
                        {startSecondsInput}s → {formatSeconds(parseSeconds(startSecondsInput) + activeDuration)}
                      </strong>
                    </span>
                    <span className="text-emerald-400 font-semibold flex items-center gap-1 text-[11px]">
                      <Sparkles className="w-3.5 h-3.5" /> High-Fidelity Lossless Cuts
                    </span>
                  </div>
                </div>
              </div>

              {/* Right Column: Framing, Audio & Rendering Triggers (5 cols) */}
              <div className="lg:col-span-5 flex flex-col gap-4">
                {/* Multi-Select Clipping Modes (6 Options) */}
                <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl shadow-xl flex flex-col gap-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                        <Scissors className="w-3.5 h-3.5 text-rose-400" />
                        <span>Clipping Modes</span>
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono border ${
                          selectedModes.length > 0
                            ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                            : "bg-red-500/20 text-red-300 border-red-500/40"
                        }`}
                      >
                        {selectedModes.length} of 6 selected
                      </span>
                    </div>

                    <div className="flex items-center gap-1 shrink-0 flex-wrap">
                      <button
                        type="button"
                        onClick={handleSelectAllModes}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-lg bg-black/40 hover:bg-black/70 text-slate-300 hover:text-white border border-white/5 hover:border-white/20 transition-all cursor-pointer"
                      >
                        All 6
                      </button>
                      <button
                        type="button"
                        onClick={handleSelectAllShorts}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-lg bg-black/40 hover:bg-black/70 text-slate-300 hover:text-white border border-white/5 hover:border-white/20 transition-all cursor-pointer"
                      >
                        Shorts (5)
                      </button>
                      <button
                        type="button"
                        onClick={handleSelectDefaultTriple}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-lg bg-black/40 hover:bg-black/70 text-slate-300 hover:text-white border border-white/5 hover:border-white/20 transition-all cursor-pointer"
                      >
                        Triple (3)
                      </button>
                    </div>
                  </div>

                  {/* 6 Modes List */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {CLIPPING_MODES.map((mode) => {
                      const isSelected = selectedModes.includes(mode.id);
                      const Icon = mode.icon;
                      return (
                        <div
                          key={mode.id}
                          onClick={() => toggleMode(mode.id)}
                          className={`p-3 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between gap-1.5 select-none ${
                            isSelected
                              ? "bg-rose-950/30 border-rose-500/60 text-white shadow-lg shadow-rose-950/20"
                              : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50 hover:border-white/10"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-1.5">
                            <div className="flex items-center gap-2">
                              <div
                                className={`p-1 rounded-md border ${
                                  isSelected
                                    ? "bg-rose-500/20 border-rose-500/40 text-rose-300"
                                    : "bg-white/5 border-white/5 text-slate-400"
                                }`}
                              >
                                <Icon className="w-3.5 h-3.5" />
                              </div>
                              <div>
                                <span
                                  className={`text-xs font-bold block leading-tight ${
                                    isSelected ? "text-white" : "text-slate-300"
                                  }`}
                                >
                                  {mode.title}
                                </span>
                                <span
                                  className={`text-[9px] font-mono px-1 py-0.2 rounded border inline-block mt-0.5 ${mode.badgeColor}`}
                                >
                                  {mode.id === "custom"
                                    ? `${Math.round(customBlurPadding * 100)}% Blur`
                                    : mode.badge}
                                </span>
                              </div>
                            </div>

                            <div
                              className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors ${
                                isSelected
                                  ? "bg-rose-600 border-rose-500 text-white"
                                  : "border-white/20 bg-black/40 text-transparent"
                              }`}
                            >
                              <Check className="w-3 h-3 stroke-[3]" />
                            </div>
                          </div>
                          <p className="text-[10px] text-slate-400 leading-tight line-clamp-2">
                            {mode.description}
                          </p>
                        </div>
                      );
                    })}
                  </div>

                  {/* Custom Blur Slider */}
                  {selectedModes.includes("custom") && (
                    <div className="mt-1 p-3 bg-black/40 border border-cyan-500/25 rounded-xl flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <Sliders className="w-3.5 h-3.5 text-cyan-400" />
                          <span className="text-xs font-bold text-white">Custom Padding</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                            {Math.round(customBlurPadding * 100)}%
                          </span>
                        </div>
                        <span className="text-[10px] text-slate-400 font-mono">
                          Width:{" "}
                          <strong className="text-cyan-300">
                            {Math.round(607 / (1 - customBlurPadding))}px
                          </strong>
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-slate-400">0%</span>
                        <input
                          type="range"
                          min="0"
                          max="0.60"
                          step="0.01"
                          value={customBlurPadding}
                          onChange={(e) => setCustomBlurPadding(parseFloat(e.target.value))}
                          className="flex-1 accent-cyan-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                        />
                        <span className="text-[10px] font-mono text-slate-400">60%</span>
                        <button
                          type="button"
                          onClick={() => setCustomBlurPadding(0.33)}
                          className="text-cyan-400 hover:text-cyan-300 text-[10px] underline ml-1 cursor-pointer"
                        >
                          Reset
                        </button>
                      </div>
                    </div>
                  )}

                  {selectedModes.length === 0 && (
                    <div className="p-2.5 bg-red-950/30 border border-red-500/30 rounded-xl text-xs text-red-300 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                      <span>Select at least 1 clipping mode above to render.</span>
                    </div>
                  )}
                </div>

                {/* Audio Configuration */}
                <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl shadow-xl flex flex-col gap-3">
                  <span className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                    <Volume2 className="w-3.5 h-3.5 text-rose-400" />
                    <span>Audio & Commentary</span>
                  </span>

                  <div className="flex flex-col gap-2">
                    <button
                      type="button"
                      onClick={() => setAudioMode("gameplay_only")}
                      className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer flex items-center justify-between text-xs font-bold ${
                        audioMode === "gameplay_only"
                          ? "bg-rose-950/30 border-rose-500/50 text-white"
                          : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50"
                      }`}
                    >
                      <span className="flex items-center gap-2 text-emerald-400">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Pure Game Audio (Unducked)</span>
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">
                        100% Vol
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setAudioMode("voiceover")}
                      className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer flex items-center justify-between text-xs font-bold ${
                        audioMode === "voiceover"
                          ? "bg-purple-950/30 border-purple-500/50 text-white"
                          : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50"
                      }`}
                    >
                      <span className="flex items-center gap-2 text-purple-400">
                        <span>🎙️ Add Narration / Voiceover</span>
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300">
                        Ducked
                      </span>
                    </button>

                    {audioMode === "voiceover" && (
                      <input
                        type="text"
                        value={narrationPath}
                        onChange={(e) => setNarrationPath(e.target.value)}
                        placeholder="Path to audio: /path/to/narration.wav"
                        className="w-full px-3 py-1.5 bg-black/50 border border-white/10 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-purple-500"
                      />
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

                {/* Render Button & Progress */}
                <div className="p-5 bg-[#12141c] border border-white/10 rounded-2xl shadow-xl flex flex-col gap-3">
                  {/* Single-Pass banner */}
                  <div className="p-2.5 bg-black/40 border border-white/5 rounded-xl flex items-center justify-between text-[11px] text-slate-400">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <Sparkles className="w-3.5 h-3.5 text-rose-400" />
                      <span>Single-Pass FFmpeg Pipeline</span>
                    </span>
                    <span className="font-mono text-emerald-400">CRF 17 Master</span>
                  </div>

                  {/* Progress bar if rendering */}
                  {isRendering && (
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-rose-300 font-semibold">
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-400" />
                          <span>{renderStatusStage}</span>
                        </span>
                        <span className="font-mono text-rose-400 font-bold">{Math.round(renderProgress)}%</span>
                      </div>
                      <div className="w-full h-2 bg-black/60 rounded-full overflow-hidden border border-white/5">
                        <div
                          className="h-full bg-gradient-to-r from-rose-600 via-rose-500 to-amber-400 rounded-full transition-all duration-300 ease-out"
                          style={{ width: `${Math.max(5, Math.min(100, renderProgress))}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {renderError && (
                    <div className="p-3 bg-rose-950/40 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                      <span>{renderError}</span>
                    </div>
                  )}

                  {renderResult && !isRendering && (
                    <div className="p-3 bg-emerald-950/30 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span>
                        Render complete ({renderResult.render_duration_seconds?.toFixed(1)}s using {renderResult.encoder_used || "FFmpeg"})! {renderResult.modes?.length || selectedModes.length} modes ready.
                      </span>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={handleStartRender}
                    disabled={isRendering || selectedModes.length === 0}
                    className="w-full flex items-center justify-center gap-2 py-3.5 bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-950/60 transition-transform active:scale-95 cursor-pointer"
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
                        <span>Render {selectedModes.length} Mode{selectedModes.length > 1 ? "s" : ""} (Single-Pass CRF 17)</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Results & Comparison Viewports */}
            {hasOutputs && (
              <div className="p-6 bg-[#12141c] border border-white/10 rounded-2xl shadow-xl flex flex-col gap-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-1.5 p-1 bg-black/50 border border-white/10 rounded-xl flex-wrap">
                    {/* If 2 or more vertical formats exist, offer side-by-side comparison */}
                    {verticalOutputKeys.length >= 2 && (
                      <button
                        type="button"
                        onClick={() => setActiveTab("comparison")}
                        className={`flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                          activeTab === "comparison"
                            ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        <Columns className="w-3.5 h-3.5" />
                        <span>Side-by-Side Dual Comparison</span>
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
                          className={`flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                            activeTab === modeKey
                              ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5" />
                          <span>{title}</span>
                        </button>
                      );
                    })}
                  </div>

                  <Link
                    href="/renders"
                    className="text-xs text-rose-400 hover:text-rose-300 font-semibold"
                  >
                    View in Render Queue & Upload Manager →
                  </Link>
                </div>

                {/* Tab: Side-by-Side Dual Comparison */}
                {activeTab === "comparison" && verticalOutputKeys.length >= 2 && (
                  <div className="bg-black/40 p-6 rounded-2xl border border-white/5 flex flex-col gap-6">
                    {/* Comparison selectors & Play controls */}
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pb-3 border-b border-white/5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs text-slate-400 font-medium">Compare:</span>
                        <select
                          value={leftCompareMode}
                          onChange={(e) => setLeftCompareMode(e.target.value)}
                          className="px-2.5 py-1.5 bg-black/60 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500 cursor-pointer"
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
                          className="px-2.5 py-1.5 bg-black/60 border border-white/10 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-rose-500 cursor-pointer"
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
                          className="flex items-center gap-1.5 px-3.5 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg shadow-md transition-all active:scale-95 cursor-pointer"
                        >
                          <Play className="w-3.5 h-3.5 fill-white" />
                          <span>Play Both</span>
                        </button>
                        <button
                          type="button"
                          onClick={handlePauseBoth}
                          className="px-3.5 py-1.5 bg-black/50 hover:bg-black/80 text-slate-300 text-xs font-medium rounded-lg border border-white/10 transition-colors cursor-pointer"
                        >
                          Pause
                        </button>
                      </div>
                    </div>

                    {/* Dual Players */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                      {/* Left Player */}
                      <div className="flex flex-col items-center gap-3">
                        <div className="flex items-center justify-between w-full max-w-[320px] text-xs">
                          <span className="font-bold text-white truncate max-w-[220px]">
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
                        <div className="w-[300px] aspect-[9/16] bg-black rounded-2xl overflow-hidden border border-white/10 shadow-2xl relative">
                          <video
                            ref={compareLeftVideoRef}
                            src={renderedOutputs[leftCompareMode]}
                            controls
                            playsInline
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <p className="text-[11px] text-slate-400 text-center max-w-[300px]">
                          {CLIPPING_MODES.find((m) => m.id === leftCompareMode)?.description || ""}
                        </p>
                      </div>

                      {/* Right Player */}
                      <div className="flex flex-col items-center gap-3">
                        <div className="flex items-center justify-between w-full max-w-[320px] text-xs">
                          <span className="font-bold text-white truncate max-w-[220px]">
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
                        <div className="w-[300px] aspect-[9/16] bg-black rounded-2xl overflow-hidden border border-white/10 shadow-2xl relative">
                          <video
                            ref={compareRightVideoRef}
                            src={renderedOutputs[rightCompareMode]}
                            controls
                            playsInline
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <p className="text-[11px] text-slate-400 text-center max-w-[300px]">
                          {CLIPPING_MODES.find((m) => m.id === rightCompareMode)?.description || ""}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Tab: Standalone Player for any active output mode */}
                {activeTab !== "comparison" && renderedOutputs[activeTab] && (
                  <div className="flex flex-col items-center justify-center p-8 bg-black/40 rounded-2xl border border-white/5 gap-4">
                    <div
                      className={`bg-black rounded-2xl overflow-hidden border border-white/10 shadow-2xl ${
                        activeTab === "landscape"
                          ? "w-full max-w-3xl aspect-video"
                          : "w-[340px] aspect-[9/16]"
                      }`}
                    >
                      <video
                        src={renderedOutputs[activeTab]}
                        controls
                        playsInline
                        className={`w-full h-full ${
                          activeTab === "landscape" ? "object-contain" : "object-cover"
                        }`}
                      />
                    </div>
                    <div className="flex items-center gap-4 text-xs text-slate-300">
                      <span>
                        {activeTab === "landscape"
                          ? "1920×1080 • Landscape Master"
                          : `1080×1920 • ${
                              CLIPPING_MODES.find((m) => m.id === activeTab)?.title || activeTab
                            }`}
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

            {/* Existing Renders for this video */}
            {existingRenders.length > 0 && (
              <div className="p-6 bg-[#12141c] border border-white/10 rounded-2xl shadow-xl flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Film className="w-4 h-4 text-rose-500" />
                    <span>Existing Renders for this Video</span>
                    <span className="text-xs text-slate-400 font-normal">({existingRenders.length})</span>
                  </h3>
                  <Link
                    href="/renders"
                    className="text-xs text-rose-400 hover:text-rose-300 font-semibold"
                  >
                    View in Render Queue →
                  </Link>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {existingRenders.map((r) => (
                    <div
                      key={r.clip_id}
                      className="p-4 bg-black/40 border border-white/5 rounded-xl flex flex-col justify-between gap-3 hover:border-rose-500/30 transition-colors"
                    >
                      <div>
                        <div className="text-xs font-mono font-bold text-white truncate">{r.clip_id}</div>
                        <div className="text-[11px] text-slate-400 mt-1">
                          Start: {formatSeconds(r.clip?.start_seconds || 0)} • {r.clip?.duration_seconds || 15}s
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-white/5 text-xs">
                        <button
                          type="button"
                          onClick={() => {
                            extractOutputs(r);
                            window.scrollTo({ top: 600, behavior: "smooth" });
                          }}
                          className="text-rose-400 hover:text-rose-300 font-medium cursor-pointer"
                        >
                          Load into Player
                        </button>
                        <Link
                          href={`/renders?manifest=${r.clip_id}`}
                          className="text-slate-400 hover:text-white"
                        >
                          Audit Details
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function StudioPage(_props: { params: Promise<{ id: string }> }) {
  return (
    <React.Suspense
      fallback={
        <div className="min-h-screen bg-[#090a0f] flex flex-col items-center justify-center">
          <Loader2 className="w-8 h-8 text-rose-500 animate-spin mb-3" />
          <p className="text-xs text-slate-400 font-medium">Opening Clip Studio Workspace...</p>
        </div>
      }
    >
      <StudioWorkspace />
    </React.Suspense>
  );
}
