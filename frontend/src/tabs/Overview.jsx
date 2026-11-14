import { Activity, ArrowRight, CheckCircle2, Database, GitBranch, ShieldCheck, Target, Users } from "lucide-react";
import { useApi } from "../api.js";
import { AreaChart, Bars, Card, ErrorBox, Loading, Pill, SegmentedBar, Stat, compact, fmt, pct } from "../ui.jsx";

const FLOW = [
  ["Skill graph", "Effective-dated prerequisites; content mapped to skills + difficulty"],
  ["Attempts", "Scores come from hidden true mastery"],
  ["Mastery", "EWMA evidence per skill, replayable"],
  ["Eligibility", "Published · prerequisites · mastered · loop guard"],
  ["Recommend", "Top-3 with reason code + rationale"],
  ["Outcome", "First attempt within 14 days"],
];

export default function Overview() {
  const { data, error, loading } = useApi("/overview");
  if (loading) return <Loading label="Linking to command center..." />;
  if (error) return <ErrorBox error={error} />;
  const { validation: v, recommendation_quality: rq, mastery_quality: mq, distributions: d, counts, timeline: tl } = data;
  const weeks = tl.filter((w) => w.week >= "2026-01-01");
  return (
    <>
      {/* hero: the one number this dashboard leads with */}
      <section className="glass relative overflow-hidden rounded-3xl p-6 sm:p-8">
        <span className="neon-line absolute inset-x-0 top-0 h-px" />
        <div className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:items-center">
          <div>
            <p className="eyebrow flex items-center gap-2"><GitBranch size={12} className="text-neon" />prerequisite safety · temporal test window</p>
            <p className="mt-3 text-[56px] leading-none font-semibold tracking-tight sm:text-[72px]">{pct(rq.engine.prerequisite_violation_rate)}</p>
            <p className="mt-3 max-w-xl text-[14px] text-ink-2">of the engine's recommendations needed a skill the learner hadn't mastered.
              The popularity baseline gets that wrong <b className="text-ink">{pct(rq.popularity.prerequisite_violation_rate)}</b> of the time.</p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <Pill value={v.status} /><Pill value={`${v.checks_run} checks`} tone="info" /><Pill value={`seed ${data.seed}`} tone="neutral" />
              <span className="font-mono text-[11px] text-muted">{compact(v.total_rows_checked)} rows validated · {v.unexpected_errors} unexpected</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[["Hit rate @3", pct(rq.engine.hit_rate_at_3), `baseline ${pct(rq.popularity.hit_rate_at_3)}`],
              ["Next-item match", pct(rq.engine.next_item_match_rate), `baseline ${pct(rq.popularity.next_item_match_rate)}`],
              ["Mastery → pass AUC", fmt(rq.mastery_at_cutoff_predicts_pass_auc), "test window"],
              ["Mastery vs truth r", fmt(mq.pearson_r), `MAE ${fmt(mq.mean_abs_error)}`]].map(([k, val, n]) => (
              <div key={k} className="rounded-2xl border border-line bg-raised p-4">
                <p className="eyebrow">{k}</p><p className="mt-1.5 text-2xl font-semibold tracking-tight">{val}</p><p className="mt-1 text-[11px] text-muted">{n}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Stat icon={Users} label="Learners" value={compact(d.learners)} note={`${fmt(d.cold_start_learners)} cold start · ${fmt(d.withdrawn_learners)} withdrawn`} trend={weeks.map((w) => w.active_learners)} />
        <Stat icon={Activity} label="Attempts" value={compact(d.attempts)} note={`${pct(d.repeated_attempt_share)} repeats · ${pct(d.abandoned_share)} abandoned`} trend={weeks.map((w) => w.attempts)} />
        <Stat icon={Target} label="Recommendations" value={compact(d.recommendations)} note={`${pct((d.recommendation_status.ACCEPTED ?? 0) / d.recommendations)} accepted within 14 days`} trend={weeks.map((w) => w.recommendations)} />
        <Stat icon={ShieldCheck} label="Pass rate" value={pct(d.pass_rate)} note={`${pct(d.pass_rate_with_prereq_gap)} with a prerequisite gap`} trend={weeks.map((w) => w.pass_rate ?? 0)} />
      </div>

      <div className="grid gap-4 sm:gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card eyebrow="telemetry" title="Weekly attempts" sub="All learners, Monday-start weeks · hover for the exact week">
          <AreaChart data={weeks} x="week" y="attempts" label="attempts" />
        </Card>
        <Card eyebrow="telemetry" title="Weekly pass rate" sub="Share of scored attempts passed (≥ 70%)">
          <AreaChart data={weeks} x="week" y="pass_rate" label="pass rate" yMax={1} format={(t) => pct(t, 0)} />
        </Card>
      </div>

      <Card eyebrow="pipeline" title="End-to-end workflow" sub="Every step writes explicit, append-only records - any decision can be traced back">
        <ol className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {FLOW.map(([t, s], i) => (
            <li key={t} className="relative rounded-xl border border-line bg-raised p-3.5">
              <p className="font-mono text-[10.5px] text-neon">0{i + 1}</p>
              <p className="mt-1 text-[13.5px] font-semibold">{t}</p>
              <p className="mt-1 text-[11.5px] leading-snug text-muted">{s}</p>
              {i < FLOW.length - 1 && <ArrowRight size={14} className="absolute top-1/2 -right-[13px] z-10 hidden -translate-y-1/2 text-neon/70 xl:block" />}
            </li>
          ))}
        </ol>
      </Card>

      <div className="grid gap-4 sm:gap-5 xl:grid-cols-3">
        <Card eyebrow="decisions" title="Why items were recommended" sub="Reason code of every recommendation"><Bars data={d.reason_codes} label="recommendations" format={compact} /></Card>
        <Card eyebrow="outcomes" title="What happened next" sub="Derived from the first attempt within 14 days"><Bars data={d.recommendation_outcomes} label="recommendations" format={compact} /></Card>
        <Card eyebrow="lifecycle" title="Learning path status" sub="Derived from activity, mastery and withdrawal events">
          <SegmentedBar data={d.path_status} />
          <p className="mt-5 eyebrow">attempts by content format</p>
          <div className="mt-3"><Bars data={d.attempt_format_mix} label="attempts" format={compact} /></div>
        </Card>
      </div>

      <div className="grid gap-4 sm:gap-5 xl:grid-cols-3">
        <Card eyebrow="coverage" title="Normal, boundary and exception cases">
          <ul className="space-y-2 text-[13px]">
            {[["Cold-start learners", d.cold_start_learners], ["Low-activity learners (1-5 attempts)", d.low_activity_learners_1_to_5],
              ["Withdrawn learners", d.withdrawn_learners], ["Repeated attempts", pct(d.repeated_attempt_share)],
              ["Attempts with a prerequisite gap", pct(d.prerequisite_gap_attempt_share)], ["Learners on more than one path", d.learners_with_multiple_paths]].map(([k, val]) => (
              <li key={k} className="flex justify-between gap-3 border-b border-line pb-1.5 last:border-0"><span className="text-ink-2">{k}</span><b className="font-mono text-[12.5px]">{fmt(val)}</b></li>
            ))}
          </ul>
          <p className="mt-3 rounded-lg bg-accent-soft p-2.5 text-xs text-ink-2">Pass rate with a prerequisite gap <b>{pct(d.pass_rate_with_prereq_gap)}</b> vs <b>{pct(d.pass_rate_without_prereq_gap)}</b> without - the prerequisite rule matters.</p>
        </Card>
        <Card eyebrow="routing" title="Exception queue" sub="Who has to act">
          <ul className="space-y-2 text-[13px]">
            {data.exceptions.map((x) => (
              <li key={x.exception_type} className="flex items-center justify-between gap-3 border-b border-line pb-1.5 last:border-0">
                <span className="min-w-0"><span className="block truncate">{x.exception_type.replace("DATA_QUALITY:", "DQ · ").replace(/_/g, " ").toLowerCase()}</span><span className="font-mono text-[10.5px] text-muted uppercase">{x.owner_role.replace("_", " ")}</span></span>
                <b className="font-mono text-[12.5px]">{fmt(x.n)}</b>
              </li>
            ))}
          </ul>
        </Card>
        <Card eyebrow="storage" title="Database tables" sub={`Dataset ${data.dataset?.data_dir} · as of ${data.as_of.slice(0, 10)}`} flush>
          <div className="grid grid-cols-2 gap-px bg-line">
            {Object.entries(counts).map(([k, n]) => (
              <div key={k} className="bg-surface-solid/60 px-4 py-2.5"><p className="font-mono text-[10.5px] text-muted">{k}</p><p className="text-[15px] font-semibold">{fmt(n)}</p></div>
            ))}
          </div>
          <p className="flex items-start gap-2 border-t border-line px-5 py-3 text-[11px] text-muted"><Database size={13} className="mt-0.5 shrink-0 text-neon" /><code className="break-all">{data.generator_command}</code><CheckCircle2 size={13} className="mt-0.5 shrink-0 text-good" /></p>
        </Card>
      </div>
    </>
  );
}
