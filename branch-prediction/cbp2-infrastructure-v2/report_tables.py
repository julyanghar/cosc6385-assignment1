#!/usr/bin/env python3
# Prints the result tables of REPORT-branch-prediction.md (markdown) from the raw files in results/.
# Usage, from cbp2-infrastructure-v2/:  python3 report_tables.py
import re
import sys

RESULTS = "results/"


def read_run(name):
    """Output of ./run traces -> ({benchmark: MPKI}, average MPKI as printed by run)."""
    mpki, avg = {}, None
    for line in open(RESULTS + name + ".txt"):
        if line.startswith("average MPKI:"):
            avg = float(line.split(":")[1])
        elif line.strip():
            path, value = line.split()
            mpki[path.split("/")[1]] = float(value)
    assert len(mpki) == 20 and avg is not None, name
    return mpki, avg


def read_stats(name):
    """results/stats_*.txt -> {benchmark: dict of the pm_stats counters and the MPKI}."""
    stats = {}
    for line in open(RESULTS + name + ".txt"):
        m = re.match(r"(\S+) pm_stats cond (\d+) hit (\d+) acc_hit (\d+) bim_acc_hit (\d+) acc_miss (\d+) ([\d.]+) MPKI", line)
        cond, hit, acc_hit, bim_acc_hit, acc_miss = (int(x) for x in m.groups()[1:6])
        stats[m.group(1).split("/")[1]] = dict(cond=cond, hit=hit, acc_hit=acc_hit, bim_acc_hit=bim_acc_hit,
                                               acc_miss=acc_miss, mpki=float(m.group(7)))
    assert len(stats) == 20, name
    return stats


runs = {n: read_run(n) for n in ["B0_always_taken", "B1_bimodal_only", "B2_gshare", "R1_pm_4way", "R2_pm_2way",
                                 "S_ctr_init1", "S_hist8", "S_hist10", "S_hist12", "S_hist14"]}
stats = {w: read_stats("stats_pm_%dway" % w) for w in (4, 2)}
benchmarks = list(runs["R1_pm_4way"][0])

# consistency: the stats builds must reproduce the MPKI of R1/R2, and the
# mispredictions counted by the stats must give the same MPKI
for w, run in ((4, "R1_pm_4way"), (2, "R2_pm_2way")):
    for b in benchmarks:
        s = stats[w][b]
        assert s["mpki"] == runs[run][0][b], (w, b)
        miss = s["cond"] - s["acc_hit"] - s["acc_miss"]
        assert abs(1000.0 * miss / 1e8 - s["mpki"]) < 0.0006, (w, b)
# the averages printed by run equal the mean of the 20 printed values (up to rounding)
for n, (mpki, avg) in runs.items():
    assert abs(sum(mpki.values()) / 20 - avg) < 0.002, n
# the bimodal table is trained the same way with or without the global table, so
# B1 mispredicts exactly where the bimodal counter is wrong: on global misses (as pm)
# and on global hits (hit - bim_acc_hit).  Both stats builds must reproduce B1.
for w in (4, 2):
    for b in benchmarks:
        s = stats[w][b]
        b1_miss = s["cond"] - s["bim_acc_hit"] - s["acc_miss"]
        assert abs(1000.0 * b1_miss / 1e8 - runs["B1_bimodal_only"][0][b]) < 0.0006, (w, b)

out = sys.stdout.write

out("### Table 1: MPKI per trace\n\n")
cols = ["B0_always_taken", "B1_bimodal_only", "B2_gshare", "R1_pm_4way", "R2_pm_2way"]
out("| Trace | B0 always taken | B1 bimodal only | B2 gshare (sample) | **R1 pm 4-way** | R2 pm 2-way | R1 vs B1 |\n")
out("|---|---:|---:|---:|---:|---:|---:|\n")
for b in benchmarks:
    r1, b1 = runs["R1_pm_4way"][0][b], runs["B1_bimodal_only"][0][b]
    out("| %s | %s | **%.3f** | %s | %s%% |\n" % (
        b, " | ".join("%.3f" % runs[c][0][b] for c in cols[:3]), r1,
        "%.3f" % runs["R2_pm_2way"][0][b], "%+.1f" % (100.0 * (r1 - b1) / b1)))
