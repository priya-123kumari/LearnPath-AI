import { useEffect, useRef, useState } from "react";
import { BarChart3, Cpu, GitBranch, GraduationCap, LayoutDashboard, Moon, Search, ShieldCheck, Siren, Sun, Waypoints } from "lucide-react";
import { useApi } from "./api.js";
import { ErrorBox, Modal } from "./ui.jsx";
import { Trace } from "./Trace.jsx";
import Overview from "./tabs/Overview.jsx";
import Learners from "./tabs/Learners.jsx";
import SkillGraph from "./tabs/SkillGraph.jsx";
import Exceptions from "./tabs/Exceptions.jsx";
import Quality from "./tabs/Quality.jsx";
import Evaluation from "./tabs/Evaluation.jsx";

const TABS = [
  { id: "overview", label: "Command center", icon: LayoutDashboard, about: "Workflow health: data, decisions, quality and evaluation at a glance", who: "Everyone" },
  { id: "learners", label: "Learner 360", icon: GraduationCap, about: "Mastery, live recommendations with reasons, attempts and outcomes", who: "Learner · instructor · support" },
  { id: "graph", label: "Skill graph", icon: GitBranch, about: "Prerequisite graph per course, coloured by a learner's state", who: "Instructor · academic admin" },
  { id: "exceptions", label: "Exception queue", icon: Siren, about: "Cases routed to a person instead of handled automatically", who: "Instructor · support · admins" },
  { id: "quality", label: "Data quality", icon: ShieldCheck, about: "Validation checks and labelled anomalies vs ground truth", who: "Platform admin" },
  { id: "evaluation", label: "Evaluation", icon: BarChart3, about: "Temporal-split recommendation quality, mastery quality, outcomes", who: "Academic · platform admin" },
];
const tabFromHash = () => TABS.find((t) => window.location.hash.startsWith(`#${t.id}`)) ?? TABS[0];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try { localStorage.setItem("theme", next ? "dark" : "light"); } catch { /* storage blocked */ }
    setDark(next);
  };
  return [dark, toggle];
}

const Brand = () => (
  <div className="flex items-center gap-3">
    <span className="relative grid size-10 shrink-0 place-items-center rounded-xl border border-cyan-400/30 bg-gradient-to-br from-cyan-400/25 to-violet-500/25 text-cyan-200 shadow-[0_0_24px_-6px_rgba(34,211,238,.6)]">
      <Waypoints size={19} />
    </span>
    <span className="leading-tight">
      <b className="block text-[15px] font-semibold tracking-tight text-white">LearnPath <span className="neon-text">AI</span></b>
      <span className="font-mono text-[10px] tracking-[0.18em] text-slate-400 uppercase">adaptive engine</span>
    </span>
  </div>
);

