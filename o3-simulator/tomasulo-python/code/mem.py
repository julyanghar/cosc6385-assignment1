# Qing 
# 26th May 2017
# COSC 6385, Oct 2026: stores no longer access memory here (they write at
# commit, see commit.py); forwarding and memory access start at the earliest
# in the cycle after the address calculation; values are 4 bytes; loads go
# ahead of stores with unknown addresses and are replayed if that was wrong;
# a load leaves the queue when it has its data.

'''
MEM stage for loads, in program order. A load or store at address a uses the
4 bytes a..a+3; two of them overlap if they share a byte.
1. memory-order check (see below)
2. a load whose address was calculated in an earlier cycle looks at the older
   stores in the ld_sd_queue whose address is known. As the handout says,
   stores whose address is not known yet do not stop it.
3. the youngest of those stores that overlaps the load:
    -- same address and its data is there: forward the data (rounded to
       single precision, as memory would hold it), 1 cycle
    -- same address, data not there yet: wait
    -- overlaps only partly: wait until that store has written memory
4. no such store: access memory when it is free (single port, not
   pipelined, time_mem cycles); one load starts per cycle, the oldest
The load leaves the ld_sd_queue in the cycle it gets its data; its result
goes to the results_buffer and onto a CDB from the next cycle.

Memory-order check: a load that went ahead of a store with an unknown address
has a wrong value if that store overlaps it, unless the load forwarded from a
younger store at the same address. In the cycle after a store's address is
calculated, it is compared with the younger loads that already got or are
getting their data. On a conflict the oldest such load and everything after it
are squashed and the load is fetched again, as after a mispredicted branch.
'''
from init import fu_result, to_single, valid_address, read_single
from squash import squash

# function: do two 4-byte accesses share a byte?
def overlap(address1, address2):
    return (address1 < address2 + 4) and (address2 < address1 + 4)

# function: forward check from sd: the youngest older store with a known
# address that overlaps the load, or None
def forward_check_from_sd(ld_sd_queue, index, cycle):
    load = ld_sd_queue[index]
    match = None
    for i in range(index):
        element = ld_sd_queue[i]
        # an address calculated in this cycle is known from the next cycle
        if (element.op == 'Sd') and (element.ready == 1) and (element.ready_cycle < cycle) \
                and overlap(element.address, load.address):
            match = element     # keep the youngest
    return match

# function: memory-order check: the oldest load that got its data without a
# store whose address was calculated in the previous cycle, and overlaps it
def check_memory_order(st, cycle):
    victim = None
    for store in st.ld_sd_queue:
        if (store.op != 'Sd') or (store.ready_cycle != cycle - 1):
            continue
        for rob in st.ROB:
            if (rob.ins.op != 'Ld') or (rob.seq < store.rob.seq) or (len(rob.mem) == 0):
                continue
            if not overlap(store.address, rob.lsq.address):
                continue
            if rob.forwarded and (rob.forwarded_from.seq > store.rob.seq):
                continue    # forwarded from a younger store at the same address: still right
            if (victim is None) or (rob.seq < victim.seq):
                victim = rob
    return victim

# function: memory read; an invalid address reads 0 and is reported if the load commits
def read_memory(st, rob, address):
    if valid_address(address):
        return read_single(st.memory, address)
    rob.error = 'load from invalid address %d' % address
    return 0.0

# function: mem
def mem(cycle, st):
    '''memory-order check'''
    victim = check_memory_order(st, cycle)
    if victim is not None:
        st.violations += 1
        squash(st, victim.seq - 1, victim.PC, cycle)    # the load is squashed too
        st.replay_pc = victim.PC
    '''forwarding check, and find the oldest load that has to access memory'''
    to_memory = None
    for index in range(len(st.ld_sd_queue)):
        element = st.ld_sd_queue[index]
        if (element.op != 'Ld') or (element.ready == 0) or (element.ready_cycle >= cycle) \
                or (element.in_memory == 1):
            continue
        store = forward_check_from_sd(st.ld_sd_queue, index, cycle)
        if store is None:
            if to_memory is None:
                to_memory = element
        elif (store.address == element.address) and (store.data_valid == 1):
            # forward the data: 1 cycle in MEM
            element.rob.mem = [cycle, cycle]
            element.rob.forwarded = 1
            element.rob.forwarded_from = store.rob
            st.results_buffer.append(fu_result(element.rob, to_single(store.data), cycle))
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
