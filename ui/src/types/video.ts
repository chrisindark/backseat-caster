export type DownloadStatus =
  | "not_downloaded"
  | "pending"
  | "downloading"
  | "completed"
  | "failed";

export interface ApiResponse<T = unknown> {
  success: boolean;
  status_code: number;
  response: T | null;
  error_message?: string | null;
  error_code?: string | null;
}


export interface UploadedHighlightSummary {
  clip_id: string;
  youtube_video_id?: string | null;
  youtube_upload_url?: string | null;
  youtube_uploaded_at?: string | null;
  title?: string | null;
  format?: string | null;
}

export interface VideoItem {
  id: string;
  title: string;
  description?: string | null;
  thumbnail_url?: string | null;
  duration: number;
  duration_formatted: string;
  channel_name?: string | null;
  channel_id?: string | null;
  channel_url?: string | null;
  view_count: number;
  published_at?: string | null;
  webpage_url: string;
  is_downloaded: boolean;
  local_file_path?: string | null;
  file_size_bytes?: number | null;
  download_status: DownloadStatus;
  download_progress: number;
  error_message?: string | null;

  // Highlight mining & YouTube upload tracking
  highlight_status?: string | null;
  highlight_progress?: number;
  highlight_stage?: string;
  highlight_candidate_count?: number;
  rendered_clip_count?: number;
  uploaded_clip_count?: number;
  has_uploaded_highlights?: boolean;
  uploaded_highlights?: UploadedHighlightSummary[];

  // Disk storage and cleanup indicators
  can_cleanup_vod?: boolean;
  can_cleanup_renders?: boolean;

  created_at?: string | null;
  updated_at?: string | null;
}

export interface VideoStorageCleanupOptions {
  clean_vod?: boolean;
  clean_uploaded_renders?: boolean;
  clean_all_renders?: boolean;
}

export interface VideoStorageCleanupResult {
  video_id: string;
  reclaimed_bytes: number;
  reclaimed_formatted: string;
  vod_deleted: boolean;
  renders_deleted_count: number;
  message: string;
}

