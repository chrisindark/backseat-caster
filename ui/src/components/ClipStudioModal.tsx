"use client";

import { createRender, fetchRenders, getDownloadedVideoStreamUrl, getRenderJobStatus, getStreamUrl } from "@/lib/api";
import {
  RenderClipResponse,
  RenderJobResponse,
  RenderManifest,
  VideoItem,
} from "@/types/video";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Columns,
  Download,
  Eye,
  EyeOff,
  Layers,
  Loader2,
  Monitor,
  Scissors,
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
type ViewTab = "vertical_blur" | "vertical_crop" | "landscape" | "comparison";

function formatSeconds(sec: number): string {
  if (isNaN(sec) || sec < 0) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

function parseSeconds(val: string): number {
  if (val.includes(":")) {
    const parts = val.split(":");
    if (parts.length === 2) {
      const min = parseFloat(parts[0]) || 0;
      const sec = parseFloat(parts[1]) || 0;
      return min * 60 + sec;
    }
  }
  return parseFloat(val) || 0;
}

export const ClipStudioModal: React.FC<ClipStudioModalProps> = ({ video, initialStartTime, onClose }) => {
  // Clip parameters
  const [startSecondsInput, setStartSecondsInput] = useState<string>("0");
  const [durationPreset, setDurationPreset] = useState<number>(15);
  const [customDuration, setCustomDuration] = useState<string>("15");
  const [isCustomDuration, setIsCustomDuration] = useState<boolean>(false);

  // Source video preview & playback
  const [showSourcePreview, setShowSourcePreview] = useState<boolean>(false);
  const [sourceCurrentTime, setSourceCurrentTime] = useState<number>(0);
  const sourceVideoRef = useRef<HTMLVideoElement | null>(null);

  // Sync initialStartTime when provided
  useEffect(() => {
    if (initialStartTime !== undefined && initialStartTime !== null && initialStartTime > 0) {
      setStartSecondsInput(formatSeconds(initialStartTime));
    } else {
      setStartSecondsInput("0");
    }
  }, [initialStartTime, video?.id]);


  // Audio mode
  const [audioMode, setAudioMode] = useState<AudioMode>("gameplay_only");
  const [narrationPath, setNarrationPath] = useState<string>("");

  // Crop layout preset
  const [cropPreset, setCropPreset] = useState<"third_person" | "direct_crop" | "cinematic">("third_person");

  // Rendering state
  const [isRendering, setIsRendering] = useState<boolean>(false);
  const [renderProgress, setRenderProgress] = useState<number>(0);
  const [renderStatusStage, setRenderStatusStage] = useState<string>("Queuing render job...");
  const [renderError, setRenderError] = useState<string | null>(null);
  const [renderResult, setRenderResult] = useState<RenderClipResponse | null>(null);

  // Active view tab for results
  const [activeTab, setActiveTab] = useState<ViewTab>("comparison");

  // Video playback states
  const [videoBlurUrl, setVideoBlurUrl] = useState<string | null>(null);
  const [videoCropUrl, setVideoCropUrl] = useState<string | null>(null);
  const [videoLandscapeUrl, setVideoLandscapeUrl] = useState<string | null>(null);

  // Previous completed renders for this video
  const [existingRenders, setExistingRenders] = useState<RenderManifest[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);

  const blurVideoRef = useRef<HTMLVideoElement | null>(null);
  const cropVideoRef = useRef<HTMLVideoElement | null>(null);

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
          setVideoBlurUrl(latest.vertical_blur_path || latest.outputs?.vertical_blur?.path || getStreamUrl(latest.clip_id, "vertical_blur"));
          setVideoCropUrl(latest.vertical_crop_path || latest.outputs?.vertical_crop?.path || getStreamUrl(latest.clip_id, "vertical_crop"));
          setVideoLandscapeUrl(latest.landscape_path || latest.outputs?.landscape?.path || getStreamUrl(latest.clip_id, "landscape"));
        } else {
          setVideoBlurUrl(null);
          setVideoCropUrl(null);
          setVideoLandscapeUrl(null);
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
  }, [video?.id]);

  const activeDuration = isCustomDuration ? parseFloat(customDuration) || 15 : durationPreset;

  const handleStartRender = async () => {
    if (!video) return;
    setRenderError(null);
    setIsRendering(true);
    setRenderProgress(5);
    setRenderStatusStage("Queuing render job...");

    const startSec = parseSeconds(startSecondsInput);

    try {
      const res = await createRender({
        video_id: video.id,
        start_seconds: startSec,
        duration_seconds: activeDuration,
        narration_path: audioMode === "voiceover" && narrationPath.trim() ? narrationPath.trim() : null,
        encoder: "auto",
        overwrite: true,
        crop_preset: cropPreset,
      });

      let completedJob: RenderJobResponse | RenderClipResponse = res;

      // If render job is asynchronous (pending/rendering), poll status endpoint until completion
      if (res.status !== "completed") {
        const targetId = res.job_id || res.clip_id;
        const startTime = Date.now();
        const timeoutMs = 10 * 60 * 1000; // 10 minutes max
        const pollIntervalMs = 1200; // 1.2s poll interval

        while (true) {
          if (Date.now() - startTime > timeoutMs) {
            throw new Error("Render job timed out. Check server logs or worker status.");
          }

          await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));

          const jobStatus = await getRenderJobStatus(targetId);
          const prog = jobStatus.progress || 0;
          setRenderProgress(prog);

          if (prog < 20) {
            setRenderStatusStage("Analyzing source video & extracting frames...");
          } else if (prog < 45) {
            setRenderStatusStage("Rendering Landscape 16:9 Master...");
          } else if (prog < 70) {
            setRenderStatusStage("Rendering Vertical Blur Shorts...");
          } else if (prog < 90) {
            setRenderStatusStage("Rendering Vertical Crop Shorts...");
          } else if (prog < 100) {
            setRenderStatusStage("Generating audit manifest & outputs...");
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

      setRenderResult(completedJob as RenderClipResponse);
      const blurUrl = completedJob.vertical_blur_path || getStreamUrl(completedJob.clip_id, "vertical_blur");
      const cropUrl = completedJob.vertical_crop_path || getStreamUrl(completedJob.clip_id, "vertical_crop");
      const landUrl = completedJob.landscape_path || getStreamUrl(completedJob.clip_id, "landscape");

      setVideoBlurUrl(blurUrl);
      setVideoCropUrl(cropUrl);
      setVideoLandscapeUrl(landUrl);
      setActiveTab("comparison");

      // Refresh history
      const histData = await fetchRenders();
      setExistingRenders(
        histData.items.filter(
          (item) => (item.source?.path || "").includes(video.id) || item.clip_id.includes(video.id)
        )
      );
    } catch (err: unknown) {
      console.error("Render failed:", err);
      const message = err instanceof Error ? err.message : "Failed to render clip. Check server logs.";
      setRenderError(message);
    } finally {
      setIsRendering(false);
    }
  };


  const hasOutputs = Boolean(videoBlurUrl && videoCropUrl);

  return (
    <AnimatePresence>
      {video && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/85 backdrop-blur-md"
          />

          {/* Modal Window */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 15 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 15 }}
            transition={{ duration: 0.2 }}
            className="relative w-full max-w-5xl bg-[#10121a] border border-rose-500/20 rounded-2xl shadow-2xl shadow-rose-950/20 overflow-hidden z-10 my-6 flex flex-col max-h-[92vh]"
          >
            {/* Header */}
            <div className="p-5 border-b border-white/10 flex items-center justify-between bg-gradient-to-r from-rose-950/40 via-purple-950/20 to-transparent">
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
          <div className="p-6 overflow-y-auto flex flex-col gap-6 space-y-2">
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
                        onTimeUpdate={(e) => setSourceCurrentTime(e.currentTarget.currentTime)}
                        className="w-full h-full object-contain"
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">
                        Current Playhead: <strong className="font-mono text-white">{formatSeconds(sourceCurrentTime)}</strong>
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          const sec = Math.floor(sourceCurrentTime);
                          setStartSecondsInput(formatSeconds(sec));
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
                    <input
                      type="text"
                      value={startSecondsInput}
                      onChange={(e) => setStartSecondsInput(e.target.value)}
                      placeholder="e.g. 0 or 01:30"
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-rose-500 transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Duration: {activeDuration}s
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
                  <span>
                    Clip Segment:{" "}
                    <strong className="text-white font-mono">
                      {startSecondsInput}s → {parseSeconds(startSecondsInput) + activeDuration}s
                    </strong>
                  </span>
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
                </div>
              </div>
            </div>

            {/* Vertical Crop Framing / Composition Preset Selector */}
            <div className="bg-[#141724] border border-white/5 rounded-xl p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                  <Scissors className="w-3.5 h-3.5 text-rose-400" />
                  <span>Vertical Crop Framing (Third-Person View Tuning)</span>
                </span>
                <span className="text-[11px] text-slate-400">
                  Customizes <code className="text-rose-400 font-mono">vertical_crop.mp4</code>
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Preset 1: Third-Person Wide (Recommended) */}
                <button
                  type="button"
                  onClick={() => setCropPreset("third_person")}
                  className={`p-3 rounded-lg border text-left transition-all cursor-pointer flex flex-col gap-1.5 ${
                    cropPreset === "third_person"
                      ? "bg-rose-950/30 border-rose-500/50 text-white shadow-lg shadow-rose-950/20"
                      : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                      Third-Person Wide
                    </span>
                    <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 font-semibold">
                      Recommended
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-300 leading-snug">
                    33.3% blurred top/bottom bars. Middle gameplay window expands 50% wider (911px) to capture character motion and actions.
                  </span>
                </button>

                {/* Preset 2: Direct Center Crop */}
                <button
                  type="button"
                  onClick={() => setCropPreset("direct_crop")}
                  className={`p-3 rounded-lg border text-left transition-all cursor-pointer flex flex-col gap-1.5 ${
                    cropPreset === "direct_crop"
                      ? "bg-rose-950/30 border-rose-500/50 text-white shadow-lg shadow-rose-950/20"
                      : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-200">
                      Direct Center Crop
                    </span>
                    <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-white/10 text-slate-300">
                      Full 9:16 Bleed
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-400 leading-snug">
                    0% blur. Traditional tight vertical strip (607px wide) filling the entire 1080x1920 canvas.
                  </span>
                </button>

                {/* Preset 3: Cinematic Balanced */}
                <button
                  type="button"
                  onClick={() => setCropPreset("cinematic")}
                  className={`p-3 rounded-lg border text-left transition-all cursor-pointer flex flex-col gap-1.5 ${
                    cropPreset === "cinematic"
                      ? "bg-rose-950/30 border-rose-500/50 text-white shadow-lg shadow-rose-950/20"
                      : "bg-black/30 border-white/5 text-slate-400 hover:bg-black/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-200">
                      Cinematic Balanced
                    </span>
                    <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-white/10 text-slate-300">
                      25% Blur
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-400 leading-snug">
                    25% subtle top/bottom blur with an 810px center gameplay frame for balanced landscape visibility.
                  </span>
                </button>
              </div>
            </div>

            {/* Quality & Output Guarantee Banner */}
            <div className="p-3.5 bg-gradient-to-r from-slate-900 via-rose-950/20 to-slate-900 border border-white/5 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-rose-400" />
                <span className="text-slate-300">
                  <strong className="text-white">Simultaneous Triple Export:</strong> Generates{" "}
                  <span className="text-rose-400">1. Blurred Portrait</span>,{" "}
                  <span className="text-rose-400">2. Cropped Portrait</span>, and{" "}
                  <span className="text-rose-400">3. 16:9 Landscape</span> so you can test and compare.
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
                    {renderResult.encoder_used}!
                  </span>
                ) : (
                  <span>Ready to render clip from local source video.</span>
                )}
              </div>

              <button
                type="button"
                onClick={handleStartRender}
                disabled={isRendering}
                className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-950/60 transition-all cursor-pointer active:scale-95 disabled:opacity-50"
              >
                {isRendering ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Rendering ({Math.round(renderProgress)}%)...</span>
                  </>
                ) : (
                  <>
                    <Scissors className="w-4 h-4" />
                    <span>Render Dual Shorts + Landscape</span>
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
                  <div className="flex items-center gap-1 p-1 bg-black/40 border border-white/5 rounded-xl">
                    <button
                      type="button"
                      onClick={() => setActiveTab("comparison")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                        activeTab === "comparison"
                          ? "bg-rose-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <Columns className="w-3.5 h-3.5" />
                      <span>Side-by-Side Comparison</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("vertical_blur")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                        activeTab === "vertical_blur"
                          ? "bg-rose-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <Smartphone className="w-3.5 h-3.5" />
                      <span>Blurred Background (9:16)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("vertical_crop")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                        activeTab === "vertical_crop"
                          ? "bg-rose-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <Scissors className="w-3.5 h-3.5" />
                      <span>Direct Center Crop (9:16)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("landscape")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                        activeTab === "landscape"
                          ? "bg-rose-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <Monitor className="w-3.5 h-3.5" />
                      <span>16:9 Landscape</span>
                    </button>
                  </div>

                  <span className="text-xs text-slate-400 font-mono">
                    Check output quality before selecting your short style
                  </span>
                </div>

                {/* Viewport Display */}
                {activeTab === "comparison" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-black/30 p-5 rounded-2xl border border-white/5">
                    {/* Left: Blurred Top & Bottom */}
                    <div className="flex flex-col items-center gap-3">
                      <div className="flex items-center justify-between w-full max-w-[280px] text-xs">
                        <span className="font-bold text-white flex items-center gap-1.5">
                          <Layers className="w-3.5 h-3.5 text-rose-400" />
                          <span>Full Width + Blurred Bars</span>
                        </span>
                        <a
                          href={videoBlurUrl!}
                          download="vertical_blur.mp4"
                          className="flex items-center gap-1 text-slate-400 hover:text-white text-[11px]"
                        >
                          <Download className="w-3 h-3" />
                          <span>Save MP4</span>
                        </a>
                      </div>
                      <div className="w-[280px] aspect-[9/16] bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl relative">
                        <video
                          ref={blurVideoRef}
                          src={videoBlurUrl!}
                          controls
                          playsInline
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <p className="text-[11px] text-slate-400 text-center max-w-[280px]">
                        Preserves 100% of horizontal gameplay frame with aesthetic blurred top and bottom padding.
                      </p>
                    </div>

                    {/* Right: Center Crop 9:16 */}
                    <div className="flex flex-col items-center gap-3">
                      <div className="flex items-center justify-between w-full max-w-[280px] text-xs">
                        <span className="font-bold text-white flex items-center gap-1.5">
                          <Scissors className="w-3.5 h-3.5 text-rose-400" />
                          <span>Direct Center Crop (9:16)</span>
                        </span>
                        <a
                          href={videoCropUrl!}
                          download="vertical_crop.mp4"
                          className="flex items-center gap-1 text-slate-400 hover:text-white text-[11px]"
                        >
                          <Download className="w-3 h-3" />
                          <span>Save MP4</span>
                        </a>
                      </div>
                      <div className="w-[280px] aspect-[9/16] bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl relative">
                        <video
                          ref={cropVideoRef}
                          src={videoCropUrl!}
                          controls
                          playsInline
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <p className="text-[11px] text-slate-400 text-center max-w-[280px]">
                        Fills the entire mobile screen with center action; cropped sides for maximum focus.
                      </p>
                    </div>
                  </div>
                )}

                {activeTab === "vertical_blur" && (
                  <div className="flex flex-col items-center justify-center p-6 bg-black/30 rounded-2xl border border-white/5 gap-3">
                    <div className="w-[320px] aspect-[9/16] bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl">
                      <video
                        src={videoBlurUrl!}
                        controls
                        playsInline
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-300">
                      <span>1080×1920 • Blurred Background</span>
                      <a
                        href={videoBlurUrl!}
                        download="vertical_blur.mp4"
                        className="flex items-center gap-1 text-rose-400 hover:text-rose-300 font-semibold"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download vertical_blur.mp4</span>
                      </a>
                    </div>
                  </div>
                )}

                {activeTab === "vertical_crop" && (
                  <div className="flex flex-col items-center justify-center p-6 bg-black/30 rounded-2xl border border-white/5 gap-3">
                    <div className="w-[320px] aspect-[9/16] bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl">
                      <video
                        src={videoCropUrl!}
                        controls
                        playsInline
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-300">
                      <span>1080×1920 • Direct Center Crop</span>
                      <a
                        href={videoCropUrl!}
                        download="vertical_crop.mp4"
                        className="flex items-center gap-1 text-rose-400 hover:text-rose-300 font-semibold"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download vertical_crop.mp4</span>
                      </a>
                    </div>
                  </div>
                )}

                {activeTab === "landscape" && (
                  <div className="flex flex-col items-center justify-center p-6 bg-black/30 rounded-2xl border border-white/5 gap-3">
                    <div className="w-full max-w-2xl aspect-video bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl">
                      <video
                        src={videoLandscapeUrl!}
                        controls
                        playsInline
                        className="w-full h-full object-contain"
                      />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-300">
                      <span>1920×1080 • Standard Landscape Master</span>
                      <a
                        href={videoLandscapeUrl!}
                        download="landscape.mp4"
                        className="flex items-center gap-1 text-rose-400 hover:text-rose-300 font-semibold"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download landscape.mp4</span>
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
    </AnimatePresence>
  );
};
