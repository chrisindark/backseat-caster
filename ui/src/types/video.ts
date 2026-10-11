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

export interface SyncResponse {
  status: string;
  channel_title: string;
  channel_url: string;
  total_found: number;
  new_added: number;
  updated: number;
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
