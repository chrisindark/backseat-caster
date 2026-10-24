import {
  DeleteHighlightsResponse,
  DetectHighlightsRequest,
  DetectHighlightsResponse,
  DownloadResponse,
  HighlightCandidateListResponse,
  HighlightRunListResponse,
  HighlightStatusResponse,
  RenderClipResponse,
  RenderJobListResponse,
  RenderJobResponse,
  RenderManifest,
  RenderRequest,
  SyncResponse,
  UploadSelectionPayload,
  StagedClipsResponse,
  VideoItem,
  VideoListResponse,
  YouTubeAuthStatus,
  YouTubeBatchUploadResponse,
  YouTubeChannelResponse,
  YouTubeChannelVideoItem,
  YouTubeQuota,
  YouTubeUploadResult,
} from "@/types/video";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001/api/v1";

async function parseResponse<T>(res: Response, fallbackActionName: string): Promise<T> {
  if (!res.ok) {
    let errMsg = `${res.status} ${res.statusText}`;
    try {
      const rawText = await res.text();
      try {
        const errJson = JSON.parse(rawText);
        if (errJson) {
          if (typeof errJson.error_message === "string") {
            errMsg = errJson.error_message;
          } else if (Array.isArray(errJson.detail)) {
            errMsg = errJson.detail
              .map((item: { msg?: string; loc?: (string | number)[] }) => {
                const field = item.loc ? item.loc.slice(1).join(".") : "";
                return field ? `${field}: ${item.msg}` : item.msg || JSON.stringify(item);
              })
              .join("; ");
          } else if (typeof errJson.detail === "string") {
            errMsg = errJson.detail;
          } else {
            errMsg = JSON.stringify(errJson);
          }
        }
      } catch {
        if (rawText && rawText.trim()) {
          errMsg = rawText.trim();
        }
      }
    } catch {
      // response body could not be read
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

export async function createVideo(data: Partial<VideoItem> & { title: string }): Promise<VideoItem> {
  const res = await fetch(`${API_BASE}/videos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return parseResponse<VideoItem>(res, "create video");
}

export async function updateVideo(videoId: string, data: Partial<VideoItem>): Promise<VideoItem> {
  const res = await fetch(`${API_BASE}/videos/${videoId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return parseResponse<VideoItem>(res, `update video ${videoId}`);
}

export async function deleteVideo(videoId: string, deleteFile = true): Promise<{ status: string; message?: string }> {
  const res = await fetch(`${API_BASE}/videos/${videoId}?delete_file=${deleteFile}`, {
    method: "DELETE",
  });
  return parseResponse<{ status: string; message?: string }>(res, `delete video ${videoId}`);
}

export function getVideoThumbnailUrl(videoId: string): string {
  return `${API_BASE}/videos/${videoId}/thumbnail`;
}

export async function uploadLocalVideo(
  file: File,
  title?: string,
  channelName: string = "OBS Studio",
  onProgress?: (progressPct: number) => void
): Promise<VideoItem> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("file", file);
    if (title) formData.append("title", title);
    if (channelName) formData.append("channel_name", channelName);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/videos/upload`);

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percentComplete = Math.round((event.loaded / event.total) * 100);
          onProgress(percentComplete);
        }
      };
    }

    xhr.onload = () => {
      try {
        const text = xhr.responseText;
        const json = JSON.parse(text);
        if (xhr.status >= 200 && xhr.status < 300 && json.success) {
          resolve(json.response as VideoItem);
        } else {
          const errMsg =
            json.error_message || json.detail || `Upload failed with HTTP status ${xhr.status}`;
          reject(new Error(typeof errMsg === "string" ? errMsg : JSON.stringify(errMsg)));
        }
      } catch (err) {
        reject(new Error(`Failed to parse response: ${err}`));
      }
    };

    xhr.onerror = () => {
      reject(new Error("Network error during local video upload"));
    };

    xhr.send(formData);
  });
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

export async function updateRenderJob(
  jobId: string,
  data: Partial<RenderJobResponse>
): Promise<RenderJobResponse> {
  const res = await fetch(`${API_BASE}/renders/jobs/${jobId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return parseResponse<RenderJobResponse>(res, `update render job ${jobId}`);
}

export async function deleteRenderJob(
  jobId: string
): Promise<{ status: string; clip_id?: string; message?: string }> {
  const res = await fetch(`${API_BASE}/renders/jobs/${jobId}`, {
    method: "DELETE",
  });
  return parseResponse<{ status: string; clip_id?: string; message?: string }>(
    res,
    `delete render job ${jobId}`
  );
}

export interface BulkDeleteRendersResponse {
  deleted_clip_ids: string[];
  failed_clip_ids: string[];
  not_found_clip_ids: string[];
  deleted_count: number;
  total_requested: number;
  task_id?: string | null;
  message: string;
}

export async function bulkDeleteRenders(
  clipIds: string[],
  options?: { sync?: boolean }
): Promise<BulkDeleteRendersResponse> {
  const res = await fetch(`${API_BASE}/renders/bulk-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      clip_ids: clipIds,
      sync: options?.sync ?? true,
    }),
  });
  return parseResponse<BulkDeleteRendersResponse>(res, "bulk delete renders");
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

export function getStreamUrl(clipId: string, videoType: "landscape" | "vertical_blur" | "vertical_crop" | "third_person" | "direct_crop" | "cinematic" | "custom" | string): string {
  return `${API_BASE}/renders/${clipId}/stream/${videoType}`;
}

export function getDownloadedVideoStreamUrl(videoId: string): string {
  return `${API_BASE}/videos/${videoId}/stream`;
}

// -----------------------------------------------------------------------------
// YouTube OAuth & Upload API Helpers
// -----------------------------------------------------------------------------

export async function getYouTubeAuthStatus(): Promise<YouTubeAuthStatus> {
  const res = await fetch(`${API_BASE}/youtube/auth/status`, {
    cache: "no-store",
  });
  return parseResponse<YouTubeAuthStatus>(res, "fetch YouTube auth status");
}

export async function getYouTubeAuthUrl(redirectUri?: string): Promise<{
  auth_url: string;
  redirect_uri: string;
  client_id?: string;
}> {
  const query = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : "";
  const res = await fetch(`${API_BASE}/youtube/auth/url${query}`, {
    cache: "no-store",
  });
  return parseResponse<{
    auth_url: string;
    redirect_uri: string;
    client_id?: string;
  }>(res, "generate YouTube authorization URL");
}

export async function uploadClipToYouTube(
  clipId: string,
  options: {
    title?: string;
    description?: string;
    tags?: string[];
    privacy?: string;
    format?: string;
    is_short?: boolean;
    sync?: boolean;
  } = {}
): Promise<YouTubeUploadResult> {
  const res = await fetch(`${API_BASE}/youtube/upload/${clipId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
  return parseResponse<YouTubeUploadResult>(res, `upload clip ${clipId} to YouTube`);
}

export async function uploadSelectedClipsToYouTube(
  sync = false
): Promise<YouTubeBatchUploadResponse> {
  const query = sync ? "?sync=true" : "";
  const res = await fetch(`${API_BASE}/youtube/upload/selected${query}`, {
    method: "POST",
  });
  return parseResponse<YouTubeBatchUploadResponse>(
    res,
    "upload selected clips to YouTube"
  );
}

export async function fetchYouTubeQuota(): Promise<YouTubeQuota> {
  const res = await fetch(`${API_BASE}/youtube/quota`, { cache: "no-store" });
  return parseResponse<YouTubeQuota>(res, "fetch YouTube quota usage");
}

export async function fetchStagedClips(): Promise<StagedClipsResponse> {
  const res = await fetch(`${API_BASE}/youtube/staging`, { cache: "no-store" });
  return parseResponse<StagedClipsResponse>(res, "fetch auto-staged clips");
}

export async function scheduleStagedClip(
  clipId: string,
  publishAt: string | null
): Promise<RenderJobResponse> {
  const res = await fetch(`${API_BASE}/youtube/staging/${clipId}/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ publish_at: publishAt }),
  });
  return parseResponse<RenderJobResponse>(
    res,
    `update schedule for ${clipId}`
  );
}

export async function publishStagedClipNow(
  clipId: string
): Promise<YouTubeUploadResult> {
  const res = await fetch(`${API_BASE}/youtube/staging/${clipId}/publish-now`, {
    method: "POST",
  });
  return parseResponse<YouTubeUploadResult>(
    res,
    `publish staged clip ${clipId}`
  );
}

export async function revokeYouTubeAuth(): Promise<{
  revoked: boolean;
  message: string;
}> {
  const res = await fetch(`${API_BASE}/youtube/auth/revoke`, {
    method: "POST",
  });
  return parseResponse<{ revoked: boolean; message: string }>(
    res,
    "revoke YouTube authorization"
  );
}

// -----------------------------------------------------------------------------
// AI Highlight Mining API Helpers
// -----------------------------------------------------------------------------

export async function detectHighlights(
  videoId: string,
  payload: DetectHighlightsRequest = {}
): Promise<DetectHighlightsResponse> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/highlights/detect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<DetectHighlightsResponse>(res, "start highlight detection");
}

export async function getHighlightStatus(
  videoId: string
): Promise<HighlightStatusResponse> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/highlights/status`, {
    cache: "no-store",
  });
  return parseResponse<HighlightStatusResponse>(
    res,
    `fetch highlight status for ${videoId}`
  );
}

export async function fetchHighlightCandidates(
  videoId: string
): Promise<HighlightCandidateListResponse> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/highlights`, {
    cache: "no-store",
  });
  return parseResponse<HighlightCandidateListResponse>(
    res,
    `fetch highlight candidates for ${videoId}`
  );
}

export async function deleteHighlightCandidates(
  videoId: string
): Promise<DeleteHighlightsResponse> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/highlights`, {
    method: "DELETE",
  });
  return parseResponse<DeleteHighlightsResponse>(
    res,
    `delete highlight candidates for ${videoId}`
  );
}

export async function fetchHighlightRuns(
  videoId: string
): Promise<HighlightRunListResponse> {
  const res = await fetch(`${API_BASE}/videos/${videoId}/highlights/runs`, {
    cache: "no-store",
  });
  return parseResponse<HighlightRunListResponse>(
    res,
    `fetch highlight runs for ${videoId}`
  );
}

export function getHighlightThumbnailUrl(
  videoId: string,
  candidateId: string
): string {
  return `${API_BASE}/videos/${videoId}/highlights/${candidateId}/thumb.jpg`;
}
