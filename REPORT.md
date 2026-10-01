# Report: Pentium M hybrid branch direction predictor

**Summary.** We implemented the branch direction (taken / not taken) part of the Pentium M
predictor as the `pm_predictor` class of the CBP2 framework: a bimodal table plus a tagged,
set-associative global table whose prediction wins whenever it hits. Built as the tiny
predictor of the assignment's worked example, the same code reproduces all 22 rows of the
appendix tables, including every table state. On the 20 CBP2 traces the main configuration
(4-way global table, 3.75 KiB of state) reaches **7.758 MPKI** on average, against 10.267 for
the bimodal table alone and 86.311 for always predicting taken.

Build and run instructions are in [README.md](README.md). All numbers below come from the
files in [`results/`](branch-prediction/cbp2-infrastructure-v2/results/); the tables were
printed by [`report_tables.py`](branch-prediction/cbp2-infrastructure-v2/report_tables.py).

## 1. What was built

The code is in [`src/my_predictor.h`](branch-prediction/cbp2-infrastructure-v2/src/my_predictor.h)
(class `pm_predictor` and its parameters, about 180 lines). For every conditional branch:

```text
   branch address PC                          GHR: outcomes of the last 15 conditional
          |                                   branches before this one, newest in bit 0
          +-------------------------+                      |
          |                         |                      |
          v                         v                      v
      PC[11:0]                  PC[14:0] ------ XOR ----- GHR[14:0]
          |                                      |
          v                                      v
  +----------------+                 HASH: set = HASH[14:6], tag = HASH[5:0]
  | Bimodal table  |                             |
  | 4096 x 2-bit   |                             v
  | counters       |          +----------------------------------------------+
  +----------------+          | Global table: 512 sets x 4 ways              |
          |                   | each way: valid bit, 6-bit tag,              |
          |                   |           2-bit counter, LRU age             |
          |                   +----------------------------------------------+
          |                       |                               |
          |              counter of the hit way         hit = some valid way of the
          |                       |                           set holds the same tag
          v                       v                               |
   bimodal prediction      global prediction                     |
          |                       |                               |
          +---------> [ hit ? global : bimodal ] <----------------+
                                  |
                           final prediction
```

A 2-bit counter predicts taken when its value is 2 or 3. After the outcome is known, the
counters are trained (saturating at 0 and 3), a global miss allocates a way, and the outcome is
shifted into the GHR. Section 3 lists the exact rules.

Not built: the loop predictor, the path information register (PIR) and its hash, and branch
target prediction, which the assignment allows to skip (PDF page 2); see section 7. No
third-party cache code was used: the global table is a set of plain two-dimensional arrays.

## 2. Parameters and storage

All sizes are compile-time macros (`PM_BIM_BITS`, `PM_PC_SHIFT`, `PM_SET_BITS`, `PM_TAG_BITS`,
`PM_WAYS`, `PM_HIST_BITS`, `PM_CTR_INIT`). The defaults are the main configuration; the golden
test (section 4) builds the same code with the parameters of the worked example.

| Parameter | Main configuration | Worked example (golden test) | Source |
|---|---|---|---|
| Bimodal table | 4096 counters, index PC[11:0] | 16 counters, index PC[5:2] | PDF p. 2 and p. 6 figures; appendix p. 5-6 |
| Global table | 512 sets × 4 ways | 4 sets × 2 ways | p. 2 and p. 6 figures; appendix |
| Global entry | valid bit, 6-bit tag, 2-bit counter | valid bit, 2-bit tag, 2-bit counter | figures; appendix |
| Hash | HASH = PC[14:0] xor GHR, 15 bits | PC[5:2] xor GHR, 4 bits | **our choice** (GHR in place of the PIR); appendix |
| Set / tag | set = HASH[14:6], tag = HASH[5:0] | set = HASH[3:2], tag = HASH[1:0] | p. 2 and p. 6 figures; appendix |
| Global history (GHR) | 15 bits | 4 bits | **our choice**; appendix |
| Replacement | LRU | LRU | appendix (pages 10-11) |
| Counter start values | all counters 2 (weakly taken) | bimodal entry i: i mod 4; global set s: way 0 = s, way 1 = 3 − s | **our choice**; appendix |

