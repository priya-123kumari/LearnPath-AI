"""Step 9: CSV / JSON / SQL export, ground truth, outputs, manifest and checksums."""
import hashlib, json, numbers, os
import pandas as pd
from backend.config import iso
from .schema import SCHEMA, columns

BIG_TABLES = {"Attempt", "AssessmentResult", "Recommendation", "LearningPathEvent"}


def _prep(name, df):
    """Typed export frame: timestamps -> ISO-8601 text, integers/booleans -> nullable Int64."""
    out = df[columns(name)].copy()
    for nm, typ, *_ in SCHEMA[name]["cols"]:
        if typ == "TIMESTAMP":
            out[nm] = out[nm].map(lambda v: None if v is None or v != v else iso(int(v)))
        elif typ in ("BOOLEAN", "INTEGER"):
            out[nm] = pd.to_numeric(out[nm]).round().astype("Int64")
        elif typ == "REAL":
            out[nm] = out[nm].astype(float)
    return out


def ddl():
    sql_t = {"TEXT": "TEXT", "INTEGER": "INTEGER", "REAL": "REAL", "DATE": "TEXT", "TIMESTAMP": "TEXT", "BOOLEAN": "INTEGER"}
    lines = ["-- LearnPath AI database schema (SQLite). Auto-generated from database/generator/schema.py", "PRAGMA foreign_keys = ON;", ""]
    for name, spec in SCHEMA.items():
        cols, fks = [], []
        for nm, typ, req, allowed, unit, uniq, rule, fk in spec["cols"]:
            d = f"  {nm} {sql_t[typ]}"
            if req or nm in spec["pk"]:
                d += " NOT NULL"
            if uniq and nm not in spec["pk"]:
                d += " UNIQUE"
            if typ == "BOOLEAN":
                d += f" CHECK ({nm} IN (0,1))"
            if allowed:
                d += f" CHECK ({nm} IN ({', '.join(str(a) if isinstance(a, int) else repr(a) for a in allowed)}))"
            cols.append(d)
            if fk:
                t, c = fk.split(".")
                fks.append(f"  FOREIGN KEY ({nm}) REFERENCES {SCHEMA[t]['file']}({c}) DEFERRABLE INITIALLY DEFERRED")
        pk = f"  PRIMARY KEY ({', '.join(spec['pk'])})"
        lines.append(f"-- {name}: {spec['desc']}\nCREATE TABLE {spec['file']} (\n" + ",\n".join(cols + [pk] + fks) + "\n);\n")
    lines += ["-- query indexes used by the backend",
              "CREATE INDEX ix_attempts_learner ON attempts(learner_id, started_at);",
              "CREATE INDEX ix_results_learner ON assessment_results(learner_id, skill_id);",
              "CREATE INDEX ix_recs_learner ON recommendations(learner_id, recommended_at);",
              "CREATE INDEX ix_events_path ON learning_path_events(path_id, event_seq);",
              "CREATE INDEX ix_paths_learner ON learning_paths(learner_id);",
              "CREATE INDEX ix_content_skills_content ON content_skills(content_id);", ""]
    return "\n".join(lines)


def _lit(v):
    if v is None or v is pd.NA or (isinstance(v, float) and v != v):
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    if isinstance(v, numbers.Integral):
        return str(int(v))
    return repr(float(v))


def seed_sql(P):
    out = ["-- Seed data (INSERTs). Load schema.sql first.",
           "-- Foreign keys are switched off while loading because the dataset deliberately contains labelled",
           "-- CONTENT_MAPPED_TO_NONEXISTENT_SKILL rows; run PRAGMA foreign_key_check afterwards: it lists exactly those rows.",
           "PRAGMA foreign_keys = OFF;", "BEGIN;"]
    for name, spec in SCHEMA.items():
        df = P[name]; cols = ", ".join(df.columns)
        for i in range(0, len(df), 500):
            vals = ",\n".join("(" + ", ".join(_lit(v) for v in row) + ")" for row in df.iloc[i:i + 500].itertuples(index=False, name=None))
            out.append(f"INSERT INTO {spec['file']} ({cols}) VALUES\n{vals};")
    out += ["COMMIT;", "PRAGMA foreign_keys = ON;"]
    return "\n".join(out) + "\n"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dump(obj, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True, default=str)


def export_all(R, out_dir, validation, metrics, exceptions, command, json_big=True):
    cfg = R["config"]
    for sub in ("csv", "json", "sql", "ground_truth", "outputs", "manifest"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    P = {n: _prep(n, R["tables"][n]) for n in SCHEMA}
    rows = {}
    for n, df in P.items():
        f = SCHEMA[n]["file"]
        df.to_csv(os.path.join(out_dir, "csv", f"{f}.csv"), index=False, lineterminator="\n")
        if json_big or n not in BIG_TABLES:
            df.to_json(os.path.join(out_dir, "json", f"{f}.json"), orient="records", force_ascii=False)
        rows[f] = len(df)
    with open(os.path.join(out_dir, "sql", "schema.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write(ddl())
    with open(os.path.join(out_dir, "sql", "seed.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write(seed_sql(P))
    gt = R["ground_truth"].sort_values("gt_id")
    gt.to_csv(os.path.join(out_dir, "ground_truth", "ground_truth.csv"), index=False, lineterminator="\n")
    gt.to_json(os.path.join(out_dir, "ground_truth", "ground_truth.json"), orient="records", indent=1)
    R["true_mastery"].to_csv(os.path.join(out_dir, "ground_truth", "true_mastery.csv"), index=False, lineterminator="\n")
    exceptions.to_csv(os.path.join(out_dir, "outputs", "exception_queue.csv"), index=False, lineterminator="\n")
    _dump(metrics, os.path.join(out_dir, "outputs", "evaluation_metrics.json"))
    _dump(validation, os.path.join(out_dir, "outputs", "validation_summary.json"))
    manifest = dict(
        dataset="LearnPath AI - adaptive learning recommendations (fully synthetic)",
        generator_command=command.split(" --out ")[0] + " --out <OUT_DIR>", seed=cfg.seed,
        scale=dict(learners=cfg.learners, skills=cfg.skills, content=cfg.content, attempts=cfg.attempts),
        row_counts=rows, ground_truth_rows=len(gt), true_mastery_rows=len(R["true_mastery"]), exception_queue_rows=len(exceptions),
        json_exported_for=sorted(SCHEMA[n]["file"] for n in SCHEMA if json_big or n not in BIG_TABLES),
        external_data_used=False, sources=[],
        provenance="All values are generated by database/generator with numpy.random.default_rng(seed). No external datasets, "
                   "no personal or confidential data; names are drawn from small synthetic lists and e-mails use the reserved "
                   "example.edu domain. Public learning-science concepts (prerequisite graphs, mastery learning, spaced review) "
                   "were used for schema inspiration only.",
        fields_discarded=[], transformations=[], license="MIT (code) / CC0 (generated data)")
    _dump(manifest, os.path.join(out_dir, "manifest", "source_manifest.json"))
    sums = {}
    for root, _, files in os.walk(out_dir):
        for fn in files:
            if fn == "checksums.json":
                continue
            p = os.path.join(root, fn)
            sums[os.path.relpath(p, out_dir).replace(os.sep, "/")] = sha256(p)
    _dump(dict(sorted(sums.items())), os.path.join(out_dir, "checksums.json"))
    return rows
