import type { Action } from "./types";

export const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "n/a" : `${(x * 100).toFixed(d)}%`);
export const usd = (x: number) => `${x < 0 ? "−\u2060" : "+\u2060"}$${Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
export const human = (s: string) => s.replace(/_/g, " ");

export const ACTION_LABEL: Record<Action, string> = {
  AUTO_REPLY_KB: "Auto-reply from KB",
  AUTO_LOOKUP: "Auto status lookup",
  AUTO_SCHEDULE_LINK: "Auto scheduling link",
  REQUEST_INFO: "Ask for missing info",
  HUMAN_REVIEW: "Person reviews draft",
  ESCALATE: "Escalate to specialist",
};

export function family(a: Action): "auto" | "person" | "escalate" {
  if (a === "ESCALATE") return "escalate";
  if (a === "HUMAN_REVIEW") return "person";
  return "auto";
}

export const FAMILY_LABEL = { auto: "Automated", person: "Person", escalate: "Escalated" };

export const CRITERIA_LABEL: Record<string, string> = {
  G1_critical_recall: "Critical recall ≥ 98%, lower bound ≥ 95%",
  G2_inappropriate_automation: "Inappropriate automation ≤ 2%, upper bound ≤ 3%",
  G3_automated_accuracy: "Automated accuracy ≥ 95%",
  G4_automated_coverage: "Automated coverage ≥ 30%",
  G5_routing_accuracy: "Routing accuracy ≥ 85%",
  G6_shift: "Shift set: critical recall ≥ 95%, inappropriate ≤ 5%",
  G7_economics: "Net value > 0 (base and pessimistic)",
};
