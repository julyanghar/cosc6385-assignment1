#!/usr/bin/env python3
# Checks that src/test_pm.cc can fail: builds the appendix test against
# deliberately broken copies of src/my_predictor.h, one per rule of REPORT-branch-prediction.md,
# and prints how many appendix rows still match and whether the test failed.
# Usage, from cbp2-infrastructure-v2/:  python3 mutants_test_pm.py
import os
import shutil
import subprocess
import tempfile

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
FLAGS = "-DPM_BIM_BITS=4 -DPM_PC_SHIFT=2 -DPM_SET_BITS=2 -DPM_TAG_BITS=2 -DPM_WAYS=2 -DPM_HIST_BITS=4".split()

# (name, text in my_predictor.h, replacement)
MUTANTS = [
    ("R3: bimodal not trained on global hits",
     "                train (bim[p->bim_index], taken);",
     "                if (p->hit_way < 0) train (bim[p->bim_index], taken);"),
    ("R4: hit way not made most recently used",
     "                touch (p->set, w);",
     "                if (p->hit_way < 0) touch (p->set, w);"),
    ("R5: allocate only when the prediction was wrong",
     "                if (w < 0) {\n",
     "                if (w < 0 && p->direction_prediction () == taken) {\n"
     "                        ghr = ((ghr << 1) | taken) & ((1 << PM_HIST_BITS) - 1);\n"
     "                        return;\n"
     "                }\n"
     "                if (w < 0) {\n"),
    ("R6: counter reset to 2 on allocation",
     "                        tag[p->set][w] = p->tag;",
     "                        tag[p->set][w] = p->tag;\n                        ctr[p->set][w] = 2;"),
    ("R7: history shifted the wrong way",
     "                ghr = ((ghr << 1) | taken) & ((1 << PM_HIST_BITS) - 1);",
     "                ghr = (ghr >> 1) | (taken << (PM_HIST_BITS - 1));"),
    ("R8: way 1 replaced first in an empty set",
     "                                age[s][w] = PM_WAYS - 1 - w;",
     "                                age[s][w] = w;"),
    ("R2: bimodal used even on a global hit",
     "                if (u.hit_way >= 0)\n                        u.direction_prediction (ctr[u.set][u.hit_way] >= 2);",
     "                if (0)\n                        u.direction_prediction (ctr[u.set][u.hit_way] >= 2);"),
    ("set and tag fields swapped",
     "                u.set = h >> PM_TAG_BITS;\n                u.tag = h & ((1 << PM_TAG_BITS) - 1);",
     "                u.tag = h >> PM_SET_BITS;\n                u.set = h & ((1 << PM_SET_BITS) - 1);"),
]

original = open(os.path.join(SRC, "my_predictor.h")).read()
print("| Broken rule | Appendix rows that still match | Other failed checks | test_pm exit code |")
print("|---|---:|---:|---:|")
all_caught = True
for name, old, new in MUTANTS:
    assert original.count(old) == 1, name
    with tempfile.TemporaryDirectory() as d:
        for f in ("test_pm.cc", "branch.h", "predictor.h"):
            shutil.copy(os.path.join(SRC, f), d)
        open(os.path.join(d, "my_predictor.h"), "w").write(original.replace(old, new))
        subprocess.run(["g++", "-O2", "-Wall", *FLAGS, "-o", "t", "test_pm.cc"], cwd=d, check=True)
        r = subprocess.run(["./t"], cwd=d, capture_output=True, text=True)
    rows = next(l.split()[0] for l in r.stdout.splitlines() if "rows match the PDF" in l)
    other = sum(l.strip().startswith("FAIL ") for l in r.stdout.splitlines())
    print("| %s | %s | %d | %d |" % (name, rows, other, r.returncode))
    all_caught = all_caught and r.returncode != 0
print("\nevery broken variant fails the test" if all_caught else "\nSOME BROKEN VARIANT PASSES THE TEST")
