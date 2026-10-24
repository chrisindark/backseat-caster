"use client";

import {
  fetchStagedClips,
  publishStagedClipNow,
  scheduleStagedClip,
} from "@/lib/api";
import { useScrollLock } from "@/lib/useScrollLock";
import { RenderJobResponse, StagedClipsResponse, YouTubeQuota } from "@/types/video";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Flame,
  Gauge,
  Loader2,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";

interface AutoStagePanelProps {
  /** Called after a staged clip is published or rescheduled so the host page can refresh. */
  onStagedChange?: () => void;
}

function parseMetadata(job: RenderJobResponse): Record<string, unknown> {
  if (!job.upload_metadata) return {};
  try {
    const parsed = JSON.parse(job.upload_metadata);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

/** Convert an ISO timestamp into a value the datetime-local input accepts. */
function toLocalInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => `${n}`.padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

function formatSchedule(iso: string | null | undefined): string {
  if (!iso) return "Unscheduled";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unscheduled";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export const QuotaBar: React.FC<{ quota: YouTubeQuota; showDetails?: boolean }> = ({
  quota,
  showDetails = true,
}) => {
  const total = Math.max(1, quota.daily_limit_units);
  const usedPercent = Math.min(100, Math.round((quota.units_used / total) * 100));
  const barColor = !quota.can_upload
    ? "bg-rose-500"
    : usedPercent >= 80
      ? "bg-amber-400"
      : "bg-emerald-500";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <Gauge className="w-3.5 h-3.5 text-emerald-400" />
          YouTube API Quota
        </span>
        <span className="text-[11px] font-mono text-slate-400">
          {quota.units_used.toLocaleString()} / {quota.daily_limit_units.toLocaleString()} units
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.max(2, usedPercent)}%` }}
        />
      </div>
      {showDetails && (
        <div className="flex items-center justify-between text-[10px] text-slate-500">
          <span>
            {quota.uploads_remaining} of {quota.max_uploads_per_day} uploads left today
            {!quota.can_upload ? " — quota exhausted" : ""}
          </span>
          <span>Resets {formatSchedule(quota.resets_at)}</span>
        </div>
      )}
    </div>
  );
};

export const AutoStagePanel: React.FC<AutoStagePanelProps> = ({ onStagedChange }) => {
  const [staged, setStaged] = useState<StagedClipsResponse | null>(null);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [busyClipId, setBusyClipId] = useState<string | null>(null);
  const [draftSchedules, setDraftSchedules] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useScrollLock(isOpen);

  const applyStaged = useCallback((res: StagedClipsResponse) => {
    setStaged(res);
    setDraftSchedules((prev) => {
      const next: Record<string, string> = {};
      for (const item of res.items || []) {
        next[item.clip_id] =
          prev[item.clip_id] ?? toLocalInputValue(item.scheduled_publish_at);
      }
      return next;
    });
  }, []);

  const loadStaged = useCallback(async () => {
    const res = await fetchStagedClips();
    applyStaged(res);
  }, [applyStaged]);

  useEffect(() => {
    let cancelled = false;
    fetchStagedClips()
      .then((res) => {
        if (!cancelled) applyStaged(res);
      })
      .catch((err) => console.error("Failed to load auto-staged clips:", err));
    return () => {
      cancelled = true;
    };
  }, [applyStaged]);

  const items = useMemo(() => staged?.items || [], [staged]);
  const quota = staged?.quota || null;
  const pendingCount = useMemo(
    () => items.filter((item) => item.status === "completed").length,
    [items]
  );

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), 6000);
    return () => clearTimeout(timer);
  }, [error]);

  const handleSaveSchedule = async (clipId: string) => {
    const draft = draftSchedules[clipId] || "";
    setBusyClipId(clipId);
    setError(null);
    try {
      const publishAt = draft ? new Date(draft).toISOString() : null;
      await scheduleStagedClip(clipId, publishAt);
      await loadStaged();
      setNotice(publishAt ? "Schedule updated." : "Schedule cleared.");
      onStagedChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update schedule");
    } finally {
      setBusyClipId(null);
    }
  };

  const handlePublishNow = async (clipId: string) => {
    setBusyClipId(clipId);
    setError(null);
    try {
      await publishStagedClipNow(clipId);
      await loadStaged();
      setNotice("Upload started — track progress in the upload queue.");
      onStagedChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to publish clip");
    } finally {
      setBusyClipId(null);
    }
  };

  if (!quota && items.length === 0) {
    return null;
  }

  return (
    <>
      {/* Auto-staged notification banner + quota bar */}
      <section className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <div
          className={`relative overflow-hidden rounded-2xl border p-4 shadow-xl backdrop-blur-xl transition-colors ${
            items.length > 0
              ? "bg-gradient-to-r from-amber-950/40 via-slate-900/90 to-slate-900/90 border-amber-500/30"
              : "bg-slate-900/80 border-white/10"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <div
                className={`p-2 rounded-xl shrink-0 ${
                  items.length > 0
                    ? "bg-amber-500/15 text-amber-400"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                <Flame className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-bold text-white">
                  {items.length > 0
                    ? `🔥 ${items.length} highlight${items.length === 1 ? "" : "s"} auto-staged`
                    : "Auto-stage standing by"}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {items.length > 0
                    ? `${pendingCount} rendered and ready — review copy, adjust the schedule, or publish now.`
                    : "Enable AUTO_STAGE_ENABLED to render and schedule top highlights automatically."}
                </p>
              </div>
            </div>

            {items.length > 0 && (
              <button
                type="button"
                onClick={() => setIsOpen(true)}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-amber-500 text-slate-950 text-xs font-bold hover:bg-amber-400 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Review Staged
              </button>
            )}
          </div>
        </div>

        {quota && (
          <div className="rounded-2xl border border-white/10 bg-slate-900/80 p-4 shadow-xl backdrop-blur-xl">
            <QuotaBar quota={quota} />
          </div>
        )}
      </section>

      {/* Review drawer */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setIsOpen(false)}
          />
          <aside className="relative z-10 h-full w-full max-w-2xl bg-[#0b0d14] border-l border-white/10 shadow-2xl flex flex-col animate-in slide-in-from-right">
            <header className="flex items-start justify-between gap-4 p-5 border-b border-white/10">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <Flame className="w-4 h-4 text-amber-400" />
                  Auto-Staged Highlights
                </h2>
                <p className="text-[11px] text-slate-400 mt-1">
                  Rendered vertical clips with LLM metadata and native YouTube{" "}
                  <code className="text-slate-300">publishAt</code> slots.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5"
                aria-label="Close auto-stage drawer"
              >
                <X className="w-4 h-4" />
              </button>
            </header>

            {quota && (
              <div className="px-5 py-3 border-b border-white/5 bg-slate-900/60">
                <QuotaBar quota={quota} />
              </div>
            )}

            {(notice || error) && (
              <div
                className={`mx-5 mt-4 flex items-center gap-2 rounded-xl border px-3 py-2 text-[11px] ${
                  error
                    ? "border-rose-500/30 bg-rose-950/30 text-rose-300"
                    : "border-emerald-500/30 bg-emerald-950/30 text-emerald-300"
                }`}
              >
                {error ? (
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                )}
                <span>{error || notice}</span>
              </div>
            )}

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {items.length === 0 && (
                <p className="text-xs text-slate-400">
                  No clips are waiting for review. Run highlight detection with auto-stage
                  enabled to populate this queue.
                </p>
              )}

              {items.map((job) => {
                const meta = parseMetadata(job);
                const source = String(meta.metadata_source || "fallback");
                const busy = busyClipId === job.clip_id;
                return (
                  <article
                    key={job.clip_id}
                    className="rounded-2xl border border-white/10 bg-slate-900/70 p-4 space-y-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-white leading-snug break-words">
                          {String(meta.title || job.video_title || job.clip_id)}
                        </p>
                        <p className="text-[10px] text-slate-500 mt-1 font-mono truncate">
                          {job.clip_id} · {Math.round(Number(job.start_seconds) || 0)}s ·{" "}
                          {Math.round(Number(job.duration_seconds) || 0)}s
                        </p>
                      </div>
                      <span
                        className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                          source === "llm"
                            ? "bg-violet-500/15 text-violet-300 border-violet-500/30"
                            : "bg-slate-800 text-slate-300 border-white/10"
                        }`}
                      >
                        {source === "llm" ? "Gemini copy" : "Fallback copy"}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                      <span className="inline-flex items-center gap-1">
                        <CalendarClock className="w-3.5 h-3.5 text-sky-400" />
                        {formatSchedule(job.scheduled_publish_at)}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                        {job.status}
                      </span>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center gap-2">
                      <input
                        type="datetime-local"
                        value={draftSchedules[job.clip_id] || ""}
                        onChange={(event) =>
                          setDraftSchedules((prev) => ({
                            ...prev,
                            [job.clip_id]: event.target.value,
                          }))
                        }
                        className="flex-1 min-w-0 rounded-lg bg-slate-950 border border-white/10 px-2.5 py-1.5 text-[11px] text-slate-200 focus:outline-none focus:border-rose-500/60"
                        aria-label={`Schedule for ${job.clip_id}`}
                      />
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => handleSaveSchedule(job.clip_id)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-200 text-[11px] font-semibold hover:bg-slate-700 disabled:opacity-50"
                        >
                          {busy ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <CalendarClock className="w-3.5 h-3.5" />
                          )}
                          Save schedule
                        </button>
                        <button
                          type="button"
                          disabled={busy || job.status !== "completed" || quota?.can_upload === false}
                          onClick={() => handlePublishNow(job.clip_id)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-[11px] font-bold hover:bg-rose-500 disabled:opacity-40"
                        >
                          <Send className="w-3.5 h-3.5" />
                          Publish now
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </aside>
        </div>
      )}
    </>
  );
};
