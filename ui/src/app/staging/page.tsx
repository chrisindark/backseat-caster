"use client";

import { Navbar } from "@/components/Navbar";
import { YoutubeIcon } from "@/components/icons";
import {
  fetchRenders,
  fetchYouTubeQuota,
  getStreamUrl,
  getYouTubeAuthStatus,
  getYouTubeAuthUrl,
  regenerateClipMetadata,
  updateUploadSelection,
  uploadClipToYouTube,
  uploadSelectedClipsToYouTube,
} from "@/lib/api";
import {
  RenderManifest,
  UploadSelectionPayload,
  YouTubeAuthStatus,
  YouTubeQuota,
  YouTubeUploadResult,
} from "@/types/video";

export type UploadPrivacy = "private" | "unlisted" | "public";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  FileJson,
  Gauge,
  History,
  Layers,
  Loader2,
  Radio,
  RefreshCw,
  Scissors,
  Smartphone,
  Sparkles,
  Trash2,
  Tv,
  UploadCloud,
  Wand2,
} from "lucide-react";
import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";

export type UploadFormat = string;

function getDefaultMetadata(item: RenderManifest) {
  const preferred: UploadFormat =
    item.upload_selection?.preferred_format ||
    (item.modes && item.modes[0]) ||
    (item.outputs && Object.keys(item.outputs)[0]) ||
    "vertical_blur";
  const start = item.clip?.start_seconds ?? item.request?.start_seconds ?? 0;
  const dur = item.clip?.duration_seconds ?? item.request?.duration_seconds ?? 15;
  const defaultTitle =
    item.upload_selection?.title ||
    `${item.video_title ? `${item.video_title.slice(0, 50)} - ` : ""}Highlight (${Math.round(start)}s-${Math.round(start + dur)}s)`;
  const defaultDesc =
    item.upload_selection?.description ||
    `Gameplay highlight rendered with BackseatCaster AI Clip Engine.\n#MarvelRivals #Gaming #Shorts #Highlight`;
  const defaultTags =
    (item.upload_selection?.tags || ["Gaming", "MarvelRivals", "Highlights", "Shorts"]).join(", ");
  const privacyVal: UploadPrivacy =
    item.upload_selection?.privacy === "private" ||
    item.upload_selection?.privacy === "unlisted"
      ? item.upload_selection.privacy
      : "public";

  return {
    title: defaultTitle,
    description: defaultDesc,
    tags: defaultTags,
    privacy: privacyVal,
    format: preferred,
    hero_name: item.upload_selection?.hero_name || "",
    clip_context: item.upload_selection?.clip_context || "",
  };
}

