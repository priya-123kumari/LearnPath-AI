import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { CircleAlert, CircleCheck, CircleDot, CircleX, LoaderCircle, TriangleAlert, X } from "lucide-react";

export const ENTITY = /^(LRN-\d{6}|CRS-\d{6}|SKL-\d{6}|CNT-\d{6}|SPR-\d{6}|CSK-\d{6}|ATT-LRN-\d{6}-\d{6}|PATH-2026-\d{6}|ASR-\d{8}|PEV-\d{8}|REC-\d{8})$/;
export const fmt = (v) => (v === null || v === undefined || v === "" ? "-" : typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : String(+v.toFixed(4))) : String(v));
export const compact = (v) => (v >= 1e6 ? `${+(v / 1e6).toFixed(1)}M` : v >= 1e4 ? `${+(v / 1e3).toFixed(1)}K` : fmt(v));
export const pct = (v, d = 1) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(d)}%`);
export const day = (s) => (s ? String(s).replace("T", " ").replace(":00Z", "").replace("Z", "") : "-");
export const humanize = (s) => {
  const t = String(s ?? "").replace(/_/g, " ").toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

// ------------------------------------------------------------------ status pills (icon + label, never colour alone)
const TONES = {
  good: { box: "bg-good-soft text-good ring-good/25", icon: CircleCheck },
  warn: { box: "bg-warn-soft text-warn ring-warn/25", icon: CircleAlert },
  bad: { box: "bg-bad-soft text-bad ring-bad/25", icon: CircleX },
  info: { box: "bg-accent-soft text-accent ring-accent/25", icon: CircleDot },
  neutral: { box: "bg-raised text-ink-2 ring-line-strong", icon: CircleDot },
};
const STATUS_TONE = {
  PASS: "good", ACTIVE: "good", COMPLETED: "good", COMPLETED_PASS: "good", ACCEPTED: "good", MASTERED: "good", PUBLISHED: "good", REPRODUCIBLE: "good",
  PROFICIENT: "info", IN_PROGRESS: "info", ISSUED: "info", PENDING: "info", UNLOCKED: "info", COMPLETED_UNSCORED: "info",
  STALLED: "warn", DEVELOPING: "warn", EXPIRED: "warn", NOT_ATTEMPTED: "warn", ABANDONED: "warn", RETIRED: "warn", LOCKED: "warn",
  FAIL: "bad", COMPLETED_FAIL: "bad", ESCALATED: "bad", WITHDRAWN: "bad", DRAFT: "neutral",
};

export function Pill({ value, tone }) {
  const t = TONES[tone ?? STATUS_TONE[value] ?? "neutral"];
  return <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ring-1 ring-inset ${t.box}`}><t.icon size={11} aria-hidden="true" />{humanize(value)}</span>;
}

