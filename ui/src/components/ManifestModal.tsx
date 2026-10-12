"use client";

import { RenderManifest } from "@/types/video";
import { Check, Copy, FileCode, X } from "lucide-react";
import React, { useState } from "react";

interface ManifestModalProps {
  manifest: RenderManifest | null;
  onClose: () => void;
}

export const ManifestModal: React.FC<ManifestModalProps> = ({ manifest, onClose }) => {
  const [copied, setCopied] = useState(false);

  if (!manifest) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(manifest, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-2xl max-h-[85vh] flex flex-col bg-slate-900/95 border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-slate-950/50">
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
                {manifest.audio_config?.has_narration ? "Voiceover" : "Original"}
              </p>
            </div>
          </div>

          {/* Formatted Code Block */}
          <div className="rounded-xl border border-white/10 bg-slate-950 p-4 overflow-x-auto text-xs font-mono text-slate-300">
            <pre>{JSON.stringify(manifest, null, 2)}</pre>
          </div>
        </div>
      </div>
    </div>
  );
};
