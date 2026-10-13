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
  created_at?: string | null;
  updated_at?: string | null;
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
  modes?: ClippingMode[] | string[];
  sync?: boolean;
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
  uploaded_at?: string | null;
}

export interface YouTubeBatchUploadResponse {
  total_requested: number;
  total_succeeded: number;
  total_failed: number;
  results: YouTubeUploadResult[];
  message: string;
}