// ------------------------------------------------------------------ layout primitives
export const Card = ({ title, sub, action, className = "", children, flush, eyebrow }) => (
  <section className={`glass glass-hover min-w-0 rounded-2xl ${className}`}>
    {(title || action) && (
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="min-w-0">
          {eyebrow && <p className="eyebrow mb-0.5">{eyebrow}</p>}
          <h2 className="text-[14.5px] font-semibold tracking-tight">{title}</h2>
          {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
        </div>
        {action}
      </header>
    )}
    <div className={flush ? "" : "p-5"}>{children}</div>
  </section>
);

/** Stat tile: label · value (proportional figures) · note. Optional sparkline in the de-emphasis hue. */
export function Stat({ label, value, note, tone = "neutral", icon: Icon, trend }) {
  const color = { good: "text-good", bad: "text-bad", warn: "text-warn", info: "text-ink", neutral: "text-ink" }[tone];
  return (
    <div className="glass glass-hover relative min-w-0 overflow-hidden rounded-2xl p-4">
      <span className="neon-line absolute inset-x-0 top-0 h-px opacity-60" />
      <p className="eyebrow flex items-center gap-1.5">{Icon && <Icon size={13} className="text-neon" />}{label}</p>
      <p className={`mt-2 text-[26px] leading-none font-semibold tracking-tight ${color}`}>{value}</p>
      {note && <p className="mt-2 text-xs text-muted">{note}</p>}
      {trend && <Sparkline values={trend} />}
    </div>
  );
}

function Sparkline({ values }) {
  const w = 160, h = 28, max = Math.max(...values, 1), min = Math.min(...values, 0);
  const pts = values.map((v, i) => [(i / Math.max(1, values.length - 1)) * w, h - ((v - min) / (max - min || 1)) * (h - 4) - 2]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 h-7 w-full" preserveAspectRatio="none" aria-hidden="true">
      <path d={d} fill="none" stroke="var(--muted)" strokeOpacity="0.55" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r="3" fill="var(--series)" stroke="var(--surface-solid)" strokeWidth="2" />
    </svg>
  );
}

// ------------------------------------------------------------------ tooltip (values lead, labels follow; React escapes text)
export function useTip() {
  const [tip, setTip] = useState(null);
  const show = (e, rows, title) => {
    const r = e.currentTarget?.getBoundingClientRect?.();
    const x = e.clientX ?? (r ? r.left + r.width / 2 : 0), y = e.clientY ?? (r ? r.top : 0);
    setTip({ x, y, rows, title });
  };
  return [tip, show, () => setTip(null)];
}

export function Tip({ tip }) {
  if (!tip) return null;
  const left = Math.min(tip.x + 14, window.innerWidth - 220), top = Math.max(8, tip.y - 12);
  return (
    <div className="viz-tooltip" style={{ left, top, transform: "translateY(-100%)" }} role="status">
      {tip.title && <p className="eyebrow mb-1">{tip.title}</p>}
      {tip.rows.map(([label, value, color], i) => (
        <p key={i} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted">{color && <span className="h-0.5 w-3 rounded" style={{ background: color }} />}{label}</span>
          <b className="tabular-nums text-ink">{value}</b>
        </p>
      ))}
    </div>
  );
}

function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(600);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const niceMax = (v) => {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v)), n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
};

