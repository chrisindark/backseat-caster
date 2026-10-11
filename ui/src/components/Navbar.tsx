"use client";

import { Badge } from "@radix-ui/themes";
import { Radio, RefreshCw, Search } from "lucide-react";
import React from "react";
import { YoutubeIcon } from "./icons";

interface NavbarProps {
  channelInput: string;
  onChannelInputChange: (val: string) => void;
  onSync: () => void;
  isSyncing: boolean;
  searchQuery: string;
  onSearchChange: (val: string) => void;
  backendHealthy: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  channelInput,
  onChannelInputChange,
  onSync,
  isSyncing,
  searchQuery,
  onSearchChange,
  backendHealthy,
}) => {
  return (
    <header className="sticky top-0 z-50 glass-nav border-b border-white/10 px-4 lg:px-8 py-3.5 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-start">
          <div className="flex items-center gap-2.5">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/30">
              <Radio className="w-5 h-5 text-white animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-lg tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400">
                  BackseatCaster
                </span>
                <Badge color="crimson" variant="surface" size="1">
                  AI Clip Engine
                </Badge>
              </div>
              <p className="text-xs text-slate-400">Gameplay Highlight Pipeline</p>
            </div>
          </div>

          {/* Backend Status indicator */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/80 border border-white/5 text-xs text-slate-400">
            <span
              className={`w-2 h-2 rounded-full ${backendHealthy ? "bg-emerald-400 shadow-sm shadow-emerald-400" : "bg-rose-500"
                }`}
            />
            <span>{backendHealthy ? "API Ready" : "API Offline"}</span>
          </div>
        </div>

        {/* Search Input */}
        <div className="flex-1 max-w-md w-full">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search video titles or keywords..."
              className="w-full pl-9 pr-4 py-2 bg-slate-900/90 border border-white/10 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
            />
          </div>
        </div>

        {/* Channel Selector & Sync Button */}
        <div className="flex items-center gap-2 w-full md:w-auto">
          <div className="relative flex-1 md:w-56">
            <YoutubeIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-rose-500" />
            <input
              type="text"
              value={channelInput}
              onChange={(e) => onChannelInputChange(e.target.value)}
              placeholder="@ChannelHandle or URL"
              className="w-full pl-9 pr-3 py-2 bg-slate-900/90 border border-white/10 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
            />
          </div>
          <button
            onClick={onSync}
            disabled={isSyncing}
            className="flex items-center gap-2 px-4 py-2 bg-rose-600 hover:bg-rose-500 disabled:bg-rose-800 disabled:opacity-70 text-white text-sm font-semibold rounded-lg shadow-md shadow-rose-900/40 transition-all cursor-pointer whitespace-nowrap active:scale-95"
          >
            <RefreshCw className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`} />
            <span>{isSyncing ? "Syncing..." : "Sync Channel"}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