Notes on the choices:

- **15-bit hash and history.** The page 2 figure XORs 15 bits of the instruction address with
  the 15-bit PIR and takes set = HASH[14:6], tag = HASH[5:0]. The page 6 figure keeps
  HASH[14:6] but draws a 14-bit BHR, which cannot produce bit 14. We use 15 bits of address
  and 15 bits of history, so every set and tag bit depends on the history. This also matches
  Uzelac and Milenković, who report a 15-bit PIR with PIR[14:6] as the global index and
  PIR[5:0] as the tag (Sections 4.1 and 6.3 of the ISPASS 2009 paper).
- **GHR instead of PIR.** The real Pentium M uses a path history, the PIR, built from
  address bits of taken conditional branches and of indirect branches. The assignment does
  not require the PIR (PDF page 2, "Highlights"); like the worked example, we use a history
  of conditional branch outcomes.
- **No address shift.** x86 instructions have variable length and branches can start at any
  byte, and the page 2 figure indexes the bimodal table with IP[11:0]. The worked example uses
  PC[5:2] only because it assumes 4-byte instructions and 8-bit addresses.
- **4 ways.** The figures show a 4-way global table; the assignment allows 2 ways. Both are the
  same code (`PM_WAYS`), so we use 4 ways and report 2 ways as a comparison (R2).
- **Counter start value 2.** It affects only the first few predictions of each counter;
  starting at 1 instead changes the average by 0.002 MPKI (section 6.4).

Storage of the implementation (LRU kept as one age per way, `log2(ways)` bits each):

| Structure | 4-way (R1), bits | 2-way (R2), bits |
|---|---:|---:|
| Bimodal: 4096 × 2 | 8,192 | 8,192 |
| Global: 512 × ways × (1 valid + 6 tag + 2 counter) | 18,432 | 9,216 |
| LRU ages: 512 × ways × log2(ways) | 4,096 | 1,024 |
| GHR | 15 | 15 |
| **Total** | **30,735 (3.75 KiB)** | **18,447 (2.25 KiB)** |

For comparison, the framework's sample gshare (baseline B2) has 32,768 2-bit counters and a
15-bit history: 65,551 bits (8.0 KiB), 2.13 times the 4-way pm.

## 3. Prediction and update rules

Sources: **PDF** = stated in the assignment text or figures; **appendix** = not stated in the
text, but shown by the worked example (pages 7-11) and checked row by row by the golden test;
**our choice** = not specified anywhere in the assignment.

| # | Rule | Source |
|---|---|---|
| R1 | Only conditional branches are looked up, trained, or shifted into the GHR. Other branches are predicted taken and change no state (the driver scores only conditional branches). | **Our choice**, as in the framework's sample gshare. Uzelac and Milenković found that unconditional branches are not allocated in the Pentium M bimodal or global predictor (Section 6.4). |
| R2 | A global hit means that some way of the selected set is valid and holds the same tag. On a hit the final prediction is that way's counter; otherwise it is the bimodal counter. | **PDF**: page 5 ("when global predictor delivers a hit, the final prediction will be determined by selecting the prediction from the global predictor") and the multiplexer in the page 6 figure. |
| R3 | The bimodal counter is trained on every conditional branch, also when the final prediction came from the global table. | **Appendix**: row 6 is a global hit, yet bimodal counter 1 goes from 1 (row 6) to 2 (row 7) on page 9. |
| R4 | On a global hit, the counter of the hit way is trained and that way becomes the most recently used. | **Appendix**: row 14 hits way 0 of set 0. On page 11 its counter goes from 1 to 0 (not taken) and the LRU bits of set 0 change from (way 0, way 1) = (1, 0) to (0, 1). |
| R5 | On a global miss a way is always allocated, whether or not the final prediction was right: the least recently used way of the set gets valid = 1 and the new tag, and becomes the most recently used. | **Appendix**: rows 7 and 17 are global misses whose bimodal prediction was correct, and rows 8 and 18 show the new entry (set 1, tag 11). |
| R6 | The allocated way keeps the counter value of the entry it replaces, and that value is then trained with the outcome. | **Appendix**: row 8 replaces way 0 of set 1, whose counter is 2; after the not-taken outcome, row 9 shows 1. |
| R7 | After the tables are trained, GHR = ((GHR << 1) \| outcome) & (2^L − 1), with L = 15 (4 in the example). | **Appendix**: GHR column (Col-4) of page 8, all 22 rows. |
| R8 | Initially way 0 is the least recently used way of every set, so an empty set fills way 0, 1, 2, 3 in that order. | **Appendix**: page 10, row 1 (the LRU bit of way 0 is 1 in every set). |

