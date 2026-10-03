# Qing 
# 21st May 2017 
# COSC 6385, Oct 2026: configuration, initial values and program come from the
# input file; issue width from the file or --width (CDB buses and commit width
# also from the file or --cdb, --commit-width); output as the assignment asks;
# simulate() can be called by the test scripts.

import argparse
import sys
from init import read_input, State, SimulationError
from print_status import print_config, print_table, print_registers, print_memory, print_summary
from issue import issue
from exe import exe
from mem import mem
from wb import wb
from commit import commit

# function: the program is finished when nothing is left to fetch, the ROB is
# empty and the last store has finished writing memory
def finished(st, cycle):
    return (len(st.ROB) == 0) and not (0 <= st.PC < len(st.instructions)) \
        and (st.mem_busy_until < cycle)

def simulate(path, width=None, max_cycles=10000, cdb=None, commit_width=None):
    config, reg_init, mem_init, instructions = read_input(path)
    if width is not None:
        config['issue_width'] = width
    if cdb is not None:
        config['cdb'] = cdb
    if commit_width is not None:
        config['commit_width'] = commit_width
    st = State(config, reg_init, mem_init, instructions)
    cycle = 1
    while not finished(st, cycle):
        if cycle > max_cycles:
            st.stop_reason = 'reached the limit of %d cycles' % max_cycles
            break
        try:
            # the stages run in this order in every cycle; a stage only uses
            # what a later stage produced if it was produced in an earlier cycle
            '''ISSUE stage'''
            issue(cycle, st)
            '''EXE stage'''
            exe(cycle, st)
            '''MEM stage'''
            mem(cycle, st)
            '''CDB stage'''
            wb(cycle, st)
            '''COMMIT stage'''
            commit(cycle, st)
        except SimulationError as error:
            st.stop_reason = str(error)
            cycle += 1
            break
        # cycle number
        cycle += 1
    st.cycles = cycle - 1
    return st

def main():
    parser = argparse.ArgumentParser(description='Tomasulo simulator with ROB, branch prediction and multiple issue')
    parser.add_argument('input', nargs='?', default='test_case.txt', help='input file (default: test_case.txt)')
    parser.add_argument('--width', type=int, choices=[1, 2, 3, 4],
                        help='issue width; overrides "Issue width = N" in the input file')
    parser.add_argument('--cdb', type=int, choices=[1, 2, 3, 4],
                        help='CDB buses; overrides "CDB buses = N" (default: the issue width)')
    parser.add_argument('--commit-width', type=int, choices=[1, 2, 3, 4],
                        help='commits per cycle; overrides "Commit width = N" (default: the issue width)')
    parser.add_argument('--max-cycles', type=int, default=10000, help='stop after this many cycles (default 10000)')
    args = parser.parse_args()
    try:
        st = simulate(args.input, args.width, args.max_cycles, args.cdb, args.commit_width)
    except SimulationError as error:
        print('input error: %s' % error)
        sys.exit(1)
    print_config(st)
    print_table(st)
    print_registers(st)
    print_memory(st)
    print_summary(st)
    if st.stop_reason is not None:
        sys.exit(2)

if __name__ == '__main__':
    main()
