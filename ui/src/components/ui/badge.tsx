import React from "react";

type Tone =
  | "default"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "accent"
  | "violet";

const tones: Record<Tone, string> = {
  default: "bg-slate-800 text-slate-200 border-white/10",
  success: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  warning: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  danger: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  info: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  accent: "bg-rose-600/20 text-rose-200 border-rose-500/40",
  violet: "bg-violet-500/15 text-violet-300 border-violet-500/30",
};

export const Badge: React.FC<{
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}> = ({ children, tone = "default", className = "" }) => (
  <span
    className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] sm:text-xs font-semibold whitespace-nowrap ${tones[tone]} ${className}`}
  >
    {children}
  </span>
);