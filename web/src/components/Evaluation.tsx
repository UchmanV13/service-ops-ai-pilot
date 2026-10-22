import React, { useState } from "react";
import { summary } from "../data";
import { human, pct, usd } from "../format";
import { DivergingBars, LineChart } from "./charts";

const ARM_LABEL: Record<string, string> = { rules: "Keyword rules", tfidf: "TF-IDF + LR", embed: "Embeddings + LR", ensemble: "Ensemble (production)" };
const ABL_LABEL: Record<string, string> = {
  full_system: "Full system", no_hard_rules: "Without safety rules", no_critical_model: "Without the critical model (rules only)",
  no_injection_detector: "Without injection detector", no_multi_request_detector: "Without multi-request detector",
  no_evidence_check: "Without retrieval evidence check", non_english_to_humans: "Non-English to people",
  "threshold_0.80_no_guarantee": "Threshold 0.80 (no guarantee)", pilot1_multi_detector: "Pilot 1 multi-request detector",
  no_sibling_guard: "Without sibling guard", critical_signal_intent_sum: "Critical signal: intent sum",
};
const COMP_LABEL: Record<string, string> = {
  automation_savings: "Automation savings", assisted_triage_savings: "Assisted triage", spot_checks: "Spot checks",
  wrong_automation: "Wrong automation", inappropriate_automation: "Inappropriate automation", misroutes: "Misroutes",
  false_escalations: "False escalations", missed_critical: "Missed critical", maintenance: "Maintenance",
};

