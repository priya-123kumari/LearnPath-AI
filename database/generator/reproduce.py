"""Step 10: regenerate twice with the same seed and compare per-table row counts and SHA-256 of every output file.

    python -m database.generator.reproduce --scale starter [--against database/data/starter]

--against also compares run 1 with a committed dataset's checksums.json (proves the published files came from this code).
Writes reproducibility_report.json in the current folder.
"""
import argparse, json, os, sys, tempfile
from .__main__ import main as generate


def run(scale, seed, against=None, report="reproducibility_report.json"):
    with tempfile.TemporaryDirectory() as tmp:
        for r in ("run1", "run2"):
            generate(["--scale", scale, "--seed", str(seed), "--out", os.path.join(tmp, r), "--quiet"] + (["--no-big-json"] if scale == "full" else []))
        load = lambda r, f: json.load(open(os.path.join(tmp, r, f), encoding="utf-8"))
        a, b = load("run1", "checksums.json"), load("run2", "checksums.json")
        ma, mb = load("run1", "manifest/source_manifest.json")["row_counts"], load("run2", "manifest/source_manifest.json")["row_counts"]
    diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    print(f"seed={seed} scale={scale}")
    print(f"{'table':26s}{'run1 rows':>11s}{'run2 rows':>11s}")
    for t in sorted(ma):
        print(f"{t:26s}{ma[t]:>11,d}{mb[t]:>11,d}{'  OK' if ma[t] == mb[t] else '  MISMATCH'}")
    print(f"files compared (SHA-256): {len(a)}; differing files: {len(diff)}")
    out = dict(seed=seed, scale=scale, files_compared=len(a), differing_files=diff, row_counts_equal=ma == mb, row_counts=ma)
    ok = not diff and ma == mb
    if against:
        pub = json.load(open(os.path.join(against, "checksums.json"), encoding="utf-8"))
        common = sorted(set(pub) & set(a))
        mism = [k for k in common if pub[k] != a[k]]
        out["against"] = dict(dataset=against.replace("\\", "/"), files_compared=len(common), differing_files=mism)
        print(f"vs published {against}: {len(common)} files compared, {len(mism)} differ")
        ok = ok and not mism
    out["result"] = "REPRODUCIBLE" if ok else "NOT REPRODUCIBLE"
    out["sample_checksums"] = {k: a[k] for k in sorted(a)[:5]}
    with open(report, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2)
    print(out["result"])
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m database.generator.reproduce")
    ap.add_argument("--scale", default="starter")
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--against", default=None)
    ap.add_argument("--report", default="reproducibility_report.json")
    a = ap.parse_args(argv)
    return run(a.scale, a.seed, a.against, a.report)


if __name__ == "__main__":
    sys.exit(main())