export default function App() {
  const [tab, setTab] = useState(tabFromHash);
  const [trace, setTrace] = useState(null);
  const [q, setQ] = useState("");
  const [dark, toggleTheme] = useTheme();
  const health = useApi("/health");
  const search = useRef(null);

  useEffect(() => {
    const sync = () => setTab(tabFromHash());
    const key = (e) => { if (e.key === "/" && document.activeElement?.tagName !== "INPUT") { e.preventDefault(); search.current?.focus(); } };
    window.addEventListener("hashchange", sync);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("hashchange", sync); window.removeEventListener("keydown", key); };
  }, []);

  const go = (t) => { window.location.hash = t.id; setTab(t); window.scrollTo(0, 0); };
  const submit = (e) => { e.preventDefault(); if (q.trim()) setTrace(q.trim().toUpperCase()); };
  const backendDown = health.error || health.data?.status === "database_missing";
  const online = !health.loading && !backendDown;

  return (
    <div className="min-h-screen lg:pl-[17rem]">
      <aside className="fixed inset-y-3 left-3 z-30 hidden w-64 flex-col overflow-y-auto rounded-2xl border border-white/10 bg-navy/85 p-4 shadow-2xl backdrop-blur-xl lg:flex">
        <div className="px-1 py-1"><Brand /></div>
        <p className="mt-7 mb-2 px-3 font-mono text-[10px] tracking-[0.18em] text-slate-500 uppercase">Modules</p>
        <nav className="flex flex-col gap-1" aria-label="Sections">
          {TABS.map((t) => {
            const on = t === tab;
            return (
              <button key={t.id} aria-current={on ? "page" : undefined} onClick={() => go(t)}
                className={`relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13.5px] font-medium transition-all ${on ? "bg-gradient-to-r from-cyan-400/15 to-transparent text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-100"}`}>
                {on && <span className="absolute top-2 bottom-2 left-0 w-[3px] rounded-full bg-cyan-300 shadow-[0_0_12px_rgba(34,211,238,.9)]" />}
                <t.icon size={17} className={`shrink-0 ${on ? "text-cyan-300" : "text-slate-500"}`} />{t.label}
              </button>
            );
          })}
        </nav>
        <div className="mt-auto space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-3.5">
          <p className="flex items-center gap-2 font-mono text-[10.5px] tracking-[0.14em] uppercase">
            <span className={`pulse-dot size-2 rounded-full ${online ? "bg-emerald-400 text-emerald-400" : "bg-red-400 text-red-400"}`} />
            <span className={online ? "text-emerald-300" : "text-red-300"}>{health.loading ? "linking..." : online ? "system online" : "backend offline"}</span>
          </p>
          <dl className="grid grid-cols-2 gap-2 text-[11px]">
            <div><dt className="font-mono text-slate-500 uppercase">engine</dt><dd className="font-semibold text-slate-200">{health.data?.model_version ?? "-"}</dd></div>
            <div><dt className="font-mono text-slate-500 uppercase">mastery</dt><dd className="font-semibold text-slate-200">{health.data?.mastery_model ?? "-"}</dd></div>
            <div className="col-span-2"><dt className="font-mono text-slate-500 uppercase">data as of</dt><dd className="font-semibold text-slate-200">{health.data?.dataset_as_of?.replace("T", " ").replace("Z", " UTC") ?? "-"}</dd></div>
          </dl>
        </div>
      </aside>

      <header className="sticky top-0 z-20 px-3 pt-3 lg:px-4">
        <div className="glass flex flex-wrap items-center gap-x-4 gap-y-2.5 rounded-2xl px-4 py-3 sm:px-5">
          <div className="lg:hidden"><Brand /></div>
          <div className="min-w-0 flex-1 basis-56">
            <p className="eyebrow flex items-center gap-1.5"><Cpu size={11} className="text-neon" />{tab.who}</p>
            <h1 className="truncate text-[18px] font-semibold tracking-tight">{tab.label}</h1>
            <p className="text-xs text-muted sm:truncate">{tab.about}</p>
          </div>
          <form onSubmit={submit} role="search" className="relative order-last w-full sm:order-none sm:w-80 xl:w-[26rem]">
            <Search size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
            <input ref={search} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Trace a record by ID" placeholder="Trace any ID  ·  LRN-000001, REC-…, PATH-2026-…"
              className="h-10 w-full rounded-xl border border-line bg-raised pr-12 pl-9 font-mono text-[12.5px] placeholder:text-muted focus:border-neon/50 focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
            <kbd className="absolute top-1/2 right-2.5 -translate-y-1/2 rounded border border-line-strong px-1.5 font-mono text-[10px] text-muted">/</kbd>
          </form>
          <button onClick={toggleTheme} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
            className="grid size-10 place-items-center rounded-xl border border-line bg-raised text-ink-2 transition-colors hover:border-neon/40 hover:text-ink">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
        <nav className="glass mt-2 flex gap-1 overflow-x-auto rounded-xl p-1.5 lg:hidden" aria-label="Sections">
          {TABS.map((t) => (
            <button key={t.id} aria-current={t === tab ? "page" : undefined} onClick={() => go(t)}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium ${t === tab ? "bg-accent-soft text-accent" : "text-ink-2"}`}>
              <t.icon size={15} />{t.label}
            </button>
          ))}
        </nav>
      </header>

      <main key={tab.id} className="fade-up mx-auto max-w-[1480px] space-y-4 px-3 py-4 sm:space-y-5 lg:px-4">
        {backendDown && !health.loading && (
          <ErrorBox error={{ code: "Backend not reachable", message: "Start the API from the project folder: python -m uvicorn backend.main:app --port 8000 (build the database first with python -m database.load_db --data database/data/starter)" }} />
        )}
        {tab.id === "overview" && <Overview onOpen={setTrace} />}
        {tab.id === "learners" && <Learners onOpen={setTrace} />}
        {tab.id === "graph" && <SkillGraph onOpen={setTrace} />}
        {tab.id === "exceptions" && <Exceptions onOpen={setTrace} />}
        {tab.id === "quality" && <Quality onOpen={setTrace} />}
        {tab.id === "evaluation" && <Evaluation />}
      </main>
      {trace && <Modal title={trace} onClose={() => setTrace(null)}><Trace id={trace} onOpen={setTrace} /></Modal>}
    </div>
  );
}
