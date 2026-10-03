# Report: multiple issue for the Tomasulo simulator

## TL;DR

We started from the course's single-issue Python simulator (`tomasulo-python.zip`) and made it
issue 1 to 4 instructions per cycle, in program order. We also added the branch unit the
handout describes: a 1-bit predictor with an 8-entry BTB, speculative execution past branches,
and recovery when a prediction is wrong. The original code had no branch prediction: it
stopped fetching at every branch.

Before adding anything, we ran the original code on small inputs. It computed a wrong
register value, let stores write memory before older instructions committed, lost a memory
write at the end of a run, shortened some multiplications by one cycle, and crashed on a
small loop (section 2). We fixed these first, because multiple issue on top of them would give
meaningless numbers.

We checked the result four ways (section 5). Every test input, at every issue width, ends with
the same registers and memory as a simple one-instruction-at-a-time interpreter. A separate
checker tests the timing limits and orderings of section 4 on every instruction. 16 instruction tables
computed by hand match exactly. 2000 random programs pass the same checks at all four widths.
19 deliberate mistakes in the code are each caught by at least one of these checks.

How much a wider issue helps depends on the program (section 6). Eight independent
instructions finish in 11 cycles at width 1 and 5 cycles at width 4. A loop over an array
(DAXPY, 28 instructions) goes from 41 to 31 cycles. A chain of dependent instructions stays at
22 cycles, and with a single CDB the eight independent instructions stay at 11.

## Contents

