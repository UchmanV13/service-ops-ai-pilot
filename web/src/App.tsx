import React, { useEffect, useState } from "react";
import { MODE } from "./data";
import type { AuditEntry, Decision, PolicyName, Review } from "./types";
import Overview from "./components/Overview";
import Triage from "./components/Triage";
import Queue from "./components/Queue";
import Evaluation from "./components/Evaluation";
import Audit from "./components/Audit";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "triage", label: "Triage" },
  { id: "queue", label: "Review queue" },
  { id: "evaluation", label: "Evaluation" },
  { id: "audit", label: "Audit log" },
];

function initialTab() {
  const h = (typeof location !== "undefined" ? location.hash : "").replace("#", "");
  return TABS.some((t) => t.id === h) ? h : "overview";
}

export default function App() {
  const [tab, setTab] = useState(initialTab);
  const [policy, setPolicy] = useState<PolicyName>("frozen");
  const [log, setLog] = useState<AuditEntry[]>([]);

  useEffect(() => {
    const on = () => setTab(initialTab());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const go = (id: string) => {
    setTab(id);
    try { history.replaceState(null, "", `#${id}`); } catch { /* frame may refuse */ }
    window.scrollTo({ top: 0 });
  };

  const onDecision = (d: Decision, ref: string) => {
    if (MODE === "live") return; // the API writes its own log
    setLog((l) => [{ id: `${ref}-${d.policy_version}-${Date.now()}`, ts: Date.now() / 1000, action: d.action, intent: d.intent,
      confidence: d.confidence, reasons: d.reasons, model_version: d.model_version, policy_version: d.policy_version, review: null }, ...l].slice(0, 200));
  };

  const onReview = (r: Review) => {
    if (MODE === "live") return;
    setLog((l) => [{ id: `review-${r.decision_id}-${r.ts}`, ts: r.ts / 1000, action: "HUMAN_REVIEW", intent: r.decision_id.split(":")[0],
      confidence: NaN, reasons: [`Reviewer ${r.reviewer} chose ${r.verdict}`], model_version: "-", policy_version: "-",
      review: { verdict: r.verdict, reviewer: r.reviewer, ts: r.ts / 1000 } }, ...l]);
  };

  return (
    <>
      <header className="top">
        <div className="wrap">
          <div className="brand">
            <strong>Halden Service Desk · AI pilot</strong>
            <span>Triage, selective automation and human review for a fictional hardware vendor</span>
          </div>
          <nav className="tabs" role="tablist" aria-label="Sections">
            {TABS.map((t) => (
              <button key={t.id} role="tab" className="tab" aria-selected={tab === t.id} onClick={() => go(t.id)}>{t.label}</button>
            ))}
          </nav>
        </div>
      </header>
      <div className="banner">
        <div className="wrap">
          Synthetic tickets and a made-up company. {MODE === "replay"
            ? "This page replays decisions the Python pipeline made on held-out tickets; nothing here calls a model."
            : "Live mode: decisions come from the running pipeline and are written to the audit log."}
        </div>
      </div>
      <main className="wrap">
        {tab === "overview" && <Overview go={go} />}
        {tab === "triage" && <Triage policy={policy} setPolicy={setPolicy} onDecision={onDecision} />}
        {tab === "queue" && <Queue policy={policy} setPolicy={setPolicy} onReview={onReview} />}
        {tab === "evaluation" && <Evaluation />}
        {tab === "audit" && <Audit local={log} />}
      </main>
    </>
  );
}
