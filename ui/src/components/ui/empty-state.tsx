import React from "react";

export const EmptyState: React.FC<{
  icon?: React.ReactNode;
  title: string;
  description: string;
  actions?: React.ReactNode;
}> = ({ icon, title, description, actions }) => (
  <div className="flex flex-col items-center justify-center py-16 sm:py-20 px-4 text-center bg-slate-900/50 border border-white/5 rounded-2xl">
    {icon && (
      <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-rose-950/40 border border-rose-500/20 flex items-center justify-center mb-4 text-rose-400">
        {icon}
      </div>
    )}
    <h2 className="text-base sm:text-lg font-bold text-white mb-1">{title}</h2>
    <p className="text-sm text-slate-400 max-w-md mb-6 leading-relaxed">{description}</p>
    {actions && <div className="flex flex-wrap items-center justify-center gap-3">{actions}</div>}
  </div>
);

export const SkeletonGrid: React.FC<{ count?: number }> = ({ count = 8 }) => (
  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-5 py-8">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="bg-slate-900 border border-white/5 rounded-2xl overflow-hidden animate-pulse">
        <div className="aspect-video bg-slate-800/60 w-full" />
        <div className="p-4 flex flex-col gap-3">
          <div className="h-4 bg-slate-800/80 rounded w-5/6" />
          <div className="h-3 bg-slate-800/40 rounded w-1/2" />
          <div className="h-9 bg-slate-800/30 rounded-lg mt-2" />
        </div>
      </div>
    ))}
  </div>
);