export default function Evaluation() {
  const [pi, setPi] = useState(1);
  const p = summary.pilots[pi];
  const sweep = p.threshold_sweep.filter((s) => s.auto_error !== null && s.n_auto >= 30);
  const certified = p.params.auto_threshold <= 1 ? p.params.auto_threshold : null;
  const [lam, setLam] = useState<number>(0.95);
  const cur = p.threshold_sweep.reduce((a, b) => (Math.abs(b.lambda - lam) < Math.abs(a.lambda - lam) ? b : a));
  const certPt = certified !== null ? p.threshold_sweep.reduce((a, b) => (Math.abs(b.lambda - certified) < Math.abs(a.lambda - certified) ? b : a)) : null;
  const comp = p.economics.test_base.components_usd_per_1000;
  const cs = p.critical_sweep;
  const lc = summary.learning_curve;
  const cal = p.calibration;

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6, maxWidth: "66ch" }}>
          <h2>Evaluation</h2>
          <p className="ink2">Each pilot was scored once, on tickets whose wording the models never trained or calibrated on. Thresholds were chosen beforehand on a separate calibration set.</p>
        </div>
        <div className="seg" role="group" aria-label="Pilot">
          {summary.pilots.map((x, i) => (<button key={x.name} aria-pressed={i === pi} onClick={() => setPi(i)}>{x.name}</button>))}
        </div>
      </div>

      <section className="panel stack" aria-label="Automation threshold">
        <h3>How much to automate</h3>
        <p className="small ink2">Move the threshold to see the trade-off on {p.name}'s held-out set. {certified !== null
          ? `The certified threshold was ${certified} (Learn-then-Test, ${pct(p.alpha, 0)} error target, chosen on ${p.calibration_split}).`
          : `No threshold passed the ${pct(p.alpha, 0)} error test on ${p.calibration_split}, so the frozen policy automates nothing.`} Everything else on this curve is descriptive.</p>
        <div className="grid3">
          <div className="stat"><span className="label">Automated</span><b>{pct(cur.coverage)}</b></div>
          <div className="stat"><span className="label">Error among automated</span><b>{pct(cur.auto_error)}</b></div>
          <div className="stat"><span className="label">Net per 1,000 tickets</span><b>{usd(cur.net_usd_per_1000)}</b></div>
        </div>
        <label className="small ink2" htmlFor="lam">Confidence threshold: <b className="num">{lam.toFixed(3)}</b></label>
        <input id="lam" type="range" min={0.5} max={0.995} step={0.005} value={lam} onChange={(e) => setLam(parseFloat(e.target.value))} />
        <LineChart ariaLabel="Coverage versus error among automated tickets"
          series={[{ name: p.name, color: "var(--s1)", points: sweep.map((s) => ({ x: s.coverage * 100, y: (s.auto_error ?? 0) * 100,
            tip: `threshold ${s.lambda.toFixed(3)}: ${pct(s.coverage)} automated, ${pct(s.auto_error)} error` })) }]}
          xDomain={[0, Math.max(45, ...sweep.map((s) => s.coverage * 100))]} yDomain={[0, Math.max(6, ...sweep.map((s) => (s.auto_error ?? 0) * 100)) + 1]}
          xLabel="Tickets automated (%)" yLabel="Error among automated (%)" xFmt={(v) => `${v}`} yFmt={(v) => `${v}`}
          refs={[{ y: 5, label: "G3 limit 5%" }]}
          marker={cur.auto_error !== null ? { x: cur.coverage * 100, y: cur.auto_error * 100, label: `${lam.toFixed(3)}`, color: "var(--s2)" } : undefined} />
        {certPt && <p className="small muted">Certified point {certified}: {pct(certPt.coverage)} automated at {pct(certPt.auto_error)} error on this held-out set.</p>}
      </section>

      <div className="grid2">
        <section className="panel stack" aria-label="Critical threshold">
          <h3>The price of catching critical tickets</h3>
          <p className="small ink2">Each point is a critical-score threshold. Lower thresholds catch more safety, security, legal and outage tickets but send more non-critical work to specialists.</p>
          <LineChart width={460} ariaLabel="Critical recall versus escalation precision"
            series={[{ name: "critical", color: "var(--escalate)", markers: true, points: cs.map((c) => ({ x: c.escalation_precision * 100, y: c.critical_recall * 100,
              tip: `${c.tau > 1 ? "rules only" : `τ ${c.tau}`}: recall ${pct(c.critical_recall)}, precision ${pct(c.escalation_precision)}, ${pct(c.escalated_share)} of tickets escalated` })) }]}
            xDomain={[20, 100]} yDomain={[60, 100]} xLabel="Escalations that were truly critical (%)" yLabel="Critical recall (%)"
            refs={[{ y: 98, label: "G1 target 98%" }]} />
        </section>
        <section className="panel stack" aria-label="Economics">
          <h3>Where the money goes: {usd(p.economics.test_base.net_usd_per_1000)} per 1,000 tickets</h3>
          <p className="small ink2">Against an all-human desk, at illustrative cost assumptions. Pessimistic case: {usd(p.economics.test_pessimistic.net_usd_per_1000)}.</p>
          <DivergingBars width={500} ariaLabel="Economics components" domain={[-1800, 900]} fmt={(v) => usd(v)}
            rows={Object.keys(COMP_LABEL).map((k) => ({ label: COMP_LABEL[k], value: comp[k] ?? 0 }))} />
          <p className="small muted">Largest swing in the sensitivity analysis: {human(p.tornado.rows[0].assumption)} ({usd(p.tornado.rows[0].low)} to {usd(p.tornado.rows[0].high)} at ×0.5 and ×1.5).</p>
        </section>
      </div>

      <div className="grid2">
        <section className="panel stack" aria-label="Learning curve">
          <h3>How much labeled variety the model needs</h3>
          <p className="small ink2">Intent accuracy on the Pilot 2 holdout when training on k distinct phrasings per intent.</p>
          <LineChart width={460} ariaLabel="Learning curve"
            series={[{ name: "accuracy", color: "var(--s1)", markers: true, points: lc.map((r) => ({ x: r.phrasings_per_intent, y: r.holdout_intent_accuracy * 100,
              tip: `${r.phrasings_per_intent} phrasings: ${pct(r.holdout_intent_accuracy)} (${r.n_train.toLocaleString()} training tickets)` })) }]}
            xDomain={[0, 20]} yDomain={[60, 95]} xLabel="Phrasings per intent" yLabel="Intent accuracy (%)" />
        </section>
        <section className="panel stack" aria-label="Calibration">
          <h3>Does confidence mean what it says?</h3>
          <p className="small ink2">Temperature scaling, fitted on out-of-fold training predictions, cut calibration error from {pct(cal.ensemble_uncalibrated.ece)} to {pct(cal.ensemble.ece)}. The raw ensemble was under-confident.</p>
          <LineChart width={460} ariaLabel="Reliability diagram"
            series={[
              { name: "Before scaling", color: "var(--s2)", markers: true, points: cal.ensemble_uncalibrated.reliability.map((r) => ({ x: r.confidence * 100, y: r.accuracy * 100, tip: `before: stated ${pct(r.confidence)}, actual ${pct(r.accuracy)} (n=${r.n})` })) },
              { name: "After scaling", color: "var(--s1)", markers: true, points: cal.ensemble.reliability.map((r) => ({ x: r.confidence * 100, y: r.accuracy * 100, tip: `after: stated ${pct(r.confidence)}, actual ${pct(r.accuracy)} (n=${r.n})` })) },
              { name: "Perfect", color: "var(--muted)", points: [{ x: 0, y: 0 }, { x: 100, y: 100 }] },
            ]}
            xDomain={[0, 100]} yDomain={[0, 100]} xLabel="Stated confidence (%)" yLabel="Actual accuracy (%)" />
          <div className="legend"><span style={{ ["--c" as string]: "var(--s2)" }}>Before scaling</span><span style={{ ["--c" as string]: "var(--s1)" }}>After scaling</span><span style={{ ["--c" as string]: "var(--muted)" }}>Perfect calibration</span></div>
        </section>
      </div>

      <div className="grid2">
        <section className="panel stack" aria-label="Comparison arms">
          <h3>Comparison arms on {p.name}'s held-out set</h3>
          <div className="tablewrap">
            <table>
              <thead><tr><th>Scorer</th><th className="num">Intent acc.</th><th className="num">Routing</th><th className="num">Critical recall</th><th className="num">Automated</th></tr></thead>
              <tbody>
                {Object.entries(p.arms).map(([k, v]) => (
                  <tr key={k}><td>{ARM_LABEL[k] ?? k}</td><td className="num">{pct(v.intent_accuracy)}</td><td className="num">{pct(v.routing_accuracy)}</td>
                    <td className="num">{pct(v.critical_recall)}</td><td className="num">{pct(v.automated_coverage)}</td></tr>
                ))}
                <tr><td>All-human baseline</td><td className="num">n/a</td><td className="num">n/a</td><td className="num">assumed 100%</td><td className="num">0%</td></tr>
              </tbody>
            </table>
          </div>
          <p className="small muted">Every arm runs inside the same guards and threshold protocol. The Claude arm is wired into the same harness and runs when an API key is supplied.</p>
        </section>
        <section className="panel stack" aria-label="Ablations">
          <h3>What each safeguard contributes</h3>
          <div className="tablewrap">
            <table>
              <thead><tr><th>Variant</th><th className="num">Critical recall</th><th className="num">Esc. precision</th><th className="num">Automated</th><th className="num">Net / 1,000</th></tr></thead>
              <tbody>
                {Object.entries(p.ablations).map(([k, v]) => (
                  <tr key={k}><td>{ABL_LABEL[k] ?? human(k)}</td><td className="num">{pct(v.critical_recall)}</td><td className="num">{pct(v.escalation_precision)}</td>
                    <td className="num">{pct(v.automated_coverage)}</td><td className="num">{usd(v.net_usd_per_1000 as number)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="panel stack" aria-label="Components">
        <h3>Component checks on {p.name}'s held-out set</h3>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Component</th><th>Result</th></tr></thead>
            <tbody>
              <tr><td>Safety rules (hand-written)</td><td>caught {p.components.hard_rules.caught} of {p.components.hard_rules.critical_n} critical tickets ({pct(p.components.hard_rules.recall)}), {p.components.hard_rules.false_positives} false alarms</td></tr>
              <tr><td>Prompt-injection detector</td><td>flagged {p.components.injection.detected} of {p.components.injection.n_injection} injected tickets, {p.components.injection.false_positives} false alarms</td></tr>
              <tr><td>Multi-request detector</td><td>flagged {p.components.multi_request.detected} of {p.components.multi_request.n_multi} two-request tickets ({pct(p.components.multi_request.recall)}), false-alarm rate {pct(p.components.multi_request.fp_rate)}</td></tr>
              <tr><td>Language identification</td><td>{pct(p.components.language_id_accuracy)} accurate across English, Polish, German, Spanish</td></tr>
              <tr><td>Retrieval (English tickets)</td><td>right article first {pct(p.retrieval.hybrid.recall_at_1)}, in top 3 {pct(p.retrieval.hybrid.recall_at_3)} (keyword-only BM25: {pct(p.retrieval.bm25.recall_at_3)})</td></tr>
              <tr><td>Paraphrase stability</td><td>same action for all {p.robustness.paraphrase.variants_per_group} phrasings of the same case in {pct(p.robustness.paraphrase.all_same_action)} of {p.robustness.paraphrase.groups} cases</td></tr>
              <tr><td>Latency (2 vCPU, no GPU)</td><td>{p.holdout_metrics.latency_ms ? `${p.holdout_metrics.latency_ms.p50} ms median, ${p.holdout_metrics.latency_ms.p95} ms p95 per ticket (batched)` : "n/a"}</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
