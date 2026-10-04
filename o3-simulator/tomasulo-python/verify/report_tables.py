# Writes the parts of REPORT.md that quote run results, from the simulator, so
# the report cannot drift from the code: the paragraph of section 1.4 on one
# CDB, the summary tables of 3.2 and the notes under them, the test cases
# 3.3-3.10 and section 3.11. Every number in these parts is computed here.
#   python3 report_tables.py                    summary tables (results/summary.md)
#   python3 report_tables.py --check REPORT.md  exit 1 if a generated part of
#                                               REPORT.md differs from what this
#                                               script writes now
#   python3 report_tables.py --write REPORT.md  rewrite those parts
# A generated part sits between "<!-- BEGIN GENERATED: name -->" and
# "<!-- END GENERATED: name -->". Numbers elsewhere in REPORT.md are written by
# hand and not checked here.

import contextlib
import glob
import io
import os
import sys
import textwrap
from collections import Counter

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


def wb_cycles(st):
    return sorted(e.cdb[0] for e in st.committed if e.cdb)


def commit_cycles(st):
    return [e.commit[0] for e in st.committed]


def cycles(name, cdb=None, commit_width=None):
    return [run(name, w, cdb, commit_width).cycles for w in WIDTHS]


def finishing_tests():
    names = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(TESTS, '*.txt')))
    names.remove('pdf_sample')      # never ends
    return names


# GLUE stands for a space where a line must not break ("12 -> 9")
GLUE = '\x00'


def para(text):
    """a paragraph wrapped like the rest of REPORT.md"""
    return textwrap.fill(text, width=95, break_long_words=False,
                         break_on_hyphens=False).replace(GLUE, ' ')


def bullet(text):
    return textwrap.fill(text, width=95, initial_indent='- ', subsequent_indent='  ', break_long_words=False,
                         break_on_hyphens=False).replace(GLUE, ' ')


def arrow(values):
    """first and last of a list of cycle counts: 12 -> 9"""
    return '%d%s\u2192%s%d' % (values[0], GLUE, GLUE, values[-1])


def span(values):
    return '%d\u2013%d' % (values[0], values[-1])


def and_list(values):
    values = [str(v) for v in values]
    return ', '.join(values[:-1]) + ' and ' + values[-1]


def consecutive(values):
    return values == list(range(values[0], values[0] + len(values)))


# The three functions below write the passages of REPORT.md that quote run
# results; every number in them is computed here. The asserts check that the
# results still fit the words around the numbers ("stays", "still gains", ...);
# if they do not, --check and --write fail instead of writing a wrong sentence.

def one_cdb_text():
    """REPORT.md 1.4: how much one CDB limits a wider issue"""
    wide, independent = cycles('wide', 1), cycles('independent', 1)
    wide4 = run('wide', 4, 1)
    together = max(Counter(e.exe[1] for e in wide4.committed).values())
    assert len(set(wide)) == 1 and independent[1] < independent[0] and together > 1
    return para(
        'With only one CDB, at most one result per cycle can be written back. How much that limits a '
        'wider issue depends on the program. Our test `wide` has %d independent instructions on %d '
        'integer adders; at width 4 up to %d of its results are ready in the same cycle, and with one '
        'CDB it takes %d cycles at every width. `independent` has %d independent instructions on units '
        'with different latencies; with one CDB it still goes from %d cycles at width 1 to %d at '
        'width 2 (section 3.2).' % (
            len(wide4.committed), wide4.config['int_fu'], together, wide[0],
            len(run('independent', 1).committed), independent[0], independent[1]))


