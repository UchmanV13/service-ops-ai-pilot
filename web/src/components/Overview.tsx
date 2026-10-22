import React from "react";
import { summary } from "../data";
import { CRITERIA_LABEL, pct, usd } from "../format";
import type { Criterion, PilotSummary } from "../types";

function critValue(k: string, c: Criterion): string {
  if (c.note) return "nothing automated";
  if (k === "G6_shift") return `${pct(c.critical_recall as number)} / ${pct((c.inappropriate as number) ?? null)}`;
  if (k === "G7_economics") return `${usd(c.base as number)} / ${usd(c.pessimistic as number)}`;
  if (k === "G1_critical_recall") return `${pct(c.value)} (LB ${pct(c.lower95 ?? null)})`;
  if (k === "G2_inappropriate_automation") return `${pct(c.value)} (UB ${pct(c.upper95 ?? null)})`;
  return pct(c.value);
}

function PilotCard({ p }: { p: PilotSummary }) {
  const go = p.decision === "GO";
  const m = p.holdout_metrics;
  return (
    <section className="panel stack" aria-label={p.name}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h3>{p.name}</h3>
          <p className="small muted">Scored once on <span className="mono">{p.holdout}</span> ({m.n.toLocaleString()} tickets) · thresholds set on {p.calibration_split}</p>
        </div>
        <span className={`chip ${go ? "pass" : "fail"}`} style={{ fontSize: "0.85rem", padding: "4px 12px" }}>{p.decision}</span>
      </div>
      <div className="grid3">
        <div className="stat"><span className="label">Automated</span><b>{pct(m.automated_coverage.rate)}</b></div>
        <div className="stat"><span className="label">Routing accuracy</span><b>{pct(m.routing_accuracy.rate)}</b></div>
        <div className="stat"><span className="label">Critical recall</span><b>{pct(m.critical_recall.rate)}</b></div>
      </div>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Criterion</th><th className="num">Result</th><th>Status</th></tr></thead>
          <tbody>
            {Object.entries(p.go_no_go).map(([k, c]) => (
              <tr key={k}>
                <td><span className="mono small">{k.slice(0, 2)}</span> {CRITERIA_LABEL[k]}</td>
                <td className="num">{critValue(k, c)}</td>
                <td><span className={`chip ${c.note ? "na" : c.pass ? "pass" : "fail"}`}>{c.note ? "n/a" : c.pass ? "Pass" : "Fail"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function Overview({ go }: { go: (tab: string) => void }) {
  const [p1, p2] = summary.pilots;
  const h1 = p1.holdout_metrics, h2 = p2.holdout_metrics;
  const sweep = p2.threshold_sweep.find((s) => Math.abs(s.lambda - 0.95) < 1e-6);
  return (
    <div className="stack" style={{ gap: 28 }}>
      <section className="verdict">
        <div className="big-decision fam-escalate" aria-label="Recommendation">Don't automate yet</div>
        <div className="stack">
          <h1>Service-request triage pilot, Halden Devices</h1>
          <p className="lede">
            Two pre-registered pilots of AI triage for a fictional hardware vendor's service desk. Both came back NO-GO on the criteria fixed
            before testing. The system routes well and catches almost every safety case, but the cost of catching them
            (false escalations) and the critical cases it still misses outweigh what it saves. One more pilot is justified, with the
            conditions below.
          </p>
          <div className="row">
            <button className="btn primary" onClick={() => go("triage")}>Try the triage console</button>
            <button className="btn" onClick={() => go("evaluation")}>See the evaluation</button>
          </div>
        </div>
      </section>

      <div className="grid2">
        <PilotCard p={p1} />
        <PilotCard p={p2} />
      </div>

      <section className="grid2">
        <div className="panel stack">
          <h3>What the pilots proved</h3>
          <ul className="prose" style={{ paddingLeft: 18, margin: 0 }}>
            <li>Iteration worked where it was aimed: intent accuracy rose from {pct(h1.intent_accuracy.rate)} to {pct(h2.intent_accuracy.rate)} and routing from {pct(h1.routing_accuracy.rate)} to {pct(h2.routing_accuracy.rate)} on phrasings the models never saw.</li>
            <li>Escalation decides the economics, not automation. Holding critical recall near 98% means escalating tickets that are not critical: only {pct(h2.escalation_precision.rate)} of Pilot 2 escalations were truly critical.</li>
            <li>Hand-written rules overfit. The safety rules caught {pct(p2.components.hard_rules.recall)} of new critical tickets after catching 98% on the Pilot 1 development data they were written from; the injection patterns caught {p2.components.injection.detected} of {p2.components.injection.n_injection} new injection phrasings.</li>
            <li>Statistical guarantees need representative calibration data. Pilot 1's automation threshold held its 4% error bound on validation (1.1%) but not on test ({pct(1 - (h1.automated_accuracy.rate ?? 0))}), because tickets that share a phrasing are correlated.</li>
            <li>Text inside a ticket cannot trigger an action. Actions come from an allow-list of read-only lookups, KB replies and scheduling links, so an injection that slips past the detector can at worst earn a routine reply.</li>
          </ul>
        </div>
        <div className="panel stack">
          <h3>Conditions for a third pilot</h3>
          <ul className="prose" style={{ paddingLeft: 18, margin: 0 }}>
            <li>Real, labeled ticket history with an agreement check between two labelers (the blind sheet and kappa script are ready).</li>
            <li>The Claude arm, already wired into the same harness, run under the same protocol.</li>
            <li>A calibration set drawn from the same period and channels as the traffic it will govern, with a cluster-aware threshold test.</li>
            <li>Fix the two design gaps the calibration set exposed: multi-request cues that carry the dominant intent, and look-alike warranty requests.</li>
            <li>An escalation path priced realistically: a senior-analyst review queue costs less than a specialist hand-off.</li>
          </ul>
          {sweep && (
            <p className="callout">
              Not a result, a reason to continue: on Pilot 2's holdout, a 0.95 threshold would have automated {pct(sweep.coverage)} of tickets at {pct(sweep.auto_error)} error.
              The protocol could not certify that in advance, so it is not claimed.
            </p>
          )}
        </div>
      </section>
      <p className="small muted">{summary.note} Halden Devices does not exist; no real company's tickets, systems or volumes are represented.</p>
    </div>
  );
}