export default function StagingPage() {
  const [renders, setRenders] = useState<RenderManifest[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form metadata mapped by clip_id
  const [clipMetadata, setClipMetadata] = useState<
    Record<
      string,
      {
        title: string;
        description: string;
        tags: string;
        privacy: UploadPrivacy;
        format: UploadFormat;
        hero_name?: string;
        clip_context?: string;
      }
    >
  >({});

  // YouTube auth and quota states
  const [ytAuth, setYtAuth] = useState<YouTubeAuthStatus | null>(null);
  const [quota, setQuota] = useState<YouTubeQuota | null>(null);
  const [uploadingClipIds, setUploadingClipIds] = useState<Set<string>>(new Set());
  const [isUploadingBatch, setIsUploadingBatch] = useState<boolean>(false);
  const [uploadedClips, setUploadedClips] = useState<Record<string, YouTubeUploadResult>>({});
  const [savingId, setSavingId] = useState<string | null>(null);

  // AI vs deterministic regeneration
  const [useAiCopy, setUseAiCopy] = useState<boolean>(true);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [previousCopies, setPreviousCopies] = useState<
    Record<
      string,
      { title?: string | null; description?: string | null; metadata_source?: string }
    >
  >({});

  // Load staged renders, YouTube auth, and quota
  const loadStagingData = useCallback(async () => {
    try {
      setErrorMessage(null);
      const [rendersRes, authRes, quotaRes] = await Promise.allSettled([
        fetchRenders(),
        getYouTubeAuthStatus(),
        fetchYouTubeQuota(),
      ]);

      if (rendersRes.status === "fulfilled" && rendersRes.value?.items) {
        // Filter renders selected for upload or auto-staged
        const staged = rendersRes.value.items.filter(
          (r) => r.upload_selection?.is_selected || r.auto_staged
        );
        setRenders(staged);

        // Initialize metadata map for any new renders
        setClipMetadata((prev) => {
          const next = { ...prev };
          staged.forEach((item) => {
            if (!next[item.clip_id]) {
              next[item.clip_id] = getDefaultMetadata(item);
            }
          });
          return next;
        });
      }

      if (authRes.status === "fulfilled") {
        setYtAuth(authRes.value);
      }

      if (quotaRes.status === "fulfilled") {
        setQuota(quotaRes.value);
      }
    } catch (err: unknown) {
      console.warn("Error loading staging page:", err);
      setErrorMessage(err instanceof Error ? err.message : "Failed to load staging data");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadStagingData();
  }, [loadStagingData]);

  const handleRefresh = () => {
    setIsRefreshing(true);
    loadStagingData();
  };

  const handleFieldChange = (
    clipId: string,
    field: "title" | "description" | "tags" | "privacy" | "format" | "hero_name" | "clip_context",
    value: string
  ) => {
    setClipMetadata((prev) => {
      const renderItem = renders.find((r) => r.clip_id === clipId);
      const existing = prev[clipId] || (renderItem ? getDefaultMetadata(renderItem) : {
        title: clipId,
        description: "",
        tags: "Gaming, Highlights, Shorts",
        privacy: "public" as UploadPrivacy,
        format: "vertical_blur" as UploadFormat,
        hero_name: "",
        clip_context: "",
      });

      return {
        ...prev,
        [clipId]: {
          ...existing,
          [field]: value,
        },
      };
    });
  };

  const handleSaveClipMetadata = async (clipId: string) => {
    const meta = clipMetadata[clipId];
    if (!meta) return;
    setSavingId(clipId);
    try {
      const tagsArray = meta.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      await updateUploadSelection(clipId, {
        is_selected: true,
        preferred_format: meta.format,
        title: meta.title,
        description: meta.description,
        tags: tagsArray,
        privacy: meta.privacy,
        hero_name: meta.hero_name,
        clip_context: meta.clip_context,
      });

      setSuccessMessage(`Saved staging details for ${clipId}`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed saving staging");
    } finally {
      setSavingId(null);
    }
  };

  const handleRegenerate = async (clipId: string) => {
    setRegeneratingId(clipId);
    setErrorMessage(null);
    try {
      const currentMeta = clipMetadata[clipId];
      const res = await regenerateClipMetadata(clipId, {
        use_llm: useAiCopy,
        hero_name: currentMeta?.hero_name || undefined,
        clip_context: currentMeta?.clip_context || undefined,
      });

      if (res.previous && (res.previous.title || res.previous.description)) {
        setPreviousCopies((prev) => ({ ...prev, [clipId]: res.previous! }));
      }

      setClipMetadata((prev) => {
        const base = prev[clipId] || {
          title: "",
          description: "",
          tags: "",
          privacy: "public" as UploadPrivacy,
          format: "vertical_blur" as UploadFormat,
          hero_name: "",
          clip_context: "",
        };
        return {
          ...prev,
          [clipId]: {
            ...base,
            title: res.upload_selection.title || base.title,
            description: res.upload_selection.description || base.description,
            tags: (res.upload_selection.tags || []).join(", "),
            privacy: (res.upload_selection.privacy as UploadPrivacy) || base.privacy,
            format: (res.upload_selection.preferred_format as UploadFormat) || base.format,
            hero_name: (res.upload_selection.hero_name as string) || base.hero_name,
            clip_context: (res.upload_selection.clip_context as string) || base.clip_context,
          },
        };
      });

      setSuccessMessage(
        res.used_llm
          ? `Gemini AI copy generated for ${clipId}!`
          : `Deterministic copy refreshed for ${clipId}.`
      );
      setTimeout(() => setSuccessMessage(null), 3500);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Regeneration failed");
    } finally {
      setRegeneratingId(null);
    }
  };

  const handleRemoveFromQueue = async (clipId: string) => {
    try {
      await updateUploadSelection(clipId, { is_selected: false });
      setRenders((prev) => prev.filter((r) => r.clip_id !== clipId));
      setSuccessMessage(`Removed ${clipId} from upload staging`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to remove clip");
    }
  };

  const handleClearAll = async () => {
    if (!confirm("Remove all clips from the upload staging queue?")) return;
    try {
      await Promise.all(
        renders.map((r) => updateUploadSelection(r.clip_id, { is_selected: false }))
      );
      setRenders([]);
      setSuccessMessage("Cleared upload staging queue");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed clearing queue");
    }
  };

  /** Warning message when the daily YouTube API budget is already exhausted. */
  const buildQuotaWarning = (): string | null => {
    if (!quota || quota.can_upload) return null;
    return (
      `Daily YouTube API quota is exhausted today ` +
      `(${quota.units_used.toLocaleString()} / ${quota.daily_limit_units.toLocaleString()} units, ` +
      `~${quota.max_uploads_per_day} uploads used). You can still attempt the upload — ` +
      "it will likely fail with a quotaExceeded error on YouTube's side until the quota resets at Pacific midnight."
    );
  };

  const handleUploadSingle = async (clipId: string) => {
    if (!ytAuth?.is_authenticated) {
      setErrorMessage("Please connect YouTube account first.");
      return;
    }
    const quotaWarning = buildQuotaWarning();
    if (
      quotaWarning &&
      !confirm(`${quotaWarning}\n\nProceed with the upload anyway?`)
    ) {
      return;
    }
    setUploadingClipIds((prev) => new Set(prev).add(clipId));
    setErrorMessage(null);
    try {
      const meta = clipMetadata[clipId];
      if (meta) {
        await updateUploadSelection(clipId, {
          is_selected: true,
          preferred_format: meta.format,
          title: meta.title,
          description: meta.description,
          tags: meta.tags.split(",").map((t) => t.trim()).filter(Boolean),
          privacy: meta.privacy,
          hero_name: meta.hero_name,
          clip_context: meta.clip_context,
        });
      }
      const res = await uploadClipToYouTube(clipId);
      setUploadedClips((prev) => ({ ...prev, [clipId]: res }));
      setSuccessMessage(`Successfully uploaded "${res.title}" to YouTube!`);
      // Refresh quota after upload
      fetchYouTubeQuota().then(setQuota).catch(() => {});
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : `Failed uploading ${clipId}`);
    } finally {
      setUploadingClipIds((prev) => {
        const next = new Set(prev);
        next.delete(clipId);
        return next;
      });
    }
  };

  const handleBatchUpload = async () => {
    if (!ytAuth?.is_authenticated) {
      setErrorMessage("Please connect your YouTube account first.");
      return;
    }
    const eligibleClips = renders.filter(
      (r) => !uploadedClips[r.clip_id] && !r.youtube_upload
    );
    if (eligibleClips.length === 0) {
      setErrorMessage("All clips in this queue have already been uploaded.");
      return;
    }

    const quotaWarning = buildQuotaWarning();
    const confirmation = quotaWarning
      ? `${quotaWarning}\n\nUpload all ${eligibleClips.length} queued clips to YouTube now anyway?`
      : `Upload all ${eligibleClips.length} queued clips to YouTube now?`;
    if (!confirm(confirmation)) {
      return;
    }

    setIsUploadingBatch(true);
    setErrorMessage(null);

    try {
      // Sync metadata for all clips first
      for (const item of eligibleClips) {
        const meta = clipMetadata[item.clip_id];
        if (meta) {
          await updateUploadSelection(item.clip_id, {
            is_selected: true,
            preferred_format: meta.format,
            title: meta.title,
            description: meta.description,
            tags: meta.tags.split(",").map((t) => t.trim()).filter(Boolean),
            privacy: meta.privacy,
            hero_name: meta.hero_name,
            clip_context: meta.clip_context,
          });
        }
      }

      const res = await uploadSelectedClipsToYouTube(true);

      const resultMap: Record<string, YouTubeUploadResult> = {};
      res.results.forEach((r) => {
        resultMap[r.clip_id] = r;
      });
      setUploadedClips((prev) => ({ ...prev, ...resultMap }));
      setSuccessMessage(
        `Batch upload complete: ${res.total_succeeded} succeeded, ${res.total_failed} failed.`
      );
      fetchYouTubeQuota().then(setQuota).catch(() => {});
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Batch upload failed");
    } finally {
      setIsUploadingBatch(false);
    }
  };

  const handleExportJSON = () => {
    const payload = renders.map((r) => ({
      clip_id: r.clip_id,
      video_id: r.video_id,
      video_title: r.video_title,
      start_seconds: r.clip?.start_seconds ?? r.request?.start_seconds,
      duration_seconds: r.clip?.duration_seconds ?? r.request?.duration_seconds,
      upload_selection: clipMetadata[r.clip_id] || getDefaultMetadata(r),
    }));

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `backseat-caster-staging-queue-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleConnectYouTube = async () => {
    try {
      const auth = await getYouTubeAuthUrl();
      if (auth.auth_url) {
        window.location.href = auth.auth_url;
      }
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Could not initialize YouTube OAuth");
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-slate-100 flex flex-col font-sans selection:bg-rose-500/30">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6 space-y-6">
        {/* Breadcrumb Navigation & Top Toolbar */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-white/10">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Link
                href="/renders"
                className="flex items-center gap-1 hover:text-white transition-colors text-slate-400"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Renders Gallery</span>
              </Link>
              <span>/</span>
              <span className="text-slate-200 font-medium">Staging Queue</span>
            </div>
            <h1 className="text-2xl lg:text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400 flex items-center gap-2.5">
              <UploadCloud className="w-7 h-7 text-rose-500 shrink-0" />
              <span>Publishing Staging Queue</span>
            </h1>
            <p className="text-xs lg:text-sm text-slate-400">
              Watch clips, verify hero identity & play context, generate Gemini AI copy, and publish to YouTube Shorts.
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2.5 flex-wrap">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="p-2 rounded-xl bg-slate-900 border border-white/10 hover:border-white/20 text-slate-300 hover:text-white transition-all text-xs"
              title="Refresh Queue"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
            </button>

            {renders.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={handleExportJSON}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold border border-white/10 transition-colors"
                >
                  <FileJson className="w-3.5 h-3.5" />
                  <span>Export JSON</span>
                </button>

                <button
                  type="button"
                  onClick={handleClearAll}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-rose-950/40 text-slate-400 hover:text-rose-300 text-xs font-semibold border border-white/10 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Clear Queue</span>
                </button>
              </>
            )}

            {/* Batch Upload Button */}
            <button
              type="button"
              onClick={handleBatchUpload}
              disabled={isUploadingBatch || renders.length === 0}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-rose-600 via-rose-500 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold shadow-lg shadow-rose-950/60 disabled:opacity-50 transition-all cursor-pointer"
            >
              {isUploadingBatch ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <YoutubeIcon className="w-4 h-4" />
              )}
              <span>
                {isUploadingBatch ? "Uploading Batch..." : `Upload All Selected (${renders.length})`}
              </span>
            </button>
          </div>
        </div>

        {/* Global Notifications */}
        {errorMessage && (
          <div className="p-3.5 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-3 animate-in fade-in">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <button
              type="button"
              onClick={() => setErrorMessage(null)}
              className="text-xs text-rose-400 hover:text-white underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {successMessage && (
          <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/25 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Top Status Strip: Quota, Auth, and AI Toggle */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
          {/* YouTube API Quota Card */}
          <div className="p-3.5 rounded-2xl bg-slate-900/70 border border-white/10 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                <Gauge className="w-4 h-4 text-emerald-400" />
                <span>YouTube API Daily Quota</span>
              </span>
              <span className="font-mono text-[11px] text-slate-400">
                {quota ? `${quota.units_used.toLocaleString()} / ${quota.daily_limit_units.toLocaleString()}` : "10,000 units"}
              </span>
            </div>
            {quota && (
              <div className="space-y-1">
                <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      !quota.can_upload
                        ? "bg-rose-500"
                        : quota.units_used >= 8000
                          ? "bg-amber-400"
                          : "bg-emerald-500"
                    }`}
                    style={{
                      width: `${Math.min(100, Math.max(2, (quota.units_used / quota.daily_limit_units) * 100))}%`,
                    }}
                  />
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-500">
                  <span>~{quota.uploads_remaining} uploads remaining today</span>
                  <span>Resets at Pacific Midnight</span>
                </div>
              </div>
            )}
          </div>

          {/* YouTube Auth Status Card */}
          <div className="p-3.5 rounded-2xl bg-slate-900/70 border border-white/10 flex items-center justify-between gap-3">
            <div className="space-y-0.5">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                Target Channel
              </span>
              <p className="text-xs font-bold text-white flex items-center gap-1.5">
                {ytAuth?.is_authenticated ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400" />
                    <span>{ytAuth.channel_title || "Connected Channel"}</span>
                  </>
                ) : (
                  <>
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    <span>Not Connected</span>
                  </>
                )}
              </p>
              <p className="text-[11px] text-slate-500 font-mono">
                {ytAuth?.channel_handle || (ytAuth?.is_authenticated ? "OAuth Active" : "OAuth Required")}
              </p>
            </div>

            {!ytAuth?.is_authenticated ? (
              <button
                type="button"
                onClick={handleConnectYouTube}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-red-600 hover:bg-red-500 text-white text-xs font-semibold shadow-md transition-colors whitespace-nowrap cursor-pointer"
              >
                <YoutubeIcon className="w-3.5 h-3.5" />
                <span>Connect</span>
              </button>
            ) : (
              <div className="p-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                <CheckCircle2 className="w-5 h-5" />
              </div>
            )}
          </div>

          {/* Global AI Copy Generation Toggle */}
          <div className="p-3.5 rounded-2xl bg-slate-900/70 border border-white/10 flex flex-col justify-between gap-2">
            <div>
              <span className="text-[11px] font-semibold text-violet-300 uppercase tracking-wider block flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-violet-400" />
                <span>AI Copy Engine (Gemini)</span>
              </span>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Conditions on hero identity, kill streaks, and gameplay context notes.
              </p>
            </div>
            <label className="inline-flex items-center gap-2 text-xs text-slate-200 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={useAiCopy}
                onChange={(e) => setUseAiCopy(e.target.checked)}
                className="h-4 w-4 rounded accent-violet-600 cursor-pointer"
              />
              <span className="font-medium">Use AI copy (Gemini) when regenerating</span>
            </label>
          </div>
        </div>

        {/* Staging Queue Clip List */}
        {isLoading ? (
          <div className="py-24 flex flex-col items-center justify-center space-y-3 text-center">
            <Loader2 className="w-8 h-8 text-rose-500 animate-spin" />
            <p className="text-sm font-semibold text-white">Loading Staged Clips...</p>
            <p className="text-xs text-slate-500">Checking pending renders and staged upload metadata</p>
          </div>
        ) : renders.length === 0 ? (
          <div className="py-20 text-center space-y-4 rounded-3xl bg-slate-900/40 border border-white/5 p-8 max-w-xl mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center mx-auto">
              <UploadCloud className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-white">No Clips Staged for Publishing Yet</h3>
              <p className="text-xs text-slate-400 leading-relaxed max-w-md mx-auto">
                Stage clips from the Renders Gallery or Studio timeline to review them with live video previews, tag hero identities, and publish to YouTube.
              </p>
            </div>
            <div className="flex items-center justify-center gap-3 pt-2">
              <Link
                href="/renders"
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold transition-colors"
              >
                <Layers className="w-4 h-4" />
                <span>Browse Renders</span>
              </Link>
              <Link
                href="/studio"
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-white/10 transition-colors"
              >
                <Scissors className="w-4 h-4" />
                <span>Open Studio</span>
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center justify-between text-xs text-slate-400 px-1">
              <span>Showing {renders.length} clip{renders.length === 1 ? "" : "s"} staged for upload</span>
              <span className="text-[11px] text-slate-500 font-mono">Changes save automatically on blur or via Save</span>
            </div>

            {renders.map((render) => {
              const meta = clipMetadata[render.clip_id] || getDefaultMetadata(render);
              const chosenFormat = meta.format;
              const streamUrl = getStreamUrl(render.clip_id, chosenFormat);
              const isShort = chosenFormat === "vertical_blur" || chosenFormat === "vertical_crop" || chosenFormat === "third_person" || chosenFormat === "direct_crop" || chosenFormat === "cinematic";
              const isUploading = uploadingClipIds.has(render.clip_id);
              const uploadResult = uploadedClips[render.clip_id];
              const isAlreadyUploaded = Boolean(uploadResult || render.youtube_upload);

              return (
                <div
                  key={render.clip_id}
                  className="p-5 lg:p-6 rounded-2xl bg-slate-950/80 border border-white/10 hover:border-white/20 transition-all shadow-xl space-y-4"
                >
                  {/* Card Header: Title, Timing, Format Switcher & Remove */}
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-white/5">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-rose-400 font-bold bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
                          {render.clip_id}
                        </span>
                        <span className="text-xs text-slate-400 font-mono">
                          {render.clip?.duration_seconds ?? render.request?.duration_seconds ?? 15}s duration
                        </span>
                        {isAlreadyUploaded && (
                          <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            Published
                          </span>
                        )}
                      </div>
                      <h3 className="text-sm font-bold text-slate-100 line-clamp-1">
                        {render.video_title || "Gameplay Highlight"}
                      </h3>
                    </div>

                    {/* Format Selector Pills */}
                    <div className="flex items-center gap-1.5 bg-slate-900 p-1 rounded-xl border border-white/10 flex-wrap self-end sm:self-auto">
                      {(() => {
                        const list: string[] = [];
                        if (render.outputs) {
                          for (const k of Object.keys(render.outputs)) {
                            if (render.outputs[k] && !list.includes(k)) list.push(k);
                          }
                        }
                        if (render.modes) {
                          for (const m of render.modes) {
                            if (!list.includes(m)) list.push(m);
                          }
                        }
                        const hasSpecialCrop = list.some((m) =>
                          ["third_person", "direct_crop", "cinematic", "custom"].includes(m)
                        );
                        const filtered = hasSpecialCrop ? list.filter((m) => m !== "vertical_crop") : list;
                        const formats = filtered.length > 0 ? filtered : ["vertical_blur", "third_person", "landscape"];

                        return formats.map((fmt) => (
                          <button
                            key={fmt}
                            type="button"
                            onClick={() => {
                              handleFieldChange(render.clip_id, "format", fmt);
                              handleSaveClipMetadata(render.clip_id);
                            }}
                            className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 ${
                              chosenFormat === fmt
                                ? "bg-rose-600 text-white shadow-md shadow-rose-950"
                                : "text-slate-400 hover:text-white hover:bg-white/5"
                            }`}
                          >
                            {fmt === "landscape" ? <Tv className="w-3 h-3" /> : <Smartphone className="w-3 h-3" />}
                            <span className="capitalize">{fmt.replace("_", " ")}</span>
                          </button>
                        ));
                      })()}

                      {/* Remove Button */}
                      <button
                        type="button"
                        onClick={() => handleRemoveFromQueue(render.clip_id)}
                        className="p-1 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors ml-1"
                        title="Remove clip from staging queue"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* 2-Column Main Section: Video Viewer (Left) + Metadata & AI Editor (Right) */}
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
                    {/* Left Column: Embedded Video Viewer (5 cols) */}
                    <div className="lg:col-span-5 flex flex-col items-center justify-center space-y-2">
                      <div
                        className={`w-full bg-black rounded-xl overflow-hidden border border-white/10 relative shadow-2xl flex items-center justify-center ${
                          chosenFormat === "landscape"
                            ? "aspect-video max-w-md"
                            : "aspect-[9/16] max-w-[220px]"
                        }`}
                      >
                        <video
                          key={`${render.clip_id}-${chosenFormat}`}
                          src={streamUrl}
                          controls
                          playsInline
                          preload="metadata"
                          className="w-full h-full object-contain bg-black"
                        />
                        <div className="absolute top-2 left-2 pointer-events-none">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-black/70 border border-white/10 text-white backdrop-blur-sm">
                            {isShort ? "9:16 Shorts" : "16:9 Master"}
                          </span>
                        </div>
                      </div>
                      <span className="text-[11px] text-slate-500 text-center">
                        Playing: <code className="text-slate-400 font-mono capitalize">{chosenFormat.replace("_", " ")}</code> format
                      </span>
                    </div>

                    {/* Right Column: Hero, Context Notes, Title, Description, Tags (7 cols) */}
                    <div className="lg:col-span-7 space-y-3.5">
                      {/* Hero & Context Hints for LLM Copy Generation */}
                      <div className="p-3 rounded-xl bg-slate-900/80 border border-violet-500/25 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-violet-300 flex items-center gap-1.5">
                            <Sparkles className="w-3.5 h-3.5 text-violet-400" />
                            <span>Hero Identity & Play Context</span>
                          </span>
                          <span className="text-[10px] text-violet-400/80">Context for AI Title & Tags</span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                          {/* Hero Identity input */}
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-slate-300">
                              Hero Identity
                            </label>
                            <input
                              type="text"
                              list="marvel-rivals-heroes-list"
                              value={meta.hero_name || ""}
                              onChange={(e) => handleFieldChange(render.clip_id, "hero_name", e.target.value)}
                              onBlur={() => handleSaveClipMetadata(render.clip_id)}
                              placeholder="e.g. Magneto, Luna Snow, Spider-Man..."
                              className="w-full px-3 py-1.5 bg-slate-950 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500 text-xs"
                            />
                          </div>

                          {/* Clip Context / Notes input */}
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-slate-300">
                              Clip Context / Notes
                            </label>
                            <input
                              type="text"
                              value={meta.clip_context || ""}
                              onChange={(e) => handleFieldChange(render.clip_id, "clip_context", e.target.value)}
                              onBlur={() => handleSaveClipMetadata(render.clip_id)}
                              placeholder="e.g. 5K streak holding point B..."
                              className="w-full px-3 py-1.5 bg-slate-950 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500 text-xs"
                            />
                          </div>
                        </div>

                        {/* Regenerate AI Copy Button right inside context box */}
                        <div className="pt-1 flex items-center justify-between gap-2 flex-wrap">
                          <button
                            type="button"
                            onClick={() => handleRegenerate(render.clip_id)}
                            disabled={regeneratingId === render.clip_id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/25 hover:bg-violet-600/40 text-violet-200 border border-violet-500/35 font-semibold text-xs transition-colors cursor-pointer disabled:opacity-50"
                            title="Generate punchy YouTube Shorts title, description, and hashtags"
                          >
                            {regeneratingId === render.clip_id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Wand2 className="w-3.5 h-3.5 text-violet-400" />
                            )}
                            <span>
                              {regeneratingId === render.clip_id
                                ? "Generating Copy..."
                                : `Generate (${useAiCopy ? "Gemini AI" : "Deterministic"}) Copy`}
                            </span>
                          </button>

                          {previousCopies[render.clip_id] && (
                            <span className="text-[10px] text-slate-400 truncate max-w-xs flex items-center gap-1">
                              <History className="w-3 h-3 text-slate-500 shrink-0" />
                              <span>Prev: <span className="line-through">{previousCopies[render.clip_id].title}</span></span>
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Video Title */}
                      <div className="space-y-1 text-xs">
                        <label className="text-[11px] font-semibold text-slate-300">
                          Upload Title
                        </label>
                        <input
                          type="text"
                          value={meta.title}
                          onChange={(e) => handleFieldChange(render.clip_id, "title", e.target.value)}
                          onBlur={() => handleSaveClipMetadata(render.clip_id)}
                          placeholder="Video or Shorts title..."
                          className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500 text-xs"
                        />
                      </div>

                      {/* Description */}
                      <div className="space-y-1 text-xs">
                        <label className="text-[11px] font-semibold text-slate-300">
                          Description & Hashtags
                        </label>
                        <textarea
                          rows={2}
                          value={meta.description}
                          onChange={(e) => handleFieldChange(render.clip_id, "description", e.target.value)}
                          onBlur={() => handleSaveClipMetadata(render.clip_id)}
                          placeholder="Video description with hashtags..."
                          className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500 text-xs resize-none"
                        />
                      </div>

                      {/* Tags & Privacy */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                        <div className="sm:col-span-2 space-y-1">
                          <label className="text-[11px] font-semibold text-slate-300">
                            Tags (comma separated)
                          </label>
                          <input
                            type="text"
                            value={meta.tags}
                            onChange={(e) => handleFieldChange(render.clip_id, "tags", e.target.value)}
                            onBlur={() => handleSaveClipMetadata(render.clip_id)}
                            placeholder="Gaming, MarvelRivals, Shorts..."
                            className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500 text-xs"
                          />
                        </div>

                        <div className="space-y-1">
                          <label className="text-[11px] font-semibold text-slate-300">
                            Privacy
                          </label>
                          <select
                            value={meta.privacy}
                            onChange={(e) => {
                              handleFieldChange(render.clip_id, "privacy", e.target.value);
                              handleSaveClipMetadata(render.clip_id);
                            }}
                            className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 focus:outline-none focus:border-rose-500 text-xs cursor-pointer"
                          >
                            <option value="public">Public</option>
                            <option value="unlisted">Unlisted</option>
                            <option value="private">Private</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Card Footer: Save & Single Upload Buttons */}
                  <div className="pt-3 border-t border-white/5 flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleSaveClipMetadata(render.clip_id)}
                        disabled={savingId === render.clip_id}
                        className="px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 text-xs font-semibold border border-white/10 transition-colors disabled:opacity-50"
                      >
                        {savingId === render.clip_id ? "Saving..." : "Save Staging"}
                      </button>
                    </div>

                    <div className="flex items-center gap-2">
                      {/* Watch on YouTube if uploaded */}
                      {isAlreadyUploaded && (uploadResult?.youtube_url || render.youtube_upload?.url) && (
                        <a
                          href={uploadResult?.youtube_url || render.youtube_upload?.url || "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-rose-400 hover:text-rose-300 text-xs font-semibold border border-rose-500/20 transition-colors"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          <span>Watch on YouTube</span>
                        </a>
                      )}

                      {/* Upload Single Button */}
                      <button
                        type="button"
                        onClick={() => handleUploadSingle(render.clip_id)}
                        disabled={isUploading}
                        className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold shadow-md shadow-rose-950/40 transition-all cursor-pointer disabled:opacity-50"
                      >
                        {isUploading ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <YoutubeIcon className="w-3.5 h-3.5" />
                        )}
                        <span>{isUploading ? "Uploading..." : isAlreadyUploaded ? "Re-Upload" : "Upload to YouTube"}</span>
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* Marvel Rivals Heroes Autocomplete Datalist */}
      <datalist id="marvel-rivals-heroes-list">
        {[
          "Adam Warlock", "Angela", "Black Cat", "Black Panther", "Black Widow", "Blade",
          "Captain America", "Cloak & Dagger", "Cyclops", "Daredevil", "Deadpool",
          "Doctor Strange", "Emma Frost", "Groot", "Hawkeye", "Hela", "Hulk",
          "Human Torch", "Invisible Woman", "Iron Fist", "Iron Man", "Jeff the Land Shark",
          "Loki", "Luna Snow", "Magik", "Magneto", "Mantis", "Mister Fantastic",
          "Moon Knight", "Namor", "Peni Parker", "Psylocke", "Punisher", "Rocket Raccoon",
          "Scarlet Witch", "Spider-Man", "Star-Lord", "Storm", "The Thing", "Thor",
          "Venom", "Winter Soldier", "Wolverine",
        ].map((hero) => (
          <option key={hero} value={hero} />
        ))}
      </datalist>
    </div>
  );
}
