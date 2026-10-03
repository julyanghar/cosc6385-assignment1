# Prints the result tables of REPORT.md section 3 from the simulator, so the
# report cannot drift from the code:
#   python3 report_tables.py                    summary tables (results/summary.md)
#   python3 report_tables.py --check REPORT.md  exit 1 if a generated block in
#                                               REPORT.md differs from the output
#   python3 report_tables.py --write REPORT.md  rewrite those blocks
# A generated block sits between "<!-- BEGIN GENERATED: name -->" and
# "<!-- END GENERATED: name -->".

import contextlib
import glob
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'code'))
from init import MEMORY_BYTES, read_single
from main import simulate
from print_status import print_table, fmt, fmt_single

TESTS = os.path.join(HERE, '..', 'tests')
WIDTHS = (1, 2, 3, 4)
# tests shown in full in the report, in this order; pdf_sample never ends and
# is cut after 40 cycles
TEST_CASES = ['pdf_sample', 'sample_tc1', 'sample_tc2', 'wide', 'memory',
              'memory_violation', 'loop', 'daxpy']
MAX_CYCLES = {'pdf_sample': 40}


def test_path(name):
    return os.path.join(TESTS, name + '.txt')


def run(name, width, cdb=None, commit_width=None):
    return simulate(test_path(name), width, MAX_CYCLES.get(name, 10000), cdb, commit_width)


def ipc(st):
    return len(st.committed) / st.cycles


def summary():
    names = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(TESTS, '*.txt')))
    names.remove('pdf_sample')      # never ends
    out = ['Default setting: CDB buses and commit width equal to the issue width (unless the input file '
           'sets them: `cdb_limit` and `squash_cdb` have one CDB).', '',
           '| Test | Instructions | Cycles W=1 | W=2 | W=3 | W=4 | IPC W=1 | W=2 | W=3 | W=4 '
           '| Mispredicted branches | Memory-order violations | Squashed W=1 / W=4 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name in names:
        runs = [run(name, w) for w in WIDTHS]
        out.append('| %s | %d | %s | %s | %d | %d | %d / %d |' % (
            name, len(runs[0].committed), ' | '.join(str(st.cycles) for st in runs),
            ' | '.join('%.2f' % ipc(st) for st in runs),
            sum(e.mispredicted for e in runs[0].committed), runs[0].violations,
            runs[0].squashed, runs[3].squashed))
    out += ['', 'One CDB, as the handout lists: cycles with one CDB bus and the commit width equal to the '
            'issue width, and with one CDB bus and one commit per cycle (then only the issue width changes).', '',
            '| Test | One CDB: W=1 | W=2 | W=3 | W=4 | One CDB, one commit: W=1 | W=2 | W=3 | W=4 |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name in names:
        one_cdb = [run(name, w, cdb=1) for w in WIDTHS]
        issue_only = [run(name, w, cdb=1, commit_width=1) for w in WIDTHS]
        out.append('| %s | %s | %s |' % (
            name, ' | '.join(str(st.cycles) for st in one_cdb), ' | '.join(str(st.cycles) for st in issue_only)))
    return '\n'.join(out)


def describe(path):
    """the leading comment of a test file, and its other lines split into
    configuration, initial values and instructions"""
    comment, config, values, program = [], [], [], []
    with open(path) as f:
        for raw in f.read().splitlines():
            line = raw.rstrip()
            if line.startswith('#'):
                if not program and not config:
                    comment.append(line[1:].strip())
            elif line.strip() == '':
                continue
            elif line.strip().startswith('#') or line.split()[0].lower() in (
                    'integer', 'fp', 'load/store', 'rob', 'issue', 'cdb', 'commit'):
                config.append(line)
            elif '=' in line:
                values.append(line)
            else:
                program.append(line.strip())
    return ' '.join(comment), config, values, program


def final_values(st):
    """the non-zero registers and memory words at the end of a run"""
    values = ['R%d = %s' % (i, fmt(v)) for i, v in enumerate(st.reg_int) if v != 0]
    values += ['F%d = %s' % (i, fmt(v)) for i, v in enumerate(st.reg_fp) if v != 0]
    values += ['Mem[%d] = %s' % (a, fmt_single(read_single(st.memory, a)))
               for a in range(0, MEMORY_BYTES, 4) if any(st.memory[a:a + 4])]
    return ', '.join(values)


def table(st):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        print_table(st)
    return out.getvalue().rstrip('\n')


def test_cases():
    out = []
    figure = 0
    for number, name in enumerate(TEST_CASES, 1):
        comment, config, values, program = describe(test_path(name))
        out += ['### 3.%d Test case %d: `%s`' % (number + 2, number, name), '', comment, '',
                'Configuration and initial values ([`tests/%s.txt`](tomasulo-python/tests/%s.txt)):' % (name, name),
                '', '```text'] + config + [''] + values + ['```', '',
                'Instructions (the number is the instruction index that branch offsets count from):',
                '', '```text'] + ['%2d  %s' % (i, text) for i, text in enumerate(program)] + ['```', '']
        runs = [run(name, width) for width in WIDTHS]
        if runs[0].stop_reason is None:
            finals = set(final_values(st) for st in runs)
            assert len(finals) == 1, name       # check_all.py checks this against the reference
            out += ['Final non-zero registers and memory words (the same at every width): %s.'
                    % finals.pop(), '']
        for width, st in zip(WIDTHS, runs):
            figure += 1
            stopped = ' Stopped by the 40-cycle limit.' if st.stop_reason else ''
            out += ['**Figure %d.** `%s`, issue width %d (CDB buses %d, commit width %d): %d cycles, '
                    '%d committed instructions, IPC %.2f, %d squashed.%s' % (
                        figure, name, width, st.cdb_buses, st.commit_width, st.cycles,
                        len(st.committed), ipc(st), st.squashed, stopped),
                    '', '```text', table(st), '```', '']
    return '\n'.join(out).rstrip('\n')


BLOCKS = {'summary': summary, 'test-cases': test_cases}


def update(report, write):
    with open(report) as f:
        text = f.read()
    new = text
    for name, make in BLOCKS.items():
        begin = '<!-- BEGIN GENERATED: %s -->\n' % name
        end = '<!-- END GENERATED: %s -->' % name
        if text.count(begin) != 1 or text.count(end) != 1:
            print('%s: block %s not found' % (report, name))
            return 1
        start = new.index(begin) + len(begin)
        stop = new.index(end)
        new = new[:start] + make() + '\n' + new[stop:]
    if new == text:
        print('%s: generated tables are up to date' % report)
        return 0
    if write:
        with open(report, 'w') as f:
            f.write(new)
        print('%s: generated tables rewritten' % report)
        return 0
    print('%s: generated tables are out of date; run report_tables.py --write' % report)
    return 1


def main():
    if len(sys.argv) == 3 and sys.argv[1] in ('--check', '--write'):
        sys.exit(update(sys.argv[2], sys.argv[1] == '--write'))
    print(summary())


if __name__ == '__main__':
    main()