R5 and R6 differ from two common alternatives, allocating only after a misprediction and
resetting a new entry's counter to a weak state. We follow the worked example because it is
the only specification of these details in the assignment, and we did not find the allocation
policy of the global predictor stated in the ISPASS paper either. We did not evaluate the
alternatives.

`predict()` computes the bimodal index, set, tag and hit way from the state before the branch
and stores them in the `pm_update` object; `update()` uses these stored values and does not
recompute them, because the GHR it would need has changed by then.

## 4. Verification

### 4.1 Golden test: the worked example of the appendix

[`src/test_pm.cc`](branch-prediction/cbp2-infrastructure-v2/src/test_pm.cc), built with the
parameters of the worked example, loads the initial state shown in row 1 of pages 8-10 and
feeds the 22 branches of page 7 (b1 = 0x44, b2 = 0x6C, b3 = 0x90). For every row it compares with the PDF:

- before the branch: the GHR (page 8), all 16 bimodal counters (page 9), and every field of the
  global table, i.e. valid bit, tag, counter and LRU bit of both ways of all 4 sets (pages
  10-11);
- after `predict()`: the set and tag (page 8 Col-6), global hit or miss and the global
  prediction (Col-7), and the final prediction (Col-8).

The expected values in the test were taken from the text of PDF pages 8-11; where these pages
share a field (branch, outcome, set, tag, global hit, bimodal prediction), they agree with
each other. Result:

```text
appendix replay (PDF pages 7-11)
  row br  outcome GHR  set tag global final  result
    1 b1  T       0000   0  01  miss   NT     ok
    2 b3  T       0001   1  01  miss   NT     ok
  ...
    6 b1  T       1001   2  00  hit T  T      ok
  ...
   14 b2  NT      1010   0  01  hit NT NT     ok
  ...
   22 b3  T       0011   1  11  miss   T      ok
  22/22 rows match the PDF
```

On page 10-11 the "Prediction" column (Col-6) shows, on a miss, the counter of the way that is
about to be replaced (for example "NT" in row 22 while the final prediction is T); the final
prediction is in Col-8 of page 8, which is what the test compares.

### 4.2 Checks that hold for any configuration

The same test file, built with the tiny parameters and with the default 4-way parameters,
also checks:

- non-conditional branches (all flag combinations of the traces) are predicted taken and leave
  the tables and the GHR unchanged (R1);
- a counter at 0 stays 0 on not taken and a counter at 3 stays 3 on taken, for the bimodal and
  the global table, through `predict()` / `update()`;
- LRU: an empty set fills ways 0, 1, ..., W−1 in order; after using them in that order the
  victim is way 0, and after using way 0 again it is way 1; the ages always stay a permutation
  of 0..W−1. The same order is checked end to end through `predict()` / `update()` by filling
  one set with W tags, reusing the first, and inserting one more: only the second tag is
  replaced.

Both builds print `all checks passed`.

### 4.3 The test detects wrong rules

[`mutants_test_pm.py`](branch-prediction/cbp2-infrastructure-v2/mutants_test_pm.py) builds the
test against deliberately broken copies of the predictor. Every one makes the test fail:

| Broken rule | Appendix rows that still match | Other failed checks | test_pm exit code |
|---|---:|---:|---:|
| R3: bimodal not trained on global hits | 9/22 | 0 | 1 |
| R4: hit way not made most recently used | 14/22 | 2 | 1 |
| R5: allocate only when the prediction was wrong | 7/22 | 3 | 1 |
| R6: counter reset to 2 on allocation | 1/22 | 0 | 1 |
| R7: history shifted the wrong way | 1/22 | 0 | 1 |
| R8: way 1 replaced first in an empty set | 22/22 | 4 | 1 |
| R2: bimodal used even on a global hit | 17/22 | 0 | 1 |
| set and tag fields swapped | 0/22 | 2 | 1 |

The R8 variant still matches all 22 rows because the replay sets its own initial LRU state
(from page 10); the LRU checks of section 4.2 catch it.

### 4.4 Consistency of the trace runs

- Running `src/predict` on single traces (164.gzip, 256.bzip2, 300.twolf) prints the same
  values as the corresponding lines of `run`.
- Running all configurations a second time gave a byte-identical `R1_pm_4way.txt`.
- The `-DPM_STATS` builds print the same MPKI as R1 and R2 on every trace, and their
  misprediction counts reproduce those values.
- The bimodal table is trained identically with or without the global table (R3), so B1 must
  mispredict exactly on the global misses that pm mispredicts plus the global hits on which the
  bimodal counter is wrong. The counters of both stats builds reproduce every B1 value this
  way (checked in `report_tables.py` for all 20 traces).

## 5. Results

