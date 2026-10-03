# Checks every input in tests/ at issue widths 1-4:
#   V1  final registers, memory and the committed instruction sequence equal
#       those of the functional reference (reference.py)
#   V2  the timing of every committed instruction obeys the model's rules
#       (written again here from the rule table in REPORT.md, not taken from
#       the simulator's code)
#   V3  where tests/golden/<test>_w<N>.txt exists, the printed instruction
#       table equals it exactly (hand-computed tables)
# Usage: python3 check_all.py [test files...]   (default: all of tests/*.txt)

import contextlib
import glob
import io
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'code'))
from main import simulate
from print_status import print_table
from reference import run_reference

TESTS = os.path.join(HERE, '..', 'tests')
BRANCHES = ('Beq', 'Bne')
# PDF: integer adder unpipelined, FP adder and multiplier pipelined; we chose
# unpipelined address adders. Kept here, not read from the simulator.
PIPELINED = {'int': False, 'fpadd': True, 'fpmul': True, 'ldsd': False}


def sources(ins):
    """registers read before EX (operands and base registers)"""
    if ins.op == 'Ld':
        return [ins.base]
    if ins.op == 'Sd':
        return [ins.base]           # the data register is checked against COMMIT
    if ins.op == 'Addi':
        return [ins.src1]
    return [ins.src1, ins.src2]


def count_overlaps(intervals):
    """largest number of closed intervals [a, b] that share a cycle"""
    events = Counter()
    for a, b in intervals:
        events[a] += 1
        events[b + 1] -= 1
    best = running = 0
    for cycle in sorted(events):
        running += events[cycle]
        best = max(best, running)
    return best


