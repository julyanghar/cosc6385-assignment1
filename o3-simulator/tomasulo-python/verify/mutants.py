# Mutation test: checks that the verification catches real mistakes. Each
# mutant copies code/ to a temporary directory, changes one line, and runs
# check_all.py on tests/ and fuzz.py on 300 random programs against the copy.
# Every mutant must make at least one of them fail.
# Usage: python3 mutants.py

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(HERE, '..', 'code')

# (description, file, original text, mutated text)
MUTANTS = [
    ('RAT not recovered after a misprediction', 'squash.py',
     "    st.rat_int = list(st.reg_int)\n    st.rat_fp = list(st.reg_fp)\n    for rob in st.ROB:",
     "    for rob in []:"),
    ('correct fetch at n+1 instead of n+2', 'squash.py',
     'st.fetch_resume = cycle + 2', 'st.fetch_resume = cycle + 1'),
    ('reservation stations of wrong-path instructions not cleared', 'squash.py',
     "            if element.busy == 1 and wrong(element.rob):\n                element.busy = 0",
     "            if element.busy == 1 and wrong(element.rob):\n                pass"),
    ('wrong-path results stay in the results buffer', 'squash.py',
     'st.results_buffer = [r for r in st.results_buffer if not wrong(r.rob)]', 'pass'),
    ('RAT written by every broadcast (bug B1 of the original)', 'wb.py',
     "if reg_tag[0] == 'F' and st.rat_fp[int(reg_tag[1:])] == dest_tag:",
     "if reg_tag[0] == 'F':"),
    ('no limit on CDB buses', 'wb.py', 'waiting[:st.cdb_buses]', 'waiting'),
    ('commit in the same cycle as WB', 'commit.py',
     'return (len(head.cdb) != 0) and (head.cdb[0] < cycle)',
     'return (len(head.cdb) != 0) and (head.cdb[0] <= cycle)'),
    ('store commits while the memory is busy', 'commit.py',
     '            and (st.mem_busy_until < cycle)', '            and True'),
    ('no limit on commit width', 'commit.py',
     'for _ in range(st.commit_width):', 'for _ in range(64):'),
    ('forward from the oldest overlapping store', 'mem.py',
     'match = element     # keep the youngest', 'match = match or element'),
    ('loads wait for every older store address (the old rule)', 'mem.py',
     "if (element.op == 'Sd') and (element.ready == 1) and (element.ready_cycle < cycle) \\\n"
     "                and overlap(element.address, load.address):",
     "if (element.op == 'Sd') and ((element.ready == 0) or (element.ready_cycle >= cycle)\n"
     "                                      or overlap(element.address, load.address)):"),
    ('partly overlapping stores ignored (only the same address counts)', 'mem.py',
     'and overlap(element.address, load.address):', 'and element.address == load.address:'),
    ('no memory-order check', 'mem.py',
     'victim = check_memory_order(st, cycle)', 'victim = None'),
    ('replay starts after the load instead of at it', 'mem.py',
     'squash(st, victim.seq - 1, victim.PC, cycle)', 'squash(st, victim.seq, victim.PC + 1, cycle)'),
    ('a load that forwarded is never replayed', 'mem.py',
     'if rob.forwarded and (rob.forwarded_from.seq > store.rob.seq):', 'if rob.forwarded:'),
    ('forwarded value not rounded to single precision', 'mem.py',
     'fu_result(element.rob, to_single(store.data), cycle)', 'fu_result(element.rob, store.data, cycle)'),
    ('register values printed with 6 decimals (as before the review)', 'print_status.py',
     '    if type(value) == float:\n        return repr(value)',
     '    if type(value) == float:\n        return str(round(value, 6))'),
    ('forwarding in the same cycle as the address calculation', 'mem.py',
     "(element.ready == 0) or (element.ready_cycle >= cycle) \\\n                or (element.in_memory == 1)",
     "(element.ready == 0) or (element.in_memory == 1)"),
    ('EX in the same cycle as ISSUE', 'exe.py',
     'and (element.rob.issue[0] < cycle):', 'and (element.rob.issue[0] <= cycle):'),
    ('unpipelined integer adder treated as pipelined', 'init.py',
     "self.pipelined = {'int': False,", "self.pipelined = {'int': True,"),
    ('BTB ignores the PC tag', 'issue.py',
     'if entry.valid and entry.pc == pc and entry.taken:', 'if entry.valid and entry.taken:'),
    ('predicted-taken branch does not end the issue group', 'issue.py',
     '                return      # predicted taken: the target is fetched next cycle', '                pass'),
    ('issue does not stop at a full ROB', 'issue.py',
     'if len(st.ROB) >= st.size_ROB:', 'if len(st.ROB) >= st.size_ROB + 1:'),
    ('youngest ready instruction dispatched first', 'exe.py',
     'ready.sort(key=lambda element: element.rob.seq)',
     'ready.sort(key=lambda element: -element.rob.seq)'),
    ('Beq resolved like Bne', 'exe.py',
     'rob.taken = value1 == value2', 'rob.taken = value1 != value2'),
]


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)


def main():
    caught = 0
    for description, filename, old, new in MUTANTS:
        with tempfile.TemporaryDirectory() as tmp:
            # same layout as the repository: code/, tests/, verify/
            root = os.path.join(tmp, 'tomasulo-python')
            shutil.copytree(CODE, os.path.join(root, 'code'))
            shutil.copytree(os.path.join(HERE, '..', 'tests'), os.path.join(root, 'tests'))
            shutil.copytree(HERE, os.path.join(root, 'verify'))
            path = os.path.join(root, 'code', filename)
            with open(path) as f:
                text = f.read()
            if text.count(old) != 1:
                print('ERROR  %s: text to change found %d times in %s' % (description, text.count(old), filename))
                sys.exit(2)
            with open(path, 'w') as f:
                f.write(text.replace(old, new))
            env_fuzz = os.path.join(tmp, 'fuzz')
            tests = run([sys.executable, 'check_all.py'], os.path.join(root, 'verify'))
            fuzz = subprocess.run([sys.executable, 'fuzz.py', '300', '1'], cwd=os.path.join(root, 'verify'),
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                                  env=dict(os.environ, FUZZ_DIR=env_fuzz))
            by_tests = tests.returncode != 0
            by_fuzz = fuzz.returncode != 0
            if by_tests or by_fuzz:
                caught += 1
            print('%-7s %-66s tests: %-6s fuzz: %s' % (
                'caught' if by_tests or by_fuzz else 'MISSED', description,
                'fail' if by_tests else 'pass', 'fail' if by_fuzz else 'pass'))
    print('%d of %d mutants caught' % (caught, len(MUTANTS)))
    sys.exit(0 if caught == len(MUTANTS) else 1)


if __name__ == '__main__':
    main()
