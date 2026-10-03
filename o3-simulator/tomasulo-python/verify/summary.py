# Prints the result table of REPORT.md: for every test input and issue width,
# the number of cycles, IPC (committed instructions per cycle), mispredicted
# branches and squashed (wrong-path) instructions.
# Usage: python3 summary.py

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'code'))
from main import simulate

TESTS = os.path.join(HERE, '..', 'tests')


def main():
    print('| Test | Instructions | Cycles W=1 | W=2 | W=3 | W=4 | IPC W=1 | W=2 | W=3 | W=4 | Mispredicted | Squashed W=1 / W=4 |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for path in sorted(glob.glob(os.path.join(TESTS, '*.txt'))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name == 'pdf_sample':
            continue        # never finishes
        runs = [simulate(path, width) for width in (1, 2, 3, 4)]
        mispredicted = sum(e.mispredicted for e in runs[0].committed)
        print('| %s | %d | %s | %s | %d | %d / %d |' % (
            name, len(runs[0].committed),
            ' | '.join(str(st.cycles) for st in runs),
            ' | '.join('%.2f' % (len(st.committed) / st.cycles) for st in runs),
            mispredicted, runs[0].squashed, runs[3].squashed))


if __name__ == '__main__':
    main()