def summary_notes():
    """REPORT.md 3.2: what the summary tables show"""
    default = dict((n, cycles(n)) for n in ('wide', 'independent', 'daxpy', 'original', 'chain', 'loop'))
    helped = ('wide', 'independent', 'daxpy', 'original')
    assert all(default[n][-1] < default[n][0] for n in helped)
    assert len(set(default['chain'])) == 1 and len(set(default['loop'])) == 1
    loop_mispredicted = sum(e.mispredicted for e in run('loop', 1).committed)
    assert loop_mispredicted > 0
    one = dict((n, cycles(n, 1)) for n in helped)
    assert len(set(one['wide'])) == 1 and all(one[n][-1] < one[n][0] for n in helped[1:])
    wide_wb = wb_cycles(run('wide', 4, 1))
    assert consecutive(wide_wb)                 # one write-back in every cycle, no gap
    independent2, independent1 = run('independent', 2, 1), run('independent', 1, 1)
    ready2 = sorted(e.exe[1] for e in independent2.committed)
    wb2, wb1 = wb_cycles(independent2), wb_cycles(independent1)
    assert consecutive(wb2) and not consecutive(wb1)
    names = finishing_tests()
    issue_only = dict((n, cycles(n, 1, 1)) for n in names)
    flat = [n for n in names if len(set(issue_only[n])) == 1]
    gains = sorted(issue_only[n][0] - issue_only[n][-1] for n in names if n not in flat)
    assert 'daxpy' in flat and 'original' in flat and 'independent' not in flat and gains[0] > 0
    gain = ('%d' % gains[0]) if gains[0] == gains[-1] else ('%d to %d' % (gains[0], gains[-1]))
    daxpy, original = issue_only['daxpy'][0], issue_only['original'][0]
    both = ('%d cycles each' % daxpy) if daxpy == original else ('%d and %d cycles' % (daxpy, original))
    return '\n'.join([
        bullet('With the default setting, a wider issue helps programs with independent work (from '
               'width 1 to 4: `wide` %s, `independent` %s, `daxpy` %s, `original` %s cycles) and does '
               'nothing for a dependence chain (`chain`, %d cycles at every width) or for a loop whose '
               'time is decided by its %d mispredictions (`loop`, %d cycles at every width).' % (
                   arrow(default['wide']), arrow(default['independent']), arrow(default['daxpy']),
                   arrow(default['original']), default['chain'][0], loop_mispredicted, default['loop'][0])),
        bullet('With one CDB, `wide` stays at %d cycles at every width: at width 4 its %d results are '
               'written back one per cycle, in cycles %s. Other programs still gain from a wider issue: '
               '`independent` %s, `daxpy` %s, `original` %s. In `independent` the results are ready in '
               'cycles %s at width 2, so the single CDB writes one back in each of cycles %s; at width 1 '
               'it writes back only in cycles %s.' % (
                   one['wide'][0], len(wide_wb), span(wide_wb), arrow(one['independent']),
                   arrow(one['daxpy']), arrow(one['original']), span(ready2), span(wb2), and_list(wb1))),
        bullet('With one CDB and one commit per cycle, %d of the %d programs that finish take the same '
               'number of cycles at every width, among them `daxpy` and `original` (%s); for `daxpy` '
               'the limit is commit (section 3.11). The other %d end %s cycles earlier at width 4 than '
               'at width 1, for example `independent` %s.' % (
                   len(flat), len(names), both, len(names) - len(flat), gain,
                   arrow(issue_only['independent']))),
    ])


