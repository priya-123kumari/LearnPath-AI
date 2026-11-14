import { useApi } from "./api.js";
import { Cell, ErrorBox, Loading, Pill, Table, humanize } from "./ui.jsx";

/** Record trail for any ID: the record itself, related records and any data-quality labels or exceptions. */
export function Trace({ id, onOpen }) {
  const { data, error, loading } = useApi(`/records/${encodeURIComponent(id)}`);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const { record, related, table } = data;
  return (
    <div className="space-y-5">
      <p className="text-xs text-muted">Table <code className="rounded bg-raised px-1.5 py-0.5">{table}</code></p>
      {related.data_quality_labels?.length > 0 && (
        <div className="rounded-xl border border-warn/30 bg-warn-soft p-3 text-sm text-warn">
          {related.data_quality_labels.map((l) => <p key={l.gt_id}><b>{humanize(l.issue_type)}</b> ({l.gt_id}) - {l.context}. Expected decision: {humanize(l.expected_decision)}</p>)}
        </div>
      )}
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 sm:grid-cols-2">
        {Object.entries(record).map(([k, v]) => (
          <div key={k} className="min-w-0 border-b border-line pb-2">
            <dt className="text-xs text-muted">{humanize(k)}</dt>
            <dd className="mt-0.5 text-[13px] break-words">{k === "rationale" ? v : <Cell col={k} value={v} onOpen={onOpen} />}</dd>
          </div>
        ))}
      </dl>
      {Object.entries(related).filter(([k, v]) => k !== "data_quality_labels" && v?.length).map(([k, v]) => (
        <section key={k} className="rounded-xl border border-line">
          <h3 className="border-b border-line px-4 py-2 text-[13px] font-semibold">{humanize(k)} <span className="font-normal text-muted">({v.length})</span></h3>
          <Table rows={v} onOpen={onOpen} />
        </section>
      ))}
      {related.exceptions?.length > 0 && <p className="text-xs text-muted">This record is in the exception queue: {related.exceptions.map((e) => <Pill key={e.exception_id} value={e.exception_type} tone="warn" />)}</p>}
    </div>
  );
}
