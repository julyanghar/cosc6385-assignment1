# COSC 6385 Assignment 1, part 2: Tomasulo simulator with multiple issue

This directory holds the second part of Assignment 1 (handout `programming-tomasulo.pdf`,
not included here). We started from the course's single-issue Python simulator
(`tomasulo-python.zip`, by Qing, 2017) and added:

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
checked it are in [REPORT.md](REPORT.md).

## Requirements

Python 3, standard library only. Tested with Python 3.12.13 and 3.10.12 on Ubuntu 22.04.
`git` is needed only by `verify/compare_original.py`, which reads the original code from the
repository history.

## Run one input

```bash
cd tomasulo-python/code
python3 main.py                            # runs test_case.txt
python3 main.py ../tests/daxpy.txt         # issue width from the file (1 if not given)
python3 main.py ../tests/daxpy.txt --width 4
python3 main.py ../tests/daxpy.txt --width 4 --cdb 1 --commit-width 1
python3 main.py ../tests/pdf_sample.txt --max-cycles 40
```

`--width N` (1–4) overrides `Issue width` in the file; `--cdb N` and `--commit-width N`
override the number of CDB buses and the commit width, which otherwise follow the issue width
(REPORT.md section 1.4). `--max-cycles` (default 10000) stops a program that never ends, such
as the handout's sample. The exit status is 0 when the program finished, 1 for an input error,
and 2 when the run stopped early (cycle limit, or an invalid memory address on the committed
path).

## Input format

The handout's format. Example (`tests/memory.txt`, shortened):

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

## Output format

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

## Tests and verification

```bash
cd tomasulo-python
./run_all.sh                     # about two minutes; rewrites results/
```

`run_all.sh` writes `results/<test>_w<N>.txt` (every input in `tests/` at widths 1–4, default
setting), `results/summary.md` (cycles and IPC of every test in three CDB/commit settings) and
the logs of the scripts below, and checks that the tables in REPORT.md are current. It exits
with status 1 if anything fails; running it twice gives byte-identical files. The scripts can
also be run alone from `verify/`:

| Script | What it checks | Current result |
|---|---|---|
| `check_all.py [files]` | every test at widths 1–4 in three CDB/commit settings: same registers, memory and committed instruction sequence as a simple in-order interpreter (`reference.py`); every timing rule of REPORT.md Appendix B; printed values; 19 tables computed by hand (`tests/golden/`) | 300 runs: 288 ok, 12 prefix (`pdf_sample` never ends), 0 failed |
| `fuzz.py [N] [seed]` | the same checks on N random programs with random configurations | 2000 programs × 4 widths, 0 failed |
| `mutants.py` | makes 25 deliberate mistakes in a copy of the code; each must make a check fail | 25 of 25 caught |
| `compare_original.py` | prints the original code's tables next to ours at width 1 | differences explained in REPORT.md Appendix D |
| `report_tables.py` | prints the summary tables; `--check REPORT.md` / `--write REPORT.md` compare or rewrite the generated tables of REPORT.md section 3 | — |

## Layout

```text
README.md, REPORT.md          this file and the report
tomasulo-python/
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
