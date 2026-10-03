# Random programs and random configurations, each run at issue widths 1-4 and
# checked like the tests (functional reference + timing rules, check_all.py).
# Programs use counted loops and forward branches and load/store to a few
# addresses, so forwarding and store ordering matter.
# Usage: python3 fuzz.py [number of programs] [seed]    (default 300, 1)
# Failing inputs are kept in verify/fuzz-failures/ (or $FUZZ_DIR).

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_all import check
from reference import run_reference

OUT = os.environ.get('FUZZ_DIR', os.path.join(HERE, 'fuzz-failures'))
INT_REGS = ['R1', 'R2', 'R3', 'R4', 'R5']
# base registers: R6 = 0 is never written; R7 = 16 is rewritten with its own
# value, so a store's address can wait for the integer adder
FP_REGS = ['F1', 'F2', 'F3', 'F4', 'F5', 'F6']


def straight_line(rng):
    kind = rng.choice(['int', 'int', 'fp', 'fp', 'fp', 'ld', 'ld', 'sd', 'sd', 'sd-ld', 'base'])
    if kind == 'base':
        return rng.choice(['Add R7, R7, R0', 'Sub R7, R7, R0', 'Addi R7, R7, 0'])
    if kind == 'int':
        op = rng.choice(['Add', 'Sub', 'Addi'])
        d, s, t = rng.choice(INT_REGS + ['R0']), rng.choice(INT_REGS + ['R0']), rng.choice(INT_REGS)
        if op == 'Addi':
            return 'Addi %s, %s, %d' % (d, s, rng.randint(-3, 3))
        return '%s %s, %s, %s' % (op, d, s, t)
    if kind == 'fp':
        op = rng.choice(['Add.d', 'Sub.d', 'Mult.d'])
        return '%s %s, %s, %s' % (op, rng.choice(FP_REGS), rng.choice(FP_REGS), rng.choice(FP_REGS))
    # R6 + 16 and R7 + 0 are the same address
    base = rng.choice(['R6', 'R7'])
    offset = 4 * rng.randint(0, 4)
    if kind == 'sd-ld':
        # a store and a load of the same address, for forwarding
        return 'Sd %s, %d(%s)\nLd %s, %d(%s)' % (rng.choice(FP_REGS), offset, base,
                                                rng.choice(FP_REGS), offset, base)
    op = 'Ld' if kind == 'ld' else 'Sd'
    return '%s %s, %d(%s)' % (op, rng.choice(FP_REGS), offset, base)


def program(rng):
    lines = '\n'.join(straight_line(rng) for _ in range(rng.randint(3, 14))).split('\n')
    # one or two counted loops: body, then "Addi Rc, Rc, -1" and "Bne Rc, R0, back"
    for counter in rng.sample(['R8', 'R9'], rng.randint(0, 2)):
        start = rng.randint(0, len(lines) - 1)
        end = rng.randint(start, min(len(lines) - 1, start + 6))
        body = lines[start:end + 1]
        loop = body + ['Addi %s, %s, -1' % (counter, counter), 'Bne %s, R0, %d' % (counter, -(len(body) + 2))]
        lines = lines[:start] + loop + lines[end + 1:]
    # forward branches (offset >= 0) inserted at random places
    for _ in range(rng.randint(0, 3)):
        at = rng.randint(0, len(lines))
        op = rng.choice(['Beq', 'Bne'])
        a, b = rng.choice(INT_REGS + ['R0']), rng.choice(INT_REGS + ['R0'])
        lines.insert(at, '%s %s, %s, %d' % (op, a, b, rng.randint(0, 3)))
    return lines


def config(rng):
    text = ['               # of rs   Cycles in EX   Cycles in Mem   # of FUs',
            'Integer adder   %d %d %d' % (rng.randint(1, 4), rng.randint(1, 3), rng.randint(1, 2)),
            'FP adder        %d %d %d' % (rng.randint(1, 4), rng.randint(1, 4), rng.randint(1, 2)),
            'FP multiplier   %d %d %d' % (rng.randint(1, 4), rng.randint(1, 6), rng.randint(1, 2)),
            'Load/store unit %d %d %d %d' % (rng.randint(1, 4), rng.randint(1, 2), rng.randint(1, 4), rng.randint(1, 2)),
            'ROB entries = %d' % rng.randint(2, 12)]
    if rng.random() < 0.5:
        text.append('CDB buses = %d' % rng.randint(1, 4))
    if rng.random() < 0.5:
        text.append('Commit width = %d' % rng.randint(1, 4))
    regs = ['R%d=%d' % (i, rng.randint(-2, 3)) for i in range(1, 6)]
    regs = [r for r in regs if not r.endswith('=0')]
    regs += ['R7=16', 'R8=%d' % rng.randint(1, 3), 'R9=%d' % rng.randint(1, 3)]
    regs += ['F%d=%s' % (i, rng.choice(['0.5', '1.5', '2.0', '-1.0', '3.0'])) for i in range(1, 7)]
    text.append(', '.join(regs))
    text.append(', '.join('Mem[%d]=%s' % (a, rng.choice(['1.0', '2.5', '-4.0'])) for a in range(0, 48, 8)))
    return text


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rng = random.Random(seed)
    os.makedirs(OUT, exist_ok=True)
    failures = 0
    runs = 0
    made = 0
    while made < n:
        lines = program(rng)
        path = os.path.join(OUT, 'fuzz_%d_%d.txt' % (seed, made + 1))
        with open(path, 'w') as f:
            f.write('\n'.join(config(rng) + [''] + lines) + '\n')
        # a forward branch can skip a loop's decrement and make it endless,
        # or send a store to an invalid address: keep only programs that the
        # reference finishes within 2000 instructions without an error
        try:
            if not run_reference(path, 2000)[4]:
                continue
        except ValueError:
            continue
        made += 1
        failed = False
        for width in (1, 2, 3, 4):
            st, errors, _ = check(path, width, max_cycles=20000)
            runs += 1
            if st.stop_reason is not None:
                errors.append('stopped: %s' % st.stop_reason)
            if errors:
                failed = True
                print('FAIL %s w=%d' % (path, width))
                for error in errors[:5]:
                    print('     ' + error)
        if failed:
            failures += 1
        else:
            os.remove(path)
    if not os.listdir(OUT):
        os.rmdir(OUT)
    print('%d programs, %d runs, %d programs failed (seed %d)' % (n, runs, failures, seed))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
