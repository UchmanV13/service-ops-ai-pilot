import React, { useMemo, useState } from "react";
import { MODE, replay, triageLive } from "../data";
import { ACTION_LABEL, FAMILY_LABEL, family, human, pct } from "../format";
import type { Decision, Gold, PolicyName, ReplayTicket } from "../types";

export function PolicyToggle({ policy, setPolicy }: { policy: PolicyName; setPolicy: (p: PolicyName) => void }) {
  const pol = replay.policies;
  return (
    <div className="stack" style={{ gap: 6 }}>
      <span className="label">Policy</span>
      <div className="seg" role="group" aria-label="Policy">
        <button aria-pressed={policy === "frozen"} onClick={() => setPolicy("frozen")}>Pilot 2 frozen</button>
        <button aria-pressed={policy === "exploratory"} onClick={() => setPolicy("exploratory")}>Exploratory 0.95</button>
      </div>
      <p className="small muted">
        {policy === "frozen"
          ? `The policy certified by the Pilot 2 protocol: automation threshold ${pol.frozen.auto_threshold > 1 ? "none (automation off)" : pol.frozen.auto_threshold}, critical threshold ${pol.frozen.critical_threshold}.`
          : "Same system with a 0.95 automation threshold. Not certified: shown so you can see what automation would do."}
      </p>
    </div>
  );
}

function Meter({ value, threshold, color, label, thresholdLabel }: { value: number; threshold: number; color: string; label: string; thresholdLabel: string }) {
  return (
    <div className="stack" style={{ gap: 4 }}>
      <div className="row small" style={{ justifyContent: "space-between" }}>
        <span className="ink2">{label}</span>
        <span className="num"><b>{pct(value)}</b> <span className="muted">· {thresholdLabel} {threshold > 1 ? "off" : pct(threshold, 0)}</span></span>
      </div>
      <div className="meter" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={1} aria-label={label}>
        <i style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
        {threshold <= 1 && <b style={{ left: `${threshold * 100}%` }} />}
      </div>
    </div>
  );
}

const OUTCOME_CLASS: Record<string, string> = {
  "correct automation": "pass", "correct escalation": "pass", "sent to a person": "na",
  "could have been automated": "warn", "inappropriate automation": "fail", "wrong automation": "fail", "missed critical": "fail", "false escalation": "warn",
};

