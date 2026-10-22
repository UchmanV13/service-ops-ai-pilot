export type Action = "AUTO_REPLY_KB" | "AUTO_LOOKUP" | "AUTO_SCHEDULE_LINK" | "REQUEST_INFO" | "HUMAN_REVIEW" | "ESCALATE";
export type PolicyName = "frozen" | "exploratory";

export interface Policy {
  auto_threshold: number;
  critical_threshold: number;
  multi_threshold: number;
  non_english: string;
  require_evidence: boolean;
  multi_mode: string;
  sibling_guard: number | null;
  critical_signal: string;
  version: string;
  certified: boolean;
}

export interface Decision {
  action: Action;
  automated: boolean;
  intent: string;
  queue: string;
  priority: string;
  confidence: number;
  p_critical: number;
  critical_score: number;
  top3: [string, number][];
  reasons: string[];
  fields: Record<string, string>;
  missing_fields: string[];
  language: string;
  pii_redacted: string[];
  injection: string[];
  guard_hits: [string, string][];
  retrieval: { id: string; title: string; score: number }[];
  lookup: Record<string, unknown> | null;
  draft: { text: string; citations: string[] } | null;
  redacted_text: string;
  model_version: string;
  policy_version: string;
  latency_ms?: number;
  audit_id?: string;
  outcome?: string;
  correct?: boolean;
}

export interface Gold {
  intent: string;
  queue: string;
  action: Action;
  priority: string;
  critical: boolean;
  missing_fields: string[];
}

export interface ReplayTicket {
  id: string;
  label: string;
  text: string;
  language: string;
  gold: Gold;
  flags: Record<string, unknown>;
  decisions: Record<PolicyName, Decision>;
}

export interface Replay {
  model_version: string;
  policies: Record<PolicyName, Policy>;
  tickets: ReplayTicket[];
}

export interface Rate {
  rate: number | null;
  k: number;
  n: number;
  ci95: [number, number] | null;
}

export interface Criterion {
  pass: boolean;
  value?: number | null;
  lower95?: number;
  upper95?: number | null;
  note?: string;
  [k: string]: unknown;
}

export interface SweepPoint {
  lambda: number;
  coverage: number;
  auto_error: number | null;
  inappropriate: number | null;
  n_auto: number;
  workload: number;
  net_usd_per_1000: number;
}

export interface Econ {
  net_usd_per_1000: number;
  gross_savings_usd_per_1000: number;
  costs_usd_per_1000: number;
  analyst_hours_saved_per_1000: number;
  components_usd_per_1000: Record<string, number>;
}

export interface PilotSummary {
  name: string;
  holdout: string;
  calibration_split: string;
  decision: string;
  go_no_go: Record<string, Criterion>;
  params: Policy;
  alpha: number;
  holdout_metrics: Record<string, Rate> & { n: number; latency_ms?: { p50: number; p95: number } };
  shift_metrics: Record<string, Rate>;
  handwritten_metrics: Record<string, Rate>;
  arms: Record<string, Record<string, number | null>>;
  economics: { test_base: Econ; test_pessimistic: Econ };
  tornado: { reference: number; rows: { assumption: string; low: number; high: number; swing: number }[] };
  threshold_sweep: SweepPoint[];
  critical_sweep: { tau: number; critical_recall: number; escalation_precision: number; escalated_share: number }[];
  ablations: Record<string, Record<string, number | null>>;
  components: Record<string, any>;
  retrieval: Record<string, { n: number; recall_at_1: number; recall_at_3: number }>;
  robustness: Record<string, any>;
  calibration: Record<string, { ece: number; reliability: { bin: string; n: number; confidence: number; accuracy: number }[] }>;
  by_language: Record<string, { n: number; coverage: number; n_auto: number; auto_errors: number; intent_accuracy: number }>;
  ltt_trace: { lambda: number; n_auto: number; errors: number; p_value: number }[];
}

export interface Summary {
  pilots: PilotSummary[];
  learning_curve: { phrasings_per_intent: number; n_train: number; holdout_intent_accuracy: number; holdout_aurc: number }[];
  note: string;
}

export interface Review {
  decision_id: string;
  ticket_id?: string;
  reviewer: string;
  verdict: "approve" | "edit" | "reject";
  final_text?: string;
  ts: number;
}

export interface AuditEntry {
  id: string;
  ts: number;
  action: Action;
  intent: string;
  confidence: number;
  reasons: string[];
  model_version: string;
  policy_version: string;
  review: { verdict: string; reviewer: string; ts: number } | null;
}
