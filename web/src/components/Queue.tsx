import React, { useEffect, useState } from "react";
import { MODE, addLocalReview, clearLocalReviews, localReviews, queueLive, replay, reviewLive } from "../data";
import { ACTION_LABEL, family, human, pct } from "../format";
import type { Decision, PolicyName, Review } from "../types";
import { PolicyToggle } from "./Triage";

interface Item { id: string; ticketText?: string; decision: Decision }

export default function Queue({ policy, setPolicy, onReview }: { policy: PolicyName; setPolicy: (p: PolicyName) => void; onReview: (r: Review) => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const [reviews, setReviews] = useState<Review[]>(localReviews());
  const [reviewer, setReviewer] = useState("Victoria (demo reviewer)");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (MODE === "live") {
      queueLive().then((q) => setItems(q.map((x) => ({ id: x.id, decision: x.decision })))).catch((e) => setErr(String(e)));
    } else {
      setItems(replay.tickets.filter((t) => !t.decisions[policy].automated)
        .map((t) => ({ id: `${t.id}:${policy}`, ticketText: t.text, decision: t.decisions[policy] }))
        .sort((a, b) => (a.decision.action === "ESCALATE" ? 0 : 1) - (b.decision.action === "ESCALATE" ? 0 : 1)));
    }
  }, [policy]);

  const submit = async (it: Item, verdict: Review["verdict"]) => {
    const r: Review = { decision_id: it.id, reviewer, verdict, final_text: verdict === "edit" ? draft : undefined, ts: Date.now() };
    if (verdict === "edit" && !draft.trim()) { setErr("Write the edited reply before saving."); return; }
    setErr(null);
    try {
      if (MODE === "live") await reviewLive(r);
      else addLocalReview(r);
      setReviews(MODE === "live" ? [...reviews, r] : localReviews());
      onReview(r);
      setEditing(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const reviewed = (id: string) => reviews.find((r) => r.decision_id === id);
  const open = items.filter((i) => !reviewed(i.id));
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6, maxWidth: "62ch" }}>
          <h2>Review queue</h2>
          <p className="ink2">Everything the system does not automate lands here with its draft and evidence. Escalations sort first. A person approves, edits or rejects; nothing reaches a customer record without that step.</p>
        </div>
        <PolicyToggle policy={policy} setPolicy={setPolicy} />
      </div>
      <div className="row">
        <label className="small ink2" htmlFor="reviewer">Reviewer</label>
        <input id="reviewer" className="btn" style={{ minWidth: 0, width: 240 }} value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
        <span className="small muted">{open.length} open · {items.length - open.length} reviewed</span>
        {MODE === "replay" && reviews.length > 0 && (
          <button className="btn" onClick={() => { clearLocalReviews(); setReviews([]); }}>Reset demo reviews</button>
        )}
        {err && <span className="small" style={{ color: "var(--escalate)" }}>{err}</span>}
      </div>
      <div className="stack">
        {items.map((it) => {
          const d = it.decision, done = reviewed(it.id), fam = family(d.action);
          return (
            <article key={it.id} className="panel stack" style={{ gap: 10, opacity: done ? 0.7 : 1 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div className="row" style={{ gap: 8 }}>
                  <span className={`chip fam-${fam}`}>{ACTION_LABEL[d.action]}</span>
                  <b>{human(d.intent)}</b>
                  <span className="small muted">{human(d.queue)} · {d.priority} · confidence {pct(d.confidence, 0)}</span>
                </div>
                <span className="mono small muted">{it.id.split(":")[0]}</span>
              </div>
              <p className="small ink2">{d.reasons[0]}</p>
              {d.redacted_text && <div className="slip" style={{ fontSize: "0.78rem" }}>{d.redacted_text}</div>}
              {editing === it.id ? (
                <div className="stack">
                  <textarea id={`edit-${it.id}`} className="slip" value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Edited reply" />
                  <div className="row">
                    <button className="btn primary" onClick={() => submit(it, "edit")}>Save edited reply</button>
                    <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
                  </div>
                </div>
              ) : done ? (
                <p className="small"><span className={`chip ${done.verdict === "reject" ? "fail" : "pass"}`}>{done.verdict}</span> by {done.reviewer}</p>
              ) : (
                <div className="row">
                  <button className="btn primary" onClick={() => submit(it, "approve")}>Approve draft</button>
                  <button className="btn" onClick={() => { setEditing(it.id); setDraft(d.draft?.text ?? ""); }}>Edit</button>
                  <button className="btn" onClick={() => submit(it, "reject")}>Reject</button>
                </div>
              )}
            </article>
          );
        })}
        {items.length === 0 && <p className="muted">Nothing waiting. Triage a ticket that needs a person and it will appear here.</p>}
      </div>
    </div>
  );
}
