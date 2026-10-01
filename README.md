# COSC 6385 Assignment 1: Pentium M hybrid branch direction predictor

This repository implements the branch direction predictor asked for in
[the assignment](branch-prediction/programming-branch-predictor.pdf): a hybrid of a
bimodal predictor and a tagged, set-associative global predictor modeled on the
Pentium M. It is written as the `pm_predictor` class of the CBP2 branch prediction
framework and evaluated on the framework's 20 traces.

Main result: **7.758 MPKI** averaged over the 20 traces (bimodal predictor alone:
10.267; always predicting taken: 86.311). Design, verification and analysis are in
[REPORT.md](REPORT.md).

## Repository layout

```text
README.md                       this file
REPORT.md                       the report
branch-prediction/
  programming-branch-predictor.pdf      the assignment
  cbp2-infrastructure-v2/               CBP2 framework with our predictor
    src/my_predictor.h          pm_predictor (our code); gshare_predictor and cpm_predictor came with the framework
    src/test_pm.cc              our tests: replay of the PDF's worked example, LRU and counter checks
    src/predict.cc              framework driver; we only added the PREDICTOR macro (see below)
    run                         framework script: MPKI of every trace and their average
    run_configs.sh              rebuilds and runs every configuration of the report into results/
    report_tables.py            prints the result tables of REPORT.md from results/ and cross-checks them
    mutants_test_pm.py          checks that test_pm fails for deliberately broken predictors
    results/                    raw outputs, one file per configuration
    traces/                     the 20 CBP2 traces, unchanged
  assignment-explained.md, completion-plan.md   working notes (in Chinese)
  cbp2-infrastructure-v2.zip, milenkovic_WDDD02.pdf   course downloads, not needed to build or run
branch-prediction.zip           course download, not needed to build or run
```

Everything else in `cbp2-infrastructure-v2/` (`trace.cc`, `trace.h`, `branch.h`,
`predictor.h`, `Makefile`, `run`, `run_extra`, `doc/`) is unchanged.

## Requirements

Tested on Ubuntu 22.04.5 LTS (x86-64) with:

| Tool | Why |
|---|---|
| g++ 11.4.0, GNU Make 4.3 | build |
| `bzip2` at `/usr/bin/bzip2` | the traces are `.bz2` files and `src/trace.h` calls `/usr/bin/bzip2` |
| `csh`, `dc` | only for the framework's `run` script (a csh script that sums the MPKI values with dc) |

If `csh` and `dc` are missing and you cannot install packages system-wide, unpack the
Ubuntu packages into your home directory. This is how the results here were produced:

```bash
mkdir -p ~/cbp2-tools && cd ~/cbp2-tools
apt-get download csh dc
for f in *.deb; do dpkg -x "$f" root; done
mkdir -p bin && ln -sf ../root/bin/bsd-csh bin/csh && ln -sf ../root/usr/bin/dc bin/dc
export PATH=~/cbp2-tools/bin:$PATH
```

`run` starts with `#!/bin/csh`. Where `/bin/csh` does not exist, call it as
`csh ./run traces`, as all commands below do. Where it exists, `./run traces` is the same.

## Build and test

```bash
cd branch-prediction/cbp2-infrastructure-v2/src
make            # builds predict (our predictor) and predict_extra_credit (untouched)

# golden test: the tiny predictor of the PDF's worked example (appendix, pages 5-11)
g++ -O2 -Wall -DPM_BIM_BITS=4 -DPM_PC_SHIFT=2 -DPM_SET_BITS=2 -DPM_TAG_BITS=2 -DPM_WAYS=2 -DPM_HIST_BITS=4 -o test_pm test_pm.cc
./test_pm       # prints the 22 rows, "22/22 rows match the PDF", ..., "all checks passed"

# the counter and LRU checks on the default (4-way) predictor
g++ -O2 -Wall -o test_pm4 test_pm.cc
./test_pm4      # "all checks passed"
```

`make` prints 8 warnings, all from the framework's `trace.cc` and `trace.h`
(`-Wwrite-strings`, `-Wunused-result`), the same 8 as for the unmodified framework.

## Run

```bash
cd branch-prediction/cbp2-infrastructure-v2
./src/predict traces/164.gzip/gzip.trace.bz2     # one trace; prints "12.692 MPKI"
csh ./run traces                                  # all 20 traces, about 30 seconds
```

`run` prints one line per trace (trace file, MPKI) and then `average MPKI:`, the
arithmetic mean of the 20 values. MPKI is mispredictions per 1000 instructions:
`1000 * (mispredicted conditional branch directions) / 100,000,000`, because the driver
(`src/predict.cc`) counts every trace as exactly 100 million instructions. It is not a
misprediction rate; its denominator is instructions, not branches.

## All configurations of the report

```bash
cd branch-prediction/cbp2-infrastructure-v2
bash run_configs.sh        # about 5 minutes; rewrites every results/*.txt except B0
python3 report_tables.py   # prints the tables of REPORT.md (Python 3, standard library only)
python3 mutants_test_pm.py # the table of REPORT.md section 4.3
```

`run_configs.sh` rebuilds `src/predict` with extra compiler flags for each configuration
(`make -B predict CXXFLAGS="-g -O3 -Wall <flags>"`; `-B` because make cannot see a change
of flags), runs `csh ./run traces`, and finally rebuilds the default predictor.

| `results/` file | Predictor | Flags added to `-g -O3 -Wall` |
|---|---|---|
| `B0_always_taken.txt` | unmodified skeleton: always predicts taken | none; see below |
| `B1_bimodal_only.txt` | `pm_predictor` without the global table | `-DPM_USE_GLOBAL=0` |
| `B2_gshare.txt` | the framework's sample gshare (32768 counters, 15-bit history) | `-DPREDICTOR=gshare_predictor` |
| `R1_pm_4way.txt` | **main result**: `pm_predictor`, 4-way global table | none |
| `R2_pm_2way.txt` | `pm_predictor`, 2-way global table | `-DPM_WAYS=2` |
| `S_hist8.txt` ... `S_hist14.txt` | R1 with a shorter global history | `-DPM_HIST_BITS=8` (10, 12, 14) |
| `S_ctr_init1.txt` | R1 with all counters starting at 1 instead of 2 | `-DPM_CTR_INIT=1` |
| `stats_pm_4way.txt`, `stats_pm_2way.txt` | R1 / R2 with diagnostic counters, one line per trace | `-DPM_STATS` (and `-DPM_WAYS=2`) |

B0 comes from the skeleton `my_predictor.h` of the first commit:

```bash
cd branch-prediction/cbp2-infrastructure-v2
git show 24ff250:branch-prediction/cbp2-infrastructure-v2/src/my_predictor.h > src/my_predictor.h
(cd src && make -B) && csh ./run traces > results/B0_always_taken.txt
git checkout src/my_predictor.h && (cd src && make -B)
```

The `PREDICTOR` macro in `src/predict.cc` names the predictor class the driver creates.
It defaults to `pm_predictor`, so `make` and `run` work exactly as in the original framework.

## Traces and framework

The framework and the 20 traces are the CBP2 branch prediction infrastructure
(`cbp2-infrastructure-v2`) by Daniel A. Jiménez, as distributed on the course website.
The same `cbp2-infrastructure-v2.tar` is on
<https://people.engr.tamu.edu/djimenez/taco/utsa-www/cs5513/competition/>.
The traces are committed unchanged (7.4 MB), so `run` works right after cloning.

`.gitattributes` makes Git check out text files with LF line endings on every platform:
with CRLF endings (for example Git on Windows with `core.autocrlf=true`) the csh scripts
stop working.
