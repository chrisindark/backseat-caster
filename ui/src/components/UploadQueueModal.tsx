"use client";

import {
  getStreamUrl,
  getYouTubeAuthStatus,
  getYouTubeAuthUrl,
  regenerateClipMetadata,
  uploadClipToYouTube,
  uploadSelectedClipsToYouTube,
} from "@/lib/api";
import { useScrollLock } from "@/lib/useScrollLock";
import {
  RenderManifest,
  UploadSelectionPayload,
  YouTubeAuthStatus,
  YouTubeUploadResult,
} from "@/types/video";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  ExternalLink,
  FileJson,
  History,
  Loader2,
  Radio,
  Smartphone,
  Trash2,
  Tv,
  UploadCloud,
  Wand2,
  X,
} from "lucide-react";
import React, { useEffect, useState } from "react";
import { YoutubeIcon } from "./icons";

export type UploadFormat = string;
export type UploadPrivacy = "private" | "unlisted" | "public";

interface UploadQueueModalProps {
  selectedRenders: RenderManifest[];
  onUpdateSelection: (clipId: string, payload: UploadSelectionPayload) => Promise<void>;
  onClose: () => void;
  onClearAll: () => Promise<void>;
}

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

export const UploadQueueModal: React.FC<UploadQueueModalProps> = ({
  selectedRenders,
  onUpdateSelection,
  onClose,
  onClearAll,
}) => {
  useScrollLock(true);

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
  >(() => {
    const initial: Record<
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
    > = {};
    selectedRenders.forEach((item) => {
      initial[item.clip_id] = getDefaultMetadata(item);
    });
    return initial;
  });

  const [savingId, setSavingId] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // YouTube integration state
  const [ytAuth, setYtAuth] = useState<YouTubeAuthStatus | null>(null);
  const [isLoadingAuth, setIsLoadingAuth] = useState<boolean>(true);
  const [uploadingClipIds, setUploadingClipIds] = useState<Set<string>>(new Set());
  const [isUploadingBatch, setIsUploadingBatch] = useState<boolean>(false);
  const [uploadedClips, setUploadedClips] = useState<Record<string, YouTubeUploadResult>>({});
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Metadata regeneration: AI vs deterministic copy for the same clip.
  const [useAiCopy, setUseAiCopy] = useState<boolean>(true);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [previousCopies, setPreviousCopies] = useState<
    Record<
      string,
      { title?: string | null; description?: string | null; metadata_source?: string }
    >
  >({});

  const handleRegenerate = async (clipId: string) => {
    setRegeneratingId(clipId);
    setUploadError(null);
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
          ? `Gemini copy generated for ${clipId}.`
          : `${res.message} (${clipId})`
      );
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadError(`Failed to regenerate metadata for ${clipId}: ${msg}`);
    } finally {
      setRegeneratingId(null);
    }
  };

  useEffect(() => {
    let mounted = true;
    async function checkAuth() {
      setIsLoadingAuth(true);
      try {
        const status = await getYouTubeAuthStatus();
        if (mounted) setYtAuth(status);
      } catch (err) {
        console.warn("Could not check YouTube auth status:", err);
      } finally {
        if (mounted) setIsLoadingAuth(false);
      }
    }
    checkAuth();
    return () => {
      mounted = false;
    };
  }, []);

  const handleConnectYouTube = async () => {
    try {
      const data = await getYouTubeAuthUrl();
      if (data.auth_url) {
        window.open(data.auth_url, "_blank", "width=600,height=750");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadError(`Failed to initiate YouTube connection: ${msg}`);
    }
  };

  const handleUploadSingle = async (clipId: string) => {
    const meta = clipMetadata[clipId];
    if (!meta) return;
    setUploadingClipIds((prev) => new Set(prev).add(clipId));
    setUploadError(null);
    try {
      const tagsArray = meta.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const isShort = meta.format !== "landscape";

      // Synchronize modified staging metadata with backend DB before uploading
      await onUpdateSelection(clipId, {
        is_selected: true,
        preferred_format: meta.format,
        title: meta.title,
        description: meta.description,
        tags: tagsArray,
        privacy: meta.privacy,
      });

      const result = await uploadClipToYouTube(clipId, {
        title: meta.title,
        description: meta.description,
        tags: tagsArray,
        privacy: meta.privacy,
        format: meta.format,
        is_short: isShort,
        sync: true,
      });
      setUploadedClips((prev) => ({ ...prev, [clipId]: result }));
      setSuccessMessage(
        `Successfully uploaded ${clipId} to YouTube as ${isShort ? "Short" : "Video"}!`
      );
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadError(`Upload failed for ${clipId}: ${msg}`);
    } finally {
      setUploadingClipIds((prev) => {
        const next = new Set(prev);
        next.delete(clipId);
        return next;
      });
    }
  };

  const handleUploadAllToYouTube = async () => {
    if (selectedRenders.length === 0) return;
    setIsUploadingBatch(true);
    setUploadError(null);
    try {
      // Synchronize modified staging metadata for all selected clips before batch uploading
      await Promise.all(
        selectedRenders.map(async (r) => {
          const meta = clipMetadata[r.clip_id];
          if (meta) {
            const tagsArray = meta.tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean);
            await onUpdateSelection(r.clip_id, {
              is_selected: true,
              preferred_format: meta.format,
              title: meta.title,
              description: meta.description,
              tags: tagsArray,
              privacy: meta.privacy,
            });
          }
        })
      );

      const batchRes = await uploadSelectedClipsToYouTube(true);
      if (batchRes.results) {
        const resultMap: Record<string, YouTubeUploadResult> = {};
        batchRes.results.forEach((r) => {
          resultMap[r.clip_id] = r;
        });
        setUploadedClips((prev) => ({ ...prev, ...resultMap }));
      }
      setSuccessMessage(
        batchRes.message || `Uploaded ${batchRes.total_succeeded} clips to YouTube!`
      );
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadError(`Batch upload failed: ${msg}`);
    } finally {
      setIsUploadingBatch(false);
    }
  };

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleFieldChange = (
    clipId: string,
    field: "title" | "description" | "tags" | "privacy" | "format" | "hero_name" | "clip_context",
    value: string
  ) => {
    setClipMetadata((prev) => {
      const renderItem = selectedRenders.find((r) => r.clip_id === clipId);
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
      await onUpdateSelection(clipId, {
        is_selected: true,
        preferred_format: meta.format,
        title: meta.title,
        description: meta.description,
        tags: tagsArray,
        privacy: meta.privacy,
        hero_name: meta.hero_name,
        clip_context: meta.clip_context,
      });
      setSuccessMessage(`Updated staging for ${clipId}`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } finally {
      setSavingId(null);
    }
  };

  const handleRemoveFromQueue = async (clipId: string) => {
    await onUpdateSelection(clipId, {
      is_selected: false,
    });
  };

  const handleExportJSON = () => {
    const exportData = selectedRenders.map((r) => {
      const meta = clipMetadata[r.clip_id];
      const fmt: UploadFormat =
        meta?.format ||
        (r.upload_selection?.preferred_format as UploadFormat) ||
        "vertical_blur";
      const downloadUrl = getStreamUrl(r.clip_id, fmt);
      return {
        clip_id: r.clip_id,
        source_video: r.video_title,
        video_id: r.video_id,
        chosen_format: fmt,
        stream_url: downloadUrl,
        title: meta?.title || r.upload_selection?.title,
        description: meta?.description || r.upload_selection?.description,
        tags: meta?.tags.split(",").map((t) => t.trim()) || r.upload_selection?.tags,
        privacy: meta?.privacy || r.upload_selection?.privacy,
        duration_seconds: r.clip?.duration_seconds,
        created_at: r.created_at,
      };
    });

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `backseat_upload_queue_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadAll = () => {
    setSuccessMessage(
      "Starting downloads sequentially. If your browser asks for permission to download multiple files, please click 'Allow'."
    );
    selectedRenders.forEach((r, idx) => {
      const meta = clipMetadata[r.clip_id];
      const fmt: UploadFormat =
        meta?.format ||
        (r.upload_selection?.preferred_format as UploadFormat) ||
        "vertical_blur";
      const url = getStreamUrl(r.clip_id, fmt);
      setTimeout(() => {
        const a = document.createElement("a");
        a.href = url;
        a.download = `${r.clip_id}_${fmt}.mp4`;
        a.click();
      }, idx * 500);
    });
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/85 backdrop-blur-md animate-in fade-in duration-200 overflow-y-auto overscroll-contain"
    >
      <div
        className="relative w-full max-w-4xl max-h-[calc(100vh-2rem)] flex flex-col bg-slate-900 border border-white/10 rounded-2xl shadow-2xl overflow-hidden my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4 border-b border-white/10 bg-slate-950/70">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/40 text-white shrink-0">
              <YoutubeIcon className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-slate-100 text-base">
                  Upload & Publishing Staging Queue
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  {selectedRenders.length} Renders Chosen
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Review chosen highlight renders, customize upload titles/tags, and stage for YouTube publication.
              </p>
              <label className="mt-2 inline-flex items-center gap-2 text-[11px] text-slate-300 cursor-pointer select-none w-fit">
                <input
                  type="checkbox"
                  checked={useAiCopy}
                  onChange={(e) => setUseAiCopy(e.target.checked)}
                  className="h-3.5 w-3.5 rounded accent-violet-500"
                />
                <span>Use AI copy (Gemini) when regenerating</span>
              </label>
            </div>
          </div>

          <div className="flex items-center gap-2 justify-end">
            {/* YouTube Auth Badge / Connect Button */}
            {isLoadingAuth ? (
              <span className="text-xs text-slate-400 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 border border-white/10">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Checking YouTube...</span>
              </span>
            ) : ytAuth?.is_authenticated ? (
              <div
                className="flex items-center gap-2 px-3 py-1 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-medium"
                title={`Connected to channel: ${ytAuth.channel_title || "YouTube"}`}
              >
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="font-semibold">{ytAuth.channel_title || "Connected Channel"}</span>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleConnectYouTube}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-md shadow-rose-900/30 transition-colors"
                title="Connect YouTube account via OAuth"
              >
                <YoutubeIcon className="w-3.5 h-3.5" />
                <span>Connect YouTube</span>
              </button>
            )}

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors ml-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Upload error notice */}
        {uploadError && (
          <div className="px-6 py-2.5 bg-rose-500/15 border-b border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-2 animate-in fade-in">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{uploadError}</span>
            </div>
            <button
              type="button"
              onClick={() => setUploadError(null)}
              className="text-rose-400 hover:text-rose-200 text-xs underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Success toast notice */}
        {successMessage && (
          <div className="px-6 py-2 bg-emerald-500/15 border-b border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 p-6 overflow-y-auto space-y-6">
          {selectedRenders.length === 0 ? (
            <div className="py-16 text-center space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center mx-auto text-slate-500">
                <Radio className="w-6 h-6" />
              </div>
              <p className="text-sm font-semibold text-slate-300">No Renders Chosen for Upload Yet</p>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Go to the Renders Gallery and click &quot;Choose for Upload&quot; on any rendered clip to queue it here.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {selectedRenders.map((render) => {
                const meta = clipMetadata[render.clip_id] || getDefaultMetadata(render);
                const chosenFormat = meta.format;
                const streamUrl = getStreamUrl(render.clip_id, chosenFormat);
                const isShort = chosenFormat === "vertical_blur" || chosenFormat === "vertical_crop";

                return (
                  <div
                    key={render.clip_id}
                    className="p-4 sm:p-5 rounded-2xl bg-slate-950/60 border border-white/10 hover:border-white/20 transition-all space-y-4"
                  >
                    {/* Top Row: Info & Quick Format Switcher */}
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-white/5">
                      <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-slate-800 overflow-hidden shrink-0 border border-white/10 relative">
                          {render.video_thumbnail_url ? (
                            <img
                              src={render.video_thumbnail_url}
                              alt={render.video_title || render.clip_id}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-slate-500">
                              <Smartphone className="w-5 h-5" />
                            </div>
                          )}
                          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex items-end justify-center pb-0.5">
                            <span className="text-[9px] font-bold text-white uppercase">
                              {isShort ? "Short" : "16:9"}
                            </span>
                          </div>
                        </div>

                        <div>
                          <h4 className="font-semibold text-sm text-slate-100 line-clamp-1">
                            {render.video_title || render.clip_id}
                          </h4>
                          <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-400">
                            <span className="font-mono text-[11px] text-slate-300">{render.clip_id}</span>
                            <span>•</span>
                            <span>
                              {render.clip?.duration_seconds ?? render.request?.duration_seconds ?? 0}s duration
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Format selector for this clip */}
                      <div className="flex items-center gap-1.5 self-end sm:self-auto bg-slate-900 p-1 rounded-xl border border-white/10 flex-wrap">
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
                          const formats = filtered.length > 0 ? filtered : ["vertical_blur", "vertical_crop", "landscape"];

                          return formats.map((fmt) => (
                            <button
                              key={fmt}
                              type="button"
                              onClick={() => {
                                handleFieldChange(render.clip_id, "format", fmt);
                                onUpdateSelection(render.clip_id, {
                                  is_selected: true,
                                  preferred_format: fmt,
                                  title: meta.title,
                                  description: meta.description,
                                  tags: meta.tags.split(",").map((t) => t.trim()).filter(Boolean),
                                  privacy: meta.privacy,
                                });
                              }}
                              className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 ${
                                chosenFormat === fmt
                                  ? "bg-rose-600 text-white shadow-sm"
                                  : "text-slate-400 hover:text-white"
                              }`}
                            >
                              {fmt === "landscape" ? <Tv className="w-3 h-3" /> : <Smartphone className="w-3 h-3" />}
                              <span className="capitalize">{fmt.replace("_", " ")}</span>
                            </button>
                          ));
                        })()}
                      </div>
                    </div>

                    {/* Form Fields for Publishing */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                      {/* Hero & Context Hints for copy generation */}
                      <div className="sm:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-2.5 p-2 rounded-lg bg-slate-900/60 border border-violet-500/20">
                        <div className="space-y-1">
                          <label className="text-[11px] font-semibold text-violet-300 flex items-center justify-between">
                            <span>Hero Identity</span>
                            <span className="text-[10px] text-slate-500 font-normal">Used in AI & Deterministic Copy</span>
                          </label>
                          <input
                            type="text"
                            list="marvel-rivals-heroes-list"
                            value={meta.hero_name || ""}
                            onChange={(e) => handleFieldChange(render.clip_id, "hero_name", e.target.value)}
                            onBlur={() => handleSaveClipMetadata(render.clip_id)}
                            placeholder="e.g. Magneto, Luna Snow, Spider-Man..."
                            className="w-full px-2.5 py-1.5 bg-slate-950 border border-white/10 rounded text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500 text-xs"
                          />
                        </div>
                        <div className="space-y-1">
                          <label className="text-[11px] font-semibold text-violet-300 flex items-center justify-between">
                            <span>Clip Context / Notes</span>
                            <span className="text-[10px] text-slate-500 font-normal">Kills, point, choke</span>
                          </label>
                          <input
                            type="text"
                            value={meta.clip_context || ""}
                            onChange={(e) => handleFieldChange(render.clip_id, "clip_context", e.target.value)}
                            onBlur={() => handleSaveClipMetadata(render.clip_id)}
                            placeholder="e.g. 5K streak holding point B..."
                            className="w-full px-2.5 py-1.5 bg-slate-950 border border-white/10 rounded text-slate-100 placeholder-slate-500 focus:outline-none focus:border-violet-500 text-xs"
                          />
                        </div>
                      </div>

                      {/* Video Title */}
                      <div className="sm:col-span-2 space-y-1">
                        <label className="text-[11px] font-semibold text-slate-300">
                          Upload Title
                        </label>
                        <input
                          type="text"
                          value={meta.title}
                          onChange={(e) => handleFieldChange(render.clip_id, "title", e.target.value)}
                          onBlur={() => handleSaveClipMetadata(render.clip_id)}
                          placeholder="Video or Short Title..."
                          className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                        />
                        {previousCopies[render.clip_id] && (
                          <p className="text-[10px] text-slate-500">
                            Previous ({
                              previousCopies[render.clip_id].metadata_source === "llm"
                                ? "Gemini"
                                : "deterministic"
                            }):{" "}
                            <span className="line-through decoration-slate-600">
                              {previousCopies[render.clip_id].title || "(no title)"}
                            </span>
                          </p>
                        )}
                      </div>

                      {/* Description */}
                      <div className="space-y-1">
                        <label className="text-[11px] font-semibold text-slate-300">
                          Description
                        </label>
                        <textarea
                          rows={2}
                          value={meta.description}
                          onChange={(e) =>
                            handleFieldChange(render.clip_id, "description", e.target.value)
                          }
                          onBlur={() => handleSaveClipMetadata(render.clip_id)}
                          placeholder="Video description, timestamps, and hashtags..."
                          className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500 resize-none"
                        />
                      </div>

                      {/* Tags & Privacy */}
                      <div className="space-y-2">
                        <div className="space-y-1">
                          <label className="text-[11px] font-semibold text-slate-300">
                            Tags (comma separated)
                          </label>
                          <input
                            type="text"
                            value={meta.tags}
                            onChange={(e) =>
                              handleFieldChange(render.clip_id, "tags", e.target.value)
                            }
                            onBlur={() => handleSaveClipMetadata(render.clip_id)}
                            placeholder="Gaming, MarvelRivals, Shorts..."
                            className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                          />
                        </div>

                        <div className="flex items-center gap-3">
                          <label className="text-[11px] font-semibold text-slate-300">
                            Privacy:
                          </label>
                          <select
                            value={meta.privacy}
                            onChange={(e) => {
                              const val = e.target.value as UploadPrivacy;
                              handleFieldChange(render.clip_id, "privacy", val);
                              onUpdateSelection(render.clip_id, {
                                is_selected: true,
                                preferred_format: meta.format,
                                title: meta.title,
                                description: meta.description,
                                tags: meta.tags.split(",").map((t) => t.trim()).filter(Boolean),
                                privacy: val,
                              });
                            }}
                            className="px-2.5 py-1 bg-slate-900 border border-white/10 rounded-lg text-slate-200 focus:outline-none focus:border-rose-500 text-xs"
                          >
                            <option value="public">Public (Default)</option>
                            <option value="unlisted">Unlisted</option>
                            <option value="private">Private</option>
                          </select>
                        </div>
                      </div>
                    </div>

                    {/* Bottom Actions for Clip */}
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <a
                          href={streamUrl}
                          download={`${render.clip_id}_${chosenFormat}.mp4`}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-white/10 transition-colors"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>Download {chosenFormat} (.mp4)</span>
                        </a>
                        <button
                          type="button"
                          onClick={() => handleSaveClipMetadata(render.clip_id)}
                          disabled={savingId === render.clip_id}
                          className="px-3 py-1.5 rounded-lg bg-rose-600/20 text-rose-300 hover:bg-rose-600/30 border border-rose-500/30 font-medium transition-colors"
                        >
                          {savingId === render.clip_id ? "Saving..." : "Save Staging"}
                        </button>

                        {/* Regenerate title/description/tags without re-rendering */}
                        <button
                          type="button"
                          onClick={() => handleRegenerate(render.clip_id)}
                          disabled={regeneratingId === render.clip_id}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/20 text-violet-300 hover:bg-violet-600/30 border border-violet-500/30 font-medium transition-colors disabled:opacity-50"
                          title={
                            useAiCopy
                              ? "Regenerate copy with Gemini (falls back if no API key)"
                              : "Regenerate copy deterministically"
                          }
                        >
                          {regeneratingId === render.clip_id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Wand2 className="w-3.5 h-3.5" />
                          )}
                          <span>
                            {regeneratingId === render.clip_id
                              ? "Generating..."
                              : `Regenerate (${useAiCopy ? "AI" : "non-AI"})`}
                          </span>
                        </button>
                        {previousCopies[render.clip_id]?.description && (
                          <span className="text-[10px] text-slate-500 max-w-[26ch] truncate" title={previousCopies[render.clip_id].description || ""}>
                            <History className="w-3 h-3 inline -mt-0.5 mr-1" />
                            Previous description kept for comparison
                          </span>
                        )}

                        {/* YouTube Upload Button or View Link */}
                        {(() => {
                          const uploadRes =
                            uploadedClips[render.clip_id] ||
                            (render.youtube_upload
                              ? {
                                  clip_id: render.clip_id,
                                  youtube_video_id: render.youtube_upload.video_id,
                                  youtube_url: render.youtube_upload.url,
                                  is_short: render.youtube_upload.is_short,
                                  status: "completed",
                                }
                              : null);

                          const isUploading = uploadingClipIds.has(render.clip_id);
                          const isShort = chosenFormat !== "landscape";

                          if (uploadRes && uploadRes.status === "completed" && uploadRes.youtube_url) {
                            return (
                              <a
                                href={uploadRes.youtube_url}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/40 font-medium transition-colors"
                              >
                                <YoutubeIcon className="w-3.5 h-3.5 text-emerald-400" />
                                <span>View on YouTube {uploadRes.is_short ? "(Short)" : ""}</span>
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            );
                          }

                          return (
                            <button
                              type="button"
                              onClick={() => handleUploadSingle(render.clip_id)}
                              disabled={!ytAuth?.is_authenticated || isUploading}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600/20 text-red-300 hover:bg-red-600/30 border border-red-500/40 font-medium transition-colors disabled:opacity-40"
                              title={
                                !ytAuth?.is_authenticated
                                  ? "Connect YouTube account first using the button at top"
                                  : `Upload to YouTube as ${isShort ? "Short" : "Video"}`
                              }
                            >
                              {isUploading ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  <span>Uploading...</span>
                                </>
                              ) : (
                                <>
                                  <UploadCloud className="w-3.5 h-3.5 text-red-400" />
                                  <span>
                                    Upload to YouTube ({isShort ? "Short" : "Video"})
                                  </span>
                                </>
                              )}
                            </button>
                          );
                        })()}
                      </div>

                      <button
                        type="button"
                        onClick={() => handleRemoveFromQueue(render.clip_id)}
                        className="flex items-center gap-1 px-2.5 py-1 text-slate-400 hover:text-rose-400 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Remove</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-6 py-4 border-t border-white/10 bg-slate-950/70">
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <button
              onClick={handleExportJSON}
              disabled={selectedRenders.length === 0}
              className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 disabled:opacity-50 text-slate-200 border border-white/10 text-xs font-semibold transition-colors"
            >
              <FileJson className="w-3.5 h-3.5" />
              <span>Export Staging JSON</span>
            </button>
            <button
              onClick={handleDownloadAll}
              disabled={selectedRenders.length === 0}
              className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 disabled:opacity-50 text-slate-200 border border-white/10 text-xs font-semibold transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download All (.mp4)</span>
            </button>
            <button
              onClick={handleUploadAllToYouTube}
              disabled={!ytAuth?.is_authenticated || selectedRenders.length === 0 || isUploadingBatch}
              className="flex items-center justify-center gap-1.5 px-4 py-1.5 rounded-xl bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 disabled:opacity-40 text-white text-xs font-bold shadow-md shadow-red-900/30 transition-all cursor-pointer whitespace-nowrap active:scale-95"
              title={!ytAuth?.is_authenticated ? "Connect YouTube account first" : "Upload all selected renders"}
            >
              {isUploadingBatch ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Uploading Selected...</span>
                </>
              ) : (
                <>
                  <YoutubeIcon className="w-3.5 h-3.5" />
                  <span>Upload All to YouTube</span>
                </>
              )}
            </button>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            {selectedRenders.length > 0 && (
              <button
                onClick={onClearAll}
                className="px-3 py-1.5 rounded-xl text-slate-400 hover:text-rose-400 text-xs font-medium transition-colors"
              >
                Clear Queue
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-lg shadow-rose-900/40 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
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
};