export function DecisionCard({ d, gold, policyName }: { d: Decision; gold?: Gold; policyName: PolicyName }) {
  const fam = family(d.action);
  const pol = replay.policies[policyName];
  return (
    <div className="stack fade" style={{ gap: 18 }}>
      <div className="row" style={{ alignItems: "stretch" }}>
        <div className={`stamp fam-${fam}`}>
          <small>{FAMILY_LABEL[fam]}</small>
          {ACTION_LABEL[d.action]}
        </div>
        <dl className="kv" style={{ alignSelf: "center" }}>
          <dt>Intent</dt><dd><b>{human(d.intent)}</b></dd>
          <dt>Queue</dt><dd>{human(d.queue)} · {d.priority}</dd>
          <dt>Language</dt><dd>{d.language}</dd>
        </dl>
        {gold && d.outcome && (
          <div className="stack" style={{ gap: 4, marginLeft: "auto", alignSelf: "center" }}>
            <span className="label">Against the labeling guide</span>
            <span className={`chip ${OUTCOME_CLASS[d.outcome] ?? "neutral"}`}>{d.outcome}</span>
            <span className="small muted">gold: {human(gold.intent)} → {ACTION_LABEL[gold.action]}</span>
          </div>
        )}
      </div>

      <div className="grid2">
        <Meter value={d.confidence} threshold={pol.auto_threshold} color="var(--s1)" label="Intent confidence (calibrated)" thresholdLabel="automate at" />
        <Meter value={d.critical_score} threshold={pol.critical_threshold} color="var(--escalate)" label="Critical score" thresholdLabel="escalate at" />
      </div>

      <div className="grid2">
        <div className="stack">
          <span className="label">Why this decision</span>
          <ol className="steps">
            {d.reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ol>
          <span className="label" style={{ marginTop: 6 }}>Model's top intents</span>
          <dl className="kv">
            {d.top3.map(([n, p]) => (<React.Fragment key={n}><dt className="num">{pct(p)}</dt><dd>{human(n)}</dd></React.Fragment>))}
          </dl>
        </div>
        <div className="stack">
          <span className="label">Evidence</span>
          <dl className="kv">
            <dt>Identifiers</dt><dd className="mono">{Object.entries(d.fields).map(([k, v]) => `${human(k)}: ${v}`).join(" · ") || "none found"}</dd>
            {d.missing_fields.length > 0 && (<><dt>Missing</dt><dd>{d.missing_fields.map(human).join(", ")}</dd></>)}
            <dt>PII redacted</dt><dd>{d.pii_redacted.length ? d.pii_redacted.join(", ") : "none"}</dd>
            {d.injection.length > 0 && (<><dt>Injection</dt><dd className="mono">“{d.injection[0]}”</dd></>)}
            {d.guard_hits.length > 0 && (<><dt>Safety rule</dt><dd>{human(d.guard_hits[0][0])}: “{d.guard_hits[0][1]}”</dd></>)}
          </dl>
          <span className="label" style={{ marginTop: 6 }}>Knowledge base (hybrid retrieval)</span>
          <dl className="kv">
            {d.retrieval.map((r) => (<React.Fragment key={r.id}><dt className="mono">{r.id}</dt><dd>{r.title} <span className="muted num">({r.score.toFixed(2)})</span></dd></React.Fragment>))}
          </dl>
        </div>
      </div>

      {d.draft && (
        <div className="stack" style={{ gap: 6 }}>
          <span className="label">{d.automated ? "Reply sent automatically" : "Draft for the person handling it"}</span>
          <div className="slip">{d.draft.text}</div>
          {d.draft.citations.length > 0 && <span className="small muted">Cites {d.draft.citations.join(", ")}. Lookups and links use sandbox data.</span>}
        </div>
      )}
      <p className="small muted mono">model {d.model_version} · policy {d.policy_version}{d.latency_ms !== undefined ? ` · ${d.latency_ms.toFixed(1)} ms` : ""}</p>
    </div>
  );
}

export default function Triage({ policy, setPolicy, onDecision }: {
  policy: PolicyName; setPolicy: (p: PolicyName) => void; onDecision: (d: Decision, ref: string) => void;
}) {
  const [selected, setSelected] = useState<string>(replay.tickets[0].id);
  const [text, setText] = useState("");
  const [live, setLive] = useState<Decision | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const groups = useMemo(() => {
    const m = new Map<string, ReplayTicket[]>();
    replay.tickets.forEach((t) => m.set(t.label, [...(m.get(t.label) ?? []), t]));
    return [...m.entries()];
  }, []);
  const ticket = replay.tickets.find((t) => t.id === selected)!;

  const choose = (t: ReplayTicket) => {
    setSelected(t.id);
    setLive(null);
    setText(t.text);
    onDecision(t.decisions[policy], t.id);
  };

  const runLive = async () => {
    setBusy(true);
    setErr(null);
    try {
      const d = await triageLive(text, policy);
      setLive(d);
      onDecision(d, "typed");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const decision = live ?? ticket.decisions[policy];
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6, maxWidth: "62ch" }}>
          <h2>Triage console</h2>
          <p className="ink2">
            {MODE === "live"
              ? "Pick a held-out ticket or type your own; the running pipeline triages it and writes the decision to the audit log."
              : "Pick a held-out ticket to see the real pipeline's decision. This hosted version replays decisions computed by the Python pipeline; run the repo locally to triage text you type."}
          </p>
        </div>
        <PolicyToggle policy={policy} setPolicy={(p) => { setPolicy(p); setLive(null); onDecision(ticket.decisions[p], ticket.id); }} />
      </div>
      <div className="triage">
        <nav className="samples" aria-label="Sample tickets">
          {groups.map(([label, ts]) => (
            <div key={label} className="stack" style={{ gap: 6 }}>
              <h4>{label}</h4>
              {ts.map((t) => {
                const d = t.decisions[policy];
                return (
                  <button key={t.id} className="sample" aria-pressed={t.id === selected && !live} onClick={() => choose(t)}>
                    <span className="row small" style={{ gap: 8 }}>
                      <span className={`chip fam-${family(d.action)}`}>{FAMILY_LABEL[family(d.action)]}</span>
                      <span className="mono muted">{t.id}</span>
                    </span>
                    <span className="snip">{t.text.replace(/\n/g, " ")}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <section className="panel stack" style={{ gap: 18 }} aria-label="Decision">
          <div className="stack" style={{ gap: 6 }}>
            <span className="label">Ticket {live ? "(typed)" : ticket.id}</span>
            {MODE === "live" ? (
              <>
                <textarea id="ticket-text" className="slip" value={text || ticket.text} onChange={(e) => setText(e.target.value)} aria-label="Ticket text" />
                <div className="row">
                  <button className="btn primary" onClick={runLive} disabled={busy || !(text || ticket.text).trim()}>{busy ? "Triaging…" : "Triage this text"}</button>
                  {err && <span className="small" style={{ color: "var(--escalate)" }}>{err}</span>}
                </div>
              </>
            ) : (
              <div className="slip">{ticket.text}</div>
            )}
          </div>
          <DecisionCard d={decision} gold={live ? undefined : ticket.gold} policyName={policy} />
        </section>
      </div>
    </div>
  );
}
