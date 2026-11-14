"""CLI:  python -m database.generator --scale full --out database/data/full"""
import argparse, sys
from .config import Config, SEED, SCALES
from .build import generate_all
from .validate import validate
from .evaluate import all_metrics
from .exceptions import build_exception_queue
from .export import export_all
from .docs import write_docs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m database.generator", description="LearnPath AI synthetic data generator")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--scale", choices=sorted(SCALES), default="full", help="preset sizes; individual flags below override")
    ap.add_argument("--learners", type=int); ap.add_argument("--skills", type=int)
    ap.add_argument("--content", type=int); ap.add_argument("--attempts", type=int)
    ap.add_argument("--out", default="database/data/full")
    ap.add_argument("--docs", default=None, help="optional: also (re)write docs/ from the schema")
    ap.add_argument("--no-big-json", action="store_true", help="skip JSON copies of the four largest tables (CSV/SQL still written)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    size = dict(SCALES[a.scale])
    for k in size:
        if getattr(a, k) is not None:
            size[k] = getattr(a, k)
    cfg = Config(seed=a.seed, **size)
    R = generate_all(cfg)
    T, gt, cat = R["tables"], R["ground_truth"], R["catalog"]
    val = validate(T, gt, cat)
    metrics = all_metrics(T, gt, cat, R["true_mastery"])
    exc = build_exception_queue(T, cat)
    cmd = (f"python -m database.generator --seed {a.seed} --learners {cfg.learners} --skills {cfg.skills} "
           f"--content {cfg.content} --attempts {cfg.attempts} --out {a.out}")
    export_all(R, a.out, val, metrics, exc, cmd, json_big=not a.no_big_json)
    if a.docs:
        write_docs(a.docs)
    if not a.quiet:
        rq = metrics["recommendation_quality"]
        print(f"[{a.out}] seed={a.seed} learners={cfg.learners} attempts={cfg.attempts} validation={val['status']} "
              f"checks={val['checks_run']} unexpected_errors={val['unexpected_errors']} labelled_findings={val['labelled_findings_observed']}")
        for k, v in metrics["detection"].items():
            print(f"   {k:38s} truth={v['ground_truth']:3d} detected={v['detected']:3d} precision={v['precision']} recall={v['recall']}")
        e, p = rq["engine"], rq["popularity"]
        print(f"   temporal split @ {rq['cutoff']}: engine hit@3={e['hit_rate_at_3']} prereq_violations={e['prerequisite_violation_rate']} "
              f"| popularity hit@3={p['hit_rate_at_3']} prereq_violations={p['prerequisite_violation_rate']} | mastery AUC={rq['mastery_at_cutoff_predicts_pass_auc']}")
    return 0 if val["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