Configurations (flags in [README.md](README.md#all-configurations-of-the-report)):
**B0** the unmodified skeleton, which always predicts taken; **B1** `pm_predictor` without the
global table; **B2** the framework's sample gshare (2.13 times the storage of R1);
**R1** the main configuration; **R2** R1 with a 2-way global table.

MPKI is mispredicted conditional branch directions per 1000 instructions, where the driver
counts every trace as 100 million instructions. Because all traces have this same
denominator, the average MPKI is proportional to the total number of mispredictions over the
20 traces, so ratios of averages are ratios of total mispredictions. The column "R1 vs B1" is
(R1 − B1) / B1 of each row.

### Table 1: MPKI per trace

| Trace | B0 always taken | B1 bimodal only | B2 gshare (sample) | **R1 pm 4-way** | R2 pm 2-way | R1 vs B1 |
|---|---:|---:|---:|---:|---:|---:|
| 164.gzip | 70.025 | 15.031 | 12.473 | **12.692** | 12.951 | -15.6% |
| 175.vpr | 85.312 | 14.673 | 13.415 | **15.967** | 16.823 | +8.8% |
| 176.gcc | 86.071 | 19.313 | 11.254 | **17.999** | 19.786 | -6.8% |
| 181.mcf | 102.497 | 33.271 | 15.837 | **18.269** | 20.081 | -45.1% |
| 186.crafty | 48.651 | 13.097 | 5.837 | **9.105** | 10.818 | -30.5% |
| 197.parser | 78.421 | 15.420 | 10.008 | **10.933** | 12.615 | -29.1% |
| 201.compress | 76.983 | 9.368 | 7.831 | **8.017** | 8.635 | -14.4% |
| 202.jess | 92.343 | 8.773 | 1.562 | **2.000** | 2.554 | -77.2% |
| 205.raytrace | 109.506 | 3.704 | 2.756 | **3.597** | 4.025 | -2.9% |
| 209.db | 91.451 | 6.437 | 3.909 | **4.824** | 5.268 | -25.1% |
| 213.javac | 109.644 | 3.198 | 2.267 | **3.008** | 3.305 | -5.9% |
| 222.mpegaudio | 110.339 | 3.166 | 2.188 | **2.940** | 3.264 | -7.1% |
| 227.mtrt | 112.022 | 3.682 | 2.657 | **3.436** | 3.886 | -6.7% |
| 228.jack | 77.958 | 7.175 | 3.033 | **4.238** | 5.669 | -40.9% |
| 252.eon | 24.226 | 9.443 | 1.807 | **2.148** | 3.838 | -77.3% |
| 253.perlbmk | 66.833 | 5.848 | 2.554 | **5.084** | 7.315 | -13.1% |
| 254.gap | 75.950 | 9.760 | 3.926 | **4.333** | 5.762 | -55.6% |
| 255.vortex | 70.524 | 1.930 | 1.222 | **1.641** | 2.239 | -15.0% |
| 256.bzip2 | 178.257 | 0.113 | 0.094 | **0.112** | 0.146 | -0.9% |
| 300.twolf | 59.221 | 21.943 | 21.489 | **24.817** | 24.239 | +13.1% |
| **average** | 86.311 | 10.267 | 6.305 | **7.758** | 8.660 | -24.4% |

### Table 2: global hits and accuracy (from the `-DPM_STATS` builds)

Definitions, per trace: *global hit rate* = global hits / conditional branches;
*accuracy on hits, global / bimodal* = share of the global hits predicted correctly by the
global counter (which pm uses) / by the bimodal counter (which pm ignores on a hit);
*accuracy on misses* = share of the global misses predicted correctly (by the bimodal counter).
The last row pools all conditional branches of the 20 traces.

| Trace | conditional branches | 4-way: global hit rate | 4-way: accuracy on hits, global / bimodal | 4-way: accuracy on misses (bimodal) | 2-way: global hit rate | 2-way: accuracy on hits, global / bimodal |
|---|---:|---:|---:|---:|---:|---:|
| 164.gzip | 15114596 | 91.6% | 92.62% / 90.93% | 80.45% | 83.1% | 93.05% / 91.39% |
| 175.vpr | 12827221 | 71.7% | 88.03% / 89.44% | 86.33% | 56.1% | 86.84% / 89.82% |
| 176.gcc | 17083242 | 70.9% | 91.21% / 90.12% | 85.22% | 54.4% | 90.46% / 90.96% |
| 181.mcf | 21700420 | 85.3% | 93.68% / 85.58% | 79.38% | 77.4% | 93.62% / 85.77% |
| 186.crafty | 8927032 | 73.7% | 92.72% / 86.66% | 81.59% | 56.5% | 91.71% / 87.20% |
| 197.parser | 14190746 | 89.4% | 93.69% / 90.15% | 80.54% | 80.1% | 93.39% / 90.92% |
| 201.compress | 11764885 | 97.7% | 93.20% / 92.03% | 92.57% | 87.7% | 92.61% / 91.90% |
| 202.jess | 14154055 | 96.5% | 98.90% / 93.94% | 90.15% | 92.4% | 98.74% / 93.98% |
| 205.raytrace | 12201864 | 84.7% | 97.43% / 97.33% | 94.95% | 62.9% | 97.50% / 97.92% |
| 209.db | 13191770 | 94.4% | 96.75% / 95.45% | 89.47% | 86.7% | 96.68% / 95.66% |
| 213.javac | 12986593 | 92.0% | 97.98% / 97.82% | 94.30% | 61.0% | 97.12% / 97.26% |
| 222.mpegaudio | 13021205 | 92.4% | 97.99% / 97.81% | 94.70% | 61.2% | 97.10% / 97.22% |
| 227.mtrt | 12512685 | 88.3% | 97.60% / 97.37% | 94.67% | 66.7% | 97.65% / 97.89% |
| 228.jack | 11926271 | 91.0% | 96.97% / 94.26% | 91.19% | 75.3% | 95.94% / 94.26% |
| 252.eon | 7724960 | 93.4% | 97.49% / 87.39% | 93.30% | 76.9% | 96.55% / 87.11% |
| 253.perlbmk | 13537118 | 90.6% | 96.68% / 96.06% | 92.02% | 72.9% | 95.44% / 96.92% |
| 254.gap | 13838041 | 96.2% | 97.13% / 93.06% | 90.14% | 87.0% | 96.78% / 93.46% |
| 255.vortex | 11073761 | 95.0% | 98.74% / 98.46% | 94.33% | 84.0% | 98.14% / 98.48% |
| 256.bzip2 | 24586276 | 99.8% | 99.97% / 99.97% | 93.50% | 99.6% | 99.96% / 99.97% |
| 300.twolf | 13098893 | 48.1% | 80.97% / 85.53% | 81.13% | 32.7% | 80.00% / 85.37% |
| **all 20 traces** | 275461634 | 87.5% | 95.59% / 93.51% | 85.85% | 74.0% | 95.32% / 93.74% |

### Table 3: sensitivity of the 4-way configuration (average MPKI over the 20 traces)

| Variant | Flags | average MPKI |
|---|---|---:|
| S_hist8 | `-DPM_HIST_BITS=8` | 9.985 |
| S_hist10 | `-DPM_HIST_BITS=10` | 9.047 |
| S_hist12 | `-DPM_HIST_BITS=12` | 8.486 |
| S_hist14 | `-DPM_HIST_BITS=14` | 7.870 |
| R1_pm_4way | none (15-bit GHR, counters start at 2) | 7.758 |
| S_ctr_init1 | `-DPM_CTR_INIT=1` | 7.756 |

Counter start value 1 instead of 2: per-trace MPKI change from -0.029 to +0.036.

## 6. Analysis

### 6.1 What the global table adds

Adding the global table to the bimodal table lowers the average from 10.267 MPKI (B1) to
7.758 MPKI (R1): 24.4% fewer mispredictions in total over the 20 traces. Both are far below
always predicting taken (86.311 MPKI).

Because the bimodal table is trained the same way in B1 and R1 (rule R3, confirmed in section
4.4), the two predictors make the same predictions on every global miss. The whole difference
comes from the global hits, where R1 follows the global counter instead of the bimodal one:

```text
mispredictions(R1) − mispredictions(B1)
    = (hits where the global counter is wrong) − (hits where the bimodal counter is wrong)
```

So the global table helps exactly on the traces where, on the hits, the global counters are
more accurate than the bimodal counters (Table 2). With 4 ways this holds on 18 of the 20
traces. The gains are largest where the global counters are much better than the bimodal ones
on most branches: 252.eon (97.49% vs 87.39% on hits, 93.4% hit rate; 9.443 → 2.148 MPKI,
−77.3%), 202.jess (−77.2%), 254.gap (−55.6%), and 181.mcf with the largest absolute drop
(33.271 → 18.269 MPKI). Where the bimodal counters are already about as accurate as the global
ones on the hits, the gain is small, e.g. 256.bzip2 (99.97% for both; 0.113 → 0.112 MPKI) and
205.raytrace (97.43% vs 97.33%; −2.9%).

On two traces the global table makes things worse: 175.vpr (+8.8%) and 300.twolf (+13.1%).
There the global counters are less accurate on the hits than the bimodal counters would have
been: 88.03% vs 89.44% on 175.vpr and 80.97% vs 85.53% on 300.twolf. 300.twolf also has by far
the lowest global hit rate (48.1%). Since a hit always overrides the bimodal prediction,
these less accurate hits cost 1.295 MPKI on 175.vpr and 2.874 MPKI on 300.twolf. We did not
test why the hit accuracy is low on these traces. A possible cause, given the low hit rate, is
that many (address, history) combinations compete for the 2048 entries, so many hits find an
entry that was allocated recently with a counter inherited from another branch (rule R6).

### 6.2 4-way versus 2-way global table

The 2-way table (R2) averages 8.660 MPKI, so the 4-way table has 10.4% fewer mispredictions in
total, at 1.67 times the storage (30,735 vs 18,447 bits). R2 is worse than R1 on 19 of the 20
traces. With half the ways, the global hit rate over all conditional branches falls from 87.5%
to 74.0%, and the global counters lose their advantage on more traces: on the hits of 10 of the
20 traces they are less accurate than the bimodal counters (Table 2, last column), and on
exactly these 10 traces R2 has a higher MPKI than B1 (Table 1). R2 still beats B1 on average
(8.660 vs 10.267 MPKI) because of the large gains on traces such as 181.mcf, 202.jess and
252.eon.

The one trace where 2-way is better than 4-way is 300.twolf (24.239 vs 24.817 MPKI). This
follows from the same accounting: on 300.twolf a global hit is less accurate than the bimodal
counter, and the 2-way table hits on fewer branches (32.7% instead of 48.1%), so fewer
predictions are overridden.

### 6.3 Comparison with the sample gshare

The framework's sample gshare (B2) averages 6.305 MPKI and is better than R1 on all 20 traces.
This is not a comparison at equal cost: B2 has 65,551 bits of state, 2.13 times R1. We did
not run a gshare of R1's size, so these results do not tell whether the hybrid organization or
the larger table explains the difference.

### 6.4 History length and counter start value

The average MPKI falls with every longer history we tried: 9.985 (8 bits), 9.047 (10), 8.486
(12), 7.870 (14) and 7.758 (15 bits, R1). 15 bits is the longest history that the 15-bit hash
can use. The best length differs per trace, however: on 9 of the 20 traces a history shorter
than 15 bits gives a lower MPKI (300.twolf: 23.417 MPKI with 8 bits vs 24.817 with 15).

Starting all counters at 1 instead of 2 changes the average from 7.758 to 7.756 MPKI, and no
trace by more than 0.036 MPKI. The start value is forgotten quickly: which counters are read
and trained, and with which outcomes, does not depend on counter values, so in both runs each
counter receives the same sequence of updates. Its values in the two runs differ by at most 1
and become equal the first time an update pushes the counter against 0 or 3; counters are
never reset afterwards (rule R6). The 6,144 counters (4,096 bimodal, 2,048 global) are few
compared with the 7.7 to 24.6 million conditional branches of each trace.

## 7. Omissions and deviations

- **Not implemented**, as allowed by the assignment (PDF page 2): the loop predictor, the PIR
  and its hash with the instruction address, and branch target prediction
  (`target_prediction(0)`, as in the skeleton). The extra-credit `cpm_predictor` (complete
  Pentium M unit) is not implemented.
- **GHR instead of PIR.** The real predictor's history is a path history that also includes
  indirect branches; ours records the outcomes of conditional branches only (rule R1).
- **Figure inconsistency.** The page 6 figure draws a 14-bit BHR but indexes with HASH[14:6];
  we use a 15-bit history and hash (section 2).
- **Allocation and counter rules** follow the worked example (R5, R6). Alternatives such as
  allocating only after a misprediction were not evaluated.
- **LRU** is implemented with one age value per way (true LRU). The page 2 figure gives the
  replacement policy only for the BTB (pseudo-LRU); the worked example uses LRU.
- **Model timing.** As in the framework, each branch is trained immediately after its
  prediction; there is no pipeline delay or speculative history update.

## 8. References and reused code

1. Assignment 1: Branch Predictor Implementation, COSC 6385
   ([`programming-branch-predictor.pdf`](branch-prediction/programming-branch-predictor.pdf)),
   including the worked example in Appendix B (pages 5-11).
2. V. Uzelac and A. Milenković, "Experiment Flows and Microbenchmarks for Reverse Engineering
   of Branch Predictor Structures," IEEE International Symposium on Performance Analysis of
   Systems and Software (ISPASS), 2009.
   <http://www.ece.uah.edu/~milenka/docs/vuam_ispass09.pdf>
3. D. A. Jiménez, CBP2 branch prediction infrastructure (`cbp2-infrastructure-v2`):
   the simulation driver, trace reader, traces, `run` script and the sample `gshare_predictor`,
   used unchanged except for the `PREDICTOR` macro in `predict.cc`.
   <https://people.engr.tamu.edu/djimenez/taco/utsa-www/cs5513/competition/>

No other code was reused. In particular, no C++ cache implementation was used (the assignment
allowed one, e.g. the L1-Cache-Simulator it links to); the 2-bit counter update follows the
style of the sample gshare in the same file.
