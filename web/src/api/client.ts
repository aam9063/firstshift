import type {
  CandidateDetail,
  CandidatesListResponse,
  LiveFeedResponse,
  OverviewResponse,
} from "./types";

/* Single access point for console data (specs/04b-console.md section 2).
   Every function fetches its documented endpoint on the FirstShift API;
   components and hooks never call fetch elsewhere and never import
   fixtures. The API base comes from VITE_API_URL with the local backend
   default; errors are typed as ApiError so views can render status. */

export const API_URL: string =
  import.meta.env.VITE_API_URL ?? "http://localhost:8001";

export class ApiError extends Error {
  /** HTTP status, or 0 when the request never got a response. */
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`);
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : "unknown error";
    throw new ApiError(0, `Network error calling ${path}: ${reason}`);
  }
  if (!response.ok) {
    throw await apiErrorFrom(response, path);
  }
  return (await response.json()) as T;
}

/* FastAPI error bodies carry { detail: string }; fall back to the status
   line when the body is missing or not JSON. */
async function apiErrorFrom(response: Response, path: string): Promise<ApiError> {
  let message = `FirstShift API answered ${response.status} for ${path}`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.length > 0) {
      message = body.detail;
    }
  } catch {
    /* body was not JSON; keep the status-line message */
  }
  return new ApiError(response.status, message);
}

export async function fetchOverview(): Promise<OverviewResponse> {
  return request<OverviewResponse>("/api/overview");
}

export async function fetchLiveFeedMeta(): Promise<LiveFeedResponse> {
  return request<LiveFeedResponse>("/api/live");
}

export async function fetchCandidates(): Promise<CandidatesListResponse> {
  return request<CandidatesListResponse>("/api/candidates");
}

export async function fetchCandidate(id: string): Promise<CandidateDetail> {
  return request<CandidateDetail>(`/api/candidates/${encodeURIComponent(id)}`);
}
