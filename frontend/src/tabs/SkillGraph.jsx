import { useEffect, useMemo, useState } from "react";
import { useApi } from "../api.js";
import { Card, ErrorBox, Field, Loading, Table, inputCls } from "../ui.jsx";

const STATE_FILL = { MASTERED: "var(--st-good)", IN_PROGRESS: "var(--series)", UNLOCKED: "var(--neon-2)", LOCKED: "var(--st-warning)" };
const W = 190, H = 54, GX = 70, GY = 22;

/** Layered DAG: columns = tiers (external prerequisites on the left), rows = topics. Hand-built SVG, theme-aware. */
function Graph({ g, onOpen }) {
  const layout = useMemo(() => {
    const topics = [...new Set(g.nodes.filter((n) => !n.external).map((n) => n.topic))];
    const ext = g.nodes.filter((n) => n.external);
    const pos = {};
    g.nodes.forEach((n) => {
      if (n.external) pos[n.skill_id] = { x: 0, y: ext.indexOf(n) * (H + GY) };
      else pos[n.skill_id] = { x: (n.tier - (ext.length ? 0 : 1)) * (W + GX), y: topics.indexOf(n.topic) * (H + GY) };
    });
    const cols = Math.max(...Object.values(pos).map((p) => p.x)) + W;
    const rows = Math.max(...Object.values(pos).map((p) => p.y)) + H;
    return { pos, width: cols + 20, height: rows + 20 };
  }, [g]);
  const { pos } = layout;
  return (
    <div className="overflow-x-auto">
      <svg width={layout.width} height={layout.height} viewBox={`-10 -10 ${layout.width} ${layout.height}`} role="img" aria-label="Skill prerequisite graph">
        <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="var(--muted)" /></marker></defs>
        {g.edges.map((e) => {
          const a = pos[e.prerequisite_skill_id], b = pos[e.skill_id];
          if (!a || !b) return null;
          const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
          const dashed = e.relation_type !== "REQUIRED" || !e.in_force;
          return <path key={e.prerequisite_id} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none" stroke="var(--muted)" strokeOpacity={dashed ? 0.45 : 0.8}
            strokeDasharray={dashed ? "4 4" : undefined} strokeWidth={e.cross_course ? 2 : 1.2} markerEnd="url(#arr)"><title>{`${e.prerequisite_skill_id} -> ${e.skill_id}: ${e.relation_type} >= ${e.min_mastery}${e.in_force ? "" : " (expired)"}`}</title></path>;
        })}
        {g.nodes.map((n) => {
          const p = pos[n.skill_id];
          const fill = n.state ? STATE_FILL[n.state] : n.external ? "var(--muted)" : "var(--accent)";
          return (
            <g key={n.skill_id} transform={`translate(${p.x},${p.y})`} onClick={() => onOpen(n.skill_id)} className="cursor-pointer" role="button" aria-label={n.name}>
              <rect width={W} height={H} rx="10" fill="var(--surface-solid)" stroke={fill} strokeWidth={n.content_available === 0 ? 2.5 : 1.5} strokeDasharray={n.content_available === 0 ? "5 3" : undefined} />
              <rect width="6" height={H} rx="3" fill={fill} />
              <text x="14" y="21" fontSize="12" fontWeight="600" fill="var(--ink)">{n.name.length > 26 ? n.name.slice(0, 25) + "..." : n.name}</text>
              <text x="14" y="39" fontSize="11" fill="var(--muted)">{n.skill_id} · {n.content_available}/{n.content_total} items{n.mastery !== undefined ? ` · m ${n.mastery.toFixed(2)}` : ""}</text>
              <title>{`${n.name}\n${n.state ?? ""} ${n.external ? "(prerequisite from another course)" : ""}`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function SkillGraph({ onOpen }) {
  const courses = useApi("/courses");
  const [course, setCourse] = useState("");
  const [learner, setLearner] = useState("");
  const [applied, setApplied] = useState("");
  useEffect(() => { if (!course && courses.data?.length) setCourse(courses.data[Math.min(1, courses.data.length - 1)].course_id); }, [courses.data, course]);
  const g = useApi(course ? `/courses/${course}/graph${applied ? `?learner_id=${applied}` : ""}` : null);
  return (
    <>
      <Card title="Course and learner" sub="Edges point from prerequisite to skill. Thick = cross-course; dashed = recommended-only or expired rule; dashed box = no published content.">
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setApplied(learner.trim().toUpperCase()); }}>
          <Field label="Course">
            <select value={course} onChange={(e) => setCourse(e.target.value)} className={`${inputCls} w-72`}>
              {courses.data?.map((c) => <option key={c.course_id} value={c.course_id}>{c.course_code} · {c.title}</option>)}
            </select>
          </Field>
          <Field label="Colour by learner (optional)"><input value={learner} onChange={(e) => setLearner(e.target.value)} placeholder="LRN-000005" className={`${inputCls} w-44`} /></Field>
          <button className="h-9 rounded-lg bg-accent px-3.5 text-[13px] font-semibold text-white">Apply</button>
          <div className="flex flex-wrap gap-3 text-xs text-muted">
            {Object.entries(STATE_FILL).map(([k, c]) => <span key={k} className="flex items-center gap-1.5"><span className="size-3 rounded" style={{ background: c }} />{k.replace("_", " ").toLowerCase()}</span>)}
          </div>
        </form>
      </Card>
      {g.loading && <Loading />}
      <ErrorBox error={g.error || courses.error} />
      {g.data && (
        <>
          <Card title={`${g.data.course.course_code} · ${g.data.course.title}`} sub={`${g.data.nodes.length} skills · ${g.data.edges.length} prerequisite rules · as of ${g.data.as_of}`}>
            <Graph g={g.data} onOpen={onOpen} />
          </Card>
          <Card title="Prerequisite rules" flush sub="Effective-dated; only REQUIRED rules in force gate eligibility">
            <Table rows={g.data.edges} cols={["prerequisite_id", "skill_id", "prerequisite_skill_id", "relation_type", "min_mastery", "cross_course", "effective_from", "effective_to", "in_force"]} onOpen={onOpen}
              render={{ in_force: (v) => (v ? "yes" : "no"), cross_course: (v) => (v ? "yes" : "no") }} />
          </Card>
        </>
      )}
    </>
  );
}
