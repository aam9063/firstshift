import type {
  CandidateDetail,
  LiveEvent,
  LiveFeedResponse,
  OverviewResponse,
} from "./types";
import {
  candidateFixture,
  liveEventsFixture,
  liveFeedFixture,
  overviewFixture,
} from "../mocks/fixtures";

/* Single access point for console data. While the backend session runs in
   parallel these functions resolve from fixtures; when the FastAPI schema is
   live each body is swapped for a real fetch against the same path named in
   specs/04b-console.md section 2. Components and hooks never import fixtures
   directly. */

const delay = (ms = 120) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export async function fetchOverview(): Promise<OverviewResponse> {
  await delay();
  return overviewFixture;
}

export async function fetchLiveFeedMeta(): Promise<LiveFeedResponse> {
  await delay();
  return liveFeedFixture;
}

export async function fetchCandidate(id: string): Promise<CandidateDetail> {
  await delay();
  if (id !== candidateFixture.id) {
    throw new Error(`Candidate ${id} not found in the mock dataset`);
  }
  return candidateFixture;
}

/* Seed events for the live feed before the stream produces new ones. */
export async function fetchLiveEventsSeed(): Promise<LiveEvent[]> {
  await delay();
  return liveEventsFixture;
}
