# Checks every input in tests/ at issue widths 1-4, each in three settings: the
# default (CDB buses and commit width as in the file, else equal to the issue
# width), "one CDB" (one CDB bus), and "issue only" (one CDB bus and one commit
# per cycle):
#   V1  final registers, memory and the committed instruction sequence equal
#       those of the functional reference (reference.py)
#   V2  the timing of every committed instruction obeys the model's rules
#       (written again here from the rule table in REPORT.md, not taken from
#       the simulator's code)
#   V3  where tests/golden/<test>_w<N>.txt exists, the printed instruction
#       table equals it exactly (hand-computed tables)
#   V4  the printed registers and non-zero memory read back as the values the
#       simulator holds
# A run that stops at the cycle limit passes only if the reference cannot
# finish the program either (pdf_sample loops forever); then only the
# committed prefix can be checked, and the run is counted as "prefix".
# Usage: python3 check_all.py [test files...]   (default: all of tests/*.txt)

import contextlib
import glob
import io
import os
import re
import struct
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'code'))
from main import simulate
from print_status import print_table, print_registers, print_memory
from reference import run_reference

TESTS = os.path.join(HERE, '..', 'tests')
BRANCHES = ('Beq', 'Bne')
# PDF: integer adder unpipelined, FP adder and multiplier pipelined; we chose
# unpipelined address adders. Kept here, not read from the simulator.
PIPELINED = {'int': False, 'fpadd': True, 'fpmul': True, 'ldsd': False}


def same(a, b):
    """equal values; two NaNs count as equal"""
    return a == b or (a != a and b != b)


def overlaps(address1, address2):
    """two 4-byte accesses share a byte"""
    return address1 < address2 + 4 and address2 < address1 + 4


def single(text):
    """a printed number read as single precision"""
    try:
        return struct.unpack('<f', struct.pack('<f', float(text)))[0]
    except OverflowError:
        return float(text) * float('inf')


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
    # loads against older stores (4-byte accesses that overlap if they share a
    # byte). A load may go ahead of stores whose address is unknown; whatever
    # it did, the committed load must have taken its data from the right place.
    stores = []
    data_wb = {}                    # store seq -> WB cycle of its data's producer (0: initial value)
    writers = {}
    for entry in entries:
        if entry.ins.op == 'Sd':
            stores.append(entry)
            producer = writers.get(entry.ins.src1)
            data_wb[entry.seq] = producer.cdb[0] if producer is not None else 0
        elif entry.ins.op == 'Ld' and len(entry.mem) == 2:
            start = entry.mem[0]
            address = entry.lsq.address
            older = [s for s in stores if overlaps(s.lsq.address, address)]
            if entry.forwarded:
                # from the youngest older overlapping store, at the same address,
                # with its address and data known, while it is still in the queue
                if not older:
                    bad(entry, 'forwarded, but no older store overlaps it')
                else:
                    source = older[-1]
                    if source.lsq.address != address:
                        bad(entry, 'forwarded, but the youngest overlapping store "%s" is at another address'
                            % source.ins.text)
                    if source.commit[0] < start:
                        bad(entry, 'forwarded at %d after "%s" left the queue (commit %d)'
                            % (start, source.ins.text, source.commit[0]))
                    if start <= source.exe[1] or start <= data_wb[source.seq]:
                        bad(entry, 'forwarded at %d before "%s" had its address and data'
                            % (start, source.ins.text))
            else:
                # memory is read only after every older overlapping store wrote it
                for store in older:
                    if start <= store.mem[1]:
                        bad(entry, 'reads memory at %d before older store "%s" wrote it (%s)'
                            % (start, store.ins.text, store.mem))
        if entry.ins.dest is not None and entry.ins.dest != 'R0':
            writers[entry.ins.dest] = entry
    return errors