r1a, b1a = runs["R1_pm_4way"][1], runs["B1_bimodal_only"][1]
out("| **average** | %s | **%.3f** | %.3f | %+.1f%% |\n\n" % (
    " | ".join("%.3f" % runs[c][1] for c in cols[:3]), r1a, runs["R2_pm_2way"][1], 100.0 * (r1a - b1a) / b1a))

out("### Table 2: where the predictions of pm come from (from the -DPM_STATS builds)\n\n")
out("| Trace | conditional branches | 4-way: global hit rate | 4-way: accuracy on hits, global / bimodal | "
    "4-way: accuracy on misses (bimodal) | 2-way: global hit rate | 2-way: accuracy on hits, global / bimodal |\n")
out("|---|---:|---:|---:|---:|---:|---:|\n")
tot = {w: dict(cond=0, hit=0, acc_hit=0, bim_acc_hit=0, acc_miss=0) for w in (4, 2)}
for b in benchmarks:
    s4, s2 = stats[4][b], stats[2][b]
    assert s4["cond"] == s2["cond"]
    for w in (4, 2):
        for k in tot[w]:
            tot[w][k] += stats[w][b][k]
    out("| %s | %d | %.1f%% | %.2f%% / %.2f%% | %.2f%% | %.1f%% | %.2f%% / %.2f%% |\n" % (
        b, s4["cond"], 100.0 * s4["hit"] / s4["cond"],
        100.0 * s4["acc_hit"] / s4["hit"], 100.0 * s4["bim_acc_hit"] / s4["hit"],
        100.0 * s4["acc_miss"] / (s4["cond"] - s4["hit"]),
        100.0 * s2["hit"] / s2["cond"], 100.0 * s2["acc_hit"] / s2["hit"], 100.0 * s2["bim_acc_hit"] / s2["hit"]))
t4, t2 = tot[4], tot[2]
out("| **all 20 traces** | %d | %.1f%% | %.2f%% / %.2f%% | %.2f%% | %.1f%% | %.2f%% / %.2f%% |\n\n" % (
    t4["cond"], 100.0 * t4["hit"] / t4["cond"],
    100.0 * t4["acc_hit"] / t4["hit"], 100.0 * t4["bim_acc_hit"] / t4["hit"],
    100.0 * t4["acc_miss"] / (t4["cond"] - t4["hit"]),
    100.0 * t2["hit"] / t2["cond"], 100.0 * t2["acc_hit"] / t2["hit"], 100.0 * t2["bim_acc_hit"] / t2["hit"]))

out("### Table 3: sensitivity of the 4-way configuration (average MPKI over the 20 traces)\n\n")
out("| Variant | Flags | average MPKI |\n|---|---|---:|\n")
for n, flags in [("S_hist8", "`-DPM_HIST_BITS=8`"), ("S_hist10", "`-DPM_HIST_BITS=10`"),
                 ("S_hist12", "`-DPM_HIST_BITS=12`"), ("S_hist14", "`-DPM_HIST_BITS=14`"),
                 ("R1_pm_4way", "none (15-bit GHR, counters start at 2)"), ("S_ctr_init1", "`-DPM_CTR_INIT=1`")]:
    out("| %s | %s | %.3f |\n" % (n, flags, runs[n][1]))
diff = [runs["S_ctr_init1"][0][b] - runs["R1_pm_4way"][0][b] for b in benchmarks]
out("\nCounter start value 1 instead of 2: per-trace MPKI change from %+.3f to %+.3f.\n" % (min(diff), max(diff)))