- [1. Terms](#1-terms)
- [2. Problems in the original code](#2-problems-in-the-original-code)
- [3. What we changed](#3-what-we-changed)
- [4. The rules the simulator follows](#4-the-rules-the-simulator-follows)
- [5. Verification](#5-verification)
- [6. Results under different issue widths](#6-results-under-different-issue-widths)
- [7. Comparison with the sample report](#7-comparison-with-the-sample-report)
- [8. What works, limitations and deviations](#8-what-works-limitations-and-deviations)

How to run everything is in [README.md](README.md). All numbers below come from the files in
[`tomasulo-python/results/`](tomasulo-python/results/), written by
[`run_all.sh`](tomasulo-python/run_all.sh). "The handout" means the assignment PDF
(`programming-tomasulo.pdf`), which is not included in this repository.

## 1. Terms

- **Issue width** *W*: how many instructions can issue (be fetched, decoded and put into a
  reservation station or the load/store queue) in one cycle. They issue in program order.
- **ROB** (reorder buffer): holds every issued instruction until it commits. Instructions
  commit in program order; only then do they change the architectural registers or memory.
- **RAT** (register alias table): for each register, either its value or the ROB tag of the
  instruction that will produce it.
- **CDB** (common data bus): carries a result to the ROB, the RAT and every waiting
  instruction. This step is WB.
- **Squash**: removing the instructions fetched after a mispredicted branch (the *wrong path*).
- **IPC**: committed instructions divided by cycles.

## 2. Problems in the original code

We copied the original code, added only a few lines at the end of `main.py` to print the final
registers and memory, and ran it on small programs. Its configuration is fixed in `main.py`
(FP multiply 15 cycles, FP add 4, memory 5; R1 = 12, F20 = 3.0). Each program below is in
`tomasulo-python/tests/bugN_*.txt` with that configuration, and
[`compare_original.py`](tomasulo-python/verify/compare_original.py) prints the original's table
next to ours (section 5.6).

| # | Program | Original code | Correct | Cause in the original code |
|---|---|---|---|---|
| B1 | `Mult.d F6 F20 F20`, `Mult.d F2 F20 F20`, `Add.d F2 F20 F20`, three `Mult.d` that need F6, `Add.d F4 F2 F2` | F4 = 18.0 | F4 = 12.0 | `wb.py` wrote every result into the RAT. The slow `Mult.d F2` finished after the newer `Add.d F2` and replaced its RAT entry with 9.0; the last `Add.d` issued later and read 9.0 |
| B2 | `Mult.d F2 F20 F20`, `Sd F20 0(R1)`, `Add.d F4 F2 F2` | the store commits and writes memory in cycles 4–8; the older `Mult.d` commits in cycle 18 | the store commits after the `Mult.d` | `mem.py` sent a store to memory as soon as it was first in the load/store queue with its address and data. The check meant to stop this, `check_if_sd_committable`, was used without being called, so it was always true |
| B3 | `Ld F8 0(R2)`, `Sd F20 4(R1)`, `Ld F2 4(R1)` | the second load computes its address and gets the forwarded value in the same cycle (EX [4, 4], MEM [4]); the run stops in cycle 9 while the store writes memory until cycle 12, so address 16 is never written | forwarding one cycle after the address; address 16 holds 3.0 at the end | `mem` ran after `exe` in the same cycle and saw the new address; the main loop stopped when the ROB was empty |
| B4 | `Mult.d F2 F20 F20`, `Ld F4 0(R1)`, `Mult.d F6 F4 F20` | the first `Mult.d` takes 14 cycles (EX [2, 15]) | 15 cycles | when a waiting instruction entered a pipelined unit, `exe.py` called `fu_exe` a second time in the same cycle, which moved every instruction in that unit forward again (the sample report found this too) |
| B5 | `Addi R1 R1 -4`, `Bne R1 R0 -8` (offset in bytes; `-2` in our format), `Add.d F4 F20 F20` | `IndexError` in `commit.py` | runs; R1 = 0, F4 = 6.0 | `commit` read `ROB[0]` after the branch had emptied the ROB |

Reading the code (not shown by a run) we also found: a reservation station chose the
instruction with the lowest station number, not the oldest; the integer adder was modelled as
pipelined; R0 could be renamed and written; the "# of FUs" column was ignored; and every data
structure was a new `namedtuple` *class* per entry, with values stored as class attributes, so an
unset field read back as a descriptor object instead of `None`.

The original code also did not read its input file: the configuration was fixed in `main.py`,
the program came from `code.in`, and `test_case.txt` was never read. It accepted only
`Bne` (offset in bytes), no commas, and printed no registers or memory.

## 3. What we changed

We kept the original's files, function names, data structure fields and the order in which the
five stages run in each cycle (issue, exe, mem, wb, commit). The diff against the original is
`git diff` from the commit that added it (see README). Per file:

| File | Change |
|---|---|
| [`init.py`](tomasulo-python/code/init.py) | Plain classes instead of `namedtuple` classes. Input file parser ([`read_input`](tomasulo-python/code/init.py#L196)). [`State`](tomasulo-python/code/init.py#L257): one object holding the whole machine, passed to every stage instead of up to 16 arguments. BTB. |
| [`issue.py`](tomasulo-python/code/issue.py) | Up to *W* instructions per cycle ([`issue`](tomasulo-python/code/issue.py#L122)); `Beq`; branch prediction ([`predict_branch`](tomasulo-python/code/issue.py#L115)); R0 is never renamed. |
| [`exe.py`](tomasulo-python/code/exe.py) | Several FUs per type; pipelined and unpipelined units; oldest-first dispatch; the second `fu_exe` call (B4) is gone. Branches are resolved at the end of EX and train the BTB; a misprediction calls `squash`. |
| [`mem.py`](tomasulo-python/code/mem.py) | Loads only (stores write at commit, B2): forwarding from the youngest older store with the same address, waiting while an older store has no address, memory access (B3). |
| [`wb.py`](tomasulo-python/code/wb.py) | Up to *N* CDB broadcasts per cycle; the RAT takes a value only if it still maps the register to that tag (B1). |
| [`commit.py`](tomasulo-python/code/commit.py) | Up to *W* commits per cycle; stores write memory here; branches get a commit cycle; no crash on an empty ROB (B5). |
| [`squash.py`](tomasulo-python/code/squash.py) (new) | Misprediction recovery. |
| [`main.py`](tomasulo-python/code/main.py) | Reads the input file; the run ends only when nothing is left to fetch, the ROB is empty and the last store has finished writing (B3); `simulate()` for the test scripts. |
| [`print_status.py`](tomasulo-python/code/print_status.py) | Prints the configuration, the instruction table, registers, non-zero memory and a summary. |

The core of multiple issue is a loop around the original single-instruction issue. It stops
at the first instruction that cannot issue, so later instructions never pass it:

```python
def issue(cycle, st):
    if cycle < st.fetch_resume:          # recovering from a misprediction
        return
    for _ in range(st.issue_width):
        if not (0 <= st.PC < len(st.instructions)):
            return
        ins = st.instructions[st.PC]
        if len(st.ROB) >= st.size_ROB:   # structural hazard: stop here
            return
        ...                              # same for the reservation station / load-store queue
        rob = put_ins_into_ROB(st, cycle, ins)
        ...                              # reservation station or queue, then RAT
        if ins.op in ('Beq', 'Bne'):
            rob.pred_next = predict_branch(st, st.PC)
            st.PC = rob.pred_next
            if rob.pred_next != rob.PC + 1:
                return                   # predicted taken: the target is fetched next cycle
        else:
            st.PC += 1
```

WB and commit got the same kind of loop, limited by the number of CDB buses and the commit
width. Instructions issued in the same cycle can depend on each other: they are renamed one
after another, so the second one already sees the first one's ROB tag in the RAT.

Recovery from a misprediction ([`squash`](tomasulo-python/code/squash.py#L15)) does the
handout's three actions and removes the wrong-path instructions from every other place they
can be:

```python
def squash(st, branch, cycle):
    # 1. ROB: drop every entry younger than the branch
    # 2. reservation stations (and their wait-for tags), load/store queue,
    #    instructions in the FUs, results waiting for a CDB, a load using the memory
    # 3. RAT: start from the architectural registers, then walk the remaining ROB
    #    entries oldest to youngest: a register maps to its youngest producer
    #    (its value if already broadcast, else its tag)
    st.PC = branch.actual_next
    st.fetch_resume = cycle + 2          # handout: detected in cycle n, fetch in n+2
```

Rebuilding the RAT from the ROB needs no saved copies (checkpoints). After the squash every ROB
entry is older than the branch. For each register, the youngest of them that writes it is the
producer the RAT pointed to when the branch issued. If that producer has broadcast since, we
store its value; if it has committed since, the architectural register holds its value. Either
way, a later instruction gets the same value it would have got through the tag.

## 4. The rules the simulator follows

Each rule says where it comes from: **Handout** (stated in the assignment PDF), **Original**
(what the original code does, kept so that width 1 stays close to it), or **Ours** (not
specified, or the original was wrong; our choice). The checker of section 5.2 tests the limits
and orderings in these rules on every committed instruction; the policies (which instruction
goes first) are tested by the hand-computed tables of section 5.3.

### 4.1 Pipeline timing

| Rule | Source |
|---|---|
| EX starts at least 1 cycle after ISSUE | Original |
| EX starts at least 1 cycle after every source operand's WB | Original |
| EX lasts the configured number of cycles: [s, s+L−1] | Handout |
| WB at least 1 cycle after the end of EX (MEM for loads) | Original |
| A load's MEM starts at least 1 cycle after its EX (address) | Original (the original broke it, B3) |
| COMMIT at least 1 cycle after WB (after EX for branches) | Original |
| A reservation station, ROB entry, queue entry or FU freed in cycle *c* can be used again in cycle *c*+1 | Ours (the original reused ROB entries in the same cycle) |
| A reservation station is freed when its instruction starts EX | Original |

### 4.2 Multiple issue

| Rule | Source |
|---|---|
| Up to *W* instructions issue per cycle, in program order; issue stops at the first one without a free ROB entry, reservation station or queue entry | Handout ("1–4 instructions, in order") |
| A branch predicted taken is the last instruction issued in its cycle; the target is fetched in the next cycle | Ours |
| CDB buses: default *W*, or `CDB buses = N` | Ours (see below) |
| Commit width: default *W*, or `Commit width = N` | Ours |
| "# of FUs" FUs per type; each can start one instruction per cycle | Handout (the original ignored the column) |
| FP adder and multiplier are pipelined; the integer adder is not; the address adders (the "# of FUs" of the load/store row) are not | Handout for the first three; Ours for the address adders (no difference when address calculation takes 1 cycle, as in every handout example) |
| When several instructions are ready for the same FU type, the oldest goes first | Ours (the original took the lowest station number) |
| When more results are waiting than there are CDB buses, the one that finished first goes first; ties go to the oldest instruction | Ours (the original used the order in which the stages added results) |

Why *W* CDB buses by default: the handout lists "one CDB", which is what width 1 gets. With a
single CDB at width 4, at most one result per cycle can be written back, and a wider issue
cannot help after the first few cycles: `tests/cdb_limit.txt` takes 11 cycles at every width,
the same program with *W* buses (`tests/wide.txt`) takes 11, 7, 6 and 5.

### 4.3 Branches

| Rule | Source |
|---|---|
| `Beq` / `Bne` use an integer adder reservation station and FU; offset in instructions: target = index + 1 + offset | Handout |
| 8-entry BTB, index = word address of the branch mod 8 (instruction *i* is at byte address 4*i*) | Handout |
| Each entry holds the PC of its branch, which is checked on lookup; a lookup with another PC predicts not taken | Ours: the handout does not say. Without it, branches 8 instructions apart use each other's target (`tests/btb_alias.txt`) |
| 1-bit predictor per entry: predict what the branch did last time; empty entry: not taken | Handout (1-bit); Ours (initial value) |
| Predict at ISSUE; resolve and update the BTB at the end of EX | Handout |
| Misprediction found in cycle *n*: no issue in *n*+1, correct fetch in *n*+2 | Handout |
| The wrong-path instructions are removed at the end of cycle *n*, so older instructions can use what they held from *n*+1 | Ours (the handout counts the recovery as cycle *n*+1; this only matters for resources the wrong path held) |
| If two branches resolve wrongly in the same cycle, the older one squashes the younger | Ours |

### 4.4 Loads and stores

| Rule | Source |
|---|---|
| Loads and stores enter the queue in program order at ISSUE; a full queue stops issue | Handout |
| Address calculation on a dedicated adder, oldest ready entry first | Handout / Ours |
| A store commits only when every older instruction has committed (possibly earlier in the same cycle), its address and data are known, and the memory is free; it writes memory from that cycle for "Cycles in Mem" cycles, and its COMMIT cycle is the first of them | Handout (stores write at commit); Original (COMMIT = start of the write) |
| From the cycle after its address is known, a load looks for the youngest older store with the same address. If that store has its data: forward it, MEM takes 1 cycle | Handout |
| If there is no such store: read memory when it is free (one access at a time, not pipelined); the oldest such load goes first | Handout |
| A load waits while any older store in the queue has no address yet | **Ours, differs from the handout** (section 8) |
| A load leaves the queue in the cycle it gets its data; a store when it commits | Handout |
| A load and a committing store that want the memory in the same cycle: the load gets it | Ours |

## 5. Verification

The original code came with no tests. The scripts in
[`verify/`](tomasulo-python/verify/) check the simulator from several independent sides.

### 5.1 Functional reference

[`reference.py`](tomasulo-python/verify/reference.py) (69 lines) runs the program one
instruction at a time with no timing, renaming or speculation. For every test and width,
[`check_all.py`](tomasulo-python/verify/check_all.py) requires the same final integer
registers, FP registers and memory, and the same sequence of committed instructions. This
catches wrong values from renaming, recovery, forwarding and store ordering. It shares only the
input parser with the simulator.

### 5.2 Timing rules

`check_all.py` also checks every committed instruction against the rules of section 4, written
again from the tables above rather than taken from the simulator's code. It reads the limits
from the input file, and which units are pipelined from its own table. The rules checked:

- ISSUE and COMMIT in program order; at most *W* issues, *W* commits and *N* CDB broadcasts
  per cycle;
- EX starts after ISSUE and after the WB of each source operand's producer, and has the
  configured length; WB after EX/MEM; COMMIT after WB (branches: after EX);
- loads: MEM after EX, 1 cycle if forwarded, else the memory latency; stores: MEM is
  [COMMIT, COMMIT + latency − 1], COMMIT after the data's producer wrote back;
- no two memory accesses overlap; unpipelined FUs never hold more instructions than there are
  units; pipelined FUs start at most one instruction per unit per cycle;
- the ROB, each reservation station type and the load/store queue never hold more entries than
  configured;
- after a mispredicted branch, the next instruction issues at least 2 cycles after the branch's
  EX; after a branch predicted taken, the next instruction issues in a later cycle;
- a load starts MEM only after every older store has its address; a forwarded load has an older
  store to the same address still in the queue; a load that reads memory starts after every
  older store to that address finished writing.

Only committed instructions appear in the table, so these checks cannot see squashed ones.

### 5.3 Hand-computed tables

Sections 5.1 and 5.2 check that the output is consistent with the rules. They cannot tell that
a rule was implemented differently from what we meant, for example "lowest station number"
instead of "oldest". So for six small tests we computed the whole instruction table by hand at
widths 1, 2 and 4 (16 tables in [`tests/golden/`](tomasulo-python/tests/golden/); squash_cdb
only at width 4) before running the simulator on them. `check_all.py` compares the printed
table with them.

15 tables matched on the first run. The 16th (dispatch_order, width 4) did not: our hand
derivation said `Add R5, R1, R0` issues in cycle 1, but we had copied the width-2 row into the
file. The simulator agreed with the derivation; we fixed the file.

Example, [`tests/loop.txt`](tomasulo-python/tests/loop.txt) at width 1 (R1 starts at 2, so the
loop runs twice):

```text
                  ISSUE   EX          MEM   WB      COMMIT  NOTE
Addi R1, R1, -1   [1]     [2, 2]      []    [3]     [4]
Bne R1, R0, -2    [2]     [4, 4]      []    []      [5]     taken, mispredicted
Addi R1, R1, -1   [6]     [7, 7]      []    [8]     [9]
Bne R1, R0, -2    [7]     [9, 9]      []    []      [10]    not taken, mispredicted
Addi R2, R2, 5    [11]    [12, 12]    []    [13]    [14]
Add R3, R2, R2    [12]    [14, 14]    []    [15]    [16]
```

- The first `Bne` needs R1, written back in cycle 3, so its EX is cycle 4. The BTB is empty, so
  it was predicted not taken, and the two instructions after it were fetched in cycles 3 and 4.
  In cycle 4 it turns out taken: those two are squashed, cycle 5 is the recovery cycle, and the
  loop body is fetched again in cycle 6 (*n* + 2).
- The second `Bne` finds its BTB entry (index 1, PC 1) saying "taken last time" and is
  predicted taken, so `Addi R1` is fetched again in cycle 8. In cycle 9 the branch turns out not
  taken (R1 = 0): squash, nothing in cycle 10, `Addi R2` in cycle 11.
- `Add R3` needs R2, written back in cycle 13, so its EX is cycle 14.

### 5.4 Random programs

[`fuzz.py`](tomasulo-python/verify/fuzz.py) generates programs of 3–35 instructions with up to
two counted loops, forward branches, loads and stores to a few overlapping addresses, store
followed by load of the same address, and base registers that are rewritten (so a store's
address can be late). Each gets a random configuration (1–4 stations and 1–2 units per FU type,
latencies 1–6, ROB of 2–12 entries, and half the time a CDB count or commit width of 1–4 that
can be below the issue width). Programs the reference
cannot finish in 2000 instructions are skipped. Each program runs at widths 1–4 through the
checks of 5.1 and 5.2. In `results/fuzz.txt`: 2000 programs, 8000 runs, 0 failures.

### 5.5 Mutation test

A check is only useful if it fails when the code is wrong.
[`mutants.py`](tomasulo-python/verify/mutants.py) copies the code, changes one line, and runs
`check_all.py` and `fuzz.py` (300 programs) on the copy. All 19 mutants are caught
(`results/mutants.txt`):

| Mistake put into the code | Caught by tests | Caught by fuzz |
|---|---|---|
| RAT not recovered after a misprediction | yes | yes |
| correct fetch at *n*+1 instead of *n*+2 | yes | yes |
| reservation stations of wrong-path instructions not cleared | yes | yes |
| wrong-path results left waiting for the CDB | yes | no |
| RAT written by every broadcast (bug B1) | yes | yes |
| no limit on CDB buses | yes | yes |
| commit in the same cycle as WB | yes | yes |
| store commits while the memory is busy | yes | yes |
| no limit on commit width | yes | yes |
| forward from the oldest matching store instead of the youngest | no | yes |
| load passes stores with unknown addresses | yes | yes |
| forwarding in the same cycle as the address calculation (bug B3) | yes | yes |
| EX in the same cycle as ISSUE | yes | yes |
| unpipelined integer adder treated as pipelined | no | yes |
| BTB ignores the PC stored in the entry | yes | no |
| a branch predicted taken does not end the issue group | yes | yes |
| issue does not stop at a full ROB | yes | yes |
| youngest ready instruction dispatched first | yes | no |
| `Beq` resolved like `Bne` | yes | yes |

The first run of this test caught only 15 of 19, and we changed the checks, not the
mutants:

- BTB tags and dispatch order change timing but not results; the hand-computed tables
  (`btb_alias`, `dispatch_order`) now catch them.
- The checker read which units are pipelined from the simulator itself, so a wrong value there
  passed. It now has its own table.
- "Load passes stores with unknown addresses" never mattered in the random programs: their base
  registers were never written, so every store had its address in time. Now they are rewritten,
  and `tests/memory.txt` has the case.

After the random programs changed, a later run missed "wrong-path results left waiting for the
CDB". Such a result only gives a wrong value if it is still waiting when its ROB tag is given to
a new instruction. [`tests/squash_cdb.txt`](tomasulo-python/tests/squash_cdb.txt) builds exactly
that case (one CDB, three older results ahead of it).

### 5.6 Width 1 compared with the original code

[`compare_original.py`](tomasulo-python/verify/compare_original.py) runs the original code (taken
from the repository history) and ours at width 1 on the five inputs the original can run
(`results/compare_original.txt`). Every difference has one of these causes:

| Cause | Where it shows |
|---|---|
| CDB ties: a load finishing MEM and an `Addi` finishing EX in cycle 7 both want the CDB in cycle 8. The original takes the `Addi` (its stage order added it first), we take the older load | `original.txt`: `Ld F2` WB 8 instead of 9, and everything that depends on it one cycle earlier |
| Branch prediction instead of stopping fetch | `original.txt`: the original issues after each `Bne` one cycle after it resolves. We lose 2 cycles on the first and last `Bne` (mispredicted) and nothing on the middle one (predicted taken correctly) |
| Branches take a commit slot | `original.txt`: the original removes a `Bne` without a commit cycle; ours commits it like any instruction. The three `Bne` add three cycles at the end and the CDB tie saves one: 41 cycles instead of 39 |
| B1, B4: pipelined units advanced twice | `bug1`, `bug4`: the original's `Mult.d` take 14 cycles, two start EX in the same cycle in one unit |
| B2, B3: stores and forwarding | `bug2`, `bug3`: stores commit after older instructions, forwarding a cycle after EX |

## 6. Results under different issue widths

From `results/summary.md`. Cycles = the last cycle in which anything happened (the last commit,
or the end of the last store's memory write). IPC = committed instructions / cycles. Squashed =
wrong-path instructions removed from the ROB. `pdf_sample` is left out: it never ends.

| Test | Instructions | Cycles W=1 | W=2 | W=3 | W=4 | IPC W=1 | W=2 | W=3 | W=4 | Mispredicted | Squashed W=1 / W=4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wide | 8 | 11 | 7 | 6 | 5 | 0.73 | 1.14 | 1.33 | 1.60 | 0 | 0 / 0 |
| cdb_limit | 8 | 11 | 11 | 11 | 11 | 0.73 | 0.73 | 0.73 | 0.73 | 0 | 0 / 0 |
| independent | 6 | 12 | 9 | 8 | 8 | 0.50 | 0.67 | 0.75 | 0.75 | 0 | 0 / 0 |
| chain | 6 | 22 | 22 | 22 | 22 | 0.27 | 0.27 | 0.27 | 0.27 | 0 | 0 / 0 |
| structural | 8 | 20 | 19 | 18 | 18 | 0.40 | 0.42 | 0.44 | 0.44 | 0 | 0 / 0 |
| memory | 7 | 17 | 15 | 15 | 14 | 0.41 | 0.47 | 0.47 | 0.50 | 0 | 0 / 0 |
| daxpy | 28 | 41 | 32 | 31 | 31 | 0.68 | 0.88 | 0.90 | 0.90 | 2 | 2 / 4 |
| loop | 6 | 16 | 16 | 16 | 16 | 0.38 | 0.38 | 0.38 | 0.38 | 2 | 4 / 5 |
| btb_alias | 4 | 10 | 10 | 10 | 10 | 0.40 | 0.40 | 0.40 | 0.40 | 1 | 2 / 4 |
| squash_cdb | 6 | 14 | 12 | 12 | 11 | 0.43 | 0.50 | 0.50 | 0.55 | 1 | 3 / 3 |
| dispatch_order | 4 | 8 | 8 | 8 | 8 | 0.50 | 0.50 | 0.50 | 0.50 | 0 | 0 / 0 |
| r0 | 6 | 12 | 10 | 10 | 10 | 0.50 | 0.60 | 0.60 | 0.60 | 1 | 2 / 2 |
| original | 15 | 41 | 35 | 34 | 34 | 0.37 | 0.43 | 0.44 | 0.44 | 2 | 2 / 4 |
| sample_tc1 | 17 | 36 | 33 | 33 | 33 | 0.47 | 0.52 | 0.52 | 0.52 | 0 | 0 / 0 |
| sample_tc2 | 17 | 49 | 47 | 47 | 47 | 0.35 | 0.36 | 0.36 | 0.36 | 0 | 0 / 0 |
| bug1_rat_overwrite | 7 | 37 | 36 | 36 | 36 | 0.19 | 0.19 | 0.19 | 0.19 | 0 | 0 / 0 |
| bug2_store_before_commit | 3 | 23 | 23 | 23 | 23 | 0.13 | 0.13 | 0.13 | 0.13 | 0 | 0 / 0 |
| bug3_forward_same_cycle | 3 | 14 | 13 | 13 | 13 | 0.21 | 0.23 | 0.23 | 0.23 | 0 | 0 / 0 |
| bug4_double_advance | 3 | 26 | 25 | 25 | 25 | 0.12 | 0.12 | 0.12 | 0.12 | 0 | 0 / 0 |
| bug5_empty_rob_crash | 7 | 20 | 20 | 20 | 20 | 0.35 | 0.35 | 0.35 | 0.35 | 2 | 4 / 4 |

The full output of every test at every width is in `results/<test>_w<N>.txt`.

### 6.1 When a wider issue helps

`wide` is the best case: eight independent `Addi` and four integer adders. At width 4, four
instructions go through each stage together; the whole program takes 5 cycles instead of 11.

```text
width 1                                          width 4
Addi R1, R0, 1  [1]  [2, 2]  [] [3]  [4]         Addi R1, R0, 1  [1]  [2, 2]  [] [3]  [4]
Addi R2, R0, 2  [2]  [3, 3]  [] [4]  [5]         Addi R2, R0, 2  [1]  [2, 2]  [] [3]  [4]
...                                              ...
Addi R8, R0, 8  [8]  [9, 9]  [] [10] [11]        Addi R8, R0, 8  [2]  [3, 3]  [] [4]  [5]
```

`daxpy` (Y[i] = a·X[i] + Y[i] for 4 elements) is a realistic loop. Width 2 saves 9 of 41 cycles,
widths 3 and 4 one more. At width 4 the four iterations issue in cycles 1–2, 7–8, 11–15 and
17–21. What stops a wider issue from doing more here:

- inside each iteration, the load (address 1 cycle, memory 2), the multiply (4), the add (2)
  and the store's write (2) must happen one after another, whatever the width;
- one memory port serves 12 accesses of 2 cycles each;
- the loop branch is mispredicted in the first iteration (empty BTB) and the last (the 1-bit
  predictor says taken); each time, the correct instructions issue only 2 cycles after the
  branch's EX;
- a branch predicted taken ends the issue group, so at most one iteration starts per cycle.

### 6.2 When it does not help

- **Dependences**: in `chain` every instruction needs the previous result. At width 4 the
  first five issue by cycle 3 (the sixth waits until cycle 10 for a free FP adder station), but
  EX still runs one after another: 22 cycles at every width.
- **One CDB**: `cdb_limit` is `wide` with `CDB buses = 1`: one write-back per cycle, 11 cycles
  at every width.
- **Full structures**: in `structural` (one station per FU type, a 2-entry queue, a 4-entry ROB)
  issue keeps stopping at the first instruction without a free entry; width 4 saves only 2
  cycles.
- **Mispredictions**: in `loop`, all four widths take 16 cycles. The two mispredictions decide
  when the correct instructions issue, and a wider issue only fetches more wrong-path
  instructions (4 squashed at width 1, 5 at width 4).

## 7. Comparison with the sample report

We ran the sample report's two test cases unchanged (`tests/sample_tc1.txt`,
`tests/sample_tc2.txt`).

Test case 1 at width 1 ends in cycle 36 in both. Rows differ where two results want the CDB in
the same cycle: the sample report's tie order puts the second `Ld F1` before `Mult.d F2 F1 F1`
(WB 16 and 17); we take the older instruction first (17 and 16), which moves the dependent
`Add.d F4 F2 F4` one cycle earlier. At width 4 both end in cycle 33. There we differ in two
places. The sample report reuses a reservation station in the cycle it is freed (the fifth
`Mult.d` issues in cycle 10, ours in 11). And its second `Addi R1 R1 8` starts EX in cycle 4,
the cycle in which the first `Addi R1 R1 8`, whose result it needs, writes back. In the other
rows we checked, an instruction starts EX one cycle after its operand's WB (at width 1, the `Ld`
after the first `Addi R1 R1 8`: WB 8, EX 9). We think cycle 4 is an error in the sample report;
ours starts in cycle 5.

Test case 2: we take 49 cycles at width 1, the sample report 47. It has "# of FUs = 2" for the
load/store unit, and the sample report lets two loads use memory at once (MEM [3, 7] and
[7, 11]). The handout says memory is single-ported, so we read that column as the number of
address adders, and the second load waits until cycle 8. Its `Addi R1 R1 8` also starts EX in
cycle 9, the cycle its operand writes back.

The sample report says branches do not work at widths above 1. In ours they work at every
width (section 5).

## 8. What works, limitations and deviations

**Works**: issue widths 1–4 with any configuration; `Ld`, `Sd`, `Beq`, `Bne`, `Add`, `Addi`,
`Sub`, `Add.d`, `Sub.d`, `Mult.d`; several FUs per type; branch prediction with recovery;
store-to-load forwarding; the handout's input format and output format. We know of no input
that gives a wrong result: all checks of section 5 pass.

**Deviations from the handout**:

- **Loads and unknown store addresses.** The handout says: "If not found, or there are still
  unresolved memory addresses for stores, then the load accesses the memory for data." Read
  literally, a load may read memory before an older store has computed its address. If that
  store then turns out to write the same address, the load has read an old value, and the
  handout gives no way to detect and redo it (the load has already left the queue). We let the
  load wait until every older store has its address instead. This gives correct results
  (section 5); some loads start later than the handout's wording allows.
- **CDB buses and commit width default to the issue width** (section 4.2). The handout's "one
  CDB" is what width 1 gets, and `CDB buses = 1` gives it at any width.
- Values are Python floats (double precision); the handout's FP values are single precision.
  We do not round to single precision.
- Each of the 256 memory addresses holds one whole value, as in the original code; values are
  not split into 4 bytes. The handout's sample loads from address 18 (`Ld F4, 8(R1)` with
  R1 = 10), so we accept addresses that are not multiples of 4.

**Choices the handout leaves open** (all listed in section 4 as "Ours"): the BTB checks the
branch PC; an empty BTB entry predicts not taken; the BTB is updated when a branch resolves,
also by branches that are later squashed; a branch predicted taken ends the issue group;
oldest-first dispatch and CDB order; resources freed in cycle *c* are reused in *c*+1; a load
gets the memory before a committing store in the same cycle; a squashed load frees the memory
at once.

**Input that is not handled**: the handout's sample program (`tests/pdf_sample.txt`) never
ends, because `Bne R2, R3, -3` always jumps back and R2 and R3 never change. The simulator
stops it at `--max-cycles` (default 10000) and says so.
