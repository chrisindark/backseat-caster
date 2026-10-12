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
  output_dir?: string | null;
  landscape_path?: string | null;
  vertical_blur_path?: string | null;
  vertical_crop_path?: string | null;
  manifest_path?: string | null;
  encoder_used?: string | null;
  render_duration_seconds?: number | null;
  error_message?: string | null;
  celery_task_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  message?: string | null;
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
  audio_config: {
    has_narration: boolean;
    narration_path: string | null;
    ducking_applied: boolean;
    game_audio_gain: number;
  };
  outputs: {
    landscape?: RenderManifestOutput;
    vertical_blur?: RenderManifestOutput;
    vertical_crop?: RenderManifestOutput;
  };
  render_stats: {
    total_render_seconds: number;
  };
}

