# Compares the original simulator (as first committed to this repository) with
# ours at issue width 1, on the inputs the original can run: its hard-coded
# configuration (the one in tests/original.txt), no Beq, no commas. Prints both
# instruction tables side by side and marks the rows that differ;
# REPORT-o3-simulator.md (Appendix D) explains every difference.
# Usage: python3 compare_original.py

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'code'))
from main import simulate

TESTS = os.path.join(HERE, '..', 'tests')
INPUTS = ['original.txt', 'bug1_rat_overwrite.txt', 'bug2_store_before_commit.txt',
          'bug3_forward_same_cycle.txt', 'bug4_double_advance.txt']
FILES = ['main.py', 'init.py', 'issue.py', 'exe.py', 'mem.py', 'wb.py', 'commit.py', 'print_status.py']
ROW = re.compile(r'^(.*?)\s+(\[[^]]*\])\s+(\[[^]]*\])\s+(\[[^]]*\])\s+(\[[^]]*\])\s+(\[[^]]*\])\s*$')


def original_code(tmp):
    """write the original files, taken from the commit that added them, into tmp"""
    top = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=HERE,
                                  universal_newlines=True).strip()
    rev = subprocess.check_output(
        ['git', 'log', '--diff-filter=A', '--format=%H', '--', 'o3-simulator/tomasulo-python/code/code.in'],
        cwd=top, universal_newlines=True).split()[-1]
    for name in FILES:
        text = subprocess.check_output(['git', 'show', '%s:o3-simulator/tomasulo-python/code/%s' % (rev, name)],
                                       cwd=top, universal_newlines=True)
        with open(os.path.join(tmp, name), 'w') as f:
            f.write(text)


def run_original(tmp, st):
    # the original reads code.in and counts branch offsets in bytes
    lines = []
    for ins in st.instructions:
        text = ins.text
        if ins.op == 'Bne':
            text = 'Bne %s %s %d' % (ins.src1, ins.src2, 4 * ins.imm)
        lines.append(text)
    with open(os.path.join(tmp, 'code.in'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    out = subprocess.run([sys.executable, 'main.py'], cwd=tmp, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, universal_newlines=True).stdout
    return [m.groups() for m in map(ROW.match, out.splitlines()[1:]) if m]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        original_code(tmp)
        for name in INPUTS:
            st = simulate(os.path.join(TESTS, name), 1)
            theirs = run_original(tmp, st)
            ours = [(e.ins.text, str(e.issue), str(e.exe), str(e.mem), str(e.cdb), str(e.commit))
                    for e in st.committed]
            print('== %s (columns: ISSUE EX MEM WB COMMIT; * = differs)' % name)
            width = max(len(r[0]) for r in ours) + 2
            print(''.ljust(width) + 'original'.ljust(44) + 'ours')
            for i in range(max(len(ours), len(theirs))):
                o = ours[i] if i < len(ours) else ('',) * 6
                t = theirs[i] if i < len(theirs) else ('(missing)',) + ('',) * 5
                mark = '*' if o[1:] != t[1:] else ' '
                print('%s %s%s%s' % (mark, (o[0] or t[0]).ljust(width - 2),
                                     ' '.join(t[1:]).ljust(44), ' '.join(o[1:])))
            print()


if __name__ == '__main__':
    main()