def check_function(st, path, max_steps):
    """V1: returns (list of differences from the functional reference,
    'full' or 'prefix')"""
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
        if not all(same(a, b) for a, b in zip(st.reg_fp, F)):
            errors.append('FP registers differ: %s vs %s' % (st.reg_fp, F))
        if bytes(st.memory) != bytes(M):
            errors.append('memory differs')
        return errors, 'full'
    if finished:
        # stopping early is right only for a program that does not end
        errors.append('stopped (%s), but the program ends after %d instructions'
                      % (st.stop_reason, len(trace)))
    elif pcs != trace[:len(pcs)]:
        errors.append('committed sequence (stopped early) is not a prefix of the reference')
    return errors, 'prefix'


def check_output(st):
    """V4: the printed registers and memory read back as the simulator's values"""
    errors = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        print_registers(st)
        print_memory(st)
    lines = out.getvalue().splitlines()
    printed = {}
    for names, values in zip(lines, lines[1:]):
        if values.startswith('value:'):
            printed.update(zip(names.split(), values.split()[1:]))
    for i in range(32):
        if printed.get('R%d' % i) != str(st.reg_int[i]):
            errors.append('R%d printed as %r, holds %r' % (i, printed.get('R%d' % i), st.reg_int[i]))
        text = printed.get('F%d' % i)
        if text is None or not same(float(text), st.reg_fp[i]):
            errors.append('F%d printed as %r, holds %r' % (i, text, st.reg_fp[i]))
    memory = {}
    for line in lines[lines.index('Addresses   Values') + 1:]:
        if not line.strip():
            break
        address, text = line.split()
        memory[int(address)] = text
    nonzero = [a for a in range(0, 256, 4) if any(st.memory[a:a + 4])]
    if sorted(memory) != nonzero:
        errors.append('non-zero memory words %s, printed %s' % (nonzero, sorted(memory)))
    for address, text in memory.items():
        value = struct.unpack('<f', bytes(st.memory[address:address + 4]))[0]
        if not same(single(text), value):
            errors.append('Mem[%d] printed as %r, holds %r' % (address, text, value))
    return errors


def normalize(text):
    """table rows with runs of spaces collapsed, so golden files need no padding"""
    return [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines() if line.strip()]


def table_text(st):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        print_table(st)
    return out.getvalue()


def check(path, width, max_cycles=10000, cdb=None, commit_width=None):
    st = simulate(path, width, max_cycles, cdb, commit_width)
    errors, kind = check_function(st, path, max_steps=len(st.committed) + 100000)
    errors += check_timing(st)
    errors += check_output(st)
    name = os.path.splitext(os.path.basename(path))[0]
    golden = os.path.join(TESTS, 'golden', '%s_w%d.txt' % (name, width))
    has_golden = os.path.exists(golden) and cdb is None and commit_width is None
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
    return st, errors, has_golden, kind


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(TESTS, '*.txt')))
    count = Counter()
    goldens = 0
    runs = 0
    for path in paths:
        for setting, cdb, commit_width in (('default', None, None), ('one-cdb', 1, None), ('issue-only', 1, 1)):
            for width in (1, 2, 3, 4):
                # pdf_sample loops forever by construction; stop it early
                max_cycles = 200 if os.path.basename(path) == 'pdf_sample.txt' else 10000
                st, errors, has_golden, kind = check(path, width, max_cycles, cdb, commit_width)
                runs += 1
                goldens += has_golden
                status = 'FAIL' if errors else ('ok' if kind == 'full' else 'prefix')
                count[status] += 1
                extra = ' (stopped: %s)' % st.stop_reason if st.stop_reason else ''
                print('%-6s %-30s %-10s w=%d cycles=%-5d committed=%-4d%s%s' % (
                    status, os.path.basename(path), setting, width, st.cycles, len(st.committed),
                    ' golden' if has_golden else '', extra))
                for error in errors[:12]:
                    print('       ' + error)
    print('%d runs: %d ok (final state checked), %d prefix (program never ends, committed '
          'prefix checked), %d failed; %d compared with hand-computed tables' % (
              runs, count['ok'], count['prefix'], count['FAIL'], goldens))
    sys.exit(1 if count['FAIL'] else 0)


if __name__ == '__main__':
    main()
