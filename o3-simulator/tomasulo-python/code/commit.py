# Qing 
# 29th may 2017
# COSC 6385, Oct 2026: up to commit_width instructions per cycle; stores write
# memory here; branches get a commit cycle; no crash when the ROB empties.
'''
Commit up to commit_width instructions from the ROB head, in order. The head
commits in this cycle if
    -- ALU instruction or load: its result was broadcast in an earlier cycle
       (architectural register written; R0 stays 0)
    -- branch: it finished EX in an earlier cycle
    -- store: its address and data arrived in an earlier cycle and the memory
       is free; the store writes memory now, as a 4-byte single-precision
       value (MEM = time_mem cycles from this cycle), and leaves the
       ld_sd_queue
Otherwise it and everything behind it wait.
'''
from init import SimulationError, valid_address, write_single

# function: modify architectual reg
def modify_arch_reg(entry, st):
    if entry.dest_tag is None:
        return
    if entry.dest_tag[0] == 'F':
        st.reg_fp[int(entry.dest_tag[1:])] = entry.value
    else:
        st.reg_int[int(entry.dest_tag[1:])] = entry.value

# function: can the ROB head commit in this cycle?
def ready_to_commit(head, st, cycle):
    op = head.ins.op
    if op in ('Beq', 'Bne'):
        return (len(head.exe) == 2) and (head.exe[1] < cycle)
    if op == 'Sd':
        lsq = head.lsq
        return (lsq.ready == 1) and (lsq.ready_cycle < cycle) \
            and (lsq.data_valid == 1) and (lsq.data_cycle < cycle) \
            and (st.mem_busy_until < cycle)
    return (len(head.cdb) != 0) and (head.cdb[0] < cycle)

# function: commit
def commit(cycle, st):
    for _ in range(st.commit_width):
        if len(st.ROB) == 0:
            return
        head = st.ROB[0]
        if not ready_to_commit(head, st, cycle):
            return
        if head.error is not None:
            raise SimulationError('%s (instruction "%s")' % (head.error, head.ins.text))
        if head.ins.op == 'Sd':
            address = head.lsq.address
            if not valid_address(address):
                raise SimulationError('store to invalid address %d (instruction "%s")' % (
                    address, head.ins.text))
            write_single(st.memory, address, head.lsq.data)
            head.mem = [cycle, cycle + st.time_mem - 1]
            st.mem_busy_until = cycle + st.time_mem - 1
            st.ld_sd_queue.remove(head.lsq)
        modify_arch_reg(head, st)
        head.commit.append(cycle)
        st.ROB.popleft()
        st.committed.append(head)
