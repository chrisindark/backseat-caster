import {
  DownloadResponse,
  RenderClipResponse,
  RenderJobListResponse,
  RenderJobResponse,
  RenderManifest,
  RenderRequest,
  SyncResponse,
  UploadSelectionPayload,
  VideoItem,
  VideoListResponse,
  YouTubeChannelResponse,
  YouTubeChannelVideoItem,
} from "@/types/video";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function parseResponse<T>(res: Response, fallbackActionName: string): Promise<T> {
  if (!res.ok) {
    let errMsg = `${res.status}`;
    try {
      const errJson = await res.json();
      errMsg = errJson.error_message || errJson.detail || JSON.stringify(errJson);
    } catch {
      errMsg = await res.text();
    }
    throw new Error(`Failed to ${fallbackActionName}: ${errMsg}`);
  }

  const data = await res.json();
  if (data && typeof data === "object" && "response" in data && data.response !== undefined) {
    return data.response as T;
  }
  return data as T;
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchVideos(params: {
  page?: number;
  limit?: number;
  status?: string;
  search?: string;
  channel?: string;
}): Promise<VideoListResponse> {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page.toString());
  if (params.limit) query.set("limit", params.limit.toString());
  if (params.status && params.status !== "all") query.set("status", params.status);
  if (params.search) query.set("search", params.search);
  if (params.channel) query.set("channel", params.channel);

  const res = await fetch(`${API_BASE}/videos?${query.toString()}`, {
    cache: "no-store",
  });
  return parseResponse<VideoListResponse>(res, "fetch videos");
}

export async function fetchVideo(videoId: string): Promise<VideoItem> {
  const res = await fetch(`${API_BASE}/videos/${videoId}`, {
    cache: "no-store",
  });
  return parseResponse<VideoItem>(res, `fetch video ${videoId}`);
}


export async function fetchYouTubeChannelVideos(params: {
  channel?: string;
  limit?: number;
  offset?: number;
}): Promise<YouTubeChannelResponse> {
  const query = new URLSearchParams();
  if (params.channel) query.set("channel", params.channel);
  if (params.limit) query.set("limit", params.limit.toString());
  if (params.offset !== undefined) query.set("offset", params.offset.toString());

  const res = await fetch(`${API_BASE}/videos/youtube/channel?${query.toString()}`, {
    cache: "no-store",
  });
  return parseResponse<YouTubeChannelResponse>(res, "fetch YouTube channel videos");
}

export async function syncChannel(
  channelUrl?: string,
  limit: number = 20,
  offset: number = 0,
  videos?: Partial<YouTubeChannelVideoItem>[]
): Promise<SyncResponse> {
  const res = await fetch(`${API_BASE}/videos/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel_url: channelUrl,
      limit,
      offset,
      videos: videos && videos.length > 0 ? videos : undefined,
    }),
  });
  return parseResponse<SyncResponse>(res, "sync channel");
}

export async function downloadVideo(videoId: string): Promise<DownloadResponse> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return parseResponse<DownloadResponse>(res, "start download");
}

export async function getVideoStatus(videoId: string): Promise<{
  video_id: string;
  is_downloaded: boolean;
  download_status: string;
  download_progress: number;
  local_file_path?: string | null;
  file_size_bytes?: number | null;
  error_message?: string | null;
}> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/status`, {
    cache: "no-store",
  });
  return parseResponse<{
    video_id: string;
    is_downloaded: boolean;
    download_status: string;
    download_progress: number;
    local_file_path?: string | null;
    file_size_bytes?: number | null;
    error_message?: string | null;
  }>(res, `fetch video status for ${videoId}`);
}

export async function deleteVideoDownload(videoId: string): Promise<{ status: string; message?: string }> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/download`, {
    method: "DELETE",
  });
  return parseResponse<{ status: string; message?: string }>(res, "delete video download");
}

export async function createRender(request: RenderRequest): Promise<RenderClipResponse> {
  const res = await fetch(`${API_BASE}/renders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseResponse<RenderClipResponse>(res, "render clip");
}

export async function fetchRenders(params?: {
  video_id?: string;
}): Promise<{ items: RenderManifest[] }> {
  const query = new URLSearchParams();
  if (params?.video_id) query.set("video_id", params.video_id);

  const url = `${API_BASE}/renders${query.toString() ? `?${query.toString()}` : ""}`;
  const res = await fetch(url, {
    cache: "no-store",
  });
  return parseResponse<{ items: RenderManifest[] }>(res, "fetch renders");
}

export async function fetchRenderJobs(params?: {
  video_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<RenderJobListResponse> {
  const query = new URLSearchParams();
  if (params?.video_id) query.set("video_id", params.video_id);
  if (params?.status && params.status !== "all") query.set("status", params.status);
  if (params?.limit) query.set("limit", params.limit.toString());
  if (params?.offset !== undefined) query.set("offset", params.offset.toString());

  const url = `${API_BASE}/renders/jobs${query.toString() ? `?${query.toString()}` : ""}`;
  const res = await fetch(url, {
    cache: "no-store",
  });
  return parseResponse<RenderJobListResponse>(res, "fetch render jobs");
}

export async function deleteRender(clipId: string): Promise<{
  status: string;
  clip_id: string;
  message?: string;
}> {
  const res = await fetch(`${API_BASE}/renders/${clipId}`, {
    method: "DELETE",
  });
  return parseResponse<{ status: string; clip_id: string; message?: string }>(
    res,
    `delete render ${clipId}`
  );
}

export async function updateUploadSelection(
  clipId: string,
  payload: UploadSelectionPayload
): Promise<{
  clip_id: string;
  upload_selection: UploadSelectionPayload;
  message: string;
}> {
  const res = await fetch(`${API_BASE}/renders/${clipId}/upload-selection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<{
    clip_id: string;
    upload_selection: UploadSelectionPayload;
    message: string;
  }>(res, `update upload selection for ${clipId}`);
}

export async function retryRenderJob(jobId: string): Promise<RenderJobResponse> {
  const res = await fetch(`${API_BASE}/renders/jobs/${jobId}/retry`, {
    method: "POST",
  });
  return parseResponse<RenderJobResponse>(res, `retry render job ${jobId}`);
}

export async function getRender(clipId: string): Promise<RenderManifest> {
  const res = await fetch(`${API_BASE}/renders/${clipId}`, {
    cache: "no-store",
  });
  return parseResponse<RenderManifest>(res, `fetch render ${clipId}`);
}

export async function getRenderJobStatus(targetId: string): Promise<RenderJobResponse> {
  const res = await fetch(`${API_BASE}/renders/jobs/${targetId}`, {
    cache: "no-store",
  });
  return parseResponse<RenderJobResponse>(res, `fetch render status for ${targetId}`);
}

export function getStreamUrl(clipId: string, videoType: "landscape" | "vertical_blur" | "vertical_crop"): string {
  return `${API_BASE}/renders/${clipId}/stream/${videoType}`;
}

export function getDownloadedVideoStreamUrl(videoId: string): string {
  return `${API_BASE}/videos/${videoId}/stream`;
}




