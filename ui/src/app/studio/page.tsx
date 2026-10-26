"use client";

import { Navbar } from "@/components/Navbar";
import { OBSUploadDropzone } from "@/components/OBSUploadDropzone";
import { checkBackendHealth, fetchVideos } from "@/lib/api";
import { VideoItem } from "@/types/video";
import {
  Clock,
  Compass,
  HardDrive,
  Loader2,
  Play,
  Scissors,
  Sparkles,
  Video,
} from "lucide-react";
import Link from "next/link";
import React, { useCallback, useEffect, useState } from "react";

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${mb.toFixed(1)} MB`;
}

export default function StudioHubPage() {
  const [downloadedVideos, setDownloadedVideos] = useState<VideoItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);

  const loadDownloadedVideos = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await fetchVideos({ status: "downloaded", limit: 50 });
      setDownloadedVideos(data.items || []);
    } catch (err) {
      console.error("Failed to fetch downloaded videos for studio hub:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    async function init() {
      const healthy = await checkBackendHealth();
      if (!mounted) return;
      setBackendHealthy(healthy);
      if (healthy) {
        await loadDownloadedVideos();
      } else {
        setIsLoading(false);
      }
    }
    init();
    return () => {
      mounted = false;
    };
  }, [loadDownloadedVideos]);

  return (
    <div className="min-h-screen bg-[#090a0f] text-slate-100 flex flex-col selection:bg-rose-500 selection:text-white">
      <Navbar backendHealthy={backendHealthy} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-8 space-y-8">
        {/* Header Hero */}
        <section className="relative rounded-3xl p-6 sm:p-8 bg-gradient-to-br from-slate-900/90 via-slate-900/60 to-rose-950/20 border border-white/10 shadow-2xl backdrop-blur-xl overflow-hidden">
          <div className="absolute top-0 right-0 -mt-12 -mr-12 w-96 h-96 bg-rose-600/10 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs font-semibold">
                <Scissors className="w-3.5 h-3.5" />
                <span>Clip Studio Creator Hub</span>
              </div>
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-white">
                Create High-Impact Clips & Shorts
              </h1>
              <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
                Select a local VOD or drop an OBS recording to begin precision timeline scrubbing, framing adjustments (9:16 Shorts & 16:9 Landscape), audio ducking, and candidate highlight extraction.
              </p>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <Link
                href="/youtube"
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-white/10 text-xs font-semibold text-slate-200 hover:text-white transition-all shadow-md"
              >
                <Compass className="w-4 h-4 text-rose-400" />
                <span>Import YouTube VOD</span>
              </Link>
            </div>
          </div>
        </section>

        {/* Upload Dropzone Section */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-rose-400" />
              <span>Instant Drop: Upload & Clip OBS Recording</span>
            </h2>
          </div>
          <OBSUploadDropzone onUploadSuccess={() => loadDownloadedVideos()} />
        </section>

        {/* Ready to Clip Section */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Video className="w-4 h-4 text-emerald-400" />
                <span>Local VODs Ready to Clip ({downloadedVideos.length})</span>
              </h2>
            </div>
            {downloadedVideos.length > 0 && (
              <span className="text-xs text-slate-400">
                Click any video to jump straight into Clip Studio
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="flex flex-col items-center justify-center p-16 text-slate-400 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-rose-500" />
              <span className="text-xs font-medium">Scanning local VOD library...</span>
            </div>
          ) : downloadedVideos.length === 0 ? (
            <div className="p-12 text-center rounded-2xl bg-slate-900/40 border border-white/5 space-y-3">
              <HardDrive className="w-10 h-10 text-slate-600 mx-auto" />
              <h3 className="text-sm font-bold text-slate-200">No Downloaded VODs Available Yet</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Drop an OBS recording above or download a gameplay stream from your YouTube library to start creating vertical shorts and landscape highlights.
              </p>
              <div className="pt-2 flex items-center justify-center gap-3">
                <Link
                  href="/"
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-xl shadow-md transition-all"
                >
                  Go to Library
                </Link>
                <Link
                  href="/youtube"
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-white/10 transition-all"
                >
                  Explore YouTube
                </Link>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {downloadedVideos.map((video) => (
                <div
                  key={video.id}
                  className="group relative flex flex-col bg-[#12141c] hover:bg-[#181b26] border border-white/5 hover:border-rose-500/30 rounded-2xl overflow-hidden shadow-lg transition-all duration-300 hover:shadow-2xl hover:shadow-rose-950/20"
                >
                  <Link
                    href={`/studio/${video.id}`}
                    className="relative aspect-video w-full bg-slate-900 block overflow-hidden"
                  >
                    <img
                      src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`}
                      alt={video.title}
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center">
                      <div className="px-4 py-2 rounded-xl bg-rose-600/90 text-white flex items-center gap-2 text-xs font-bold shadow-lg transform scale-90 group-hover:scale-100 transition-transform">
                        <Scissors className="w-4 h-4" />
                        <span>Open in Studio</span>
                      </div>
                    </div>
                    <div className="absolute bottom-2.5 right-2.5 yt-badge shadow-md">
                      {video.duration_formatted}
                    </div>
                    <div className="absolute top-2.5 left-2.5 flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/90 text-white text-xs font-semibold backdrop-blur-md shadow-md">
                      <HardDrive className="w-3 h-3" />
                      <span>{formatBytes(video.file_size_bytes) || "Ready"}</span>
                    </div>
                  </Link>

                  <div className="p-4 flex-1 flex flex-col justify-between gap-3">
                    <div>
                      <Link
                        href={`/studio/${video.id}`}
                        className="text-sm font-semibold text-slate-100 group-hover:text-rose-400 line-clamp-2 leading-snug transition-colors"
                        title={video.title}
                      >
                        {video.title}
                      </Link>
                      <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
                        <span className="font-medium text-slate-300 truncate max-w-[160px]">
                          {video.channel_name || "Gameplay VOD"}
                        </span>
                        {video.published_at && (
                          <div className="flex items-center gap-1">
                            <Clock className="w-3 h-3 text-slate-500" />
                            <span>{video.published_at}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="pt-2 border-t border-white/5 flex items-center justify-between gap-2">
                      <Link
                        href={`/videos/${video.id}`}
                        className="text-xs text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-1"
                      >
                        <Play className="w-3 h-3" />
                        <span>View VOD</span>
                      </Link>

                      <Link
                        href={`/studio/${video.id}`}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold rounded-lg shadow-md shadow-rose-900/30 transition-all cursor-pointer active:scale-95"
                      >
                        <Scissors className="w-3.5 h-3.5" />
                        <span>Create Clips</span>
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
