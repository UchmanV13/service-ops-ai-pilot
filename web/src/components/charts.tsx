import React, { useState } from "react";

export interface Pt { x: number; y: number; tip?: string }
export interface Series { name: string; color: string; points: Pt[]; markers?: boolean }
interface Ref { y?: number; x?: number; label: string }

const M = { l: 52, r: 20, t: 14, b: 40 };

function ticks(lo: number, hi: number, n = 5) {
  const step = (hi - lo) / n;
  const mag = Math.pow(10, Math.floor(Math.log10(step)));
  const nice = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step) ?? step;
  const out: number[] = [];
  for (let v = Math.ceil(lo / nice) * nice; v <= hi + 1e-9; v += nice) out.push(+v.toFixed(6));
  return out;
}

export function LineChart(props: {
  series: Series[]; xDomain: [number, number]; yDomain: [number, number]; xLabel: string; yLabel: string;
  xFmt?: (v: number) => string; yFmt?: (v: number) => string; refs?: Ref[]; marker?: { x: number; y: number; label: string; color: string };
  ariaLabel: string; width?: number;
}) {
  const { series, xDomain, yDomain, xFmt = String, yFmt = String } = props;
  const W = props.width ?? 640, H = Math.round(W * 0.47);
  const [hover, setHover] = useState<{ px: number; py: number; text: string } | null>(null);
  const sx = (v: number) => M.l + ((v - xDomain[0]) / (xDomain[1] - xDomain[0])) * (W - M.l - M.r);
  const sy = (v: number) => H - M.b - ((v - yDomain[0]) / (yDomain[1] - yDomain[0])) * (H - M.t - M.b);
  const all = series.flatMap((s) => s.points.map((p) => ({ ...p, s })));
  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const mx = ((e.clientX - box.left) / box.width) * W;
    const my = ((e.clientY - box.top) / box.height) * H;
    let best = all[0], bd = Infinity;
    for (const p of all) {
      const d = (sx(p.x) - mx) ** 2 + (sy(p.y) - my) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
    if (!best) return;
    setHover({ px: (sx(best.x) / W) * 100, py: (sy(best.y) / H) * 100,
      text: best.tip ?? `${best.s.name}: ${xFmt(best.x)}, ${yFmt(best.y)}` });
  };
  return (
    <div className="chartbox">
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={props.ariaLabel}>
        {ticks(yDomain[0], yDomain[1]).map((t) => (
          <g key={`y${t}`}>
            <line className="grid" x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} />
            <text x={M.l - 8} y={sy(t) + 4} textAnchor="end">{yFmt(t)}</text>
          </g>
        ))}
        {ticks(xDomain[0], xDomain[1], 6).map((t) => (
          <text key={`x${t}`} x={sx(t)} y={H - M.b + 16} textAnchor="middle">{xFmt(t)}</text>
        ))}
        <line className="axis" x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} />
        <text x={(M.l + W - M.r) / 2} y={H - 6} textAnchor="middle">{props.xLabel}</text>
        <text x={12} y={(M.t + H - M.b) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(M.t + H - M.b) / 2})`}>{props.yLabel}</text>
        {(props.refs ?? []).map((r, i) =>
          r.y !== undefined ? (
            <g key={i}>
              <line x1={M.l} x2={W - M.r} y1={sy(r.y)} y2={sy(r.y)} stroke="var(--muted)" strokeWidth={1} />
              <text x={W - M.r} y={sy(r.y) - 5} textAnchor="end">{r.label}</text>
            </g>
          ) : (
            <g key={i}>
              <line x1={sx(r.x!)} x2={sx(r.x!)} y1={M.t} y2={H - M.b} stroke="var(--muted)" strokeWidth={1} />
              <text x={sx(r.x!) + 4} y={M.t + 10}>{r.label}</text>
            </g>
          ),
        )}
        {series.map((s) => (
          <g key={s.name}>
            <polyline fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
              points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")} />
            {s.markers && s.points.map((p, i) => (
              <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={4.5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            ))}
          </g>
        ))}
        {props.marker && (
          <g>
            <circle cx={sx(props.marker.x)} cy={sy(props.marker.y)} r={6} fill={props.marker.color} stroke="var(--surface)" strokeWidth={2} />
            <text x={sx(props.marker.x) + 10} y={sy(props.marker.y) - 8} style={{ fill: "var(--ink)", fontWeight: 600 }}>{props.marker.label}</text>
          </g>
        )}
        <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} fill="transparent" onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
      </svg>
      {hover && <div className="tip" style={{ left: `${hover.px}%`, top: `${hover.py}%` }}>{hover.text}</div>}
    </div>
  );
}

export function DivergingBars(props: { rows: { label: string; value: number }[]; fmt: (v: number) => string; ariaLabel: string; domain: [number, number]; width?: number }) {
  const rowH = 30, lw = 160, w = props.width ?? 640, h = props.rows.length * rowH + 30;
  const [lo, hi] = props.domain;
  const sx = (v: number) => lw + ((v - lo) / (hi - lo)) * (w - lw - 70);
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={props.ariaLabel}>
      {ticks(lo, hi, 4).map((t) => (
        <g key={t}>
          <line className="grid" x1={sx(t)} x2={sx(t)} y1={0} y2={h - 22} />
          <text x={sx(t)} y={h - 6} textAnchor="middle">{props.fmt(t)}</text>
        </g>
      ))}
      <line x1={sx(0)} x2={sx(0)} y1={0} y2={h - 22} stroke="var(--ink-2)" />
      {props.rows.map((r, i) => {
        const y = i * rowH + 6, x0 = sx(Math.min(0, r.value)), x1 = sx(Math.max(0, r.value));
        return (
          <g key={r.label}>
            <title>{`${r.label}: ${props.fmt(r.value)}`}</title>
            <text x={lw - 10} y={y + 13} textAnchor="end">{r.label}</text>
            {Math.abs(r.value) > 0.5 && (
              <rect x={x0} y={y + 2} width={Math.max(2, x1 - x0)} height={16} rx={3}
                fill={r.value >= 0 ? "var(--s1)" : "var(--s2)"} />
            )}
            <text x={r.value >= 0 ? x1 + 6 : x0 - 6} y={y + 14} textAnchor={r.value >= 0 ? "start" : "end"}
              style={{ fill: "var(--ink)" }}>{Math.abs(r.value) > 0.5 ? props.fmt(r.value) : "–"}</text>
          </g>
        );
      })}
    </svg>
  );
}