export interface VideoListResponse {
  items: VideoItem[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
  channel_title?: string | null;
  channel_url?: string | null;
}

export interface YouTubeChannelVideoItem {
  id: string;
  title: string;
  description?: string | null;
  thumbnail_url?: string | null;
  duration: number;
  duration_formatted: string;
  channel_name?: string | null;
  channel_id?: string | null;
  channel_url?: string | null;
  view_count: number;
  published_at?: string | null;
  webpage_url: string;
  is_in_database: boolean;
  is_downloaded: boolean;
  download_status: DownloadStatus;
}

export interface YouTubeChannelResponse {
  channel_title: string;
  channel_id?: string | null;
  channel_url: string;
  limit: number;
  offset: number;
  total_loaded: number;
  has_more: boolean;
  videos: YouTubeChannelVideoItem[];
}

export interface SyncResponse {
  status: string;
  channel_title: string;
  channel_url: string;
  total_found: number;
  new_added: number;
  updated: number;
  skipped?: number;
  message: string;
}

export interface DownloadResponse {
  video_id: string;
  download_status: DownloadStatus;
  download_progress: number;
  local_file_path?: string | null;
  task_id?: string | null;
  message: string;
}

export type ClippingMode =
  | "landscape"
  | "vertical_blur"
  | "third_person"
  | "direct_crop"
  | "cinematic"
  | "custom";

export interface RenderRequest {
  video_id: string;
  start_seconds: number;
  duration_seconds: number;
  narration_path?: string | null;
  encoder?: string;
  overwrite?: boolean;
  clip_id?: string | null;
  crop_preset?: "third_person" | "direct_crop" | "cinematic" | "custom" | string;
  crop_blur_padding?: number | null;
  quality_preset?: "high" | "compact" | "archive" | string | null;
  modes?: ClippingMode[] | string[];
  normalize_audio?: boolean;
  target_lufs?: number;
  sync?: boolean;
  highlight_candidate_id?: string | null;
  hero_name?: string | null;
  clip_context?: string | null;
}

export interface RenderClipResponse {
  job_id?: string | null;
  clip_id: string;
  status: string;
  progress?: number;
  output_dir: string;
  landscape_path?: string | null;
  vertical_blur_path?: string | null;
  vertical_crop_path?: string | null;
  manifest_path?: string | null;
  encoder_used?: string | null;
  render_duration_seconds?: number | null;
  error_message?: string | null;
  modes?: string[];
  outputs?: Record<string, string>;
  message: string;
}

export interface RenderJobResponse {
  job_id: string;
  clip_id: string;
  video_id: string;
  status: "pending" | "rendering" | "completed" | "failed" | string;
  progress: number;
  start_seconds: number;
  duration_seconds: number;
  narration_path?: string | null;
  encoder?: string;
  crop_preset?: string;
  crop_blur_padding?: number | null;
  quality_preset?: string;
  normalize_audio?: boolean;
  target_lufs?: number;
  modes?: string[];
  outputs?: Record<string, string>;
  output_dir?: string | null;
  landscape_path?: string | null;
  vertical_blur_path?: string | null;
  vertical_crop_path?: string | null;
  manifest_path?: string | null;
  encoder_used?: string | null;
  render_duration_seconds?: number | null;
  error_message?: string | null;
  celery_task_id?: string | null;
  video_title?: string | null;
  video_thumbnail_url?: string | null;
  channel_name?: string | null;
  is_selected_for_upload?: boolean;
  selected_format?: string | null;
  upload_metadata?: string | null;
  youtube_video_id?: string | null;
  youtube_upload_status?: string | null;
  youtube_upload_progress?: number | null;
  youtube_upload_url?: string | null;
  youtube_uploaded_at?: string | null;
  youtube_upload_error?: string | null;
  auto_staged?: boolean;
  highlight_candidate_id?: string | null;
  scheduled_publish_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  message?: string | null;
}

export interface RenderJobListResponse {
  items: RenderJobResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface UploadSelectionPayload {
  is_selected: boolean;
  preferred_format?: "vertical_blur" | "vertical_crop" | "landscape" | string;
  title?: string;
  description?: string;
  tags?: string[];
  privacy?: "private" | "unlisted" | "public" | string;
  hero_name?: string;
  clip_context?: string;
  game?: string;
  updated_at?: string;
}

export interface RenderManifestOutput {
  path: string;
  width: number;
  height: number;
  duration: number;
  size_bytes: number;
  encoder: string;
  crop_preset?: string;
  crop_blur_padding?: number;
}

export interface RenderManifest {
  clip_id: string;
  created_at: string;
  landscape_path?: string;
  vertical_blur_path?: string;
  vertical_crop_path?: string;
  manifest_path?: string;
  video_id?: string;
  video_title?: string;
  video_thumbnail_url?: string;
  channel_name?: string;
  upload_selection?: UploadSelectionPayload;
  source: {
    path: string;
    duration: number;
    width: number;
    height: number;
    fps: number;
    has_audio: boolean;
  };
  clip: {
    start_seconds: number;
    duration_seconds: number;
  };
  request?: {
    start_seconds: number;
    duration_seconds: number;
    has_narration?: boolean;
    crop_preset?: string;
    crop_blur_padding?: number;
  };
  modes?: string[];
  audio_config?: {
    has_narration: boolean;
    narration_path: string | null;
    ducking_applied: boolean;
    game_audio_gain: number;
  };
  outputs: {
    landscape?: RenderManifestOutput;
    vertical_blur?: RenderManifestOutput;
    vertical_crop?: RenderManifestOutput;
    third_person?: RenderManifestOutput;
    direct_crop?: RenderManifestOutput;
    cinematic?: RenderManifestOutput;
    custom?: RenderManifestOutput;
    [key: string]: RenderManifestOutput | undefined;
  };
  render_stats?: {
    total_render_seconds: number;
  };
  render_duration_seconds?: number;
  quality_preset?: string | null;
  watermark?: {
    enabled: boolean;
    position?: string;
    opacity?: number;
    scale?: number;
    margin?: number;
  };
  branding?: {
    enabled: boolean;
    intro?: boolean;
    outro?: boolean;
    intro_seconds?: number;
    outro_seconds?: number;
    padding_seconds?: number;
    total_duration_seconds?: number;
    channel_name?: string | null;
  };
  cta?: {
    enabled: boolean;
    style?: "outro_card" | "overlay" | string;
    seconds?: number;
    overlay?: boolean;
    headline?: string;
    subtitle?: string;
    speech_text?: string;
    voice?: string;
    voiceover?: boolean;
    voiceover_start_seconds?: number;
  };
  auto_staged?: boolean;
  highlight_candidate_id?: string | null;
  youtube_upload_status?: string | null;
  youtube_upload_progress?: number | null;
  youtube_upload_error?: string | null;
  youtube_uploaded_at?: string | null;
  scheduled_publish_at?: string | null;
  youtube_upload?: {
    video_id: string;
    url: string;
    format: string;
    is_short: boolean;
    privacy: string;
    title?: string;
    uploaded_at?: string;
  };
}

export interface YouTubeAuthStatus {
  is_authenticated: boolean;
  channel_title?: string | null;
  channel_id?: string | null;
  channel_handle?: string | null;
  thumbnail_url?: string | null;
  scopes?: string[];
  expires_at?: string | null;
  client_configured: boolean;
  message?: string | null;
}

export interface YouTubeUploadResult {
  clip_id: string;
  youtube_video_id?: string | null;
  youtube_url?: string | null;
  title: string;
  format: string;
  is_short: boolean;
  status: "completed" | "uploading" | "failed" | string;
  privacy: string;
  progress: number;
  error_message?: string | null;
  error_code?: string | null;
  retry_at?: string | null;
  uploaded_at?: string | null;
}

export interface YouTubeBatchUploadResponse {
  total_requested: number;
  total_succeeded: number;
  total_failed: number;
  results: YouTubeUploadResult[];
  message: string;
}

// -----------------------------------------------------------------------------
// Phase 8: Auto-Stage, Native Scheduling & Quota Types
// -----------------------------------------------------------------------------

export interface YouTubeQuota {
  quota_day: string;
  daily_limit_units: number;
  units_used: number;
  units_remaining: number;
  upload_quota_cost: number;
  max_uploads_per_day: number;
  uploads_today: number;
  uploads_remaining: number;
  failed_uploads: number;
  can_upload: boolean;
  blocked_reason?: string | null;
  blocked_until?: string | null;
  api_quota_exhausted: boolean;
  upload_limit_exceeded: boolean;
  last_error_code?: string | null;
  last_error_message?: string | null;
  last_error_at?: string | null;
  resets_at: string;
}

export interface AutoStagedClip {
  clip_id: string;
  candidate_id: string;
  video_id: string;
  score: number;
  title: string;
  is_selected_for_upload: boolean;
  scheduled_publish_at?: string | null;
  metadata_source: "llm" | "fallback" | string;
}

export interface AutoStageResponse {
  video_id: string;
  staged_count: number;
  clips: AutoStagedClip[];
  message: string;
}

export interface StagedClipsResponse {
  items: RenderJobResponse[];
  total: number;
  quota?: YouTubeQuota | null;
  llm_available?: boolean;
}

export interface RegenerateMetadataRequest {
  use_llm?: boolean | null;
  hero_name?: string | null;
  clip_context?: string | null;
  game?: string | null;
  highlight_candidate_id?: string | null;
}

export interface RegenerateMetadataResponse {
  clip_id: string;
  metadata_source: "llm" | "fallback" | string;
  used_llm: boolean;
  llm_available: boolean;
  upload_selection: {
    title?: string;
    description?: string;
    tags?: string[];
    privacy?: string;
    preferred_format?: string;
    metadata_source?: string;
    previous_metadata?: PreviousMetadata;
    [key: string]: unknown;
  };
  previous?: PreviousMetadata | null;
  message: string;
}

export interface PreviousMetadata {
  title?: string | null;
  description?: string | null;
  tags?: string[];
  metadata_source?: string;
  regenerated_at?: string;
}

// -----------------------------------------------------------------------------
// AI Highlight Mining Types
// -----------------------------------------------------------------------------

export interface TriggerEventItem {
  time: number;
  label: string;
  roi_name?: string;
  confidence?: number;
  [key: string]: unknown;
}

export interface HighlightDetailsItem {
  kill_count?: number | null;
  has_ultimate?: boolean | null;
  is_team_wipe?: boolean | null;
  game_phase?: string | null;
  trigger_events?: TriggerEventItem[];
  [key: string]: unknown;
}

export interface HighlightCandidateItem {
  candidate_id: string;
  video_id: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  score: number;
  event_type: string;
  game: string;
  details: HighlightDetailsItem;
  thumbnail_url?: string | null;
  thumbnail_path?: string | null;
  peak_timestamp: number;
  suggested_title: string;
  suggested_tags: string[];
  // Lifecycle state & render / upload linkage (Phase 8.5)
  processing_status?: "unprocessed" | "rendering" | "rendered" | "staged" | "uploaded" | "failed";
  render_status?: string | null;
  render_job_id?: string | null;
  clip_id?: string | null;
  youtube_upload_status?: string | null;
  youtube_video_id?: string | null;
  youtube_upload_url?: string | null;
  scheduled_publish_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface HighlightRunItem {
  id: string;
  video_id: string;
  status: "pending" | "scanning" | "completed" | "failed" | string;
  game: string;
  detector_used?: string | null;
  parameters?: Record<string, unknown>;
  audio_scan_duration_seconds?: number | null;
  roi_extract_duration_seconds?: number | null;
  visual_match_duration_seconds?: number | null;
  cluster_duration_seconds?: number | null;
  total_duration_seconds?: number | null;
  video_duration_seconds?: number | null;
  audio_windows_count: number;
  frames_analyzed_count: number;
  visual_events_count: number;
  candidates_produced_count: number;
  speedup_factor?: number | null;
  celery_task_id?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
}

export interface HighlightCandidateListResponse {
  video_id: string;
  status: string;
  count: number;
  unprocessed_count?: number;
  rendered_count?: number;
  staged_count?: number;
  uploaded_count?: number;
  top_rated_left_count?: number;
  candidates: HighlightCandidateItem[];
}

export interface HighlightRunListResponse {
  video_id: string;
  count: number;
  runs: HighlightRunItem[];
}

export interface HighlightStatusResponse {
  video_id: string;
  status: "idle" | "pending" | "scanning" | "completed" | "failed" | string;
  progress: number;
  stage: string;
  error?: string | null;
  candidate_count: number;
  task_id?: string | null;
  latest_run?: HighlightRunItem | null;
}

export interface DetectHighlightsRequest {
  game?: string | null;
  force_rescan?: boolean;
  min_score?: number;
  sync?: boolean;
}

export interface DetectHighlightsResponse {
  video_id: string;
  status: string;
  message: string;
  task_id?: string | null;
  run_id?: string | null;
}

export interface DeleteHighlightsResponse {
  video_id: string;
  deleted_count: number;
  message: string;
}

export interface BatchStageHighlightsRequest {
  candidate_ids?: string[];
  top_n?: number;
  min_score?: number;
  clipping_mode?: string;
  schedule?: boolean;
  same_day_catchup?: boolean;
  crop_blur_padding?: number;
  normalize_audio?: boolean;
}

export interface BatchStageHighlightsResponse {
  video_id: string;
  requested_count: number;
  staged_count: number;
  skipped_count: number;
  staged_clips: Array<Record<string, unknown>>;
  skipped_candidate_ids: string[];
  message: string;
}

export interface ToolStatusItem {
  name: string;
  status: "ok" | "warning" | "error" | string;
  installed: boolean;
  version?: string | null;
  path?: string | null;
  error?: string | null;
  remedy?: string | null;
}

export interface DiskStatusItem {
  path: string;
  status: "ok" | "warning" | "error" | string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  percent_used: number;
  min_required_gb: number;
  error?: string | null;
  remedy?: string | null;
}

export interface PreflightReportItem {
  ready: boolean;
  status: "healthy" | "degraded" | "unhealthy" | string;
  checks: {
    ffmpeg: ToolStatusItem;
    ffprobe: ToolStatusItem;
    yt_dlp: ToolStatusItem;
    disk_space: DiskStatusItem;
    [key: string]: unknown;
  };
  errors: string[];
  warnings: string[];
}

export interface SystemHealthResponse {
  status: string;
  ready: boolean;
  version: string;
  downloads_dir: string;
  preflight?: PreflightReportItem;
}

// -----------------------------------------------------------------------------
// Setup Wizard, In-App Settings, and Demo Interfaces
// -----------------------------------------------------------------------------

export interface SetupCheckItem {
  name: string;
  title: string;
  status: "ok" | "warning" | "error" | string;
  required: boolean;
  message: string;
  remedy?: string | null;
  details?: Record<string, unknown>;
}

export interface SetupStatusResponse {
  ready: boolean;
  checks: SetupCheckItem[];
  ai_status: {
    enabled: boolean;
    configured: boolean;
    available: boolean;
    model: string;
    base_url: string;
    has_api_key: boolean;
  };
  youtube_status: YouTubeAuthStatus;
  sample_project: {
    is_loaded: boolean;
    video_id: string | null;
    rendered_count: number;
  };
}

export interface SetupSettings {
  llm_enabled: boolean;
  llm_base_url?: string | null;
  llm_model?: string | null;
  llm_has_api_key: boolean;
  default_clipping_mode: string;
  auto_stage_top_n: number;
  auto_stage_min_score: number;
  auto_cleanup_uploaded_renders: boolean;
  auto_cleanup_vod: boolean;
  youtube_redirect_uri: string;
  auto_mine_on_ingest: boolean;
  watch_dir?: string | null;
  watch_poll_interval_minutes: number;
  watch_delete_after_ingest: boolean;
}

export interface UpdateSetupSettingsPayload {
  llm_enabled?: boolean;
  llm_base_url?: string | null;
  llm_api_key?: string | null;
  llm_model?: string | null;
  default_clipping_mode?: string | null;
  auto_stage_top_n?: number | null;
  auto_stage_min_score?: number | null;
  auto_cleanup_uploaded_renders?: boolean | null;
  auto_cleanup_vod?: boolean | null;
  youtube_redirect_uri?: string | null;
  auto_mine_on_ingest?: boolean | null;
  watch_dir?: string | null;
  watch_poll_interval_minutes?: number | null;
  watch_delete_after_ingest?: boolean | null;
}

export interface WatchIngestItem {
  source_name: string;
  status: string;
  video_id?: string | null;
  title?: string | null;
  error?: string | null;
}

export interface WatchScanResponse {
  enabled: boolean;
  watch_dir?: string | null;
  discovered: number;
  ingested: number;
  skipped: number;
  failed: number;
  items: WatchIngestItem[];
  message: string;
}

export interface WatchStatusResponse {
  enabled: boolean;
  watch_dir?: string | null;
  exists: boolean;
  pending_files: number;
  poll_interval_minutes: number;
  delete_after_ingest: boolean;
  stability_seconds: number;
  supported_extensions: string[];
  recent_ingests: Array<Record<string, unknown>>;
}

export interface DemoProjectResponse {
  success: boolean;
  message: string;
  video_id: string;
  video_title: string;
  candidates_count: number;
  staged_jobs_count: number;
  rendered_jobs_count: number;
  clip_ids: string[];
}

export interface ChannelProfile {
  channel_name?: string | null;
  watermark_enabled: boolean;
  has_watermark: boolean;
  watermark_url?: string | null;
  watermark_position: "top_left" | "top_right" | "bottom_left" | "bottom_right" | "center" | string;
  watermark_opacity: number;
  watermark_scale: number;
  watermark_margin: number;
  default_framing_preset: "third_person" | "cinematic" | "direct_crop" | "vertical_blur" | "custom" | string;
  default_quality_preset: "high" | "compact" | "archive" | string;
  branding_enabled: boolean;
  branding_intro: boolean;
  branding_outro: boolean;
  branding_intro_seconds: number;
  branding_outro_seconds: number;
  branding_intro_title?: string | null;
  branding_intro_subtitle?: string | null;
  branding_outro_title: string;
  branding_outro_subtitle?: string | null;
  branding_background_color: string;
  branding_accent_color: string;
  branding_text_color: string;
  branding_font_path?: string | null;
  max_clip_seconds: number;
  cta_enabled: boolean;
  cta_style: string;
  cta_seconds: number;
  cta_headline: string;
  cta_subtitle: string;
  cta_speech_text: string;
  cta_voice: string;
  title_template?: string | null;
  pinned_hashtags: string[];
  default_privacy: "public" | "unlisted" | "private" | string;
  upload_slots: string[];
  upload_timezone: string;
  updated_at?: string | null;
}

export interface ChannelProfileUpdate {
  channel_name?: string | null;
  watermark_enabled?: boolean;
  watermark_position?: string;
  watermark_opacity?: number;
  watermark_scale?: number;
  watermark_margin?: number;
  default_framing_preset?: string;
  default_quality_preset?: string;
  branding_enabled?: boolean;
  branding_intro?: boolean;
  branding_outro?: boolean;
  branding_intro_seconds?: number;
  branding_outro_seconds?: number;
  branding_intro_title?: string | null;
  branding_intro_subtitle?: string | null;
  branding_outro_title?: string | null;
  branding_outro_subtitle?: string | null;
  branding_background_color?: string | null;
  branding_accent_color?: string | null;
  branding_text_color?: string | null;
  branding_font_path?: string | null;
  max_clip_seconds?: number;
  cta_enabled?: boolean;
  cta_style?: string;
  cta_seconds?: number;
  cta_headline?: string | null;
  cta_subtitle?: string | null;
  cta_speech_text?: string | null;
  cta_voice?: string | null;
  title_template?: string | null;
  pinned_hashtags?: string[];
  default_privacy?: string;
  upload_slots?: string[];
  upload_timezone?: string;
}

export interface WatermarkUploadResponse {
  profile: ChannelProfile;
  filename: string;
  message: string;
}

export interface YouTubeCredentialsPayload {
  client_id?: string;
  client_secret?: string;
  refresh_token?: string;
  client_secrets_json?: string;
}