def limits_text():
    """REPORT.md 3.11: what limits the gain from a wider issue"""
    chain = [c for cdb, commit in ((None, None), (1, None), (1, 1)) for c in cycles('chain', cdb, commit)]
    assert len(set(chain)) == 1
    wide4 = run('wide', 4, 1)
    together = max(Counter(e.exe[1] for e in wide4.committed).values())
    wide = cycles('wide', 1)
    assert len(set(wide)) == 1 and together > 1
    assert describe(test_path('cdb_limit'))[3] == describe(test_path('wide'))[3]
    assert run('cdb_limit', 1).config['cdb'] == 1
    one_commit, wide_commit = run('daxpy', 4, 1, 1), run('daxpy', 4, 1)
    per_cycle = Counter(commit_cycles(wide_commit))
    most = max(per_cycle.values())
    bursts = sorted(c for c, k in per_cycle.items() if k == most)
    daxpy_one = cycles('daxpy', 1, 1)
    assert wide_commit.cycles < one_commit.cycles and most > 1 and len(set(daxpy_one)) == 1
    daxpy = run('daxpy', 1)
    accesses = [e for e in daxpy.committed if e.ins.op == 'Sd' or (e.ins.op == 'Ld' and not e.forwarded)]
    figure = 4 * TEST_CASES.index('daxpy') + 1
    loop, loop1, loop4 = cycles('loop'), run('loop', 1), run('loop', 4)
    loop_mispredicted = sum(e.mispredicted for e in loop1.committed)
    assert len(set(loop)) == 1 and loop4.squashed > loop1.squashed
    structural = run('structural', 1).config
    assert structural['int_rs'] == structural['fpadd_rs'] == structural['fpmul_rs']
    return '\n'.join([
        bullet('**Dependences.** In `chain` every instruction needs the previous result: %d cycles at '
               'every width and in every setting.' % chain[0]),
        bullet('**The CDB.** In `wide`, %d integer adders finish up to %d instructions in the same cycle, '
               'but with one CDB only one result per cycle is written back: %d cycles at every width '
               '(`cdb_limit` is the same program with `CDB buses = 1` in the file).' % (
                   wide4.config['int_fu'], together, wide[0])),
        bullet('**Commit.** For `daxpy` at width 4 with one CDB, one commit per cycle gives %d cycles; a '
               'commit width of 4 gives %d, with %d instructions committing in the same cycle in cycles '
               '%s. With one CDB and one commit per cycle, `daxpy` takes %d cycles at every width.' % (
                   one_commit.cycles, wide_commit.cycles, most, and_list(bursts), daxpy_one[0])),
        bullet('**Memory.** One port and memory accesses of several cycles: in `daxpy` %d accesses of %d '
               'cycles each (Figures %d\u2013%d); in `sample_tc1` and `sample_tc2` each access takes %d or '
               '%d cycles.' % (
                   len(accesses), daxpy.config['ldsd_mem'], figure, figure + 3,
                   run('sample_tc1', 1).config['ldsd_mem'], run('sample_tc2', 1).config['ldsd_mem'])),
        bullet("**Branches.** Each misprediction delays the correct instructions until 2 cycles after the "
               "branch's EX, and a branch predicted taken ends the issue group, so at most one loop "
               "iteration starts per cycle. In `loop` the %d mispredictions decide the timing: %d cycles "
               "at every width; a wider issue only fetches more wrong-path instructions (%d squashed at "
               "width 1, %d at width%s4)." % (loop_mispredicted, loop[0], loop1.squashed, loop4.squashed, GLUE)),
        bullet('**Full structures.** In `structural` (%d reservation station per FU type, a %d-entry '
               'load/store queue, a %d-entry ROB) issue keeps stopping at the first instruction without '
               'a free entry: %s cycles.' % (
                   structural['int_rs'], structural['ldsd_rs'], structural['rob'], arrow(cycles('structural')))),
    ])


BLOCKS = {'one-cdb': one_cdb_text, 'summary': summary, 'summary-notes': summary_notes,
          'test-cases': test_cases, 'limits': limits_text}


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
        try:
            block = make()
        except AssertionError:
            print('%s: the results no longer fit the words of block %s; see report_tables.py' % (report, name))
            return 1
        start = new.index(begin) + len(begin)
        stop = new.index(end)
        new = new[:start] + block + '\n' + new[stop:]
    if new == text:
        print('%s: generated parts are up to date' % report)
        return 0
    if write:
        with open(report, 'w') as f:
            f.write(new)
        print('%s: generated parts rewritten' % report)
        return 0
    print('%s: generated parts are out of date; run report_tables.py --write' % report)
    return 1


def main():
    if len(sys.argv) == 3 and sys.argv[1] in ('--check', '--write'):
        sys.exit(update(sys.argv[2], sys.argv[1] == '--write'))
    print(summary())


if __name__ == '__main__':
    main()
