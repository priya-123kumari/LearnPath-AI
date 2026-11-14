"""Fallback runner if pytest is unavailable:  python tests/run_without_pytest.py"""
import os, sys, time, traceback
here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [here, os.path.dirname(here)]
import test_engine, test_pipeline, test_backend
fails = 0
for mod in (test_engine, test_pipeline, test_backend):
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        s = time.time()
        try:
            getattr(mod, name)(); print(f"PASS {mod.__name__}.{name} ({time.time()-s:.1f}s)")
        except Exception:
            fails += 1; print(f"FAIL {mod.__name__}.{name}"); traceback.print_exc()
print(f"\n{'ALL PASSED' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
