import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useApi } from "../api.js";
import { Card, ErrorBox, Loading, Pill, Stat, Table, fmt, humanize } from "../ui.jsx";

export default function Quality({ onOpen }) {
  const { data, error, loading } = useApi("/quality");
  const [onlyHits, setOnlyHits] = useState(true);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const v = data.validation;
  const checks = Object.entries(v.checks).map(([check, s]) => ({ check, ...s, expected_hits: v.labelled_findings_by_check[check] ?? 0 }))
    .filter((c) => !onlyHits || c.violations > 0);
  const det = Object.entries(data.detection).map(([issue_type, d]) => ({ issue_type, ...d }));
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Stat icon={ShieldCheck} label="Validation status" value={v.status} tone={v.status === "PASS" ? "good" : "bad"} note="PASS = 0 unexpected errors and 0 missed labels" />
        <Stat label="Checks run" value={v.checks_run} note={`${fmt(v.total_rows_checked)} rows examined`} />
        <Stat label="Unexpected errors" value={v.unexpected_errors} tone={v.unexpected_errors ? "bad" : "good"} />
        <Stat label="Labelled findings observed" value={v.labelled_findings_observed} tone="warn" note={`missed labels: ${v.missed_labelled}`} />
      </div>
      <Card title="Anomaly detection vs ground truth" flush sub="Rules run on input tables only; ground truth is used to score them, never as a feature">
        <Table rows={det} cols={["issue_type", "ground_truth", "detected", "true_positive", "false_positive", "false_negative", "precision", "recall"]}
          render={{ issue_type: (x) => humanize(x) }} />
      </Card>
      <Card title="Validation checks" flush sub="PK, ID formats, FK on every join, enums, dates, graph, arithmetic, lifecycle, business rules, duplicates, leakage"
        action={<label className="flex items-center gap-2 text-xs text-ink-2"><input type="checkbox" checked={onlyHits} onChange={(e) => setOnlyHits(e.target.checked)} />only checks with findings</label>}>
        <Table rows={checks} cols={["check", "rows_checked", "violations", "expected_hits"]}
          render={{ violations: (n, r) => (n === 0 ? <Pill value="PASS" /> : n === r.expected_hits ? <Pill value={`${n} labelled`} tone="warn" /> : <Pill value={`${n}`} tone="bad" />) }} />
      </Card>
      {v.unexpected_error_samples?.length > 0 && <Card title="Unexpected errors" flush><Table rows={v.unexpected_error_samples} onOpen={onOpen} /></Card>}
      <Card title="Ground truth (separate file, never joined into inputs)" flush sub="Click an entity to see the record and its trail">
        <Table rows={data.ground_truth} onOpen={onOpen} cols={["gt_id", "issue_type", "entity_type", "entity_id", "expected_decision", "context"]} />
      </Card>
    </>
  );
}
