import React, { useEffect, useState } from "react";
import { MODE, auditLive } from "../data";
import { ACTION_LABEL, human, pct } from "../format";
import type { AuditEntry } from "../types";

export default function Audit({ local }: { local: AuditEntry[] }) {
  const [rows, setRows] = useState<AuditEntry[]>(local);
  useEffect(() => {
    if (MODE === "live") auditLive().then(setRows).catch(() => setRows([]));
    else setRows(local);
  }, [local]);
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="stack" style={{ gap: 6, maxWidth: "70ch" }}>
        <h2>Audit log</h2>
        <p className="ink2">
          Every decision is logged with the model version, policy version, confidence and the reasons the policy gave. Reviews are separate
          rows that point to a decision; in the API's SQLite log, triggers block any update or delete, so the record is append-only.
          {MODE === "replay" && " In this hosted version the log holds what you did in this browser session."}
        </p>
      </div>
      <div className="panel tablewrap">
        <table>
          <thead>
            <tr><th>Time</th><th>Decision</th><th>Intent</th><th className="num">Confidence</th><th>First reason</th><th>Versions</th><th>Review</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="num mono small">{new Date(r.ts * 1000).toLocaleTimeString()}</td>
                <td>{ACTION_LABEL[r.action]}</td>
                <td>{human(r.intent)}</td>
                <td className="num">{pct(r.confidence, 0)}</td>
                <td className="small ink2" style={{ minWidth: 220 }}>{r.reasons[0]}</td>
                <td className="mono small muted">{r.model_version}<br />{r.policy_version}</td>
                <td>{r.review ? <span className={`chip ${r.review.verdict === "reject" ? "fail" : "pass"}`}>{r.review.verdict}</span> : <span className="muted small">none</span>}</td>
              </tr>
            ))}
            {rows.length === 0 && (<tr><td colSpan={7} className="muted">No decisions yet. Open a ticket in the triage console and it is logged here.</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
