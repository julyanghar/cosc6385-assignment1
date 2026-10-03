# Qing 
# 26th May 2017
# COSC 6385, Oct 2026: stores no longer access memory here (they write at
# commit, see commit.py); forwarding and memory access start at the earliest
# in the cycle after the address calculation; a load leaves the queue when it
# has its data.

'''
MEM stage for loads, in program order. A load whose address was calculated in
an earlier cycle:
1. waits while an older store in the ld_sd_queue has no address yet
2. forwarding check: the youngest older store with the same address
    -- has its data: forward it, 1 cycle
    -- data not there yet: wait
3. no such store: access memory when it is free (single port, not
   pipelined, time_mem cycles); one load starts per cycle, the oldest
The load leaves the ld_sd_queue in the cycle it gets its data; its result
goes to the results_buffer and onto a CDB from the next cycle.
'''
from init import fu_result

# function: forward check from sd
# returns (store, all older stores have their address)
def forward_check_from_sd(ld_sd_queue, index, cycle):
    load = ld_sd_queue[index]
    match = None
    for i in range(index):
        element = ld_sd_queue[i]
        if element.op == 'Sd':
            # an address calculated in this cycle is known from the next cycle
            if (element.ready == 0) or (element.ready_cycle >= cycle):
                return None, False
            if element.address == load.address:
                match = element     # keep the youngest
    return match, True

# function: memory read; an address outside 0-255 reads 0 and is reported if the load commits
def read_memory(st, rob, address):
    if 0 <= address < 256:
        return float(st.memory[address])
    rob.error = 'load from invalid address %d' % address
    return 0.0

# function: mem
def mem(cycle, st):
    '''forwarding check, and find the oldest load that has to access memory'''
    to_memory = None
    for index in range(len(st.ld_sd_queue)):
        element = st.ld_sd_queue[index]
        if (element.op != 'Ld') or (element.ready == 0) or (element.ready_cycle >= cycle) \
                or (element.in_memory == 1):
            continue
        store, addresses_known = forward_check_from_sd(st.ld_sd_queue, index, cycle)
        if not addresses_known:
            continue
        if store is None:
            if to_memory is None:
                to_memory = element
        elif store.data_valid == 1:
            # forward the data: 1 cycle in MEM
            element.rob.mem = [cycle, cycle]
            element.rob.forwarded = 1
            st.results_buffer.append(fu_result(element.rob, store.data, cycle))
            element.in_memory = -1      # done; removed from the queue below
    for element in [e for e in st.ld_sd_queue if e.in_memory == -1]:
        st.ld_sd_queue.remove(element)
    '''start a memory access'''
    if (to_memory is not None) and (st.mem_busy_until < cycle):
        to_memory.in_memory = 1
        to_memory.rob.mem = [cycle, cycle + st.time_mem - 1]
        st.mem_busy_until = cycle + st.time_mem - 1
        st.mem_load = to_memory.rob
    '''finish a memory access'''
    if (st.mem_load is not None) and (st.mem_load.mem[1] == cycle):
        rob = st.mem_load
        st.results_buffer.append(fu_result(rob, read_memory(st, rob, rob.lsq.address), cycle))
        st.ld_sd_queue.remove(rob.lsq)
        st.mem_load = None
