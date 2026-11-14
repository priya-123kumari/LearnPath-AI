import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Play, Save, Send, Sparkles, TriangleAlert, UserRound } from "lucide-react";
import { api, useApi } from "../api.js";
import { Card, ErrorBox, Field, IdLink, Loading, Pill, Progress, Table, btnGhost, btnPrimary, day, fmt, humanize, inputCls, pct } from "../ui.jsx";

const PAGE = 25;
const isoNow = (minutesAgo = 0) => new Date(Date.now() - minutesAgo * 60000).toISOString().slice(0, 19) + "Z";

function LearnerList({ selected, onSelect }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const { data, error, loading } = useApi(`/learners?q=${encodeURIComponent(q)}&status=${status}&limit=${PAGE}&offset=${page * PAGE}`);
  useEffect(() => setPage(0), [q, status]);
  return (
    <Card title="Learners" sub={data ? `${fmt(data.total)} found` : " "} flush className="xl:sticky xl:top-24">
      <div className="flex gap-2 border-b border-line p-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search id, name, e-mail" className={`${inputCls} min-w-0 flex-1`} aria-label="Search learners" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls} aria-label="Status">
          <option value="">All</option><option value="ACTIVE">Active</option><option value="WITHDRAWN">Withdrawn</option>
        </select>
      </div>
      {error && <div className="p-3"><ErrorBox error={error} /></div>}
      {loading && !data ? <Loading /> : (
        <ul className="max-h-[60vh] overflow-y-auto">
          {data?.items.map((l) => (
            <li key={l.learner_id}>
              <button onClick={() => onSelect(l.learner_id)} aria-current={selected === l.learner_id}
                className={`flex w-full items-center justify-between gap-3 border-b border-line px-4 py-2.5 text-left hover:bg-raised ${selected === l.learner_id ? "bg-accent-soft" : ""}`}>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium">{l.display_name}</span>
                  <span className="font-mono text-[11.5px] text-muted">{l.learner_id} · {humanize(l.prior_level)}</span>
                </span>
                <span className="shrink-0 text-right text-xs text-muted">{l.attempts === 0 ? <Pill value="COLD_START" tone="info" /> : `${l.attempts} attempts`}
                  {l.status === "WITHDRAWN" && <span className="mt-0.5 block"><Pill value="WITHDRAWN" /></span>}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center justify-between p-2">
        <button className={btnGhost} disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft size={15} /></button>
        <span className="text-xs text-muted">page {page + 1} of {data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1}</span>
        <button className={btnGhost} disabled={!data || (page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight size={15} /></button>
      </div>
    </Card>
  );
}

function LiveRecommendations({ id, onOpen, onPick, refreshKey, onSaved }) {
  const [asOf, setAsOf] = useState("");
  const [state, setState] = useState({});
  const run = async (persist) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const qs = `?k=3${asOf ? `&as_of=${encodeURIComponent(asOf)}` : ""}`;
      const data = await api(`/learners/${id}/recommendations${qs}`, persist ? { method: "POST" } : {});
      setState({ data });
      if (persist) onSaved();
    } catch (error) { setState({ error }); }
  };
  useEffect(() => { run(false); /* eslint-disable-next-line */ }, [id, refreshKey]);
  const d = state.data;
  return (
    <Card title="Live recommendations" sub="The backend engine ranks eligible items now, from this learner's evidence only"
      action={
        <div className="flex flex-wrap items-end gap-2">
          <Field label="As of (blank = dataset as-of)"><input value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="2026-09-01T00:00:00Z" className={`${inputCls} w-52`} /></Field>
          <button className={btnGhost} onClick={() => run(false)}><Play size={14} />Run engine</button>
          <button className={btnPrimary} onClick={() => run(true)} title="Append these recommendations and a STEP_ASSIGNED path event"><Save size={14} />Save</button>
        </div>
      }>
      {state.loading && <Loading label="Running engine..." />}
      <ErrorBox error={state.error} />
      {d && (
        <div className="space-y-4">
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
            As of {day(d.as_of)} · {d.evidence_rows} evidence rows · paths {d.open_paths.map((p) => <IdLink key={p.path_id} id={p.path_id} onOpen={onOpen} />)}
            {d.cold_start && <Pill value="COLD_START" tone="info" />}{d.persisted && <Pill value={`saved ${d.persisted_ids.join(", ")}`} tone="good" />}
          </p>
          {d.escalated && <div className="rounded-xl border border-bad/30 bg-bad-soft p-3 text-sm text-bad"><TriangleAlert size={15} className="mr-1 inline" />Escalated to an instructor: {d.recommendations[0].rationale}</div>}
          <ol className="grid gap-3 lg:grid-cols-3">
            {d.recommendations.filter((r) => r.content_id).map((r) => (
              <li key={r.content_id} className="flex flex-col rounded-xl border border-line bg-raised p-4">
                <div className="flex items-start justify-between gap-2">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-white">{r.rank}</span>
                  <Pill value={r.reason_code} tone="info" />
                </div>
                <p className="mt-2 text-[13.5px] font-semibold">{r.content_title}</p>
                <p className="mt-0.5 text-xs text-muted">{humanize(r.format)} · difficulty {r.difficulty} (target {r.target_difficulty}) · score {fmt(r.score)}</p>
                <p className="mt-2 flex-1 text-xs text-ink-2">{r.rationale}</p>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <IdLink id={r.content_id} onOpen={onOpen} />
                  <button className="text-xs font-semibold text-accent hover:underline" onClick={() => onPick(r)}>Record attempt</button>
                </div>
              </li>
            ))}
          </ol>
          <div>
            <p className="mb-2 text-xs font-medium text-muted">Items excluded by the eligibility rules</p>
            <div className="flex flex-wrap gap-2">{Object.entries(d.excluded_counts).map(([k, v]) => <Pill key={k} value={`${k}: ${v}`} tone={k === "PREREQ_NOT_MET" ? "warn" : "neutral"} />)}</div>
            {d.exclusions_sample?.PREREQ_NOT_MET && (
              <details className="mt-2 text-xs"><summary className="cursor-pointer text-accent">Why are items locked?</summary>
                <Table rows={d.exclusions_sample.PREREQ_NOT_MET} cols={["content_id", "skill_id", "detail"]} onOpen={onOpen} /></details>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

function RecordAttempt({ learnerId, pick, onDone, onOpen }) {
  const [form, setForm] = useState({ content_id: "", raw_score: "", status: "COMPLETED", started_at: isoNow(15), submitted_at: isoNow(0), recommendation_id: "" });
  const [state, setState] = useState({});
  useEffect(() => {
    if (pick) setForm((f) => ({ ...f, content_id: pick.content_id, recommendation_id: pick.recommendation_id ?? "", started_at: isoNow(15), submitted_at: isoNow(0) }));
  }, [pick]);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setState({ loading: true });
    try {
      const body = { ...form, learner_id: learnerId, raw_score: form.raw_score === "" ? null : Number(form.raw_score), recommendation_id: form.recommendation_id || null };
      const data = await api("/attempts", { method: "POST", body: JSON.stringify(body) });
      setState({ data }); onDone();
    } catch (error) { setState({ error }); }
  };
  const r = state.data;
  return (
    <Card title="Record an attempt" sub="Append-only write: attempt, mastery evidence and path events. Invalid timestamps are rejected.">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <Field label="Content ID"><input required value={form.content_id} onChange={set("content_id")} placeholder="CNT-000001" className={inputCls} /></Field>
        <Field label="Raw score (assessed items)"><input value={form.raw_score} onChange={set("raw_score")} inputMode="numeric" placeholder="e.g. 16" className={inputCls} /></Field>
        <Field label="Status"><select value={form.status} onChange={set("status")} className={inputCls}><option>COMPLETED</option><option>ABANDONED</option></select></Field>
        <Field label="Started at (UTC)"><input value={form.started_at} onChange={set("started_at")} className={inputCls} /></Field>
        <Field label="Submitted at (UTC)"><input value={form.submitted_at} onChange={set("submitted_at")} className={inputCls} /></Field>
        <div className="flex items-end"><button disabled={state.loading} className={`${btnPrimary} w-full`}><Send size={14} />Submit</button></div>
      </form>
      <div className="mt-3 space-y-3">
        <ErrorBox error={state.error} />
        {r && (
          <div className="rounded-xl border border-good/30 bg-good-soft/50 p-4 text-[13px]">
            <p className="font-semibold text-good">Saved <IdLink id={r.attempt_id} onOpen={onOpen} /> (attempt #{r.attempt_no}) on <IdLink id={r.path_id} onOpen={onOpen} /> · score {fmt(r.score_pct)} · path {humanize(r.path_status)}</p>
            {r.prerequisite_gap.length > 0 && <p className="mt-1 text-warn"><TriangleAlert size={14} className="mr-1 inline" />Prerequisite gap: {r.prerequisite_gap.map((g) => `${g.skill_id} ${g.mastery} < ${g.min_mastery}`).join("; ")}</p>}
            <ul className="mt-2 space-y-1">{r.mastery_changes.map((m) => (
              <li key={m.skill_id}><b>{m.skill_name}</b>: {fmt(m.before)} → {fmt(m.after)} <Pill value={m.level} /></li>
            ))}</ul>
            {r.path_events.length > 0 && <p className="mt-1 text-xs text-muted">New path events: {r.path_events.map((e) => humanize(e.event_type)).join(", ")}</p>}
          </div>
        )}
      </div>
    </Card>
  );
}

function LearnerDetail({ id, onOpen }) {
  const [key, setKey] = useState(0);
  const [pick, setPick] = useState(null);
  const { data, error, loading } = useApi(`/learners/${id}?v=${key}`);
  const repro = useApi(`/learners/${id}/mastery?v=${key}`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const { learner: L, stats, paths } = data;
  return (
    <div className="min-w-0 space-y-4 sm:space-y-6">
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          <span className="grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent"><UserRound size={22} /></span>
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold">{L.display_name} <span className="font-mono text-sm text-muted">{L.learner_id}</span></p>
            <p className="text-xs text-muted">{humanize(L.prior_level)} · {L.country} · cohort {L.cohort} · enrolled {day(L.enrolled_at)}{L.withdrawn_at && ` · withdrawn ${day(L.withdrawn_at)}`}</p>
          </div>
          <Pill value={L.status} />{data.cold_start && <Pill value="COLD_START" tone="info" />}
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[["Attempts", stats.attempts], ["Average score", stats.avg_score ? `${stats.avg_score.toFixed(1)}%` : "-"], ["Pass rate", stats.pass_rate != null ? pct(stats.pass_rate) : "-"], ["Last attempt", day(stats.last_attempt)]].map(([k, v]) => (
            <div key={k} className="rounded-xl bg-raised p-3"><dt className="text-xs text-muted">{k}</dt><dd className="mt-0.5 font-semibold tabular-nums">{fmt(v)}</dd></div>
          ))}
        </dl>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {paths.map((p) => (
            <div key={p.path_id} className="rounded-xl border border-line p-3">
              <div className="flex items-center justify-between gap-2"><span className="text-[13px] font-semibold">{p.course_code} · {p.course_title}</span><Pill value={p.status} /></div>
              <div className="mt-2 flex items-center gap-3"><Progress value={p.progress_pct} /><span className="shrink-0 text-xs tabular-nums text-muted">{p.skills_mastered}/{p.skills_total}</span></div>
              <p className="mt-1.5 text-xs text-muted"><IdLink id={p.path_id} onOpen={onOpen} /> · last activity {day(p.last_activity_at)}</p>
            </div>
          ))}
        </div>
      </Card>
      <LiveRecommendations id={id} onOpen={onOpen} refreshKey={key} onPick={setPick} onSaved={() => setKey((k) => k + 1)} />
      <RecordAttempt learnerId={id} pick={pick} onOpen={onOpen} onDone={() => setKey((k) => k + 1)} />
      <Card title="Skill mastery" flush sub="EWMA of weighted assessment evidence"
        action={repro.data && <Pill value={repro.data.reproducible ? "REPRODUCIBLE" : "MISMATCH"} tone={repro.data.reproducible ? "good" : "bad"} />}>
        <Table rows={data.mastery} cols={["skill_id", "skill_name", "tier", "mastery", "mastery_level", "evidence_count", "last_practiced_at"]} onOpen={onOpen}
          empty="No assessment evidence yet (cold start)" render={{ mastery: (m) => <span className="flex w-36 items-center gap-2"><Progress value={m * 100} tone={m >= 0.8 ? "bg-good" : m >= 0.5 ? "bg-series" : "bg-warn"} /><span className="tabular-nums text-xs">{m.toFixed(2)}</span></span> }} />
      </Card>
      <Card title="Recommendation history and outcomes" flush sub="Latest 90; outcome = first attempt on the item within 14 days">
        <Table rows={data.recommendations} cols={["recommendation_id", "recommended_at", "rank", "content_id", "reason_code", "status", "outcome", "outcome_score_pct"]} onOpen={onOpen}
          render={{ reason_code: (v) => <Pill value={v} tone="info" /> }} />
      </Card>
      <Card title="Recent attempts" flush sub="Latest 100">
        <Table rows={data.recent_attempts} cols={["attempt_id", "content_id", "format", "attempt_no", "started_at", "status", "score_pct", "passed", "recommendation_id"]} onOpen={onOpen} />
      </Card>
    </div>
  );
}

export default function Learners({ onOpen }) {
  const [selected, setSelected] = useState(() => window.location.hash.split("/")[1] || "LRN-000005");
  const select = (id) => { setSelected(id); window.location.hash = `learners/${id}`; };
  return (
    <div className="grid gap-4 sm:gap-6 xl:grid-cols-[22rem_minmax(0,1fr)]">
      <div><LearnerList selected={selected} onSelect={select} /></div>
      {selected ? <LearnerDetail key={selected} id={selected} onOpen={onOpen} /> : <Card><p className="flex items-center gap-2 text-muted"><Sparkles size={16} />Pick a learner</p></Card>}
    </div>
  );
}
