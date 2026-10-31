"use client";

import { Navbar } from "@/components/Navbar";
import {
  checkBackendHealth,
  deleteChannelWatermark,
  fetchChannelProfile,
  getChannelWatermarkUrl,
  updateChannelProfile,
  uploadChannelWatermark,
  getApiBase,
} from "@/lib/api";
import { ChannelProfile, ChannelProfileUpdate } from "@/types/video";
import {
  AlertCircle,
  CheckCircle2,
  Clapperboard,
  Clock,
  Hash,
  Image as ImageIcon,
  Layers,
  Mic,
  Loader2,
  Palette,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
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
  const [watermarkEnabled, setWatermarkEnabled] = useState(true);
  const [watermarkPosition, setWatermarkPosition] = useState("bottom_right");
  const [watermarkOpacity, setWatermarkOpacity] = useState(0.85);
  const [watermarkScale, setWatermarkScale] = useState(0.14);
  const [watermarkMargin, setWatermarkMargin] = useState(0.03);
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

  const [maxClipSeconds, setMaxClipSeconds] = useState(90);
  const [previewTick, setPreviewTick] = useState(0);

  // CTA voiceover (TTS + bell chime)
  const [ctaEnabled, setCtaEnabled] = useState(false);
  const [ctaStyle, setCtaStyle] = useState("outro_card");
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
    setWatermarkEnabled(Boolean(data.watermark_enabled));
    setWatermarkPosition(data.watermark_position || "bottom_right");
    setWatermarkOpacity(data.watermark_opacity ?? 0.85);
    setWatermarkScale(data.watermark_scale ?? 0.14);
    setWatermarkMargin(data.watermark_margin ?? 0.03);
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
    setMaxClipSeconds(data.max_clip_seconds ?? 90);
    setCtaEnabled(Boolean(data.cta_enabled));
    setCtaStyle(data.cta_style || "outro_card");
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
      const data = await fetchChannelProfile();
      applyProfile(data);
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
        watermark_enabled: watermarkEnabled,
        watermark_position: watermarkPosition,
        watermark_opacity: watermarkOpacity,
        watermark_scale: watermarkScale,
        watermark_margin: watermarkMargin,
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
        max_clip_seconds: maxClipSeconds,
        cta_enabled: ctaEnabled,
        cta_style: ctaStyle,
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

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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

                <div className="flex items-center gap-3 border-t border-white/5 pt-3">
                  <img
                    src={`${getApiBase()}/channel/branding/preview?kind=intro&orientation=landscape&t=${previewTick}`}
                    alt="Intro card preview"
                    className="h-16 w-auto rounded border border-white/10"
                  />
                  <img
                    src={`${getApiBase()}/channel/branding/preview?kind=outro&orientation=landscape&t=${previewTick}`}
                    alt="Outro card preview"
                    className="h-16 w-auto rounded border border-white/10"
                  />
                  <button
                    type="button"
                    onClick={() => setPreviewTick((t) => t + 1)}
                    className="text-[10px] px-2 py-1 rounded bg-white/5 border border-white/10 text-slate-300 hover:bg-white/10 cursor-pointer"
                  >
                    Refresh previews
                  </button>
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
                      Synthesises a neural voiceover plus the bell chime and mixes
                      it into the outro of every render. Requires network on first
                      use; results are cached by text + voice.
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

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
                      <option value="overlay">In-video overlay (planned)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Voiceover length{" "}
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
                  </div>
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