def check_timing(st):
    """V2: returns a list of rule violations"""
    errors = []
    # limits from the parsed input file (issue width already overridden by --width)
    cfg = st.config
    M = cfg['ldsd_mem']
    issue_width = cfg['issue_width']
    cdb_buses = cfg['cdb'] or issue_width
    commit_width = cfg['commit_width'] or issue_width
    entries = st.committed

    def bad(entry, rule):
        errors.append('%s (seq %d): %s' % (entry.ins.text, entry.seq, rule))

    last_writer = {}                # register -> latest committed entry writing it
    previous = None
    for entry in entries:
        ins = entry.ins
        unit = ins.unit
        issue = entry.issue[0]
        commit = entry.commit[0]
        ex = entry.exe
        # issue and commit in program order
        if previous is not None:
            if issue < previous.issue[0]:
                bad(entry, 'issued before an older instruction')
            if commit < previous.commit[0]:
                bad(entry, 'committed before an older instruction')
            # predicted-taken branch ends the issue group; misprediction: correct fetch at n+2
            if previous.ins.op in BRANCHES:
                if previous.mispredicted and issue < previous.exe[1] + 2:
                    bad(entry, 'issued %d, earlier than 2 cycles after the mispredicted branch resolved (%d)'
                        % (issue, previous.exe[1]))
                if previous.pred_next != previous.PC + 1 and issue <= previous.issue[0]:
                    bad(entry, 'issued in the same cycle as the predicted-taken branch before it')
        # EX
        if len(ex) != 2 or ex[0] <= issue:
            bad(entry, 'EX %s does not start after ISSUE %d' % (ex, issue))
            continue
        if ex[1] - ex[0] + 1 != cfg[unit + '_ex']:
            bad(entry, 'EX %s is not %d cycles' % (ex, cfg[unit + '_ex']))
        for reg in sources(ins):
            producer = last_writer.get(reg)
            if producer is not None and ex[0] <= producer.cdb[0]:
                bad(entry, 'EX starts %d, not after %s WB %d' % (ex[0], producer.ins.text, producer.cdb[0]))
        # MEM, WB, COMMIT per instruction class
        if ins.op in BRANCHES:
            if entry.mem or entry.cdb:
                bad(entry, 'branch with MEM or WB')
            if commit <= ex[1]:
                bad(entry, 'COMMIT not after EX')
        elif ins.op == 'Sd':
            if entry.cdb:
                bad(entry, 'store with WB')
            if entry.mem != [commit, commit + M - 1]:
                bad(entry, 'MEM %s is not [COMMIT, COMMIT+%d]' % (entry.mem, M - 1))
            if commit <= ex[1]:
                bad(entry, 'COMMIT not after EX')
            producer = last_writer.get(ins.src1)
            if producer is not None and commit <= producer.cdb[0]:
                bad(entry, 'COMMIT %d not after the data producer WB %d' % (commit, producer.cdb[0]))
        else:
            if len(entry.cdb) != 1:
                bad(entry, 'no WB')
                continue
            wb = entry.cdb[0]
            if ins.op == 'Ld':
                mem = entry.mem
                if len(mem) != 2 or mem[0] <= ex[1]:
                    bad(entry, 'MEM %s does not start after EX %s' % (mem, ex))
                    continue
                length = 1 if entry.forwarded else M
                if mem[1] - mem[0] + 1 != length:
                    bad(entry, 'MEM %s is not %d cycles' % (mem, length))
                if wb <= mem[1]:
                    bad(entry, 'WB not after MEM')
            else:
                if entry.mem:
                    bad(entry, 'ALU instruction with MEM')
                if wb <= ex[1]:
                    bad(entry, 'WB not after EX')
            if commit <= wb:
                bad(entry, 'COMMIT not after WB')
        if ins.dest is not None and ins.dest != 'R0':
            last_writer[ins.dest] = entry
        previous = entry

    # per-cycle limits: issue width, commit width, CDB buses
    for name, cycles, limit in (
            ('issued', [e.issue[0] for e in entries], issue_width),
            ('committed', [e.commit[0] for e in entries], commit_width),
            ('broadcast', [e.cdb[0] for e in entries if e.cdb], cdb_buses)):
        for cycle, n in Counter(cycles).items():
            if n > limit:
                errors.append('cycle %d: %d instructions %s, limit %d' % (cycle, n, name, limit))
    # functional units: unpipelined ones hold one instruction for all of EX,
    # pipelined ones start at most one instruction per cycle each
    for unit in ('int', 'fpadd', 'fpmul', 'ldsd'):
        ex = [tuple(e.exe) for e in entries if e.ins.unit == unit and len(e.exe) == 2]
        n_units = cfg[unit + '_fu']
        if PIPELINED[unit]:
            starts = Counter(a for a, b in ex)
            if starts and max(starts.values()) > n_units:
                errors.append('%s: more than %d EX starts in one cycle' % (unit, n_units))
        elif count_overlaps(ex) > n_units:
            errors.append('%s: more than %d instructions in EX at once' % (unit, n_units))
    # memory: one access at a time (loads that read memory, stores at commit)
    accesses = [tuple(e.mem) for e in entries
                if (e.ins.op == 'Sd' or (e.ins.op == 'Ld' and not e.forwarded)) and len(e.mem) == 2]
    if count_overlaps(accesses) > 1:
        errors.append('memory: overlapping accesses')
    # capacities: ROB [ISSUE, COMMIT], reservation stations [ISSUE, EX start],
    # ld/sd queue: loads [ISSUE, MEM end], stores [ISSUE, COMMIT]
    if count_overlaps([(e.issue[0], e.commit[0]) for e in entries]) > cfg['rob']:
        errors.append('ROB: more than %d entries in use' % cfg['rob'])
    for unit in ('int', 'fpadd', 'fpmul'):
        held = [(e.issue[0], e.exe[0]) for e in entries if e.ins.unit == unit and e.exe]
        if count_overlaps(held) > cfg[unit + '_rs']:
            errors.append('%s: more than %d reservation stations in use' % (unit, cfg[unit + '_rs']))
    held = [(e.issue[0], e.mem[1] if e.ins.op == 'Ld' else e.commit[0])
            for e in entries if e.ins.unit == 'ldsd' and len(e.mem) == 2]
    if count_overlaps(held) > cfg['ldsd_rs']:
        errors.append('ld/sd queue: more than %d entries in use' % cfg['ldsd_rs'])
    # loads against older stores
    stores = []
    for entry in entries:
        if entry.ins.op == 'Sd':
            stores.append(entry)
        elif entry.ins.op == 'Ld' and len(entry.mem) == 2:
            start = entry.mem[0]
            address = entry.lsq.address
            for store in stores:
                # every older store's address is known before the load decides
                if start <= store.exe[1]:
                    bad(entry, 'MEM starts %d before older store "%s" has its address (%d)'
                        % (start, store.ins.text, store.exe[1]))
            same = [s for s in stores if s.lsq.address == address]
            if entry.forwarded:
                # from the youngest older store to that address, still in the queue
                if not same or same[-1].commit[0] < start:
                    bad(entry, 'forwarded, but no older store to that address is in the queue')
            else:
                # memory is read only after every older store to that address wrote it
                for store in same:
                    if start <= store.mem[1]:
                        bad(entry, 'reads memory at %d before older store "%s" wrote it (%s)'
                            % (start, store.ins.text, store.mem))
    return errors


