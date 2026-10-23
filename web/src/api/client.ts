import type {
  AdaptersHealthResponse,
  AuditQuery,
  AuditResponse,
  CandidateDetail,
  CandidatesListResponse,
  ErasureInput,
  ErasureResponse,
  EvalReport,
  EvalSummaryRow,
  LiveFeedResponse,
  OutboxListResponse,
  OverviewResponse,
  PauseResponse,
  ReplayResponse,
  RestaurantShiftsResponse,
  RestaurantRow,
  SimClockAdvanceInput,
  SimClockAdvanceResponse,
  SimMessageInput,
  SimMessageResponse,
  SimScenarioLoadResponse,
  AttentionItem,
  SimulatorMessage,
} from "./types";

/* Single access point for console data (specs/04b-console.md section 2).
   Every function fetches its documented endpoint on the FirstShift API;
   components and hooks never call fetch elsewhere and never import
   fixtures. The API base comes from VITE_API_URL with the local backend
   default; errors are typed as ApiError so views can render status. */

export const API_URL: string =
  import.meta.env.VITE_API_URL ?? "http://localhost:8001";

/** Backend role values accepted by X-Actor-Role (app/api/console/helpers.py). */
export type ActorRole = "talent" | "dpo" | "ops";

export class ApiError extends Error {
  /** HTTP status, or 0 when the request never got a response. */
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : "unknown error";
    throw new ApiError(0, `Network error calling ${path}: ${reason}`);
  }
  if (!response.ok) {
    throw await apiErrorFrom(response, path);
  }
  return (await response.json()) as T;
}

/* Human actions are audited with the acting role from X-Actor-Role
   (specs/04b-console.md section 2, app/api/console/helpers.py). */
async function mutate<T>(
  method: "POST",
  path: string,
  options: { body?: unknown; role?: ActorRole },
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.role) headers["X-Actor-Role"] = options.role;
  return request<T>(path, {
    method,
    headers,
    body: options.body === undefined ? JSON.stringify({}) : JSON.stringify(options.body),
  });
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

/* Restaurants (specs/04b-console.md section 3.5) */

export async function fetchRestaurants(): Promise<RestaurantRow[]> {
  return request<RestaurantRow[]>("/api/restaurants");
}

export async function fetchRestaurantShifts(id: string): Promise<RestaurantShiftsResponse> {
  return request<RestaurantShiftsResponse>(
    `/api/restaurants/${encodeURIComponent(id)}/shifts`,
  );
}

export async function pauseRestaurant(
  id: string,
  body: { resume: boolean },
): Promise<PauseResponse> {
  return mutate<PauseResponse>("POST", `/api/restaurants/${encodeURIComponent(id)}/pause`, {
    body,
    role: "ops",
  });
}

/* Operations queues (specs/04b-console.md section 3.6) */

export async function fetchEscalations(): Promise<AttentionItem[]> {
  return request<AttentionItem[]>("/api/escalations");
}

export async function fetchAdapterHealth(): Promise<AdaptersHealthResponse> {
  return request<AdaptersHealthResponse>("/health/adapters");
}

export async function fetchOutbox(status: string, role: ActorRole): Promise<OutboxListResponse> {
  return request<OutboxListResponse>(
    `/api/outbox?status=${encodeURIComponent(status)}`,
    { headers: { "X-Actor-Role": role } },
  );
}

export async function replayOutboxMessage(id: string): Promise<ReplayResponse> {
  return mutate<ReplayResponse>("POST", `/api/outbox/${encodeURIComponent(id)}/replay`, {
    role: "ops",
  });
}

/* Audit log (specs/04b-console.md section 3.8) */

export async function fetchAudit(query: AuditQuery = {}): Promise<AuditResponse> {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.eventType) params.set("eventType", query.eventType);
  if (query.candidateId) params.set("candidateId", query.candidateId);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<AuditResponse>(`/api/audit${suffix}`);
}

/* Evals (specs/04b-console.md section 3.7) */

export async function fetchEvalVersions(): Promise<EvalSummaryRow[]> {
  return request<EvalSummaryRow[]>("/api/evals");
}

export async function fetchEvalReport(version: string): Promise<EvalReport> {
  return request<EvalReport>(`/api/evals/${encodeURIComponent(version)}`);
}

/* Compliance actions (specs/04b-console.md section 3.8) */

export async function createErasureRequest(input: ErasureInput): Promise<ErasureResponse> {
  return mutate<ErasureResponse>("POST", "/api/erasure-requests", {
    role: "dpo",
    body: { candidate_id: input.candidateId, reason: input.reason },
  });
}

/* Simulator (specs/04b-console.md section 3.9) */

export async function fetchSimulatorMessages(): Promise<SimulatorMessage[]> {
  const raw = await request<
    {
      recipient_ref: string;
      body: string;
      quick_replies: string[];
      correlation_id: string;
    }[]
  >("/simulator/messages");
  return raw.map((message) => ({
    recipientRef: message.recipient_ref,
    body: message.body,
    quickReplies: message.quick_replies,
    correlationId: message.correlation_id,
  }));
}

export async function loadSimScenario(scenarioId: string): Promise<SimScenarioLoadResponse> {
  return mutate<SimScenarioLoadResponse>(
    "POST",
    `/api/sim/scenarios/${encodeURIComponent(scenarioId)}/load`,
    {},
  );
}

export async function advanceSimClock(input: SimClockAdvanceInput): Promise<SimClockAdvanceResponse> {
  return mutate<SimClockAdvanceResponse>("POST", "/api/sim/clock/advance", { body: input });
}

export async function sendSimMessage(input: SimMessageInput): Promise<SimMessageResponse> {
  return mutate<SimMessageResponse>("POST", "/api/sim/messages", { body: input });
}
