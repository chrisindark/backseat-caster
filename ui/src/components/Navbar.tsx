"use client";

import { Badge } from "@radix-ui/themes";
import { Compass, Film, Layers, Radio, RefreshCw, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import React from "react";
import { YoutubeIcon } from "./icons";

interface NavbarProps {
  channelInput?: string;
  onChannelInputChange?: (val: string) => void;
  onSync?: () => void;
  isSyncing?: boolean;
  searchQuery?: string;
  onSearchChange?: (val: string) => void;
  backendHealthy?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  channelInput = "",
  onChannelInputChange,
  onSync,
  isSyncing = false,
  searchQuery,
  onSearchChange,
  backendHealthy = true,
}) => {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 glass-nav border-b border-white/10 px-4 lg:px-8 py-3 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand & Nav Links */}
        <div className="flex items-center gap-6 w-full md:w-auto justify-between md:justify-start">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/30 group-hover:scale-105 transition-transform">
              <Radio className="w-4 h-4 text-white animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400">
                  BackseatCaster
                </span>
                <Badge color="crimson" variant="surface" size="1">
                  AI Clip Engine
                </Badge>
              </div>
              <p className="text-[11px] text-slate-400">Gameplay Highlight Pipeline</p>
            </div>
          </Link>

          {/* Navigation Tabs */}
          <nav className="flex items-center p-1 bg-slate-900/90 border border-white/10 rounded-xl" aria-label="Main Navigation">
            <Link
              href="/"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname === "/"
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Film className="w-3.5 h-3.5" />
              <span>Library</span>
            </Link>
            <Link
              href="/youtube"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname?.startsWith("/youtube")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>YouTube Explorer</span>
            </Link>
            <Link
              href="/renders"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                pathname?.startsWith("/renders")
                  ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Renders & Jobs</span>
            </Link>
          </nav>

          {/* Backend Status indicator */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/80 border border-white/5 text-xs text-slate-400">
            <span
              className={`w-2 h-2 rounded-full ${
                backendHealthy ? "bg-emerald-400 shadow-sm shadow-emerald-400" : "bg-rose-500"
              }`}
            />
            <span>{backendHealthy ? "API Ready" : "API Offline"}</span>
          </div>
        </div>

        {/* Search Input (if callback provided) */}
        {onSearchChange && (
          <div className="flex-1 max-w-sm w-full">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery ?? ""}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Search video titles or keywords..."
                className="w-full pl-9 pr-4 py-1.5 bg-slate-900/90 border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
              />
            </div>
          </div>
        )}

        {/* Channel Selector & Sync Button (if provided) */}
        {onChannelInputChange && (
          <div className="flex items-center gap-2 w-full md:w-auto">
            <div className="relative flex-1 md:w-48">
              <YoutubeIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-rose-500" />
              <input
                type="text"
                value={channelInput}
                onChange={(e) => onChannelInputChange(e.target.value)}
                placeholder="@Channel or URL"
                className="w-full pl-8 pr-2.5 py-1.5 bg-slate-900/90 border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
              />
            </div>
            {onSync && (
              <button
                onClick={onSync}
                disabled={isSyncing}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 disabled:bg-rose-800 disabled:opacity-70 text-white text-xs font-semibold rounded-lg shadow-md shadow-rose-900/40 transition-all cursor-pointer whitespace-nowrap active:scale-95"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                <span>{isSyncing ? "Syncing..." : "Sync Channel"}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </header>
  );
};
