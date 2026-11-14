"""Database tier: build the SQLite database the backend serves.

    python -m database.load_db --data database/data/starter --db database/learnpath.db

1. creates the 11 operational tables from <data>/sql/schema.sql (PK, FK, CHECK constraints, indexes)
2. loads <data>/csv/*.csv in parent -> child order
3. loads audit material into separate audit_* tables (ground truth, exception queue, validation, metrics, manifest).
   The recommender never reads audit_* tables, so ground truth cannot leak into decisions.
4. runs PRAGMA foreign_key_check: the only violations allowed are the labelled CONTENT_MAPPED_TO_NONEXISTENT_SKILL rows
"""
import argparse, csv, json, os, sqlite3, sys
from database.generator.schema import SCHEMA

AUDIT_DDL = """
CREATE TABLE audit_ground_truth (gt_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, issue_type TEXT NOT NULL,
  expected_detection_rule TEXT, expected_decision TEXT, context TEXT);
CREATE TABLE audit_exception_queue (exception_id TEXT PRIMARY KEY, exception_type TEXT NOT NULL, owner_role TEXT NOT NULL,
  entity_type TEXT, entity_id TEXT, learner_id TEXT, detected_at TEXT, detail TEXT, recommended_action TEXT);
CREATE INDEX ix_exc_type ON audit_exception_queue(exception_type);
CREATE TABLE audit_report (name TEXT PRIMARY KEY, body TEXT NOT NULL);
"""


def _rows(path, cols, types):
    with open(path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            out = []
            for c in cols:
                v = r.get(c, "")
                if v == "":
                    out.append(None)
                elif types[c] in ("INTEGER", "BOOLEAN"):
                    out.append(int(float(v)))
                elif types[c] == "REAL":
                    out.append(float(v))
                else:
                    out.append(v)
            yield out


def build(data_dir, db_path, quiet=False):
    data_dir = os.path.abspath(data_dir)
    if not os.path.exists(os.path.join(data_dir, "csv")):
        raise SystemExit(f"No dataset at {data_dir}. Generate it first: python -m database.generator --scale starter --out database/data/starter")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute("PRAGMA journal_mode = OFF"); con.execute("PRAGMA synchronous = OFF")
    with open(os.path.join(data_dir, "sql", "schema.sql"), encoding="utf-8") as f:
        con.executescript(f.read())
    con.executescript(AUDIT_DDL)
    con.execute("PRAGMA foreign_keys = OFF")             # labelled FK anomalies must load; checked below
    counts = {}
    for name, spec in SCHEMA.items():
        cols = [c[0] for c in spec["cols"]]
        types = {c[0]: c[1] for c in spec["cols"]}
        sql = f"INSERT INTO {spec['file']} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        con.executemany(sql, _rows(os.path.join(data_dir, "csv", f"{spec['file']}.csv"), cols, types))
        counts[spec["file"]] = con.execute(f"SELECT COUNT(*) FROM {spec['file']}").fetchone()[0]
    gt_cols = ["gt_id", "entity_type", "entity_id", "issue_type", "expected_detection_rule", "expected_decision", "context"]
    con.executemany(f"INSERT INTO audit_ground_truth VALUES ({','.join('?' * 7)})",
                    _rows(os.path.join(data_dir, "ground_truth", "ground_truth.csv"), gt_cols, {c: "TEXT" for c in gt_cols}))
    ex_cols = ["exception_id", "exception_type", "owner_role", "entity_type", "entity_id", "learner_id", "detected_at", "detail", "recommended_action"]
    con.executemany(f"INSERT INTO audit_exception_queue VALUES ({','.join('?' * 9)})",
                    _rows(os.path.join(data_dir, "outputs", "exception_queue.csv"), ex_cols, {c: "TEXT" for c in ex_cols}))
    for name, rel in (("validation_summary", "outputs/validation_summary.json"), ("evaluation_metrics", "outputs/evaluation_metrics.json"),
                      ("source_manifest", "manifest/source_manifest.json")):
        with open(os.path.join(data_dir, rel), encoding="utf-8") as f:
            con.execute("INSERT INTO audit_report VALUES (?, ?)", (name, f.read()))
    con.execute("INSERT INTO audit_report VALUES (?, ?)", ("dataset", json.dumps(dict(data_dir=os.path.basename(data_dir), row_counts=counts))))
    con.commit()
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    labelled = {r[0] for r in con.execute("SELECT entity_id FROM audit_ground_truth WHERE issue_type = 'CONTENT_MAPPED_TO_NONEXISTENT_SKILL'")}
    rowids = {r[0]: r[1] for r in con.execute("SELECT rowid, content_skill_id FROM content_skills")}
    unexpected = [r for r in fk if not (r[0] == "content_skills" and rowids.get(r[1]) in labelled)]
    con.close()
    try:
        os.replace(tmp, db_path)
    except PermissionError:
        os.remove(tmp)
        raise SystemExit(f"{db_path} is in use (is the backend running?). Stop uvicorn, then run this command again.")
    if not quiet:
        print(f"[{db_path}] loaded from {data_dir}")
        for t, n in counts.items():
            print(f"   {t:24s}{n:>9,d}")
        print(f"   foreign_key_check: {len(fk)} violations, all labelled anomalies: {not unexpected}")
    return dict(counts=counts, fk_violations=len(fk), unexpected_fk=len(unexpected))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m database.load_db")
    ap.add_argument("--data", default="database/data/starter")
    ap.add_argument("--db", default="database/learnpath.db")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    r = build(a.data, a.db, a.quiet)
    return 0 if r["unexpected_fk"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
