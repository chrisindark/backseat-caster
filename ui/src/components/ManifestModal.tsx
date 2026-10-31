"use client";

import { RenderManifest } from "@/types/video";
import { useScrollLock } from "@/lib/useScrollLock";
import { Check, Copy, FileCode, X } from "lucide-react";
import React, { useEffect, useState } from "react";

interface ManifestModalProps {
  manifest: RenderManifest | null;
  onClose: () => void;
}

export const ManifestModal: React.FC<ManifestModalProps> = ({ manifest, onClose }) => {
  useScrollLock(Boolean(manifest));

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!manifest) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(manifest, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200 overflow-y-auto overscroll-contain"
    >
      <div
        className="relative w-full max-w-2xl max-h-[calc(100vh-2rem)] flex flex-col bg-slate-900/95 border border-white/10 rounded-2xl shadow-2xl overflow-hidden my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-slate-950/50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20">
              <FileCode className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-100 text-sm md:text-base">
                Render Manifest Audit
              </h3>
              <p className="text-xs text-slate-400 font-mono">{manifest.clip_id}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-white/5 hover:bg-white/10 text-slate-200 border border-white/10 transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? "Copied" : "Copy JSON"}</span>
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 p-6 overflow-y-auto space-y-4">
          {/* Quick Stats Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
              <span className="text-[10px] uppercase font-bold text-slate-400">Duration</span>
              <p className="text-sm font-semibold text-slate-100 mt-0.5">
                {manifest.clip?.duration_seconds ?? manifest.request?.duration_seconds ?? 0}s
              </p>
            </div>
            <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
              <span className="text-[10px] uppercase font-bold text-slate-400">Encoder</span>
              <p className="text-sm font-semibold text-rose-400 mt-0.5">
                {manifest.outputs?.landscape?.encoder ?? "h264"}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
              <span className="text-[10px] uppercase font-bold text-slate-400">Render Time</span>
              <p className="text-sm font-semibold text-emerald-400 mt-0.5">
                {manifest.render_stats?.total_render_seconds ?? manifest.render_duration_seconds ?? "N/A"}s
              </p>
            </div>
            <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
              <span className="text-[10px] uppercase font-bold text-slate-400">Audio Mode</span>
              <p className="text-sm font-semibold text-amber-400 mt-0.5">
                {manifest.cta?.voiceover ?? manifest.request?.has_narration
                  ? "Voiceover"
                  : "Original"}
              </p>
            </div>
          </div>

          {/* Branding & CTA */}
          {manifest.branding?.enabled || manifest.cta?.enabled ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
                <span className="text-[10px] uppercase font-bold text-slate-400">
                  Branded Cards
                </span>
                <p className="text-sm font-semibold text-slate-100 mt-0.5">
                  {manifest.branding?.enabled
                    ? `${((manifest.branding.padding_seconds ?? 0)).toFixed(1)}s`
                    : "Off"}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
                <span className="text-[10px] uppercase font-bold text-slate-400">CTA Style</span>
                <p className="text-sm font-semibold text-slate-100 mt-0.5">
                  {manifest.cta?.enabled
                    ? manifest.cta.style === "overlay"
                      ? "Lower-third"
                      : "Outro card"
                    : "Off"}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
                <span className="text-[10px] uppercase font-bold text-slate-400">CTA Voiceover</span>
                <p className="text-sm font-semibold text-amber-400 mt-0.5">
                  {manifest.cta?.voiceover
                    ? `@${manifest.cta.voiceover_start_seconds ?? 0}s`
                    : manifest.cta?.enabled
                      ? "Silent"
                      : "Off"}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-slate-800/60 border border-white/5">
                <span className="text-[10px] uppercase font-bold text-slate-400">CTA Voice</span>
                <p className="text-sm font-semibold text-slate-100 mt-0.5 truncate">
                  {manifest.cta?.enabled ? manifest.cta.voice ?? "default" : "—"}
                </p>
              </div>
            </div>
          ) : null}

          {/* Formatted Code Block */}
          <div className="rounded-xl border border-white/10 bg-slate-950 p-4 overflow-x-auto text-xs font-mono text-slate-300">
            <pre>{JSON.stringify(manifest, null, 2)}</pre>
          </div>
        </div>
      </div>
    </div>
  );
};
