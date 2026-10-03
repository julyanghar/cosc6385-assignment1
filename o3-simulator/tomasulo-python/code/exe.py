# Qing 
# 24th May 2017
# COSC 6385, Oct 2026: several FUs per type, pipelined and unpipelined FUs,
# oldest-first dispatch, branch resolution with misprediction recovery.

'''
1. dispatch: move ready instructions from the reservation stations into free
   functional units, oldest first; start address calculations of loads/stores
   whose base register is ready (dedicated address adders, not the integer ALU)
2. finish instructions whose last EX cycle is this cycle
    -- ALU instructions: result into results_buffer (CDB from next cycle)
    -- loads/stores: address written into the ld_sd_queue entry
    -- branches: compare, update the BTB; on a misprediction squash the younger
       instructions (squash.py)
'''
from init import fu_entry, fu_result
from squash import squash

# function: check rs and return the ready instructions, oldest first
def check_valid_ins_in_rs(rs, cycle):
    ready = []
    for element in rs:
        # an instruction issued in this cycle starts EX next cycle at the earliest
        if (element.busy == 1) and (element.valid_1st == 1) and (element.valid_2nd == 1) \
                and (element.rob.issue[0] < cycle):
            ready.append(element)
    ready.sort(key=lambda element: element.rob.seq)
    return ready

# function: check ld_sd_queue and return the entries ready for address calculation
# (the queue is in program order, so this is oldest first)
def check_valid_ins_in_ldsd(ldsd, cycle):
    return [element for element in ldsd
            if (element.valid == 1) and (element.started == 0) and (element.rob.issue[0] < cycle)]

# function: a functional unit of this type that can start an instruction in this cycle
def find_free_fu(units, cycle):
    for unit in units:
        if unit.next_free <= cycle:
            return unit
    return None

# function: start EX of one instruction on a functional unit
def start_exe(st, kind, unit, rob, value1, value2, cycle):
    end = cycle + st.ex_cycles[kind] - 1
    # pipelined: a new instruction every cycle; unpipelined: busy until EX ends
    unit.next_free = cycle + 1 if st.pipelined[kind] else end + 1
    rob.exe = [cycle, end]
    st.in_flight.append(fu_entry(rob, unit, end, value1, value2))

# function: compute the result of a finished instruction
def calculate(op, value1, value2):
    if op in ('Add', 'Add.d', 'Addi'):
        return value1 + value2
    if op in ('Sub', 'Sub.d'):
        return value1 - value2
    if op == 'Mult.d':
        return value1 * value2
    raise ValueError(op)

# function: resolve a branch at the end of EX and train the BTB entry
def resolve_branch(st, rob, value1, value2):
    if rob.ins.op == 'Beq':
        rob.taken = value1 == value2
    else:
        rob.taken = value1 != value2
    target = rob.PC + 1 + rob.ins.imm
    rob.actual_next = target if rob.taken else rob.PC + 1
    rob.mispredicted = 1 if rob.actual_next != rob.pred_next else 0
    entry = st.BTB[rob.PC % 8]
    entry.valid = 1
    entry.pc = rob.PC
    entry.target = target
    entry.taken = 1 if rob.taken else 0

# function: execution
def exe(cycle, st):
    '''dispatch from reservation stations'''
    for kind in ('int', 'fpadd', 'fpmul'):
        for element in check_valid_ins_in_rs(st.rs[kind], cycle):
            unit = find_free_fu(st.fu[kind], cycle)
            if unit is None:
                break
            start_exe(st, kind, unit, element.rob, element.value_1st, element.value_2nd, cycle)
            # remove ins from rs: the entry can be reused from the next cycle
            element.busy = 0
    '''address calculation of loads and stores'''
    for element in check_valid_ins_in_ldsd(st.ld_sd_queue, cycle):
        unit = find_free_fu(st.fu['ldsd'], cycle)
        if unit is None:
            break
        start_exe(st, 'ldsd', unit, element.rob, element.reg_value, element.immediate, cycle)
        element.started = 1
    '''finish instructions whose EX ends in this cycle'''
    mispredicted = []
    for op in [element for element in st.in_flight if element.end == cycle]:
        st.in_flight.remove(op)
        rob = op.rob
        if rob.ins.unit == 'ldsd':
            rob.lsq.address = op.value1 + op.value2
            rob.lsq.ready = 1
            rob.lsq.ready_cycle = cycle
        elif rob.ins.op in ('Beq', 'Bne'):
            resolve_branch(st, rob, op.value1, op.value2)
            if rob.mispredicted:
                mispredicted.append(rob)
        else:
            st.results_buffer.append(fu_result(rob, calculate(rob.ins.op, op.value1, op.value2), cycle))
    '''misprediction: the oldest one squashes everything younger, including younger branches'''
    if mispredicted:
        branch = min(mispredicted, key=lambda rob: rob.seq)
        squash(st, branch.seq, branch.actual_next, cycle)
