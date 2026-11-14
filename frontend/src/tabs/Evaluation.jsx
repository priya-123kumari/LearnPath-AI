import { useApi } from "../api.js";
import { Bars, Card, CompareBars, ErrorBox, Loading, Meter, Ring, Stat, Table, compact, fmt, humanize, pct } from "../ui.jsx";

const LEVELS = ["NOT_STARTED", "DEVELOPING", "PROFICIENT", "MASTERED"];

export default function Evaluation() {
  const { data, error, loading } = useApi("/evaluation");
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const rq = data.recommendation_quality, mq = data.mastery_quality;
  const rows = [
    ["Hit rate @3 - a recommended item was attempted", "hit_rate_at_3"],
    ["Next item match - the first test attempt was recommended", "next_item_match_rate"],
    ["Prerequisite violations - lower is better", "prerequisite_violation_rate"],
    ["Pass rate on recommended items attempted", "pass_rate_on_recommended_items"],
  ].map(([label, k]) => ({ label, engine: rq.engine[k], popularity: rq.popularity[k] }));
  const reasons = Object.entries(data.outcomes_by_reason_code).map(([reason_code, r]) => ({ reason_code, ...r, meaning: data.reason_codes[reason_code] }));
  const lv = rq.pass_rate_by_mastery_level_at_cutoff;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Stat label="Cutoff" value={rq.cutoff.slice(0, 10)} note={`test window until ${rq.test_window_end.slice(0, 10)}`} />
        <Stat label="Train attempts" value={compact(rq.train_attempts)} note={`last started ${rq.train_max_started.slice(0, 16).replace("T", " ")}`} />
        <Stat label="Test attempts" value={compact(rq.test_attempts)} note={`first started ${rq.test_min_started.slice(0, 16).replace("T", " ")}`} />
        <Stat label="Split is temporal" value={rq.split_is_temporal ? "Yes" : "No"} tone={rq.split_is_temporal ? "good" : "bad"} note={`${fmt(rq.learners_evaluated)} learners evaluated`} />
      </div>
      <div className="grid gap-4 sm:gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card eyebrow="benchmark" title="Engine vs popularity baseline" sub="State rebuilt from attempts before the cutoff only; the next 30 days are the test set">
          <CompareBars rows={rows} series={[{ key: "engine", label: "Recommendation engine", color: "var(--series)" }, { key: "popularity", label: "Popularity baseline", color: "var(--series-2)" }]} />
          <p className="mt-5 rounded-lg bg-accent-soft p-3 text-xs text-ink-2">Simulated learners follow recommendations 80% of the time, so hit rate is partly self-fulfilling. The independent evidence:
            the baseline recommends locked items, the engine never does, and pass rates rise steeply with mastery at the cutoff
            (non-recommended items pass {pct(rq.pass_rate_on_non_recommended_items)}).</p>
        </Card>
        <Card eyebrow="mastery model" title="Does mastery predict success?">
          <div className="flex items-center gap-5">
            <Ring value={rq.mastery_at_cutoff_predicts_pass_auc} label="AUC" display={rq.mastery_at_cutoff_predicts_pass_auc.toFixed(2)} />
            <div className="min-w-0 space-y-1 text-[13px]">
              <p><b>AUC {fmt(rq.mastery_at_cutoff_predicts_pass_auc)}</b> <span className="text-muted">mastery at cutoff → pass in test window</span></p>
              <p><b>r = {fmt(mq.pearson_r)}</b> <span className="text-muted">vs hidden true mastery (MAE {fmt(mq.mean_abs_error)}, {compact(mq.pairs)} pairs)</span></p>
            </div>
          </div>
          <p className="mt-6 mb-3 eyebrow">pass rate in the test window by mastery level at the cutoff</p>
          <div className="space-y-3.5">
            {LEVELS.filter((k) => lv[k]).map((k) => <Meter key={k} label={humanize(k)} value={lv[k].pass_rate} note={`${fmt(lv[k].attempts)} attempts`} />)}
          </div>
        </Card>
      </div>
      <Card eyebrow="outcomes" title="Historical outcomes by reason code" flush sub="Acceptance = attempted within 14 days; pass rate over scored outcomes">
        <Table rows={reasons} cols={["reason_code", "meaning", "recommendations", "acceptance_rate", "pass_rate_when_scored", "mean_outcome_score_pct"]}
          render={{ reason_code: (v) => <b className="text-[12.5px]">{humanize(v)}</b>, acceptance_rate: (v) => pct(v), pass_rate_when_scored: (v) => pct(v) }} />
      </Card>
      <div className="grid gap-4 sm:gap-5 xl:grid-cols-3">
        <Card eyebrow="at cutoff" title="Reason mix when the engine ran"><Bars data={rq.engine.reason_mix_at_cutoff} label="recommendations" /></Card>
        <Card eyebrow="catalogue" title="Content difficulty (items)"><Bars sort={false} data={data.distributions.content_difficulty_mix} label="items" /></Card>
        <Card eyebrow="learners" title="Current mastery levels (learner × skill)"><Bars data={data.distributions.current_mastery_levels} label="learner-skills" format={compact} /></Card>
      </div>
    </>
  );
}