/** Single-series area chart over time: 2px line, 10% wash, end dot + end label, crosshair tooltip. One y-axis. */
export function AreaChart({ data, x, y, format = compact, height = 220, label, yMax }) {
  const [ref, w] = useWidth();
  const [hover, setHover] = useState(null);
  const pad = { l: 44, r: 56, t: 14, b: 26 };
  const iw = w - pad.l - pad.r, ih = height - pad.t - pad.b;
  const top = yMax ?? niceMax(Math.max(...data.map((d) => d[y] ?? 0)));
  const sx = (i) => pad.l + (data.length < 2 ? iw / 2 : (i / (data.length - 1)) * iw);
  const sy = (v) => pad.t + ih - (v / top) * ih;
  const pts = data.map((d, i) => [sx(i), sy(d[y] ?? 0)]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  const area = `${line}L${pts.at(-1)[0]},${pad.t + ih}L${pts[0][0]},${pad.t + ih}Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  const months = data.map((d, i) => [i, String(d[x]).slice(0, 7)]).filter(([i, m], k, arr) => k === 0 || m !== arr[k - 1][1]);
  const move = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - pad.l) / iw) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, i)));
  };
  const h = hover != null ? data[hover] : null;
  return (
    <div ref={ref} className="relative">
      <svg width={w} height={height} role="img" aria-label={label} onPointerMove={move} onPointerLeave={() => setHover(null)} className="block touch-none">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={pad.l + iw} y1={sy(t)} y2={sy(t)} stroke="var(--line)" strokeWidth="1" />
            <text x={pad.l - 8} y={sy(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--muted)" className="tabular-nums">{format(t)}</text>
          </g>
        ))}
        {months.map(([i, m]) => (
          <text key={m} x={sx(i)} y={height - 8} fontSize="10.5" fill="var(--muted)" textAnchor="start">{new Date(m + "-01T00:00:00Z").toLocaleString("en", { month: "short", timeZone: "UTC" })}</text>
        ))}
        <path d={area} fill="var(--series)" fillOpacity="0.1" />
        <path d={line} fill="none" stroke="var(--series)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" className="draw-line" style={{ "--len": 3000 }} />
        <circle cx={pts.at(-1)[0]} cy={pts.at(-1)[1]} r="4" fill="var(--series)" stroke="var(--surface-solid)" strokeWidth="2" />
        <text x={pts.at(-1)[0] + 8} y={pts.at(-1)[1] + 4} fontSize="11.5" fontWeight="600" fill="var(--ink)">{format(data.at(-1)[y])}</text>
        {h && (
          <g pointerEvents="none">
            <line x1={sx(hover)} x2={sx(hover)} y1={pad.t} y2={pad.t + ih} stroke="var(--line-strong)" strokeWidth="1" />
            <circle cx={sx(hover)} cy={sy(h[y] ?? 0)} r="4.5" fill="var(--series)" stroke="var(--surface-solid)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {h && (
        <div className="viz-tooltip absolute" style={{ position: "absolute", left: Math.min(sx(hover) + 12, w - 170), top: 6 }}>
          <p className="eyebrow mb-1">week of {h[x]}</p>
          <p className="flex items-center justify-between gap-4"><span className="flex items-center gap-1.5 text-muted"><span className="h-0.5 w-3 rounded bg-series" />{label}</span><b className="tabular-nums">{fmt(h[y])}</b></p>
        </div>
      )}
    </div>
  );
}

/** Horizontal bars, one series = one colour. <=24px, 4px rounded data end, value at the tip, per-bar tooltip. */
export function Bars({ data, format = (v) => fmt(v), sort = true, max, label = "value", color = "bg-series" }) {
  const [tip, show, hide] = useTip();
  const entries = Object.entries(data ?? {});
  if (sort) entries.sort((a, b) => b[1] - a[1]);
  const top = Math.max(...entries.map(([, v]) => v), 1);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  return (
    <>
      <ul className="space-y-2.5">
        {entries.slice(0, max).map(([k, v], i) => (
          <li key={k} tabIndex={0} onPointerMove={(e) => show(e, [[label, format(v)], ["share", pct(v / total)]], humanize(k))} onPointerLeave={hide}
            onFocus={(e) => show(e, [[label, format(v)], ["share", pct(v / total)]], humanize(k))} onBlur={hide}
            className="group grid grid-cols-[minmax(0,10.5rem)_1fr] items-center gap-3 rounded-md text-[13px] outline-none">
            <span className="truncate text-ink-2" title={humanize(k)}>{humanize(k)}</span>
            <span className="flex items-center gap-2">
              <span className="relative h-3 flex-1">
                <span className={`grow-x absolute inset-y-0 left-0 rounded-r-[4px] ${color} transition-opacity group-hover:opacity-80`} style={{ width: `${(v / top) * 100}%`, animationDelay: `${i * 40}ms` }} />
              </span>
              <span className="w-14 shrink-0 text-right text-xs font-medium tabular-nums text-ink-2">{format(v)}</span>
            </span>
          </li>
        ))}
      </ul>
      <Tip tip={tip} />
    </>
  );
}

/** Two-series comparison bars (engine vs baseline). Legend always present; values at the tips. */
export function CompareBars({ rows, series, format = (v) => pct(v) }) {
  const [tip, show, hide] = useTip();
  const top = Math.max(...rows.flatMap((r) => series.map((s) => r[s.key] ?? 0)), 0.0001);
  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-4 text-xs text-ink-2">
        {series.map((s) => <span key={s.key} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: s.color }} />{s.label}</span>)}
      </div>
      <ul className="space-y-4">
        {rows.map((r) => (
          <li key={r.label}>
            <p className="mb-1.5 text-[13px] text-ink-2">{r.label}</p>
            <div className="space-y-[2px]">
              {series.map((s) => (
                <div key={s.key} className="flex items-center gap-2" tabIndex={0}
                  onPointerMove={(e) => show(e, series.map((x) => [x.label, format(r[x.key]), x.color]), r.label)} onPointerLeave={hide}
                  onFocus={(e) => show(e, series.map((x) => [x.label, format(r[x.key]), x.color]), r.label)} onBlur={hide}>
                  <span className="relative h-3 flex-1">
                    <span className="grow-x absolute inset-y-0 left-0 rounded-r-[4px]" style={{ width: `${Math.max(0.4, ((r[s.key] ?? 0) / top) * 100)}%`, background: s.color }} />
                  </span>
                  <span className="w-14 shrink-0 text-right text-xs font-medium tabular-nums text-ink-2">{format(r[s.key])}</span>
                </div>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <Tip tip={tip} />
    </div>
  );
}

const STATUS_FILL = { ACTIVE: "var(--st-good)", COMPLETED: "var(--series)", STALLED: "var(--st-warning)", ABANDONED: "var(--st-critical)" };

/** Tall segmented bar: one whole split into parts (path status). Legend lists names; share printed when it fits. */
export function SegmentedBar({ data, order = ["ACTIVE", "COMPLETED", "STALLED", "ABANDONED"], fills = STATUS_FILL }) {
  const [tip, show, hide] = useTip();
  const parts = order.filter((k) => data[k]).map((k) => [k, data[k]]);
  const total = parts.reduce((a, [, v]) => a + v, 0) || 1;
  return (
    <div>
      <div className="flex h-7 gap-[2px]" role="img" aria-label={parts.map(([k, v]) => `${humanize(k)} ${v} (${pct(v / total, 0)})`).join(", ")}>
        {parts.map(([k, v]) => (
          <div key={k} tabIndex={0} className="grow-x flex items-center overflow-hidden rounded-[4px] px-2 text-[11px] font-semibold text-black/80 outline-none hover:brightness-110"
            style={{ width: `${(v / total) * 100}%`, background: fills[k] }}
            onPointerMove={(e) => show(e, [["paths", fmt(v)], ["share", pct(v / total)]], humanize(k))} onPointerLeave={hide}
            onFocus={(e) => show(e, [["paths", fmt(v)], ["share", pct(v / total)]], humanize(k))} onBlur={hide}>
            {v / total > 0.1 ? pct(v / total, 0) : ""}
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2">
        {parts.map(([k, v]) => <span key={k} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: fills[k] }} />{humanize(k)} <b className="tabular-nums text-ink">{fmt(v)}</b></span>)}
      </div>
      <Tip tip={tip} />
    </div>
  );
}

/** Meter: fill on a lighter track of the same ramp. */
export function Meter({ value, label, note }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[13px]"><span className="text-ink-2">{label}</span><b className="tabular-nums">{pct(value)}</b></div>
      <div className="h-2 rounded-full bg-track"><div className="grow-x h-full rounded-full bg-series" style={{ width: `${Math.min(100, value * 100)}%` }} /></div>
      {note && <p className="mt-1 text-[11px] text-muted">{note}</p>}
    </div>
  );
}

/** Circular gauge for a single headline ratio (chrome-level figure, label inside). */
export function Ring({ value, size = 92, label, display }) {
  const r = (size - 10) / 2, c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${display ?? pct(value)}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--track)" strokeWidth="6" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--series)" strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${c * value} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="52%" textAnchor="middle" dominantBaseline="middle" fontSize="17" fontWeight="600" fill="var(--ink)">{display ?? pct(value, 0)}</text>
    </svg>
  );
}

export function Progress({ value, tone = "bg-series" }) {
  return <span className="block h-1.5 w-full rounded-full bg-track"><span className={`grow-x block h-full rounded-full ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></span>;
}

// ------------------------------------------------------------------ IDs, cells, tables
export function IdLink({ id, onOpen }) {
  if (!id || !ENTITY.test(String(id)) || !onOpen) return <span className="font-mono text-[12px] whitespace-nowrap">{fmt(id)}</span>;
  return <button onClick={() => onOpen(String(id))} className="font-mono text-[12px] whitespace-nowrap text-accent decoration-accent/40 underline-offset-2 hover:underline">{id}</button>;
}

export function Cell({ col, value, onOpen }) {
  if (value === null || value === undefined || value === "") return <span className="text-muted">-</span>;
  if (typeof value === "string" && ENTITY.test(value)) return <IdLink id={value} onOpen={onOpen} />;
  if (/(^|_)(status|outcome|level|state)$/.test(col) && typeof value === "string") return <Pill value={value} />;
  if (/_at$/.test(col)) return <span className="font-mono text-[12px] whitespace-nowrap text-ink-2">{day(value)}</span>;
  if (typeof value === "object") return <code className="text-xs">{JSON.stringify(value)}</code>;
  return <span className="tabular-nums">{fmt(value)}</span>;
}

export function Table({ rows, cols, onOpen, empty = "No rows", render = {}, max }) {
  if (!rows?.length) return <p className="px-5 py-6 text-sm text-muted">{empty}</p>;
  const list = max ? rows.slice(0, max) : rows;
  const columns = cols ?? Object.keys(rows[0]);
  return (
    <div className="@container overflow-x-auto">
      <table className="stack-table w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left">
            {columns.map((c) => <th key={c} className="eyebrow px-3 py-2.5 font-medium whitespace-nowrap first:pl-5 last:pr-5">{humanize(c)}</th>)}
          </tr>
        </thead>
        <tbody>
          {list.map((r, i) => (
            <tr key={i} className="border-b border-line transition-colors last:border-0 hover:bg-accent-soft">
              {columns.map((c) => (
                <td key={c} data-label={humanize(c)} className="max-w-[28rem] px-3 py-2 align-top first:pl-5 last:pr-5">
                  {render[c] ? render[c](r[c], r) : <Cell col={c} value={r[c]} onOpen={onOpen} />}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const Loading = ({ label = "Loading..." }) => <p className="flex items-center gap-2 p-6 font-mono text-xs text-muted"><LoaderCircle className="animate-spin text-neon" size={15} />{label}</p>;

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div className="rounded-xl border border-bad/30 bg-bad-soft p-4 text-sm text-bad">
      <p className="flex items-center gap-2 font-semibold"><TriangleAlert size={16} />{error.code ?? "Error"}</p>
      <p className="mt-1 break-words">{error.message}</p>
    </div>
  );
}

export function Modal({ title, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <aside ref={ref} tabIndex={-1} role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}
        className="drawer-in glass flex h-full w-full max-w-2xl flex-col overflow-hidden rounded-none border-y-0 border-r-0 !bg-surface-solid outline-none">
        <span className="neon-line h-px w-full" />
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div><p className="eyebrow">record trail</p><h2 className="truncate font-mono text-[14px] font-semibold">{title}</h2></div>
          <button onClick={onClose} aria-label="Close" className="grid size-8 place-items-center rounded-lg text-ink-2 hover:bg-raised"><X size={17} /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  );
}

export const Field = ({ label, children }) => (
  <label className="flex min-w-0 flex-col gap-1"><span className="eyebrow">{label}</span>{children}</label>
);
export const inputCls = "h-9 rounded-lg border border-line bg-raised px-3 text-[13px] text-ink placeholder:text-muted focus:border-neon/50";
export const btnCls = "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-3.5 text-[13px] font-semibold transition-all disabled:opacity-50";
export const btnPrimary = `${btnCls} bg-gradient-to-r from-cyan-500 to-sky-600 text-white shadow-[0_0_18px_-4px_var(--glow)] hover:brightness-110`;
export const btnGhost = `${btnCls} border border-line bg-raised text-ink-2 hover:border-neon/40 hover:text-ink`;

