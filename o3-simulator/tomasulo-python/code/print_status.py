# Qing 
# 21st May 2017
# COSC 6385, Oct 2026: replaced the namedtuple dumps with the output the
# assignment asks for: instruction status table, registers, non-zero memory.

# function: format a register or memory value
def fmt(value):
    if type(value) == float:
        return str(round(value, 6))
    return str(value)

# function: print the configuration actually used
def print_config(st):
    c = st.config
    print('CONFIGURATION'.ljust(18) + '# of rs'.ljust(10) + 'Cycles in EX'.ljust(15)
          + 'Cycles in Mem'.ljust(15) + '# of FUs')
    rows = [('Integer adder', 'int'), ('FP adder', 'fpadd'),
            ('FP multiplier', 'fpmul'), ('Load/store unit', 'ldsd')]
    for name, unit in rows:
        mem = str(c['ldsd_mem']) if unit == 'ldsd' else ''
        print(name.ljust(18) + str(c[unit + '_rs']).ljust(10) + str(c[unit + '_ex']).ljust(15)
              + mem.ljust(15) + str(c[unit + '_fu']))
    print('ROB entries = %d, Issue width = %d, CDB buses = %d, Commit width = %d'
          % (st.size_ROB, st.issue_width, st.cdb_buses, st.commit_width))
    print()

# function: print the instruction status table (committed instructions, in order)
def print_table(st):
    width = max([len(ins.text) for ins in st.instructions] + [11]) + 2
    print(''.ljust(width) + 'ISSUE'.ljust(8) + 'EX'.ljust(12) + 'MEM'.ljust(12)
          + 'WB'.ljust(8) + 'COMMIT'.ljust(8) + 'NOTE')
    for entry in st.committed:
        note = []
        if entry.ins.op in ('Beq', 'Bne'):
            note.append('taken' if entry.taken else 'not taken')
            if entry.mispredicted:
                note.append('mispredicted')
        if entry.forwarded:
            note.append('forwarded')
        print(entry.ins.text.ljust(width) + str(entry.issue).ljust(8) + str(entry.exe).ljust(12)
              + str(entry.mem).ljust(12) + str(entry.cdb).ljust(8) + str(entry.commit).ljust(8)
              + ', '.join(note))
    print()

# function: print the architectural registers, 8 per row
def print_registers(st):
    print('REGISTER VALUES')
    for kind, regs in (('R', st.reg_int), ('F', st.reg_fp)):
        for start in range(0, 32, 8):
            print(''.ljust(8) + ''.join((kind + str(i)).ljust(10) for i in range(start, start + 8)))
            print('value:'.ljust(8) + ''.join(fmt(regs[i]).ljust(10) for i in range(start, start + 8)))
    print()

# function: print the non-zero memory words
def print_memory(st):
    print('NON-ZERO MEMORY VALUES')
    print('Addresses'.ljust(12) + 'Values')
    for address in range(256):
        if st.memory[address] != 0:
            print(str(address).ljust(12) + fmt(st.memory[address]))
    print()

# function: one summary line
def print_summary(st):
    branches = [e for e in st.committed if e.ins.op in ('Beq', 'Bne')]
    mispredicted = [e for e in branches if e.mispredicted]
    ipc = len(st.committed) / st.cycles if st.cycles else 0.0
    print('Cycles: %d, committed instructions: %d, IPC: %.3f, branches: %d, mispredicted: %d, '
          'squashed instructions: %d' % (st.cycles, len(st.committed), ipc, len(branches),
                                          len(mispredicted), st.squashed))
    if st.stop_reason is not None:
        print('STOPPED: ' + st.stop_reason)
