"use client";

import { uploadLocalVideo } from "@/lib/api";
import { VideoItem } from "@/types/video";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Film,
  HardDrive,
  Loader2,
  Radio,
  Scissors,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import React, { useCallback, useRef, useState } from "react";

interface OBSUploadDropzoneProps {
  onUploadSuccess: (video: VideoItem) => void;
}

const SUPPORTED_EXTENSIONS = [".mp4", ".mkv", ".mov", ".webm", ".ts", ".flv", ".m4v"];

export const OBSUploadDropzone: React.FC<OBSUploadDropzoneProps> = ({
  onUploadSuccess,
}) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadedVideo, setUploadedVideo] = useState<VideoItem | null>(null);
  const [customTitle, setCustomTitle] = useState("");
  const [channelName, setChannelName] = useState("OBS Studio");
  const [isExpanded, setIsExpanded] = useState(true);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      const ext = `.${file.name.split(".").pop()?.toLowerCase() || ""}`;
      if (!SUPPORTED_EXTENSIONS.includes(ext)) {
        setErrorMessage(
          `Unsupported file format '${ext}'. Please upload OBS recordings in ${SUPPORTED_EXTENSIONS.join(", ")}.`
        );
        return;
      }

      setErrorMessage(null);
      setIsUploading(true);
      setUploadProgress(0);
      setStatusMessage("Uploading local gameplay footage...");
      setUploadedVideo(null);

      try {
        const titleToUse =
          customTitle.trim() ||
          file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");

        const video = await uploadLocalVideo(
          file,
          titleToUse,
          channelName.trim() || "OBS Studio",
          (pct) => {
            setUploadProgress(pct);
            if (pct >= 100) {
              setStatusMessage("Probing video streams & extracting frame thumbnail...");
            } else {
              setStatusMessage(`Uploading OBS recording (${pct}%)...`);
            }
          }
        );

        setUploadedVideo(video);
        setStatusMessage("Video ready for clipping & audio processing!");
        setCustomTitle("");
        onUploadSuccess(video);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setErrorMessage(msg);
      } finally {
        setIsUploading(false);
      }
    },
    [customTitle, channelName, onUploadSuccess]
  );

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      handleFile(file);
    }
  };

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      handleFile(file);
      e.target.value = "";
    }
  };

  return (
    <div className="mb-8 bg-[#12141c]/90 border border-white/10 rounded-2xl overflow-hidden shadow-2xl backdrop-blur-xl transition-all">
      {/* Header bar */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/5 bg-gradient-to-r from-rose-950/20 via-slate-900/50 to-transparent">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-rose-600/20 text-rose-400 border border-rose-500/30">
            <Radio className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-white tracking-wide">
                Direct OBS & Local VOD Import
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                Instant Ingestion
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Drag-and-drop raw OBS recordings (.mp4, .mkv, .mov) directly without YouTube roundtripping
            </p>
          </div>
        </div>

        <button
          onClick={() => setIsExpanded((prev) => !prev)}
          className="text-slate-400 hover:text-slate-200 p-1.5 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
          title={isExpanded ? "Collapse" : "Expand"}
        >
          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {isExpanded && (
        <div className="p-5">
          {/* Hidden native input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp4,.mkv,.mov,.webm,.ts,.flv,.m4v,video/*"
            onChange={onFileInputChange}
            className="hidden"
          />

          {/* Error Banner */}
          {errorMessage && (
            <div className="mb-4 p-3 rounded-xl bg-red-950/40 border border-red-500/40 text-red-200 text-xs flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                <span>{errorMessage}</span>
              </div>
              <button
                onClick={() => setErrorMessage(null)}
                className="text-red-300 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Success Banner / Card */}
          {uploadedVideo && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/30 flex flex-col sm:flex-row items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3.5">
                <div className="w-16 h-10 bg-slate-900 rounded-lg overflow-hidden shrink-0 border border-emerald-500/20 relative">
                  {uploadedVideo.thumbnail_url ? (
                    <img
                      src={uploadedVideo.thumbnail_url}
                      alt={uploadedVideo.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <Film className="w-5 h-5 text-emerald-400 m-auto mt-2.5" />
                  )}
                  <div className="absolute bottom-0.5 right-1 text-[9px] bg-black/80 px-1 rounded text-white font-mono">
                    {uploadedVideo.duration_formatted}
                  </div>
                </div>

                <div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-bold text-white">
                      {uploadedVideo.title}
                    </span>
                  </div>
                  <p className="text-xs text-emerald-300/80">
                    Probed & catalogued • Local file ready for clipping and EBU R128 audio normalization
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2.5 shrink-0">
                <Link
                  href={`/studio/${uploadedVideo.id}`}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold rounded-lg shadow-lg shadow-rose-950/40 transition-all cursor-pointer active:scale-95"
                >
                  <Scissors className="w-3.5 h-3.5" />
                  <span>Open in Clip Studio</span>
                </Link>

                <button
                  onClick={() => setUploadedVideo(null)}
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg border border-white/10 transition-colors cursor-pointer"
                >
                  Upload Another
                </button>
              </div>
            </motion.div>
          )}

          {/* Active Upload Progress Card */}
          {isUploading && (
            <div className="mb-5 p-4 rounded-xl bg-slate-900/90 border border-rose-500/30">
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="text-slate-200 font-semibold flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 text-rose-400 animate-spin" />
                  {statusMessage}
                </span>
                <span className="text-rose-400 font-mono font-bold">
                  {uploadProgress}%
                </span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-white/5">
                <motion.div
                  className="bg-gradient-to-r from-rose-500 via-amber-500 to-emerald-400 h-full rounded-full transition-all duration-200"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* Interactive Drag & Drop Zone */}
          <div
            onDragEnter={onDragEnter}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => !isUploading && fileInputRef.current?.click()}
            className={`relative rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all duration-300 flex flex-col items-center justify-center gap-3 ${
              isDragOver
                ? "border-rose-500 bg-rose-500/10 scale-[1.01] shadow-2xl shadow-rose-900/30"
                : "border-white/15 bg-slate-900/40 hover:border-rose-500/50 hover:bg-slate-900/70"
            }`}
          >
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-transform ${
                isDragOver
                  ? "bg-rose-600 text-white scale-110 shadow-lg shadow-rose-900/50"
                  : "bg-slate-800 text-rose-400 border border-white/10 group-hover:scale-105"
              }`}
            >
              <Upload className="w-6 h-6 animate-pulse" />
            </div>

            <div>
              <p className="text-sm font-bold text-white mb-1">
                Drop your OBS or gameplay recording here
              </p>
              <p className="text-xs text-slate-400 max-w-md">
                or <span className="text-rose-400 underline font-medium">browse local files</span>. Supports{" "}
                <code className="text-slate-300 bg-black/40 px-1 py-0.5 rounded">.mp4</code>,{" "}
                <code className="text-slate-300 bg-black/40 px-1 py-0.5 rounded">.mkv</code>,{" "}
                <code className="text-slate-300 bg-black/40 px-1 py-0.5 rounded">.mov</code>,{" "}
                <code className="text-slate-300 bg-black/40 px-1 py-0.5 rounded">.webm</code> up to several gigabytes.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-2 mt-1">
              <span className="px-2 py-0.5 rounded text-[11px] bg-slate-800 text-slate-300 border border-white/5 flex items-center gap-1">
                <HardDrive className="w-3 h-3 text-slate-400" />
                Zero-reencode local copy
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] bg-slate-800 text-slate-300 border border-white/5 flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-amber-400" />
                Auto-frame thumbnail
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] bg-slate-800 text-slate-300 border border-white/5 flex items-center gap-1">
                <Clock className="w-3 h-3 text-emerald-400" />
                Immediate Studio Scrubbing
              </span>
            </div>
          </div>

          {/* Optional metadata inputs */}
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Optional Title (defaults to filename)
              </label>
              <input
                type="text"
                value={customTitle}
                onChange={(e) => setCustomTitle(e.target.value)}
                placeholder="e.g. Marvel Rivals Grandmaster Team Wipe"
                className="w-full px-3 py-1.5 bg-slate-900/90 border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
                disabled={isUploading}
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Channel / Source Name
              </label>
              <input
                type="text"
                value={channelName}
                onChange={(e) => setChannelName(e.target.value)}
                placeholder="OBS Studio"
                className="w-full px-3 py-1.5 bg-slate-900/90 border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors"
                disabled={isUploading}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
