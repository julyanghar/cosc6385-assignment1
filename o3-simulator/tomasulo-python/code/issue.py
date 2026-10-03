# Qing 
# 21st May 2017
# COSC 6385, Oct 2026: up to issue_width instructions per cycle, Beq, branch
# prediction with an 8-entry BTB, R0 never renamed.

"""
Up to issue_width times per cycle, in program order:
1. fetch the instruction at PC; stop if its ROB entry, reservation station or
   ld/sd queue entry is not free (structural hazard: later ones wait too)
2. put it in the ROB and in a reservation station / the ld_sd_queue
3. update RAT
4. next PC: PC+1, or the BTB prediction for a branch; a branch predicted
   taken is the last instruction issued in this cycle
"""
from init import ld_sd_entry, ROB_entry

# function: find a tag for ld_sd_entry
def find_tag_new_ldsd_entry(ld_sd_queue, size_ld_sd_queue):
    existing_tag = [element.ld_sd_tag for element in ld_sd_queue]
    for i in range(size_ld_sd_queue):
        if 'ldsd' + str(i) not in existing_tag:
            return 'ldsd' + str(i)

# function put ins into ROB
def put_ins_into_ROB(st, cycle, ins):
    entry = ROB_entry()
    # ROB_tag: the slot after the youngest entry
    if len(st.ROB) == 0:
        entry.ROB_tag = 'ROB0'
    else:
        index = st.ROB[-1].ROB_tag[3:]
        entry.ROB_tag = 'ROB' + str((int(index) + 1) % st.size_ROB)
    entry.seq = st.seq
    st.seq += 1
    entry.PC = st.PC
    entry.ins = ins
    # dest_tag: destination register; never R0, which is hardwired to 0
    if ins.dest != 'R0':
        entry.dest_tag = ins.dest
    # issue
    entry.issue.append(cycle)
    st.ROB.append(entry)
    return entry

# function: read a source register: (value, None) if the value is known, else (None, ROB tag)
def read_register(st, register):
    if register == 'R0':
        return 0, None
    if register[0] == 'F':
        content = st.rat_fp[int(register[1:])]
    else:
        content = st.rat_int[int(register[1:])]
    if type(content) == str:
        return None, content
    return content, None

# function: put ins into reservation station (ALU instructions and branches)
def put_ins_into_rs(entry, ins, rob, st):
    entry.busy = 1
    entry.op = ins.op
    entry.rob = rob
    entry.dest_tag = rob.ROB_tag
    # operand 1
    entry.value_1st, entry.tag_1st = read_register(st, ins.src1)
    entry.valid_1st = 1 if entry.tag_1st is None else 0
    # operand 2: a register, or the immediate of Addi
    if ins.op == 'Addi':
        entry.value_2nd, entry.tag_2nd = ins.imm, None
    else:
        entry.value_2nd, entry.tag_2nd = read_register(st, ins.src2)
    entry.valid_2nd = 1 if entry.tag_2nd is None else 0

# function: put ins into ld_sd_queue
def put_ins_into_ldsd(st, ins, rob, cycle):
    entry = ld_sd_entry()
    entry.ld_sd_tag = find_tag_new_ldsd_entry(st.ld_sd_queue, st.size_ld_sd_queue)
    entry.op = ins.op
    entry.rob = rob
    entry.dest_tag = rob.ROB_tag
    entry.immediate = ins.imm
    # base register
    entry.reg_value, entry.reg_tag = read_register(st, ins.base)
    entry.valid = 1 if entry.reg_tag is None else 0
    # Sd: data register
    if ins.op == 'Sd':
        value, tag = read_register(st, ins.src1)
        if tag is None:
            entry.data, entry.data_valid, entry.data_cycle = value, 1, cycle
        else:
            entry.data, entry.data_valid = tag, 0
    rob.lsq = entry
    st.ld_sd_queue.append(entry)

# function: check space of reservation station
def check_rs_space(station):
    index = -1
    for i in range(len(station)):
        if station[i].busy == 0:
            index = i
            break
    return index

# update RAT
def update_rat(rob, st):
    if rob.dest_tag is None:
        return
    if rob.dest_tag[0] == 'F':
        st.rat_fp[int(rob.dest_tag[1:])] = rob.ROB_tag
    else:
        st.rat_int[int(rob.dest_tag[1:])] = rob.ROB_tag

# branch prediction: 8-entry BTB indexed by the 3 low bits of the word address
# of the branch (instruction i is at byte address 4*i, word address i). An entry
# holds the PC of the branch it belongs to, its target and a 1-bit predictor.
def predict_branch(st, pc):
    entry = st.BTB[pc % 8]
    if entry.valid and entry.pc == pc and entry.taken:
        return entry.target
    return pc + 1

""""""
def issue(cycle, st):
    # no issue in the cycle after a misprediction was detected
    if cycle < st.fetch_resume:
        return
    for _ in range(st.issue_width):
        # fetch: nothing to fetch past the end of the program (or on a wrong
        # path that left it); a misprediction recovery sets PC again
        if not (0 <= st.PC < len(st.instructions)):
            return
        ins = st.instructions[st.PC]
        '''check space'''
        if len(st.ROB) >= st.size_ROB:
            return
        if ins.unit == 'ldsd':
            if len(st.ld_sd_queue) >= st.size_ld_sd_queue:
                return
        else:
            index = check_rs_space(st.rs[ins.unit])
            if index < 0:
                return
        '''issue'''
        rob = put_ins_into_ROB(st, cycle, ins)
        if ins.unit == 'ldsd':
            put_ins_into_ldsd(st, ins, rob, cycle)
        else:
            put_ins_into_rs(st.rs[ins.unit][index], ins, rob, st)
        update_rat(rob, st)
        '''next PC'''
        if ins.op in ('Beq', 'Bne'):
            rob.pred_next = predict_branch(st, st.PC)
            st.PC = rob.pred_next
            if rob.pred_next != rob.PC + 1:
                return      # predicted taken: the target is fetched next cycle
        else:
            st.PC += 1
