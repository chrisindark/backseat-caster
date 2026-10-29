"use client";

import { Navbar } from "@/components/Navbar";
import { YoutubeIcon } from "@/components/icons";
import {
  configureYouTubeCredentials,
  fetchSetupSettings,
  fetchSetupStatus,
  getYouTubeAuthUrl,
  loadDemoProject,
  revokeYouTubeCredentials,
  updateSetupSettings,
} from "@/lib/api";
import {
  DemoProjectResponse,
  SetupCheckItem,
  SetupSettings,
  SetupStatusResponse,
} from "@/types/video";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  Copy,
  Cpu,
  ExternalLink,
  Film,
  HardDrive,
  HelpCircle,
  Key,
  Layers,
  Loader2,
  LogOut,
  Play,
  Radio,
  RefreshCw,
  Save,
  Scissors,
  Settings as SettingsIcon,
  Sliders,
  Sparkles,
  Tv,
  UploadCloud,
  Video,
  Wand2,
  XCircle,
  Zap,
} from "lucide-react";
import Link from "next/link";
import React, { useCallback, useEffect, useState } from "react";

export default function SetupWizardPage() {
  const [status, setStatus] = useState<SetupStatusResponse | null>(null);
  const [settings, setSettings] = useState<SetupSettings | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Demo Project state
  const [isLaunchingDemo, setIsLaunchingDemo] = useState<boolean>(false);
  const [demoResult, setDemoResult] = useState<DemoProjectResponse | null>(null);

  // Guided YouTube Connect state
  const [clientSecretsInput, setClientSecretsInput] = useState<string>("");
  const [isSavingCreds, setIsSavingCreds] = useState<boolean>(false);
  const [isConnectingYt, setIsConnectingYt] = useState<boolean>(false);
  const [copiedRedirect, setCopiedRedirect] = useState<boolean>(false);

  // In-app settings form state
  const [formLlmEnabled, setFormLlmEnabled] = useState<boolean>(false);
  const [formLlmBaseUrl, setFormLlmBaseUrl] = useState<string>("");
  const [formLlmModel, setFormLlmModel] = useState<string>("llama3.2");
  const [formLlmApiKey, setFormLlmApiKey] = useState<string>("");
  const [formClippingMode, setFormClippingMode] = useState<string>("third_person");
  const [formTopN, setFormTopN] = useState<number>(3);
  const [formCleanupRenders, setFormCleanupRenders] = useState<boolean>(true);
  const [formCleanupVod, setFormCleanupVod] = useState<boolean>(false);
  const [isSavingSettings, setIsSavingSettings] = useState<boolean>(false);

  // Load initial status & settings
  const loadData = useCallback(async () => {
    try {
      const [statusRes, settingsRes] = await Promise.all([
        fetchSetupStatus(),
        fetchSetupSettings(),
      ]);
      setStatus(statusRes);
      setSettings(settingsRes);

      // Populate settings form
      setFormLlmEnabled(settingsRes.llm_enabled);
      setFormLlmBaseUrl(settingsRes.llm_base_url || "");
      setFormLlmModel(settingsRes.llm_model || "llama3.2");
      setFormClippingMode(settingsRes.default_clipping_mode || "third_person");
      setFormTopN(settingsRes.auto_stage_top_n ?? 3);
      setFormCleanupRenders(settingsRes.auto_cleanup_uploaded_renders ?? true);
      setFormCleanupVod(settingsRes.auto_cleanup_vod ?? false);

      setErrorMsg(null);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load setup diagnostics");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    setIsRefreshing(true);
    loadData();
  };

  // Launch Demo Project
  const handleLaunchDemo = async () => {
    setIsLaunchingDemo(true);
    setErrorMsg(null);
    try {
      const res = await loadDemoProject({ auto_render: true, sync: true });
      setDemoResult(res);
      setSuccessMsg(res.message);
      await loadData();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to generate demo project");
    } finally {
      setIsLaunchingDemo(false);
    }
  };

  // Copy redirect URI
  const handleCopyRedirectUri = (uri: string) => {
    navigator.clipboard.writeText(uri);
    setCopiedRedirect(true);
    setTimeout(() => setCopiedRedirect(false), 2000);
  };

  // Save YouTube client_secrets.json
  const handleSaveCredentials = async () => {
    if (!clientSecretsInput.trim()) {
      setErrorMsg("Please paste client_secrets.json content or OAuth credentials JSON.");
      return;
    }
    setIsSavingCreds(true);
    setErrorMsg(null);
    try {
      const res = await configureYouTubeCredentials({
        client_secrets_json: clientSecretsInput.trim(),
      });
      setSuccessMsg("OAuth client credentials saved! You can now authorize your channel.");
      setClientSecretsInput("");
      await loadData();
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Invalid client_secrets.json. Ensure it matches the JSON downloaded from Google Cloud."
      );
    } finally {
      setIsSavingCreds(false);
    }
  };

  // Connect YouTube (OAuth flow)
  const handleConnectYouTube = async () => {
    setIsConnectingYt(true);
    setErrorMsg(null);
    try {
      const auth = await getYouTubeAuthUrl();
      if (auth?.auth_url) {
        window.location.href = auth.auth_url;
      } else {
        throw new Error("No authorization URL returned by server.");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to generate YouTube authorization URL");
      setIsConnectingYt(false);
    }
  };

  // Revoke YouTube connection
  const handleRevokeYouTube = async () => {
    if (!confirm("Are you sure you want to disconnect your YouTube account?")) return;
    try {
      await revokeYouTubeCredentials();
      setSuccessMsg("YouTube credentials disconnected.");
      await loadData();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to disconnect credentials");
    }
  };

  // Save in-app settings
  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingSettings(true);
    setErrorMsg(null);
    try {
      const updated = await updateSetupSettings({
        llm_enabled: formLlmEnabled,
        llm_base_url: formLlmBaseUrl.trim() || null,
        llm_model: formLlmModel.trim() || null,
        llm_api_key: formLlmApiKey.trim() || undefined,
        default_clipping_mode: formClippingMode,
        auto_stage_top_n: formTopN,
        auto_cleanup_uploaded_renders: formCleanupRenders,
        auto_cleanup_vod: formCleanupVod,
      });
      setSettings(updated);
      setSuccessMsg("Settings updated and saved to data/settings.json!");
      setFormLlmApiKey(""); // Clear sensitive input
      setTimeout(() => setSuccessMsg(null), 3500);
      await loadData();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setIsSavingSettings(false);
    }
  };

  const redirectUri =
    settings?.youtube_redirect_uri || "http://localhost:3001/api/v1/youtube/auth/callback";

  return (
    <div className="min-h-screen bg-[#0b0d13] text-slate-100 flex flex-col font-sans selection:bg-rose-500/30 selection:text-white">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/5 pb-6">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-semibold mb-2">
              <Zap className="w-3.5 h-3.5" />
              <span>Tier 1 First-Run Experience</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-slate-400">
              Setup Wizard & Readiness
            </h1>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">
              Verify your local environment, launch an instant 60-second gaming demo highlight, or configure YouTube publishing and AI copy settings in seconds.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 border border-white/10 hover:bg-slate-800 text-xs font-semibold text-slate-200 transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
              <span>Re-check System</span>
            </button>

            <Link
              href="/"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-semibold text-slate-300 transition-colors"
            >
              <span>Go to Library</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Global Feedback Banners */}
        {errorMsg && (
          <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{errorMsg}</span>
            </div>
            <button
              type="button"
              onClick={() => setErrorMsg(null)}
              className="text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>
        )}

        {successMsg && (
          <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
              <span>{successMsg}</span>
            </div>
            <button
              type="button"
              onClick={() => setSuccessMsg(null)}
              className="text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>
        )}

        {/* SECTION 1: The 4 Setup Checks */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Cpu className="w-4 h-4 text-rose-500" />
                <span>System Readiness Checks</span>
              </h2>
              <p className="text-xs text-slate-400">
                Core local binaries and services evaluated automatically
              </p>
            </div>

            {status && (
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${
                  status.ready
                    ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                    : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                }`}
              >
                {status.ready ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>System Ready</span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>Action Required</span>
                  </>
                )}
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="py-12 flex flex-col items-center justify-center space-y-2">
              <Loader2 className="w-6 h-6 text-rose-500 animate-spin" />
              <p className="text-xs text-slate-400">Probing FFmpeg, disk space, and services...</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {status?.checks.map((check) => {
                const isOk = check.status === "ok";
                const isWarn = check.status === "warning";
                const isErr = check.status === "error";

                return (
                  <div
                    key={check.name}
                    className={`p-4 rounded-2xl border transition-all flex flex-col justify-between ${
                      isErr
                        ? "bg-rose-950/20 border-rose-500/30"
                        : isWarn
                        ? "bg-amber-950/20 border-amber-500/30"
                        : "bg-slate-900/60 border-white/10"
                    }`}
                  >
                    <div className="space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                          {check.name === "ffmpeg" && <Video className="w-3.5 h-3.5 text-rose-400" />}
                          {check.name === "disk_space" && <HardDrive className="w-3.5 h-3.5 text-sky-400" />}
                          {check.name === "ai_key" && <Sparkles className="w-3.5 h-3.5 text-violet-400" />}
                          {check.name === "youtube" && <YoutubeIcon className="w-3.5 h-3.5 text-rose-500" />}
                          <span>{check.title}</span>
                        </span>

                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            isOk
                              ? "bg-emerald-500/20 text-emerald-300"
                              : isWarn
                              ? "bg-amber-500/20 text-amber-300"
                              : "bg-rose-500/20 text-rose-300"
                          }`}
                        >
                          {isOk ? "Ready ✓" : isWarn ? "Notice ⚠" : "Missing ✕"}
                        </span>
                      </div>

                      <p className="text-xs text-slate-300 leading-relaxed font-medium">
                        {check.message}
                      </p>

                      {check.remedy && (
                        <div className="p-2 rounded-lg bg-black/40 border border-white/5 text-[11px] text-slate-400 font-mono">
                          {check.remedy}
                        </div>
                      )}
                    </div>

                    <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-[11px] text-slate-500">
                      <span>{check.required ? "Required" : "Optional"}</span>
                      {check.name === "ai_key" && (
                        <a href="#settings-section" className="text-violet-400 hover:text-violet-300 font-semibold">
                          Configure →
                        </a>
                      )}
                      {check.name === "youtube" && (
                        <a href="#youtube-section" className="text-rose-400 hover:text-rose-300 font-semibold">
                          Connect →
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* SECTION 2: Sample Project ("Try a Demo") */}
        <section className="relative overflow-hidden p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-rose-950/40 via-slate-900 to-amber-950/20 border border-rose-500/30 shadow-2xl space-y-6">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gradient-to-r from-rose-500/20 to-amber-500/20 border border-rose-500/30 text-rose-300 text-xs font-bold">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                <span>Zero-Download Instant Demo</span>
              </div>
              <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
                Try a Demo: Instant 60-Second Gaming Highlight
              </h2>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                No local VOD or 4GB download required! Generate a synthetic 60-second Marvel Rivals highlight clip with 3 pre-mined clutch candidates (Magneto 5K team wipe, Luna Snow counter-ult, Spider-Man contest). Tests auto-highlight mining, vertical cropping presets, and YouTube Shorts staging in under 30 seconds.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 shrink-0">
              <button
                type="button"
                onClick={handleLaunchDemo}
                disabled={isLaunchingDemo}
                className="inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-2xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white font-bold text-sm shadow-xl shadow-rose-950/50 transition-all disabled:opacity-50 cursor-pointer"
              >
                {isLaunchingDemo ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Generating & Rendering 3 Shorts...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-white" />
                    <span>Launch Demo & Render 3 Shorts</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Demo status or results */}
          {status?.sample_project.is_loaded && (
            <div className="p-4 rounded-2xl bg-slate-950/80 border border-emerald-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-white">
                    Sample Highlight Project Loaded
                  </h4>
                  <p className="text-[11px] text-slate-400">
                    60-second Marvel Rivals clip with {status.sample_project.rendered_count} vertical Shorts rendered
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <Link
                  href={`/studio/${status.sample_project.video_id}`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-white/10 text-xs font-semibold text-slate-200"
                >
                  <Scissors className="w-3.5 h-3.5 text-rose-400" />
                  <span>Open in Studio</span>
                </Link>

                <Link
                  href="/staging"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-600/30 hover:bg-violet-600/40 border border-violet-500/40 text-xs font-semibold text-violet-200"
                >
                  <UploadCloud className="w-3.5 h-3.5 text-violet-300" />
                  <span>Review in Staging</span>
                </Link>

                <Link
                  href="/renders"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-white/10 text-xs font-semibold text-slate-200"
                >
                  <Layers className="w-3.5 h-3.5 text-sky-400" />
                  <span>View Renders</span>
                </Link>
              </div>
            </div>
          )}
        </section>

        {/* SECTION 3: Guided YouTube Connect */}
        <section id="youtube-section" className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 text-xs font-semibold mb-1">
                <YoutubeIcon className="w-3.5 h-3.5" />
                <span>2-Minute Setup</span>
              </div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <span>Guided YouTube Connect</span>
              </h2>
              <p className="text-xs text-slate-400">
                Turn the Google Cloud Console gauntlet into 4 painless steps
              </p>
            </div>

            {status?.youtube_status?.is_authenticated && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>
                  Connected to @{status.youtube_status.channel_handle || status.youtube_status.channel_title}
                </span>
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Step 1 & 2: Google Cloud Console Links + Redirect URI */}
            <div className="p-5 rounded-2xl bg-slate-900/70 border border-white/10 space-y-5 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-rose-500/20 text-rose-400 text-xs font-bold flex items-center justify-center">
                    1
                  </div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    Google Cloud Console
                  </h3>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Open these 3 exact Google Cloud Console pages in your browser:
                </p>

                <div className="space-y-2">
                  <a
                    href="https://console.cloud.google.com/apis/library/youtube.googleapis.com"
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-white/5 hover:border-white/20 text-xs text-slate-200 transition-colors group"
                  >
                    <span>1. Enable YouTube Data API v3</span>
                    <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-rose-400" />
                  </a>

                  <a
                    href="https://console.cloud.google.com/apis/credentials/consent"
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-white/5 hover:border-white/20 text-xs text-slate-200 transition-colors group"
                  >
                    <span>2. OAuth Consent Screen</span>
                    <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-rose-400" />
                  </a>

                  <a
                    href="https://console.cloud.google.com/apis/credentials"
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950 border border-white/5 hover:border-white/20 text-xs text-slate-200 transition-colors group"
                  >
                    <span>3. Create OAuth Client ID</span>
                    <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-rose-400" />
                  </a>
                </div>
              </div>

              {/* Step 2: Copy Redirect URI */}
              <div className="space-y-2 pt-4 border-t border-white/5">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-rose-500/20 text-rose-400 text-xs font-bold flex items-center justify-center">
                    2
                  </div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    Authorized Redirect URI
                  </h3>
                </div>
                <p className="text-[11px] text-slate-400">
                  Paste this exact URI into &ldquo;Authorized redirect URIs&rdquo; in Google Cloud:
                </p>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={redirectUri}
                    className="flex-1 px-3 py-1.5 rounded-lg bg-black/60 border border-white/10 text-[11px] font-mono text-slate-300 select-all"
                  />
                  <button
                    type="button"
                    onClick={() => handleCopyRedirectUri(redirectUri)}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 flex items-center gap-1.5 shrink-0"
                  >
                    {copiedRedirect ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Step 3: Paste client_secrets.json */}
            <div className="p-5 rounded-2xl bg-slate-900/70 border border-white/10 space-y-4 flex flex-col justify-between">
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-rose-500/20 text-rose-400 text-xs font-bold flex items-center justify-center">
                    3
                  </div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    Paste Client Secrets JSON
                  </h3>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Download the JSON from Google Cloud Console and paste its content here:
                </p>

                <textarea
                  rows={6}
                  value={clientSecretsInput}
                  onChange={(e) => setClientSecretsInput(e.target.value)}
                  placeholder='{"web":{"client_id":"...","client_secret":"..."}}'
                  className="w-full p-3 rounded-xl bg-slate-950 border border-white/10 focus:border-rose-500 focus:outline-none text-slate-200 text-xs font-mono placeholder:text-slate-600 resize-none"
                />
              </div>

              <button
                type="button"
                onClick={handleSaveCredentials}
                disabled={isSavingCreds || !clientSecretsInput.trim()}
                className="w-full py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs transition-colors disabled:opacity-40 flex items-center justify-center gap-2 cursor-pointer"
              >
                {isSavingCreds ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Saving Credentials...</span>
                  </>
                ) : (
                  <>
                    <Save className="w-3.5 h-3.5" />
                    <span>Save client_secrets.json</span>
                  </>
                )}
              </button>
            </div>

            {/* Step 4: Authorize Account Button & Connected Profile */}
            <div className="p-5 rounded-2xl bg-slate-900/70 border border-white/10 space-y-4 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-rose-500/20 text-rose-400 text-xs font-bold flex items-center justify-center">
                    4
                  </div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    Authorize YouTube Account
                  </h3>
                </div>

                {status?.youtube_status?.is_authenticated ? (
                  <div className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/30 space-y-3">
                    <div className="flex items-center gap-3">
                      {status.youtube_status.thumbnail_url ? (
                        <img
                          src={status.youtube_status.thumbnail_url}
                          alt="Channel Avatar"
                          className="w-10 h-10 rounded-full border border-emerald-500/50"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">
                          YT
                        </div>
                      )}
                      <div>
                        <h4 className="text-xs font-bold text-white">
                          {status.youtube_status.channel_title || "Authorized Channel"}
                        </h4>
                        <p className="text-[11px] text-emerald-400">
                          @{status.youtube_status.channel_handle || "connected"}
                        </p>
                      </div>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      YouTube Data API credentials active. Ready for automatic Short uploads and scheduled release slots.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Click below to sign in with Google and grant upload permissions to your gaming YouTube channel.
                    </p>
                    <div className="p-3 rounded-xl bg-slate-950/60 border border-white/5 text-[11px] text-slate-400">
                      Requires client credentials from Step 3. Tokens are stored locally in{" "}
                      <code className="text-slate-300 font-mono">./data/youtube_token.json</code>.
                    </div>
                  </div>
                )}
              </div>

              {status?.youtube_status?.is_authenticated ? (
                <button
                  type="button"
                  onClick={handleRevokeYouTube}
                  className="w-full py-2.5 rounded-xl bg-slate-800 hover:bg-rose-950/50 hover:text-rose-300 hover:border-rose-500/30 border border-white/10 text-slate-300 font-semibold text-xs transition-colors flex items-center justify-center gap-2 cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Disconnect Account</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleConnectYouTube}
                  disabled={isConnectingYt}
                  className="w-full py-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow-lg shadow-rose-950/40 transition-colors disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
                >
                  {isConnectingYt ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Redirecting to Google...</span>
                    </>
                  ) : (
                    <>
                      <YoutubeIcon className="w-4 h-4" />
                      <span>Connect YouTube Account (OAuth)</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </section>

        {/* SECTION 4: In-App Settings */}
        <section id="settings-section" className="space-y-6 pt-4 border-t border-white/5">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-violet-500/10 text-violet-400 text-xs font-semibold mb-1">
              <Sliders className="w-3.5 h-3.5" />
              <span>In-App Customization</span>
            </div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <span>Application Settings</span>
            </h2>
            <p className="text-xs text-slate-400">
              No need to edit .env! Changes persist automatically to data/settings.json
            </p>
          </div>

          <form onSubmit={handleSaveSettings} className="p-6 rounded-3xl bg-slate-900/60 border border-white/10 space-y-6">
            {/* AI Copy Settings */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold text-violet-300 uppercase tracking-wider flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-violet-400" />
                    <span>AI Copy Engine (Universal OpenAI-compatible API)</span>
                  </h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Works offline with local Ollama or with OpenAI, Groq, DeepSeek, and Gemini
                  </p>
                </div>

                <label className="relative inline-flex items-center cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={formLlmEnabled}
                    onChange={(e) => setFormLlmEnabled(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-violet-600" />
                  <span className="ml-2.5 text-xs font-semibold text-slate-300">
                    {formLlmEnabled ? "Enabled" : "Deterministic Copy (Off)"}
                  </span>
                </label>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300">Base URL</label>
                  <input
                    type="text"
                    value={formLlmBaseUrl}
                    onChange={(e) => setFormLlmBaseUrl(e.target.value)}
                    placeholder="http://localhost:11434/v1"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-white/10 focus:border-violet-500 focus:outline-none text-slate-200 text-xs font-mono"
                  />
                  <span className="text-[10px] text-slate-500">
                    Ollama default: http://localhost:11434/v1
                  </span>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300">Model Name</label>
                  <input
                    type="text"
                    value={formLlmModel}
                    onChange={(e) => setFormLlmModel(e.target.value)}
                    placeholder="llama3.2"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-white/10 focus:border-violet-500 focus:outline-none text-slate-200 text-xs font-mono"
                  />
                  <span className="text-[10px] text-slate-500">
                    e.g. llama3.2, gpt-4o-mini, gemini-2.5-flash
                  </span>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300">API Key (Optional)</label>
                  <input
                    type="password"
                    value={formLlmApiKey}
                    onChange={(e) => setFormLlmApiKey(e.target.value)}
                    placeholder={settings?.llm_has_api_key ? "••••••••••••••••" : "Leave blank for Ollama"}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-white/10 focus:border-violet-500 focus:outline-none text-slate-200 text-xs font-mono"
                  />
                  <span className="text-[10px] text-slate-500">
                    {settings?.llm_has_api_key ? "Key currently configured on server" : "Not needed for local models"}
                  </span>
                </div>
              </div>
            </div>

            {/* Video & Automation Defaults */}
            <div className="space-y-4 pt-4 border-t border-white/5">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Video className="w-3.5 h-3.5 text-rose-400" />
                <span>Video Rendering & Staging Defaults</span>
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300">Default Crop Layout</label>
                  <select
                    value={formClippingMode}
                    onChange={(e) => setFormClippingMode(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-white/10 focus:border-rose-500 focus:outline-none text-slate-200 text-xs"
                  >
                    <option value="third_person">Third Person (Action Centered)</option>
                    <option value="cinematic">Cinematic 9:16 Center Crop</option>
                    <option value="direct_crop">Direct 1080x1920 Crop</option>
                    <option value="vertical_blur">Vertical Background Blur</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300">Auto-Stage Top N Highlights</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={formTopN}
                    onChange={(e) => setFormTopN(parseInt(e.target.value, 10) || 3)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-white/10 focus:border-rose-500 focus:outline-none text-slate-200 text-xs"
                  />
                </div>

                <div className="space-y-2 flex flex-col justify-end">
                  <label className="inline-flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={formCleanupRenders}
                      onChange={(e) => setFormCleanupRenders(e.target.checked)}
                      className="rounded accent-rose-500"
                    />
                    <span>Clean uploaded render files</span>
                  </label>
                  <span className="text-[10px] text-slate-500">
                    Frees local disk space after successful YouTube upload
                  </span>
                </div>

                <div className="space-y-2 flex flex-col justify-end">
                  <label className="inline-flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={formCleanupVod}
                      onChange={(e) => setFormCleanupVod(e.target.checked)}
                      className="rounded accent-rose-500"
                    />
                    <span>Delete source VOD after full upload</span>
                  </label>
                  <span className="text-[10px] text-slate-500">
                    Only when all candidate renders are published
                  </span>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-white/5 flex items-center justify-end gap-3">
              <button
                type="submit"
                disabled={isSavingSettings}
                className="px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow-lg shadow-rose-950/40 transition-colors disabled:opacity-50 flex items-center gap-2 cursor-pointer"
              >
                {isSavingSettings ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Save className="w-3.5 h-3.5" />
                    <span>Save In-App Settings</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}
