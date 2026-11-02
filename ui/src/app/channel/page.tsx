"use client";

import { Navbar } from "@/components/Navbar";
import {
  checkBackendHealth,
  deleteChannelMusic,
  deleteChannelWatermark,
  fetchChannelProfile,
  fetchPresentationPresets,
  getChannelBrandingPreviewUrl,
  getChannelMusicUrl,
  getChannelWatermarkUrl,
  updateChannelProfile,
  uploadChannelMusic,
  uploadChannelWatermark,
  getApiBase,
} from "@/lib/api";
import {
  ChannelProfile,
  ChannelProfileUpdate,
  PresentationPreset,
  PresentationPresetName,
} from "@/types/video";
import {
  AlertCircle,
  CheckCircle2,
  Clapperboard,
  Clock,
  Crosshair,
  Hash,
  Image as ImageIcon,
  Layers,
  Mic,
  Monitor,
  Music,
  Loader2,
  Palette,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Trash2,
  UploadCloud,
  Zap,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";

const FRAMING_PRESETS = [
  { value: "third_person", label: "Third-Person Wide (33% blur)" },
  { value: "cinematic", label: "Cinematic Balanced (25% blur)" },
  { value: "direct_crop", label: "Direct Center Crop (0% blur)" },
  { value: "vertical_blur", label: "Full Blurred Background" },
  { value: "custom", label: "Custom Blur Padding" },
];

const QUALITY_PRESETS = [
  { value: "high", label: "High — balanced broadcast quality" },
  { value: "compact", label: "Compact — smaller uploads" },
  { value: "archive", label: "Archive — maximum bitrate" },
];

const WATERMARK_POSITIONS = [
  { value: "bottom_right", label: "Bottom Right" },
  { value: "bottom_left", label: "Bottom Left" },
  { value: "top_right", label: "Top Right" },
  { value: "top_left", label: "Top Left" },
  { value: "center", label: "Center" },
];

const TARGET_FPS_OPTIONS = [
  { value: "", label: "Match Source (Default)" },
  { value: "30", label: "30 FPS — Standard Web" },
  { value: "60", label: "60 FPS — High-Motion Broadcast" },
];

const CTA_POSITIONS = [
  { value: "bottom", label: "Bottom (Standard lower-third)" },
  { value: "upper_third", label: "Upper Third (Avoids bottom HUD)" },
];

const HOOK_POSITIONS = [
  { value: "upper_third", label: "Upper Third (Avoids crosshairs)" },
  { value: "bottom", label: "Bottom" },
];

const TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "America/Los_Angeles",
  "America/New_York",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Tokyo",
  "Australia/Sydney",
];

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function ChannelProfilePage() {
  const [profile, setProfile] = useState<ChannelProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [channelName, setChannelName] = useState("");
  const [presentationPreset, setPresentationPreset] =
    useState<PresentationPresetName>("viral_kill");
  const [availablePresets, setAvailablePresets] = useState<PresentationPreset[]>(
    []
  );
  const [watermarkEnabled, setWatermarkEnabled] = useState(true);
  const [watermarkPosition, setWatermarkPosition] = useState("bottom_right");
  const [watermarkOpacity, setWatermarkOpacity] = useState(0.85);
  const [watermarkScale, setWatermarkScale] = useState(0.14);
  const [watermarkMargin, setWatermarkMargin] = useState(0.03);
  const [watermarkStartSeconds, setWatermarkStartSeconds] = useState("");
  const [watermarkEndSeconds, setWatermarkEndSeconds] = useState("");

  // Hook caption (Milestone 2)
  const [hookEnabled, setHookEnabled] = useState(false);
  const [hookText, setHookText] = useState("");
  const [hookStartSeconds, setHookStartSeconds] = useState(0.0);
  const [hookDurationSeconds, setHookDurationSeconds] = useState(1.5);
  const [hookPosition, setHookPosition] = useState("upper_third");

  // Kill effects (Milestone 3)
  const [killEffectsEnabled, setKillEffectsEnabled] = useState(false);

  // Dynamic tracking (Milestone 4)
  const [trackingEnabled, setTrackingEnabled] = useState(false);

  // Cinematic Treatment (Milestone 7.4)
  const [cinematicTreatmentEnabled, setCinematicTreatmentEnabled] = useState(false);

  // Frame rate (Milestone 6)
  const [targetFps, setTargetFps] = useState("");

  // Background music & looping (Milestone 5 & 7.3)
  const [hasMusic, setHasMusic] = useState(false);
  const [musicVolume, setMusicVolume] = useState(0.30);
  const [loopOptimization, setLoopOptimization] = useState(false);
  const [isUploadingMusic, setIsUploadingMusic] = useState(false);
  const [isRemovingMusic, setIsRemovingMusic] = useState(false);
  const [musicTick, setMusicTick] = useState(0);
  const musicFileInputRef = useRef<HTMLInputElement | null>(null);

  const [framingPreset, setFramingPreset] = useState("third_person");
  const [qualityPreset, setQualityPreset] = useState("high");

  // Branded intro/outro cards
  const [brandingEnabled, setBrandingEnabled] = useState(false);
  const [brandingIntro, setBrandingIntro] = useState(true);
  const [brandingOutro, setBrandingOutro] = useState(true);
  const [brandingIntroSeconds, setBrandingIntroSeconds] = useState(1.2);
  const [brandingOutroSeconds, setBrandingOutroSeconds] = useState(2.0);
  const [brandingIntroTitle, setBrandingIntroTitle] = useState("");
  const [brandingIntroSubtitle, setBrandingIntroSubtitle] = useState("");
  const [brandingOutroTitle, setBrandingOutroTitle] = useState("SUBSCRIBE");
  const [brandingOutroSubtitle, setBrandingOutroSubtitle] = useState("");
  const [brandingAccentColor, setBrandingAccentColor] = useState("#F43F5E");
  const [brandingBackgroundColor, setBrandingBackgroundColor] =
    useState("#0B0D13");
  const [brandingOpacity, setBrandingOpacity] = useState(0.85);
  const [brandingStyle, setBrandingStyle] = useState<"overlay" | "bookend">("overlay");

  const [maxClipSeconds, setMaxClipSeconds] = useState(90);
  const [previewTick, setPreviewTick] = useState(0);
  const [previewOrientation, setPreviewOrientation] = useState<"landscape" | "vertical">("landscape");

  // CTA voiceover (TTS + bell chime)
  const [ctaEnabled, setCtaEnabled] = useState(false);
  const [ctaStyle, setCtaStyle] = useState("outro_card");
  const [ctaPosition, setCtaPosition] = useState("bottom");
  const [ctaSeconds, setCtaSeconds] = useState(3.5);
  const [ctaHeadline, setCtaHeadline] = useState("SUBSCRIBE & TAP THE BELL");
  const [ctaSubtitle, setCtaSubtitle] = useState("Click the bell for more clips");
  const [ctaSpeechText, setCtaSpeechText] = useState(
    "Subscribe to the channel and tap the bell for more clips."
  );
  const [ctaVoice, setCtaVoice] = useState("en-US-ChristopherNeural");

  const [titleTemplate, setTitleTemplate] = useState("");
  const [pinnedHashtags, setPinnedHashtags] = useState("");
  const [defaultPrivacy, setDefaultPrivacy] = useState("public");
  const [uploadSlots, setUploadSlots] = useState("");
  const [uploadTimezone, setUploadTimezone] = useState("UTC");

  const applyProfile = useCallback((data: ChannelProfile) => {
    setProfile(data);
    setChannelName(data.channel_name || "");
    setPresentationPreset(data.presentation_preset || "viral_kill");
    setWatermarkEnabled(Boolean(data.watermark_enabled));
    setWatermarkPosition(data.watermark_position || "bottom_right");
    setWatermarkOpacity(data.watermark_opacity ?? 0.85);
    setWatermarkScale(data.watermark_scale ?? 0.14);
    setWatermarkMargin(data.watermark_margin ?? 0.03);
    setWatermarkStartSeconds(
      data.watermark_start_seconds != null ? String(data.watermark_start_seconds) : ""
    );
    setWatermarkEndSeconds(
      data.watermark_end_seconds != null ? String(data.watermark_end_seconds) : ""
    );
    setHookEnabled(Boolean(data.hook_enabled));
    setHookText(data.hook_text || "");
    setHookStartSeconds(data.hook_start_seconds ?? 0.0);
    setHookDurationSeconds(data.hook_duration_seconds ?? 1.5);
    setHookPosition(data.hook_position || "upper_third");
    setKillEffectsEnabled(Boolean(data.kill_effects_enabled));
    setTrackingEnabled(Boolean(data.tracking_enabled));
    setCinematicTreatmentEnabled(
      data.cinematic_treatment_enabled ?? (data.presentation_preset === "cinematic_kill")
    );
    setTargetFps(data.target_fps != null ? String(data.target_fps) : "");
    setHasMusic(Boolean(data.has_music || data.bg_music_path));
    setMusicVolume(data.bg_music_volume ?? 0.30);
    setLoopOptimization(Boolean(data.loop_optimization));
    setFramingPreset(data.default_framing_preset || "third_person");
    setQualityPreset(data.default_quality_preset || "high");
    setBrandingEnabled(Boolean(data.branding_enabled));
    setBrandingIntro(data.branding_intro ?? true);
    setBrandingOutro(data.branding_outro ?? true);
    setBrandingIntroSeconds(data.branding_intro_seconds ?? 1.2);
    setBrandingOutroSeconds(data.branding_outro_seconds ?? 2.0);
    setBrandingIntroTitle(data.branding_intro_title || "");
    setBrandingIntroSubtitle(data.branding_intro_subtitle || "");
    setBrandingOutroTitle(data.branding_outro_title || "SUBSCRIBE");
    setBrandingOutroSubtitle(data.branding_outro_subtitle || "");
    setBrandingAccentColor(data.branding_accent_color || "#F43F5E");
    setBrandingBackgroundColor(data.branding_background_color || "#0B0D13");
    setBrandingOpacity(data.branding_opacity ?? 0.85);
    setBrandingStyle((data.branding_style as "overlay" | "bookend") || "overlay");
    setMaxClipSeconds(data.max_clip_seconds ?? 90);
    setCtaEnabled(Boolean(data.cta_enabled));
    setCtaStyle(data.cta_style || "outro_card");
    setCtaPosition(data.cta_position || "bottom");
    setCtaSeconds(data.cta_seconds ?? 3.5);
    setCtaHeadline(data.cta_headline || "SUBSCRIBE & TAP THE BELL");
    setCtaSubtitle(data.cta_subtitle || "Click the bell for more clips");
    setCtaSpeechText(
      data.cta_speech_text || "Subscribe to the channel and tap the bell for more clips."
    );
    setCtaVoice(data.cta_voice || "en-US-ChristopherNeural");
    setTitleTemplate(data.title_template || "");
    setPinnedHashtags((data.pinned_hashtags || []).join(", "));
    setDefaultPrivacy(data.default_privacy || "public");
    setUploadSlots((data.upload_slots || []).join(", "));
    setUploadTimezone(data.upload_timezone || "UTC");
  }, []);

  const loadProfile = useCallback(async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const [data, presets] = await Promise.all([
        fetchChannelProfile(),
        fetchPresentationPresets().catch(() => []),
      ]);
      applyProfile(data);
      if (presets && presets.length > 0) {
        setAvailablePresets(presets);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load channel profile");
    } finally {
      setIsLoading(false);
    }
  }, [applyProfile]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const healthy = await checkBackendHealth();
      if (!mounted) return;
      setBackendHealthy(healthy);
      if (healthy) await loadProfile();
      else setIsLoading(false);
    })();
    return () => {
      mounted = false;
    };
  }, [loadProfile]);

  const flash = (message: string) => {
    setSuccessMsg(message);
    setTimeout(() => setSuccessMsg(null), 3500);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    setErrorMsg(null);
    try {
      const payload: ChannelProfileUpdate = {
        channel_name: channelName.trim() || null,
        presentation_preset: presentationPreset,
        watermark_enabled: watermarkEnabled,
        watermark_position: watermarkPosition,
        watermark_opacity: watermarkOpacity,
        watermark_scale: watermarkScale,
        watermark_margin: watermarkMargin,
        watermark_start_seconds:
          watermarkStartSeconds.trim() !== "" && !isNaN(Number(watermarkStartSeconds))
            ? Number(watermarkStartSeconds)
            : null,
        watermark_end_seconds:
          watermarkEndSeconds.trim() !== "" && !isNaN(Number(watermarkEndSeconds))
            ? Number(watermarkEndSeconds)
            : null,
        hook_enabled: hookEnabled,
        hook_text: hookText.trim() || null,
        hook_start_seconds: Number(hookStartSeconds) || 0.0,
        hook_duration_seconds: Number(hookDurationSeconds) || 1.5,
        hook_position: hookPosition || "upper_third",
        kill_effects_enabled: killEffectsEnabled,
        tracking_enabled: trackingEnabled,
        cinematic_treatment_enabled: cinematicTreatmentEnabled,
        target_fps: targetFps ? parseInt(targetFps, 10) : null,
        bg_music_volume: Number(musicVolume),
        loop_optimization: loopOptimization,
        default_framing_preset: framingPreset,
        default_quality_preset: qualityPreset,
        branding_enabled: brandingEnabled,
        branding_intro: brandingIntro,
        branding_outro: brandingOutro,
        branding_intro_seconds: brandingIntroSeconds,
        branding_outro_seconds: brandingOutroSeconds,
        branding_intro_title: brandingIntroTitle.trim() || null,
        branding_intro_subtitle: brandingIntroSubtitle.trim() || null,
        branding_outro_title: brandingOutroTitle.trim() || "SUBSCRIBE",
        branding_outro_subtitle: brandingOutroSubtitle.trim() || null,
        branding_accent_color: brandingAccentColor,
        branding_background_color: brandingBackgroundColor,
        branding_opacity: Number(brandingOpacity),
        branding_style: brandingStyle,
        max_clip_seconds: maxClipSeconds,
        cta_enabled: ctaEnabled,
        cta_style: ctaStyle,
        cta_position: ctaPosition as "bottom" | "upper_third",
        cta_seconds: ctaSeconds,
        cta_headline: ctaHeadline.trim() || null,
        cta_subtitle: ctaSubtitle.trim() || null,
        cta_speech_text: ctaSpeechText.trim() || null,
        cta_voice: ctaVoice.trim() || null,
        title_template: titleTemplate.trim() || null,
        pinned_hashtags: splitList(pinnedHashtags).map((h) => h.replace(/^#/, "")),
        default_privacy: defaultPrivacy,
        upload_slots: splitList(uploadSlots),
        upload_timezone: uploadTimezone.trim() || "UTC",
      };
      const updated = await updateChannelProfile(payload);
      applyProfile(updated);
      flash("Channel profile saved. New renders and staged clips now use these defaults.");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save channel profile");
    } finally {
      setIsSaving(false);
    }
  };

  const handleWatermarkFile = async (file?: File | null) => {
    if (!file) return;
    setIsUploading(true);
    setErrorMsg(null);
    try {
      const result = await uploadChannelWatermark(file);
      applyProfile(result.profile);
      flash(result.message);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to upload watermark");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRemoveWatermark = async () => {
    setIsRemoving(true);
    setErrorMsg(null);
    try {
      const updated = await deleteChannelWatermark();
      applyProfile(updated);
      flash("Watermark removed. New renders will be unbranded.");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to remove watermark");
    } finally {
      setIsRemoving(false);
    }
  };

  const handleMusicFile = async (file?: File | null) => {
    if (!file) return;
    setIsUploadingMusic(true);
    setErrorMsg(null);
    try {
      const res = await uploadChannelMusic(file);
      applyProfile(res.profile);
      setMusicTick((t) => t + 1);
      flash(res.message);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to upload background music");
    } finally {
      setIsUploadingMusic(false);
      if (musicFileInputRef.current) musicFileInputRef.current.value = "";
    }
  };

  const handleRemoveMusic = async () => {
    setIsRemovingMusic(true);
    setErrorMsg(null);
    try {
      const updated = await deleteChannelMusic();
      applyProfile(updated);
      setMusicTick((t) => t + 1);
      flash("Background music removed.");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to remove background music");
    } finally {
      setIsRemovingMusic(false);
    }
  };

  const handleSelectPreset = (name: PresentationPresetName) => {
    setPresentationPreset(name);
    const p = availablePresets.find((x) => x.name === name);
    if (p) {
      setBrandingEnabled(Boolean(p.branding_enabled));
      setBrandingIntro(Boolean(p.branding_intro));
      setBrandingOutro(Boolean(p.branding_outro));
      if (p.branding_opacity !== undefined) {
        setBrandingOpacity(p.branding_opacity);
      }
      if (p.branding_style) {
        setBrandingStyle((p.branding_style as "overlay" | "bookend") || "overlay");
      }
      setWatermarkEnabled(Boolean(p.watermark_enabled));
      setWatermarkPosition(p.watermark_position || "bottom_right");
      setWatermarkOpacity(p.watermark_opacity ?? 0.85);
      setWatermarkScale(p.watermark_scale ?? 0.14);
      setWatermarkMargin(p.watermark_margin ?? 0.03);
      setFramingPreset(p.default_framing_preset || "third_person");
      setQualityPreset(p.default_quality_preset || "high");
      setHookEnabled(Boolean(p.hook_enabled));
      setHookPosition(p.hook_position || "upper_third");
      setHookDurationSeconds(p.hook_duration_seconds ?? 1.5);
      setKillEffectsEnabled(Boolean(p.kill_effects_enabled));
      setCinematicTreatmentEnabled(Boolean(p.cinematic_treatment_enabled));
      setMusicVolume(p.bg_music_volume ?? 0.30);
      setLoopOptimization(Boolean(p.loop_optimization));
      setCtaEnabled(Boolean(p.cta_enabled));
      setCtaStyle(p.cta_style || "outro_card");
      setCtaSeconds(p.cta_seconds ?? 3.5);
    }
  };

  const previewUrl =
    profile?.watermark_url || getChannelWatermarkUrl(profile?.updated_at);

  return (
    <div className="min-h-screen bg-[#0b0d13] text-slate-100 flex flex-col font-sans selection:bg-rose-500/30 selection:text-white">
      <Navbar backendHealthy={backendHealthy} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/5 pb-6">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-semibold mb-2">
              <Palette className="w-3.5 h-3.5" />
              <span>Tier 3 · Brand Consistency</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400">
              Channel Brand Profile
            </h1>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">
              Set it once and every clip carries your logo, framing, quality, title style,
              hashtags, privacy and publish schedule. Stored locally in your database.
            </p>
          </div>

          <button
            type="button"
            onClick={loadProfile}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 border border-white/10 hover:bg-slate-800 text-xs font-semibold text-slate-200 transition-colors cursor-pointer disabled:opacity-60"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>Reload</span>
          </button>
        </div>

        {errorMsg && (
          <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{errorMsg}</span>
          </div>
        )}
        {successMsg && (
          <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2.5">
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
            <span>{successMsg}</span>
          </div>
        )}

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-24 text-slate-400 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-rose-500" />
            <span className="text-xs font-medium">Loading channel profile...</span>
          </div>
        ) : (
          <form onSubmit={handleSave} className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Presentation Style & Presets (Milestone 1) */}
            <section className="lg:col-span-12 p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-rose-400" />
                  <h2 className="text-sm font-bold text-white">
                    Presentation Style & Presets
                  </h2>
                </div>
                <span className="text-[11px] text-slate-400">
                  Deterministic baseline · Settings configured below override preset defaults
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
                {(availablePresets.length > 0
                  ? availablePresets.map((p) => ({
                      name: p.name,
                      title: p.label,
                      badge:
                        p.name === "viral_kill"
                          ? "Gameplay-First"
                          : p.name === "cinematic_kill"
                          ? "Cinematic Framing"
                          : "Event-Aware",
                      desc: p.description,
                    }))
                  : [
                      {
                        name: "viral_kill" as const,
                        title: "Viral Kill (Default)",
                        badge: "Gameplay-First",
                        desc: "Gameplay begins immediately on frame 1. Subtle watermark, no full-screen cards, and an optional in-video subscribe overlay near the end.",
                      },
                      {
                        name: "cinematic_kill" as const,
                        title: "Cinematic Kill",
                        badge: "Cinematic Framing",
                        desc: "Gameplay begins immediately with minimal text and branding. Game audio is the focus, paired with cinematic balanced framing.",
                      },
                      {
                        name: "multi_kill_montage" as const,
                        title: "Multi-Kill Montage",
                        badge: "Event-Aware",
                        desc: "Fast-paced highlight driven by detected kill events. Features combo notifications, kill counter, and subtle subscribe overlay.",
                      },
                    ]
                ).map((item) => {
                  const active = presentationPreset === item.name;
                  return (
                    <div
                      key={item.name}
                      onClick={() => handleSelectPreset(item.name)}
                      className={`relative p-4 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                        active
                          ? "bg-rose-500/10 border-rose-500/50 ring-1 ring-rose-500/30"
                          : "bg-slate-900/60 border-white/5 hover:border-white/15 hover:bg-slate-900/90"
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-xs font-bold text-white">
                            {item.title}
                          </span>
                          <span
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                              active
                                ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                : "bg-white/5 text-slate-400"
                            }`}
                          >
                            {item.badge}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 leading-relaxed">
                          {item.desc}
                        </p>
                      </div>

                      <div className="mt-3 flex items-center gap-1.5 text-[11px] font-medium text-slate-300">
                        <input
                          type="radio"
                          name="presentation_preset"
                          checked={active}
                          onChange={() => handleSelectPreset(item.name)}
                          className="text-rose-500 focus:ring-0 cursor-pointer"
                        />
                        <span>{active ? "Active Preset" : "Select Preset"}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Identity + watermark */}
            <section className="lg:col-span-5 space-y-6">
              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  <ImageIcon className="w-4 h-4 text-rose-400" />
                  Identity & Watermark
                </h2>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Channel / creator name
                  </label>
                  <input
                    type="text"
                    value={channelName}
                    onChange={(e) => setChannelName(e.target.value)}
                    placeholder="e.g. @NightOwlPlays"
                    className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                  />
                  <p className="text-[11px] text-slate-500 mt-1">
                    Available as <code className="text-rose-300">{"{channel}"}</code> in title templates.
                  </p>
                </div>

                <div className="rounded-xl border border-dashed border-white/15 bg-black/20 p-4 space-y-3">
                  {profile?.has_watermark ? (
                    <div className="flex flex-col items-center gap-3">
                      <div className="relative w-full h-36 rounded-xl bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiI+PGRlZiBzPSJwYXR0ZXJuIiBpZD0iYSIgd2lkdGg9IjE2IiBoZWlnaHQ9IjE2IiBwYXR0ZXJuVW5pdHM9InVzZXJTcGFjZU9uVXNlIj48cmVjdCB3aWR0aD0iOCIgaGVpZ2h0PSI4IiBmaWxsPSIjMjIyNjMzIi8+PHJlY3QgeD0iOCIgeT0iOCIgd2lkdGg9IjgiIGhlaWdodD0iOCIgZmlsbD0iIzIyMjYzMyIvPjwvcGF0dGVybj48L2RlZj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSJ1cmwoI2EpIi8+PC9zdmc+')] border border-white/10 flex items-center justify-center overflow-hidden">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={previewUrl}
                          alt="Channel watermark"
                          className="max-h-28 max-w-full object-contain"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => fileInputRef.current?.click()}
                          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-white/10"
                        >
                          Replace logo
                        </button>
                        <button
                          type="button"
                          onClick={handleRemoveWatermark}
                          disabled={isRemoving}
                          className="px-3 py-1.5 rounded-lg bg-rose-950/50 hover:bg-rose-900/60 text-xs font-semibold text-rose-300 border border-rose-500/30 flex items-center gap-1.5 disabled:opacity-60"
                        >
                          {isRemoving ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                          Remove
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploading}
                      className="w-full py-10 rounded-xl flex flex-col items-center gap-2 text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors cursor-pointer disabled:opacity-60"
                    >
                      {isUploading ? (
                        <Loader2 className="w-7 h-7 animate-spin text-rose-400" />
                      ) : (
                        <UploadCloud className="w-7 h-7 text-rose-400" />
                      )}
                      <span className="text-xs font-semibold">
                        {isUploading ? "Uploading logo..." : "Upload a PNG, JPG or WEBP logo"}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        Transparent PNG recommended. Applied to every output format.
                      </span>
                    </button>
                  )}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="hidden"
                    onChange={(e) => handleWatermarkFile(e.target.files?.[0])}
                  />
                </div>

                <label className="flex items-center justify-between rounded-xl bg-black/30 border border-white/10 px-3 py-2.5 cursor-pointer">
                  <span className="text-xs font-semibold text-slate-200">
                    Burn watermark into renders
                  </span>
                  <input
                    type="checkbox"
                    checked={watermarkEnabled}
                    onChange={(e) => setWatermarkEnabled(e.target.checked)}
                    className="w-4 h-4 accent-rose-500"
                  />
                </label>

                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Position
                    </label>
                    <select
                      value={watermarkPosition}
                      onChange={(e) => setWatermarkPosition(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-rose-500"
                    >
                      {WATERMARK_POSITIONS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Size <span className="font-mono text-rose-300">{Math.round(watermarkScale * 100)}%</span>
                    </label>
                    <input
                      type="range"
                      min={4}
                      max={40}
                      value={Math.round(watermarkScale * 100)}
                      onChange={(e) => setWatermarkScale(Number(e.target.value) / 100)}
                      className="w-full accent-rose-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Opacity <span className="font-mono text-rose-300">{Math.round(watermarkOpacity * 100)}%</span>
                    </label>
                    <input
                      type="range"
                      min={10}
                      max={100}
                      value={Math.round(watermarkOpacity * 100)}
                      onChange={(e) => setWatermarkOpacity(Number(e.target.value) / 100)}
                      className="w-full accent-rose-500"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Edge margin <span className="font-mono text-rose-300">{Math.round(watermarkMargin * 100)}%</span>
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={15}
                      value={Math.round(watermarkMargin * 100)}
                      onChange={(e) => setWatermarkMargin(Number(e.target.value) / 100)}
                      className="w-full accent-rose-500"
                    />
                  </div>

                  <div className="col-span-2 pt-2 border-t border-white/5 space-y-2">
                    <span className="block text-[11px] font-semibold text-slate-300">
                      Watermark Timing (Optional)
                    </span>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[10px] text-slate-400 mb-1">
                          Start time (seconds)
                        </label>
                        <input
                          type="number"
                          step="0.1"
                          min="0"
                          placeholder="0.0 (From start)"
                          value={watermarkStartSeconds}
                          onChange={(e) => setWatermarkStartSeconds(e.target.value)}
                          className="w-full px-2.5 py-1.5 bg-black/40 border border-white/10 rounded-lg text-xs text-white placeholder-slate-600 focus:outline-none focus:border-rose-500"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] text-slate-400 mb-1">
                          End time (seconds)
                        </label>
                        <input
                          type="number"
                          step="0.1"
                          min="0"
                          placeholder="Clip end"
                          value={watermarkEndSeconds}
                          onChange={(e) => setWatermarkEndSeconds(e.target.value)}
                          className="w-full px-2.5 py-1.5 bg-black/40 border border-white/10 rounded-lg text-xs text-white placeholder-slate-600 focus:outline-none focus:border-rose-500"
                        />
                      </div>
                    </div>
                    <span className="text-[10px] text-slate-500 block">
                      Leave empty to display across the entire render.
                    </span>
                  </div>
                </div>
              </div>

              {/* Opening Hook Caption (Milestone 2) */}
              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-rose-400" />
                      Opening Hook Caption
                    </h2>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Crisp, high-contrast banner burned into the first 1–2 seconds.
                      Positioned to never obscure combat reticles or HUD elements.
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none shrink-0">
                    <input
                      type="checkbox"
                      checked={hookEnabled}
                      onChange={(e) => setHookEnabled(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-rose-500" />
                    <span className="ml-2.5 text-xs font-semibold text-slate-300">
                      {hookEnabled ? "On" : "Off"}
                    </span>
                  </label>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Hook text
                  </label>
                  <input
                    type="text"
                    value={hookText}
                    onChange={(e) => setHookText(e.target.value)}
                    placeholder="e.g. WAIT FOR THE FLANK... or CLEAN 4K"
                    className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                  />
                  <p className="text-[10px] text-slate-500 mt-1">
                    Creator-written headline displayed at the start of gameplay.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Position
                    </label>
                    <select
                      value={hookPosition}
                      onChange={(e) => setHookPosition(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-rose-500"
                    >
                      {HOOK_POSITIONS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Duration{" "}
                      <span className="font-mono text-rose-300">
                        {hookDurationSeconds.toFixed(1)}s
                      </span>
                    </label>
                    <input
                      type="range"
                      min={0.5}
                      max={5.0}
                      step={0.1}
                      value={hookDurationSeconds}
                      onChange={(e) =>
                        setHookDurationSeconds(Number(e.target.value))
                      }
                      className="w-full accent-rose-500"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Start delay{" "}
                      <span className="font-mono text-rose-300">
                        {hookStartSeconds.toFixed(1)}s
                      </span>
                    </label>
                    <input
                      type="range"
                      min={0.0}
                      max={3.0}
                      step={0.1}
                      value={hookStartSeconds}
                      onChange={(e) =>
                        setHookStartSeconds(Number(e.target.value))
                      }
                      className="w-full accent-rose-500"
                    />
                  </div>
                </div>
              </div>
            </section>

            {/* Defaults */}
            <section className="lg:col-span-7 space-y-6">
              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  <Layers className="w-4 h-4 text-rose-400" />
                  Render Defaults
                </h2>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Default framing preset
                    </label>
                    <select
                      value={framingPreset}
                      onChange={(e) => setFramingPreset(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-rose-500"
                    >
                      {FRAMING_PRESETS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Default quality
                    </label>
                    <select
                      value={qualityPreset}
                      onChange={(e) => setQualityPreset(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-rose-500"
                    >
                      {QUALITY_PRESETS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Target frame rate
                    </label>
                    <select
                      value={targetFps}
                      onChange={(e) => setTargetFps(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-rose-500"
                    >
                      {TARGET_FPS_OPTIONS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2 border-t border-white/5">
                  <label className="flex flex-col justify-between rounded-xl bg-black/30 border border-white/10 p-3 cursor-pointer hover:border-white/20 transition-colors">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                        <Crosshair className="w-3.5 h-3.5 text-rose-400" />
                        Dynamic Player Tracking
                      </span>
                      <input
                        type="checkbox"
                        checked={trackingEnabled}
                        onChange={(e) => setTrackingEnabled(e.target.checked)}
                        className="w-4 h-4 accent-rose-500"
                      />
                    </div>
                    <span className="text-[11px] text-slate-400 leading-normal">
                      Dynamically reframes 9:16 vertical crop to follow player action. Falls back to static crop preset if motion is unclear.
                    </span>
                  </label>

                  <label className="flex flex-col justify-between rounded-xl bg-black/30 border border-white/10 p-3 cursor-pointer hover:border-white/20 transition-colors">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                        <Zap className="w-3.5 h-3.5 text-rose-400" />
                        Kill Payoff &amp; Badges
                      </span>
                      <input
                        type="checkbox"
                        checked={killEffectsEnabled}
                        onChange={(e) => setKillEffectsEnabled(e.target.checked)}
                        className="w-4 h-4 accent-rose-500"
                      />
                    </div>
                    <span className="text-[11px] text-slate-400 leading-normal">
                      Triggers punch-in zooms and combo badges (DOUBLE KO, etc.) on confirmed eliminations. Degrades cleanly when timestamps are missing.
                    </span>
                  </label>

                  <label className="flex flex-col justify-between rounded-xl bg-black/30 border border-white/10 p-3 cursor-pointer hover:border-white/20 transition-colors">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                        <Clapperboard className="w-3.5 h-3.5 text-rose-400" />
                        Cinematic Payoff Zoom
                      </span>
                      <input
                        type="checkbox"
                        checked={cinematicTreatmentEnabled}
                        onChange={(e) => setCinematicTreatmentEnabled(e.target.checked)}
                        className="w-4 h-4 accent-rose-500"
                      />
                    </div>
                    <span className="text-[11px] text-slate-400 leading-normal">
                      Applies a restrained, elegant punch-in zoom (8%) on confirmed eliminations or midpoint without noisy text badges.
                    </span>
                  </label>
                </div>

                <div className="p-3 rounded-xl bg-rose-500/5 border border-rose-500/15 flex items-start gap-2 text-[11px] text-slate-300">
                  <Sparkles className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
                  <span>
                    Studio, batch staging and auto-stage use these defaults unless a clip
                    explicitly overrides them.
                  </span>
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  <Hash className="w-4 h-4 text-rose-400" />
                  Copy & Publishing Defaults
                </h2>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Title template
                  </label>
                  <input
                    type="text"
                    value={titleTemplate}
                    onChange={(e) => setTitleTemplate(e.target.value)}
                    placeholder="{title} | {channel}"
                    className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                  />
                  <p className="text-[11px] text-slate-500 mt-1.5">
                    Tokens: <code className="text-rose-300">{"{title}"}</code>{" "}
                    <code className="text-rose-300">{"{channel}"}</code>{" "}
                    <code className="text-rose-300">{"{hero}"}</code>{" "}
                    <code className="text-rose-300">{"{game}"}</code>{" "}
                    <code className="text-rose-300">{"{event}"}</code>{" "}
                    <code className="text-rose-300">{"{date}"}</code>{" "}
                    <code className="text-rose-300">{"{clip_id}"}</code>
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Pinned hashtags
                    </label>
                    <input
                      type="text"
                      value={pinnedHashtags}
                      onChange={(e) => setPinnedHashtags(e.target.value)}
                      placeholder="Shorts, MarvelRivals, NightOwl"
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                    />
                    <p className="text-[11px] text-slate-500 mt-1">
                      Always added first to tags and appended to descriptions.
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Default privacy
                    </label>
                    <select
                      value={defaultPrivacy}
                      onChange={(e) => setDefaultPrivacy(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-rose-500"
                    >
                      <option value="public">Public</option>
                      <option value="unlisted">Unlisted</option>
                      <option value="private">Private</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-rose-400" />
                      Daily upload slots
                    </label>
                    <input
                      type="text"
                      value={uploadSlots}
                      onChange={(e) => setUploadSlots(e.target.value)}
                      placeholder="08:00, 12:30, 18:30"
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                    />
                    <p className="text-[11px] text-slate-500 mt-1">
                      Comma-separated 24h times used for native publishAt scheduling.
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Schedule timezone
                    </label>
                    <input
                      type="text"
                      list="channel-timezones"
                      value={uploadTimezone}
                      onChange={(e) => setUploadTimezone(e.target.value)}
                      placeholder="Asia/Kolkata"
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                    />
                    <datalist id="channel-timezones">
                      {TIMEZONES.map((tz) => (
                        <option key={tz} value={tz} />
                      ))}
                    </datalist>
                  </div>
                </div>
              </div>

              {/* Branded intro & outro cards */}
              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <Clapperboard className="w-4 h-4 text-amber-400" />
                      Intro &amp; Outro Cards
                    </h2>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Baked into every render: a channel card before the clip and
                      a &ldquo;subscribe&rdquo; card after it. Cards add{" "}
                      {(brandingIntroSeconds + brandingOutroSeconds).toFixed(1)}s
                      to each clip.
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none shrink-0">
                    <input
                      type="checkbox"
                      checked={brandingEnabled}
                      onChange={(e) => setBrandingEnabled(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500" />
                    <span className="ml-2.5 text-xs font-semibold text-slate-300">
                      {brandingEnabled ? "On" : "Off"}
                    </span>
                  </label>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Intro headline
                    </label>
                    <input
                      type="text"
                      value={brandingIntroTitle}
                      onChange={(e) => setBrandingIntroTitle(e.target.value)}
                      placeholder={channelName || "@YourChannel"}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                    <span className="text-[10px] text-slate-500">
                      Blank uses the channel name
                    </span>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Intro subtitle
                    </label>
                    <input
                      type="text"
                      value={brandingIntroSubtitle}
                      onChange={(e) => setBrandingIntroSubtitle(e.target.value)}
                      placeholder="Highlight clips"
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Outro headline
                    </label>
                    <input
                      type="text"
                      value={brandingOutroTitle}
                      onChange={(e) => setBrandingOutroTitle(e.target.value)}
                      placeholder="SUBSCRIBE"
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Outro subtitle
                    </label>
                    <input
                      type="text"
                      value={brandingOutroSubtitle}
                      onChange={(e) => setBrandingOutroSubtitle(e.target.value)}
                      placeholder={channelName || "for more clips"}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Intro length{" "}
                      <span className="font-mono text-amber-300">
                        {brandingIntroSeconds.toFixed(1)}s
                      </span>
                    </label>
                    <input
                      type="range"
                      min={0.2}
                      max={5}
                      step={0.1}
                      value={brandingIntroSeconds}
                      onChange={(e) =>
                        setBrandingIntroSeconds(Number(e.target.value))
                      }
                      className="w-full accent-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Outro length{" "}
                      <span className="font-mono text-amber-300">
                        {brandingOutroSeconds.toFixed(1)}s
                      </span>
                    </label>
                    <input
                      type="range"
                      min={0.2}
                      max={10}
                      step={0.1}
                      value={brandingOutroSeconds}
                      onChange={(e) =>
                        setBrandingOutroSeconds(Number(e.target.value))
                      }
                      className="w-full accent-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Accent colour
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={brandingAccentColor}
                        onChange={(e) => setBrandingAccentColor(e.target.value)}
                        className="w-9 h-8 rounded border border-white/10 bg-black/40 cursor-pointer"
                      />
                      <span className="text-[10px] font-mono text-slate-500">
                        {brandingAccentColor.toUpperCase()}
                      </span>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Card background
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={brandingBackgroundColor}
                        onChange={(e) =>
                          setBrandingBackgroundColor(e.target.value)
                        }
                        className="w-9 h-8 rounded border border-white/10 bg-black/40 cursor-pointer"
                      />
                      <span className="text-[10px] font-mono text-slate-500">
                        {brandingBackgroundColor.toUpperCase()}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-3 rounded-xl bg-black/20 border border-white/5">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Card background opacity{" "}
                      <span className="font-mono text-amber-300">
                        {Math.round(brandingOpacity * 100)}%
                      </span>
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={brandingOpacity}
                      onChange={(e) => setBrandingOpacity(Number(e.target.value))}
                      className="w-full accent-amber-500"
                    />
                    <p className="text-[11px] text-slate-400 mt-1">
                      Semi-transparent backdrop lets gameplay motion play continuously underneath the card.
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Card display style
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setBrandingStyle("overlay")}
                        className={`px-3 py-2 rounded-xl text-xs font-semibold border transition-all text-left ${
                          brandingStyle === "overlay"
                            ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
                            : "bg-black/30 border-white/10 text-slate-400 hover:border-white/20"
                        }`}
                      >
                        <div>Overlay on Gameplay</div>
                        <div className="text-[10px] font-normal text-slate-500 mt-0.5">
                          Shows action behind card
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => setBrandingStyle("bookend")}
                        className={`px-3 py-2 rounded-xl text-xs font-semibold border transition-all text-left ${
                          brandingStyle === "bookend"
                            ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
                            : "bg-black/30 border-white/10 text-slate-400 hover:border-white/20"
                        }`}
                      >
                        <div>Standalone Bookend</div>
                        <div className="text-[10px] font-normal text-slate-500 mt-0.5">
                          Sequential pre/post screen
                        </div>
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-4">
                  <label className="inline-flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={brandingIntro}
                      onChange={(e) => setBrandingIntro(e.target.checked)}
                      className="w-4 h-4 accent-amber-500"
                    />
                    <span>Include intro card</span>
                  </label>
                  <label className="inline-flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={brandingOutro}
                      onChange={(e) => setBrandingOutro(e.target.checked)}
                      className="w-4 h-4 accent-amber-500"
                    />
                    <span>Include outro card</span>
                  </label>
                </div>

                {/* Intro & Outro Cards Preview Section */}
                <div className="border-t border-white/10 pt-4 space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                        <Clapperboard className="w-3.5 h-3.5 text-amber-400" />
                        <span>Intro &amp; Outro Card Visual Previews</span>
                      </h3>
                      <p className="text-[11px] text-slate-400">
                        Real-time rendered preview of your channel intro bumper and subscribe outro screen.
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      {/* Orientation switcher */}
                      <div className="flex items-center p-0.5 bg-black/50 border border-white/10 rounded-lg text-xs">
                        <button
                          type="button"
                          onClick={() => setPreviewOrientation("landscape")}
                          className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${
                            previewOrientation === "landscape"
                              ? "bg-amber-500 text-slate-950 shadow-sm"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          <Monitor className="w-3 h-3" />
                          <span>16:9 Landscape</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setPreviewOrientation("vertical")}
                          className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${
                            previewOrientation === "vertical"
                              ? "bg-amber-500 text-slate-950 shadow-sm"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          <Smartphone className="w-3 h-3" />
                          <span>9:16 Shorts</span>
                        </button>
                      </div>

                      <button
                        type="button"
                        onClick={() => setPreviewTick((t) => t + 1)}
                        className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-slate-300 hover:bg-white/10 transition-colors cursor-pointer"
                        title="Re-fetch card previews"
                      >
                        <RefreshCw className="w-3 h-3 text-amber-400" />
                        <span>Refresh</span>
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                    {/* Intro Card Box */}
                    <div className="p-3.5 rounded-xl bg-black/40 border border-white/5 space-y-2.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-slate-200 flex items-center gap-1.5">
                          <span>Intro Card</span>
                          <span className="text-[10px] font-mono text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                            {brandingIntroSeconds.toFixed(1)}s
                          </span>
                        </span>
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                            brandingIntro && brandingEnabled
                              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {brandingIntro && brandingEnabled ? "Active in Renders" : "Disabled"}
                        </span>
                      </div>

                      <div
                        className={`relative w-full ${
                          previewOrientation === "landscape"
                            ? "aspect-video max-w-sm mx-auto"
                            : "aspect-[9/16] max-w-[200px] mx-auto"
                        } rounded-lg overflow-hidden bg-[#0B0D13] border border-white/10 shadow-lg flex items-center justify-center`}
                      >
                        <img
                          key={`intro-${previewOrientation}-${previewTick}`}
                          src={getChannelBrandingPreviewUrl({
                            kind: "intro",
                            orientation: previewOrientation,
                            title: brandingIntroTitle,
                            subtitle: brandingIntroSubtitle,
                            accent: brandingAccentColor,
                            background: brandingBackgroundColor,
                            t: previewTick,
                          })}
                          alt="Branded Intro Card Preview"
                          className="w-full h-full object-contain"
                          loading="lazy"
                          onError={(e) => {
                            const target = e.currentTarget;
                            target.style.display = "none";
                            const parent = target.parentElement;
                            if (parent && !parent.querySelector(".preview-fallback")) {
                              const errDiv = document.createElement("div");
                              errDiv.className =
                                "preview-fallback flex flex-col items-center justify-center p-3 text-center text-rose-300 text-xs gap-1";
                              errDiv.innerHTML = `<span>Preview generation error</span><span class="text-[10px] text-slate-400">Click Refresh to retry</span>`;
                              parent.appendChild(errDiv);
                            }
                          }}
                        />
                      </div>
                    </div>

                    {/* Outro Card Box */}
                    <div className="p-3.5 rounded-xl bg-black/40 border border-white/5 space-y-2.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-slate-200 flex items-center gap-1.5">
                          <span>Outro Card</span>
                          <span className="text-[10px] font-mono text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                            {brandingOutroSeconds.toFixed(1)}s
                          </span>
                        </span>
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                            brandingOutro && brandingEnabled
                              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {brandingOutro && brandingEnabled ? "Active in Renders" : "Disabled"}
                        </span>
                      </div>

                      <div
                        className={`relative w-full ${
                          previewOrientation === "landscape"
                            ? "aspect-video max-w-sm mx-auto"
                            : "aspect-[9/16] max-w-[200px] mx-auto"
                        } rounded-lg overflow-hidden bg-[#0B0D13] border border-white/10 shadow-lg flex items-center justify-center`}
                      >
                        <img
                          key={`outro-${previewOrientation}-${previewTick}`}
                          src={getChannelBrandingPreviewUrl({
                            kind: "outro",
                            orientation: previewOrientation,
                            title: brandingOutroTitle,
                            subtitle: brandingOutroSubtitle,
                            accent: brandingAccentColor,
                            background: brandingBackgroundColor,
                            t: previewTick,
                          })}
                          alt="Branded Outro Card Preview"
                          className="w-full h-full object-contain"
                          loading="lazy"
                          onError={(e) => {
                            const target = e.currentTarget;
                            target.style.display = "none";
                            const parent = target.parentElement;
                            if (parent && !parent.querySelector(".preview-fallback")) {
                              const errDiv = document.createElement("div");
                              errDiv.className =
                                "preview-fallback flex flex-col items-center justify-center p-3 text-center text-rose-300 text-xs gap-1";
                              errDiv.innerHTML = `<span>Preview generation error</span><span class="text-[10px] text-slate-400">Click Refresh to retry</span>`;
                              parent.appendChild(errDiv);
                            }
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {brandingEnabled &&
                  brandingIntroSeconds + brandingOutroSeconds > 6 && (
                    <p className="text-[11px] text-amber-300/80">
                      Long bookends — a 60s highlight will no longer fit the 60s
                      Shorts window.
                    </p>
                  )}
              </div>

              {/* Max clip length / upload ceiling */}
              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <div>
                  <h2 className="text-sm font-bold text-white flex items-center gap-2">
                    <Clock className="w-4 h-4 text-amber-400" />
                    Max Clip Length
                  </h2>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Hard ceiling applied to the composed clip (source window +
                    intro/outro cards). Anything at or below it uploads as
                    short-form; 60 / 72 / 88 are labels, never gates.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Ceiling{" "}
                    <span className="font-mono text-amber-300">
                      {maxClipSeconds}s
                    </span>
                  </label>
                  <input
                    type="range"
                    min={30}
                    max={180}
                    step={1}
                    value={maxClipSeconds}
                    onChange={(e) => setMaxClipSeconds(Number(e.target.value))}
                    className="w-full accent-amber-500"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500 mt-1 font-mono">
                    <span>30</span>
                    <span>60</span>
                    <span>72</span>
                    <span>88</span>
                    <span>90</span>
                    <span>180</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {[60, 72, 88, maxClipSeconds].map((tier, idx) => (
                    <span
                      key={`${tier}-${idx}`}
                      className="text-[10px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-300 font-mono"
                    >
                      {tier}s
                    </span>
                  ))}
                </div>
              </div>

              {/* CTA voiceover (TTS + bell chime) */}
              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <Mic className="w-4 h-4 text-amber-400" />
                      CTA Voiceover (TTS + Bell)
                    </h2>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Synthesises a neural voiceover plus the bell chime. The
                      lower-third overlay burns a banner onto the last seconds of
                      gameplay; the outro-card style speaks over your branded
                      outro. Works independently of the intro/outro cards. Needs
                      network on first synthesis, falls back to silence offline
                      and retries on the next render.
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer select-none shrink-0">
                    <input
                      type="checkbox"
                      checked={ctaEnabled}
                      onChange={(e) => setCtaEnabled(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-800 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500" />
                    <span className="ml-2.5 text-xs font-semibold text-slate-300">
                      {ctaEnabled ? "On" : "Off"}
                    </span>
                  </label>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Style
                    </label>
                    <select
                      value={ctaStyle}
                      onChange={(e) => setCtaStyle(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-amber-500"
                    >
                      <option value="outro_card">Outro card</option>
                      <option value="overlay">In-video overlay banner</option>
                    </select>
                    <span className="block text-[10px] text-slate-500 mt-1">
                      {ctaStyle === "overlay"
                        ? "Banner sits on gameplay."
                        : "Plays over branded outro."}
                    </span>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Overlay position
                    </label>
                    <select
                      value={ctaPosition}
                      onChange={(e) => setCtaPosition(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white focus:outline-none focus:border-amber-500"
                    >
                      {CTA_POSITIONS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                    <span className="block text-[10px] text-slate-500 mt-1">
                      Upper third avoids ability HUD.
                    </span>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      {ctaStyle === "overlay" ? "Overlay window" : "Voiceover length"}{" "}
                      <span className="font-mono text-amber-300">
                        {ctaSeconds.toFixed(1)}s
                      </span>
                    </label>
                    <input
                      type="range"
                      min={2}
                      max={10}
                      step={0.5}
                      value={ctaSeconds}
                      onChange={(e) => setCtaSeconds(Number(e.target.value))}
                      className="w-full accent-amber-500"
                    />
                    <span className="block text-[10px] text-slate-500 mt-1">
                      {ctaStyle === "overlay"
                        ? "Banner and audio sit in final seconds."
                        : brandingEnabled && brandingOutro
                          ? `Capped to outro length (${brandingOutroSeconds.toFixed(1)}s).`
                          : "Capped to outro card length."}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Headline
                    </label>
                    <input
                      type="text"
                      value={ctaHeadline}
                      onChange={(e) => setCtaHeadline(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Subtitle
                    </label>
                    <input
                      type="text"
                      value={ctaSubtitle}
                      onChange={(e) => setCtaSubtitle(e.target.value)}
                      className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                </div>

                {ctaEnabled && ctaStyle === "outro_card" && !(brandingEnabled && brandingOutro) ? (
                  <p className="text-[10px] text-amber-300/90 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
                    No outro card is enabled, so the voiceover plays over the end
                    of the clip instead. Enable Branded Intro &amp; Outro cards for
                    a dedicated CTA card.
                  </p>
                ) : null}

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Speech text
                  </label>
                  <textarea
                    value={ctaSpeechText}
                    onChange={(e) => setCtaSpeechText(e.target.value)}
                    rows={2}
                    className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Voice
                  </label>
                  <input
                    type="text"
                    value={ctaVoice}
                    onChange={(e) => setCtaVoice(e.target.value)}
                    className="w-full px-3 py-2 bg-black/40 border border-white/10 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500"
                  />
                  <span className="text-[10px] text-slate-500">
                    edge-tts voice name, e.g. en-US-ChristopherNeural
                  </span>
                </div>

                <div className="flex items-center gap-3 border-t border-white/5 pt-3">
                  <audio
                    src={`${getApiBase()}/channel/assets/bell-chime`}
                    controls
                    className="h-8"
                  />
                  <span className="text-[10px] text-slate-500">
                    Preview the bell chime asset.
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <img
                    src={`${getApiBase()}/channel/branding/preview?kind=overlay&orientation=vertical&t=${previewTick}`}
                    alt="CTA overlay preview"
                    className="h-24 w-auto rounded border border-white/10"
                  />
                  <span className="text-[10px] text-slate-500">
                    Live preview of the in-video overlay pill.
                  </span>
                </div>
              </div>

              {/* Background Music & Seamless Looping (Milestone 5 & 7.3) */}
              <div className="p-5 rounded-2xl bg-[#12141c] border border-white/10 shadow-xl space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <Music className="w-4 h-4 text-emerald-400" />
                      Background Music &amp; Seamless Looping
                    </h2>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Mix creator-supplied background audio into renders beneath
                      gameplay and voiceover with automatic sidechain ducking.
                      Loop optimization applies subtle micro-fades to start and
                      end boundaries for seamless replay looping.
                    </p>
                  </div>
                </div>

                {/* Music Upload and Audio Player */}
                <div className="rounded-xl border border-dashed border-white/15 bg-black/20 p-4 space-y-3">
                  {hasMusic ? (
                    <div className="flex flex-col gap-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          Background track active
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => musicFileInputRef.current?.click()}
                            disabled={isUploadingMusic}
                            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-white/10 cursor-pointer"
                          >
                            Replace track
                          </button>
                          <button
                            type="button"
                            onClick={handleRemoveMusic}
                            disabled={isRemovingMusic}
                            className="px-3 py-1.5 rounded-lg bg-rose-950/50 hover:bg-rose-900/60 text-xs font-semibold text-rose-300 border border-rose-500/30 flex items-center gap-1.5 disabled:opacity-60 cursor-pointer"
                          >
                            {isRemovingMusic ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="w-3.5 h-3.5" />
                            )}
                            Remove
                          </button>
                        </div>
                      </div>

                      <audio
                        key={musicTick}
                        src={`${getChannelMusicUrl()}?t=${musicTick}`}
                        controls
                        className="w-full h-9 rounded-lg"
                      />
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => musicFileInputRef.current?.click()}
                      disabled={isUploadingMusic}
                      className="w-full py-8 rounded-xl flex flex-col items-center gap-2 text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors cursor-pointer disabled:opacity-60"
                    >
                      {isUploadingMusic ? (
                        <Loader2 className="w-7 h-7 animate-spin text-emerald-400" />
                      ) : (
                        <UploadCloud className="w-7 h-7 text-emerald-400" />
                      )}
                      <span className="text-xs font-semibold">
                        {isUploadingMusic
                          ? "Uploading audio..."
                          : "Upload background track (MP3, WAV, AAC, M4A, OGG)"}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        Automatically ducked beneath gameplay sounds and voiceover.
                      </span>
                    </button>
                  )}
                  <input
                    ref={musicFileInputRef}
                    type="file"
                    accept="audio/mpeg,audio/wav,audio/aac,audio/mp4,audio/ogg,audio/flac,.mp3,.wav,.aac,.m4a,.ogg"
                    className="hidden"
                    onChange={(e) => handleMusicFile(e.target.files?.[0])}
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center justify-between">
                      <span>Music Volume</span>
                      <span className="font-mono text-emerald-300">
                        {Math.round(musicVolume * 100)}%
                      </span>
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={Math.round(musicVolume * 100)}
                      onChange={(e) => setMusicVolume(Number(e.target.value) / 100)}
                      className="w-full accent-emerald-500"
                    />
                    <span className="block text-[10px] text-slate-500 mt-1">
                      Relative to gameplay audio. Default is 30%.
                    </span>
                  </div>

                  <label className="flex flex-col justify-between rounded-xl bg-black/30 border border-white/10 p-3 cursor-pointer hover:border-white/20 transition-colors">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                        <RefreshCw className="w-3.5 h-3.5 text-emerald-400" />
                        Seamless Loop Optimization
                      </span>
                      <input
                        type="checkbox"
                        checked={loopOptimization}
                        onChange={(e) => setLoopOptimization(e.target.checked)}
                        className="w-4 h-4 accent-emerald-500"
                      />
                    </div>
                    <span className="text-[11px] text-slate-400 leading-normal">
                      Applies subtle 100ms micro-fades at the clip boundaries to prevent audio pops on loop playback.
                    </span>
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-between gap-4 p-4 rounded-2xl bg-slate-900/60 border border-white/10">
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Stored locally in your BackseatCaster database — no cloud account required.</span>
                </div>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold shadow-md shadow-rose-900/30 transition-all cursor-pointer active:scale-95 disabled:opacity-60"
                >
                  {isSaving ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  )}
                  <span>{isSaving ? "Saving..." : "Save channel profile"}</span>
                </button>
              </div>
            </section>
          </form>
        )}
      </main>
    </div>
  );
}
