import { useState } from "react";
import { useApi } from "../api.js";
import { Card, ErrorBox, Field, Loading, Pill, Table, btnGhost, fmt, inputCls } from "../ui.jsx";

const OWNERS = ["", "INSTRUCTOR", "SUPPORT_STAFF", "ACADEMIC_ADMIN", "PLATFORM_ADMIN"];
const PAGE = 50;

export default function Exceptions({ onOpen }) {
  const [type, setType] = useState("");
  const [owner, setOwner] = useState("");
  const [page, setPage] = useState(0);
  const { data, error, loading } = useApi(`/exceptions?exception_type=${encodeURIComponent(type)}&owner_role=${owner}&limit=${PAGE}&offset=${page * PAGE}`);
  const summary = data?.summary ?? [];
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {OWNERS.slice(1).map((o) => {
          const n = summary.filter((s) => s.owner_role === o).reduce((a, s) => a + s.n, 0);
          return (
            <button key={o} onClick={() => { setOwner(owner === o ? "" : o); setType(""); setPage(0); }}
              className={`rounded-2xl border bg-surface p-4 text-left shadow-sm ${owner === o ? "border-accent ring-2 ring-accent/30" : "border-line"}`}>
              <p className="text-xs font-medium text-muted">{o.replace("_", " ").toLowerCase()}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{fmt(n)}</p>
            </button>
          );
        })}
      </div>
      <Card title="Exception types" flush sub="Click a row to filter. Built from rules on operational data only, never from ground truth.">
        <Table rows={summary} cols={["exception_type", "owner_role", "n"]}
          render={{ exception_type: (v) => <button className="text-left text-accent hover:underline" onClick={() => { setType(v); setPage(0); }}>{v}</button> }} />
      </Card>
      <Card title={type || owner ? `Queue: ${type || owner}` : "Queue"} sub={data ? `${fmt(data.total)} items` : ""} flush
        action={(type || owner) && <button className={btnGhost} onClick={() => { setType(""); setOwner(""); setPage(0); }}>Clear filter</button>}>
        <ErrorBox error={error} />
        {loading && !data ? <Loading /> : (
          <Table rows={data?.items} onOpen={onOpen} cols={["exception_id", "exception_type", "owner_role", "entity_id", "learner_id", "detected_at", "detail", "recommended_action"]}
            render={{ exception_type: (v) => <Pill value={v.replace("DATA_QUALITY:", "DQ:")} tone={v.startsWith("DATA") ? "bad" : v === "STALLED_PATH" ? "warn" : "info"} /> }} />
        )}
        <div className="flex items-center justify-end gap-2 border-t border-line p-2">
          <button className={btnGhost} disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <button className={btnGhost} disabled={!data || (page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </Card>
    </>
  );
}
