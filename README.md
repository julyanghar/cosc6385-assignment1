# COSC 6385 Assignment 1

This repository holds both parts of Assignment 1. Each part has its own directory and its own
report in the repository root; this README describes how to build, run and check each part.

| Part | Handout (not included here) | Code | Report | Main result |
|---|---|---|---|---|
| 1. Pentium M hybrid branch direction predictor | `programming-branch-predictor.pdf` | [`branch-prediction/`](branch-prediction/) | [REPORT-branch-prediction.md](REPORT-branch-prediction.md) ([PDF](REPORT-branch-prediction.pdf)) | **7.758 MPKI** averaged over the 20 CBP2 traces |
| 2. Tomasulo simulator with multiple issue | `programming-tomasulo.pdf` | [`o3-simulator/`](o3-simulator/) | [REPORT-o3-simulator.md](REPORT-o3-simulator.md) ([PDF](REPORT-o3-simulator.pdf)) | 1 to 4 instructions issued per cycle; eight independent instructions take 11 cycles at width 1 and 5 at width 4 |

## Contents

- [Part 1: Pentium M hybrid branch direction predictor](#part-1-pentium-m-hybrid-branch-direction-predictor)
- [Part 2: Tomasulo simulator with multiple issue](#part-2-tomasulo-simulator-with-multiple-issue)
- [Repository layout](#repository-layout)
- [Line endings](#line-endings)

## Part 1: Pentium M hybrid branch direction predictor

This part implements the branch direction predictor asked for in the first handout
(`programming-branch-predictor.pdf`): a hybrid of a bimodal predictor and a tagged,
set-associative global predictor modeled on the Pentium M. It is written as the
`pm_predictor` class of the CBP2 branch prediction framework and evaluated on the
framework's 20 traces.

Main result: **7.758 MPKI** averaged over the 20 traces (bimodal predictor alone:
10.267; always predicting taken: 86.311). Design, verification and analysis are in
[REPORT-branch-prediction.md](REPORT-branch-prediction.md).

### Files (part 1)

```text
branch-prediction/
  cbp2-infrastructure-v2/               CBP2 framework with our predictor
    src/my_predictor.h          pm_predictor (our code); gshare_predictor and cpm_predictor came with the framework
    src/test_pm.cc              our tests: replay of the PDF's worked example, LRU and counter checks
    src/predict.cc              framework driver; we only added the PREDICTOR macro (see below)
    run                         framework script: MPKI of every trace and their average
    run_configs.sh              rebuilds and runs every configuration of the report into results/
    report_tables.py            prints the result tables of REPORT-branch-prediction.md from results/ and cross-checks them
    mutants_test_pm.py          checks that test_pm fails for deliberately broken predictors
    results/                    raw outputs, one file per configuration
    traces/                     the 20 CBP2 traces, unchanged
```

Everything else in `cbp2-infrastructure-v2/` (`trace.cc`, `trace.h`, `branch.h`,
`predictor.h`, `Makefile`, `run`, `run_extra`, `doc/`) is unchanged.

### Requirements (part 1)

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

### Build and test

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

### Run

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

### All configurations of the report

```bash
cd branch-prediction/cbp2-infrastructure-v2
bash run_configs.sh        # about 5 minutes; rewrites every results/*.txt except B0
python3 report_tables.py   # prints the tables of REPORT-branch-prediction.md (Python 3, standard library only)
python3 mutants_test_pm.py # the table of REPORT-branch-prediction.md section 4.3
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

B0 comes from the skeleton `my_predictor.h` of the repository's first commit:

```bash
cd branch-prediction/cbp2-infrastructure-v2
git show $(git rev-list --max-parents=0 HEAD):branch-prediction/cbp2-infrastructure-v2/src/my_predictor.h > src/my_predictor.h
(cd src && make -B) && csh ./run traces > results/B0_always_taken.txt
git checkout src/my_predictor.h && (cd src && make -B)
```

The `PREDICTOR` macro in `src/predict.cc` names the predictor class the driver creates.
It defaults to `pm_predictor`, so `make` and `run` work exactly as in the original framework.

### Traces and framework

The framework and the 20 traces are the CBP2 branch prediction infrastructure
(`cbp2-infrastructure-v2`) by Daniel A. Jiménez, as distributed on the course website.
The same `cbp2-infrastructure-v2.tar` is on
<https://people.engr.tamu.edu/djimenez/taco/utsa-www/cs5513/competition/>.
The traces are committed unchanged (7.7 MB in total), so `run` works right after cloning.

## Part 2: Tomasulo simulator with multiple issue

This part answers the second handout (`programming-tomasulo.pdf`). We started from the
course's single-issue Python simulator (`tomasulo-python.zip`, by Qing, 2017) and added:

- **multiple issue**: 1 to 4 instructions per cycle, in program order (`Issue width = N`
  in the input file, or `--width N`);
- **branch prediction**: a 1-bit predictor in an 8-entry BTB, speculative execution, and
  recovery from mispredictions (the original code stopped fetching at every branch);
- **the handout's memory**: 256 bytes, `Ld` and `Sd` moving single-precision values, loads
  that do not wait for stores with unknown addresses, and a check that executes such a load
  again when a store turns out to write its address;
- reading the configuration, initial values and program from the input file, and printing
  the registers and non-zero memory at the end;
- fixes for five bugs of the original code, each with an input that shows it.

What we changed, the results for issue widths 1–4, the rules the simulator follows and how we
checked it are in [REPORT-o3-simulator.md](REPORT-o3-simulator.md).

### Files (part 2)

```text
o3-simulator/tomasulo-python/
  README.md, data_structure.txt   from the original zip, updated
  code/                       the simulator: the original files, changed, plus squash.py
    test_case.txt             default input (the original's program and configuration)
  tests/                      25 inputs; tests/golden/ hand-computed tables
  verify/                     reference.py, check_all.py, fuzz.py, mutants.py,
                              compare_original.py, report_tables.py
  results/                    outputs and logs written by run_all.sh
  run_all.sh
```

The first commit that touches `o3-simulator/` adds the zip's files unchanged, so
`git diff <that commit> -- o3-simulator/tomasulo-python/code` shows every change we made.

### Requirements (part 2)

Python 3, standard library only. Tested with Python 3.12.13 and 3.10.12 on Ubuntu 22.04.
`git` is needed only by `verify/compare_original.py`, which reads the original code from the
repository history.

### Run one input

```bash
cd o3-simulator/tomasulo-python/code
python3 main.py                            # runs test_case.txt
python3 main.py ../tests/daxpy.txt         # issue width from the file (1 if not given)
python3 main.py ../tests/daxpy.txt --width 4
python3 main.py ../tests/daxpy.txt --width 4 --cdb 1 --commit-width 1
python3 main.py ../tests/pdf_sample.txt --max-cycles 40
```

`--width N` (1–4) overrides `Issue width` in the file; `--cdb N` and `--commit-width N`
override the number of CDB buses and the commit width, which otherwise follow the issue width
(REPORT-o3-simulator.md section 1.4). `--max-cycles` (default 10000) stops a program that never
ends, such as the handout's sample. The exit status is 0 when the program finished, 1 for an
input error, and 2 when the run stopped early (cycle limit, or an invalid memory address on the
committed path).

### Input format

The handout's format. Example (`o3-simulator/tomasulo-python/tests/memory.txt`, shortened):

```text
               # of rs   Cycles in EX   Cycles in Mem   # of FUs
Integer adder   2         2                              1
FP adder        2         2                              1
FP multiplier   1         6                              1
Load/store unit 6         1              3               1

ROB entries = 16
R1=8, F1=1.5, F2=2.5
Mem[0]=7.0, Mem[8]=10.0, Mem[12]=20.0

Mult.d F6, F1, F2
Sd F1, 0(R1)
Ld F3, 0(R1)
```

- `#` starts a comment (the table header is one); blank lines are ignored.
- The four table rows are found by their names. `Integer adder`, `FP adder` and
  `FP multiplier` take 3 numbers (reservation stations, EX cycles, FUs); `Load/store unit`
  takes 4 (load/store queue entries, address calculation cycles, memory cycles, address adders).
- `ROB entries = N`, `Issue width = N` (1–4, default 1), and two optional lines we added:
  `CDB buses = N` and `Commit width = N` (both default to the issue width).
- Initial values: `R1=10, F2=30.1` and `Mem[4]=1, Mem[8]=2`. Everything else starts at 0;
  R0 is always 0. Memory has 256 bytes. `Mem[a]=v` stores *v* as a 4-byte single-precision
  value at bytes *a* to *a*+3, so *a* can be 0 to 252 (also not a multiple of 4; the handout's
  sample loads from address 18).
- Instructions: `Ld`, `Sd`, `Beq`, `Bne`, `Add`, `Addi`, `Sub`, `Add.d`, `Sub.d`, `Mult.d`, as
  in the handout. Commas are optional and case does not matter. A branch offset counts
  instructions: the target of the instruction at index *i* is *i* + 1 + offset.
- A missing table row or setting takes the value of the handout's sample input. The output
  starts with the configuration that was actually used.

### Output format

The first rows for that input (issue width 1):

```text
                   ISSUE   EX          MEM         WB      COMMIT  NOTE
Mult.d F6, F1, F2  [1]     [2, 7]      []          [8]     [9]
Sd F1, 0(R1)       [2]     [3, 3]      [11, 13]    []      [11]
Ld F3, 0(R1)       [3]     [4, 4]      [5, 5]      [6]     [12]    forwarded
```

One row per committed instruction, in program order; an instruction executed several times by
a loop appears once per execution. Wrong-path instructions that were squashed are not listed.
Cycles are written as in the original code: `[first, last]` for EX and MEM, `[cycle]` for
the others, `[]` when the instruction has no such stage.

- EX of a load or store is its address calculation. MEM of a load is the memory read, or one
  cycle if the value was forwarded from a store. MEM of a store is its memory write, which
  starts when the store commits.
- NOTE: `taken` / `not taken` and `mispredicted` for branches; `forwarded` for a load that got
  its value from a store; `replayed` for a load executed again after a memory-order violation.

Then come the 32 integer and 32 FP registers (8 per row) and the non-zero memory words (the 64
words at addresses 0, 4, ..., 252, each read as a single-precision value). Every value is
printed with the fewest digits that read back as exactly the stored number: FP registers hold
Python floats (for example `1e-07` or `3.4000000953674316`), memory words are single precision
(`3.4`). The last line gives cycles, committed instructions, IPC (committed instructions per
cycle), branches, mispredicted branches, memory-order violations and squashed instructions.

### Tests and verification

```bash
cd o3-simulator/tomasulo-python
./run_all.sh                     # about two minutes; rewrites results/
```

`run_all.sh` writes `results/<test>_w<N>.txt` (every input in `tests/` at widths 1–4, default
setting), `results/summary.md` (cycles and IPC of every test in three CDB/commit settings) and
the logs of the scripts below, and checks that the generated parts of REPORT-o3-simulator.md
are current. It exits with status 1 if anything fails; running it twice gives byte-identical
files. The scripts can also be run alone from `verify/`:

| Script | What it checks | Current result |
|---|---|---|
| `check_all.py [files]` | every test at widths 1–4 in three CDB/commit settings: same registers, memory and committed instruction sequence as a simple in-order interpreter (`reference.py`); the limits and orderings of the timing rules in REPORT-o3-simulator.md Appendix B; printed values; 19 tables computed by hand (`tests/golden/`) | 300 runs: 288 ok, 12 prefix (`pdf_sample` never ends), 0 failed |
| `fuzz.py [N] [seed]` | the same checks on N random programs with random configurations | 2000 programs × 4 widths, 0 failed |
| `mutants.py` | makes 25 deliberate mistakes in a copy of the code; each must make a check fail | 25 of 25 caught |
| `compare_original.py` | prints the original code's tables next to ours at width 1 | differences explained in REPORT-o3-simulator.md Appendix D |
| `report_tables.py` | prints the summary tables; `--write ../../../REPORT-o3-simulator.md` writes the parts of the report that quote run results (the paragraph of section 1.4 on one CDB, the tables and notes of 3.2, the test cases 3.3–3.10, section 3.11), computing every number in them; `--check ../../../REPORT-o3-simulator.md` fails if those parts differ from what it writes now. Numbers elsewhere in the report are written by hand and not checked by it | report up to date |

`REPORT-o3-simulator.pdf` is `REPORT-o3-simulator.md` printed to an A4 PDF with the same styles
and page layout as `REPORT-branch-prediction.pdf` (those of the VS Code extension "Markdown
PDF"); its links to files open them on GitHub. `run_all.sh` does not regenerate it.

## Repository layout

```text
README.md                         this file
REPORT-branch-prediction.md       report of part 1 (and REPORT-branch-prediction.pdf)
REPORT-o3-simulator.md            report of part 2 (and REPORT-o3-simulator.pdf)
branch-prediction/                part 1, see "Files (part 1)"
o3-simulator/                     part 2, see "Files (part 2)"
.gitattributes, .gitignore
```

## Line endings

`.gitattributes` makes Git check out text files with LF line endings on every platform:
with CRLF endings (for example Git on Windows with `core.autocrlf=true`) the csh scripts of
part 1 and `run_all.sh` of part 2 stop working.
