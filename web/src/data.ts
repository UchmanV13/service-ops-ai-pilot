// Data access for both builds. "live" calls the Flask API; "replay" serves the
// real pipeline's precomputed decisions and keeps reviews in this browser.
import replayData from "../public/replay.json";
import summaryData from "../public/results_summary.json";
import type { AuditEntry, Decision, PolicyName, Replay, Review, Summary } from "./types";

declare const __MODE__: "live" | "replay";
export const MODE = __MODE__;
export const replay = replayData as unknown as Replay;
export const summary = summaryData as unknown as Summary;

const STORE_KEY = "sopilot.reviews.v1";

function readStore(): Review[] {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as Review[]) : [];
  } catch {
    return [];
  }
}

function writeStore(rows: Review[]) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(rows));
  } catch {
    /* storage unavailable: reviews live only in memory for this visit */
  }
}

let memoryReviews: Review[] = readStore();

export function localReviews(): Review[] {
  return memoryReviews;
}

export function addLocalReview(r: Review) {
  memoryReviews = [...memoryReviews.filter((x) => x.decision_id !== r.decision_id), r];
  writeStore(memoryReviews);
}

export function clearLocalReviews() {
  memoryReviews = [];
  writeStore(memoryReviews);
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data as T;
}

export async function triageLive(text: string, policy: PolicyName): Promise<Decision> {
  return post<Decision>("/api/triage", { text, policy });
}

export async function reviewLive(r: Omit<Review, "ts">): Promise<void> {
  await post("/api/review", r);
}

export async function auditLive(): Promise<AuditEntry[]> {
  const res = await fetch("/api/audit");
  return (await res.json()) as AuditEntry[];
}

export async function queueLive(): Promise<{ id: string; decision: Decision }[]> {
  const res = await fetch("/api/queue");
  return (await res.json()) as { id: string; decision: Decision }[];
}
