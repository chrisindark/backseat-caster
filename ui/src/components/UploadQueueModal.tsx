"use client";

import { getStreamUrl } from "@/lib/api";
import { RenderManifest, UploadSelectionPayload } from "@/types/video";
import {
  CheckCircle2,
  Download,
  FileJson,
  Radio,
  Smartphone,
  Trash2,
  Tv,
  X,
} from "lucide-react";
import React, { useState } from "react";
import { YoutubeIcon } from "./icons";

export type UploadFormat = "vertical_blur" | "vertical_crop" | "landscape";
export type UploadPrivacy = "private" | "unlisted" | "public";

interface UploadQueueModalProps {
  selectedRenders: RenderManifest[];
  onUpdateSelection: (clipId: string, payload: UploadSelectionPayload) => Promise<void>;
  onClose: () => void;
  onClearAll: () => Promise<void>;
}

export const UploadQueueModal: React.FC<UploadQueueModalProps> = ({
  selectedRenders,
  onUpdateSelection,
  onClose,
  onClearAll,
}) => {
  const [clipMetadata, setClipMetadata] = useState<
    Record<
      string,
      {
        title: string;
        description: string;
        tags: string;
        privacy: UploadPrivacy;
        format: UploadFormat;
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
      }
    > = {};
    selectedRenders.forEach((item) => {
      const preferred: UploadFormat =
        item.upload_selection?.preferred_format === "vertical_crop" ||
        item.upload_selection?.preferred_format === "landscape"
          ? item.upload_selection.preferred_format
          : "vertical_blur";
      const start = item.clip?.start_seconds ?? item.request?.start_seconds ?? 0;
      const dur = item.clip?.duration_seconds ?? item.request?.duration_seconds ?? 15;
      const defaultTitle =
        item.upload_selection?.title ||
        `${item.video_title ? `${item.video_title.slice(0, 50)} - ` : ""}Highlight (${Math.round(start)}s-${Math.round(start + dur)}s)`;
      const defaultDesc =
        item.upload_selection?.description ||
        `Gameplay highlight rendered with BackseatCaster AI Clip Engine.\n#MarvelRivals #Gaming #Shorts #Highlight`;
      const defaultTags =
        (item.upload_selection?.tags || ["Gaming", "MarvelRivals", "Highlights"]).join(", ");
      const privacyVal: UploadPrivacy =
        item.upload_selection?.privacy === "private" ||
        item.upload_selection?.privacy === "public"
          ? item.upload_selection.privacy
          : "unlisted";

      initial[item.clip_id] = {
        title: defaultTitle,
        description: defaultDesc,
        tags: defaultTags,
        privacy: privacyVal,
        format: preferred,
      };
    });
    return initial;
  });

  const [savingId, setSavingId] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleFieldChange = (
    clipId: string,
    field: "title" | "description" | "tags" | "privacy" | "format",
    value: string
  ) => {
    setClipMetadata((prev) => ({
      ...prev,
      [clipId]: {
        ...prev[clipId],
        [field]: value,
      },
    }));
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/85 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-slate-900 border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-slate-950/70">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/40 text-white">
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
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

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
                const meta = clipMetadata[render.clip_id] || {
                  title: render.upload_selection?.title || render.clip_id,
                  description: render.upload_selection?.description || "",
                  tags: (render.upload_selection?.tags || []).join(", "),
                  privacy:
                    (render.upload_selection?.privacy as UploadPrivacy) || "unlisted",
                  format:
                    (render.upload_selection?.preferred_format as UploadFormat) ||
                    "vertical_blur",
                };
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
                      <div className="flex items-center gap-1.5 self-end sm:self-auto bg-slate-900 p-1 rounded-xl border border-white/10">
                        <button
                          type="button"
                          onClick={() => handleFieldChange(render.clip_id, "format", "vertical_blur")}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 ${
                            chosenFormat === "vertical_blur"
                              ? "bg-rose-600 text-white shadow-sm"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          <Smartphone className="w-3 h-3" />
                          <span>Vertical Blur (Short)</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleFieldChange(render.clip_id, "format", "vertical_crop")}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 ${
                            chosenFormat === "vertical_crop"
                              ? "bg-rose-600 text-white shadow-sm"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          <Smartphone className="w-3 h-3" />
                          <span>Vertical Crop</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleFieldChange(render.clip_id, "format", "landscape")}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 ${
                            chosenFormat === "landscape"
                              ? "bg-rose-600 text-white shadow-sm"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          <Tv className="w-3 h-3" />
                          <span>16:9 Landscape</span>
                        </button>
                      </div>
                    </div>

                    {/* Form Fields for Publishing */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                      {/* Video Title */}
                      <div className="sm:col-span-2 space-y-1">
                        <label className="text-[11px] font-semibold text-slate-300">
                          Upload Title
                        </label>
                        <input
                          type="text"
                          value={meta.title}
                          onChange={(e) => handleFieldChange(render.clip_id, "title", e.target.value)}
                          placeholder="Video or Short Title..."
                          className="w-full px-3 py-1.5 bg-slate-900 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500"
                        />
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
                            onChange={(e) =>
                              handleFieldChange(render.clip_id, "privacy", e.target.value)
                            }
                            className="px-2.5 py-1 bg-slate-900 border border-white/10 rounded-lg text-slate-200 focus:outline-none focus:border-rose-500 text-xs"
                          >
                            <option value="unlisted">Unlisted (Recommended)</option>
                            <option value="private">Private</option>
                            <option value="public">Public</option>
                          </select>
                        </div>
                      </div>
                    </div>

                    {/* Bottom Actions for Clip */}
                    <div className="flex items-center justify-between pt-2 text-xs">
                      <div className="flex items-center gap-2">
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
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={handleExportJSON}
              disabled={selectedRenders.length === 0}
              className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 disabled:opacity-50 text-slate-200 border border-white/10 text-xs font-semibold transition-colors"
            >
              <FileJson className="w-3.5 h-3.5" />
              <span>Export Staging JSON</span>
            </button>
            <button
              onClick={handleDownloadAll}
              disabled={selectedRenders.length === 0}
              className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 disabled:opacity-50 text-slate-200 border border-white/10 text-xs font-semibold transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download All Selected (.mp4)</span>
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
    </div>
  );
};