def check_function(st, path, max_steps):
    """V1: returns a list of differences from the functional reference"""
    errors = []
    trace, R, F, M, finished = run_reference(path, max_steps)
    pcs = [e.PC for e in st.committed]
    if st.stop_reason is None:
        if not finished:
            errors.append('reference did not finish but the simulator did')
        if pcs != trace:
            errors.append('committed sequence differs from the reference')
        if st.reg_int != R:
            errors.append('integer registers differ: %s vs %s' % (st.reg_int, R))
        if st.reg_fp != F:
            errors.append('FP registers differ: %s vs %s' % (st.reg_fp, F))
        if [float(x) for x in st.memory] != [float(x) for x in M]:
            errors.append('memory differs')
    elif pcs != trace[:len(pcs)]:
        errors.append('committed sequence (stopped early) is not a prefix of the reference')
    return errors


def normalize(text):
    """table rows with runs of spaces collapsed, so golden files need no padding"""
    return [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines() if line.strip()]


def table_text(st):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        print_table(st)
    return out.getvalue()


def check(path, width, max_cycles=10000):
    st = simulate(path, width, max_cycles)
    errors = check_function(st, path, max_steps=len(st.committed) + 100000)
    errors += check_timing(st)
    name = os.path.splitext(os.path.basename(path))[0]
    golden = os.path.join(TESTS, 'golden', '%s_w%d.txt' % (name, width))
    has_golden = os.path.exists(golden)
    if has_golden:
        with open(golden) as f:
            expected = f.read()
        got = normalize(table_text(st))
        want = normalize(expected)
        if got != want:
            errors.append('instruction table differs from %s' % os.path.relpath(golden))
            for i in range(max(len(got), len(want))):
                g = got[i] if i < len(got) else '(missing)'
                w = want[i] if i < len(want) else '(missing)'
                if g != w:
                    errors.append('  got:      ' + g)
                    errors.append('  expected: ' + w)
    return st, errors, has_golden


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(TESTS, '*.txt')))
    failed = 0
    goldens = 0
    for path in paths:
        for width in (1, 2, 3, 4):
            # pdf_sample loops forever by construction; stop it early
            max_cycles = 200 if os.path.basename(path) == 'pdf_sample.txt' else 10000
            st, errors, has_golden = check(path, width, max_cycles)
            goldens += has_golden
            status = 'FAIL' if errors else 'ok'
            extra = ' (stopped: %s)' % st.stop_reason if st.stop_reason else ''
            print('%-4s %-34s w=%d cycles=%-5d committed=%-4d%s%s' % (
                status, os.path.basename(path), width, st.cycles, len(st.committed),
                ' golden' if has_golden else '', extra))
            for error in errors[:12]:
                print('       ' + error)
            failed += bool(errors)
    print('%d runs, %d failed, %d compared with hand-computed tables' % (
        4 * len(paths), failed, goldens))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
