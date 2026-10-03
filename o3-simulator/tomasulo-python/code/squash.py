# COSC 6385, Oct 2026: misprediction recovery (new file)

'''
Called in the cycle n in which a branch finishes EX and turns out to be
mispredicted. Everything younger than the branch is on the wrong path:
1. clear ROB entries younger than the branch
2. clear the reservation stations (and with them their wait-for tags) and
   ld/sd queue entries of those instructions; also drop them from the
   functional units, from the results waiting for a CDB and from the memory
3. recover the RAT
The PDF counts these actions as one cycle (n+1): fetching from the correct
PC starts in cycle n+2.
'''

def squash(st, branch, cycle):
    def wrong(rob):
        return rob.seq > branch.seq
    '''1. ROB'''
    young = [rob for rob in st.ROB if wrong(rob)]
    for rob in young:
        st.ROB.remove(rob)
    st.squashed += len(young)
    '''2. reservation stations, ld/sd queue, functional units, results, memory'''
    for kind in st.rs:
        for element in st.rs[kind]:
            if element.busy == 1 and wrong(element.rob):
                element.busy = 0
    for element in [e for e in st.ld_sd_queue if wrong(e.rob)]:
        st.ld_sd_queue.remove(element)
    for op in [op for op in st.in_flight if wrong(op.rob)]:
        st.in_flight.remove(op)
        # an unpipelined unit becomes free again; a pipelined one already is
        op.unit.next_free = min(op.unit.next_free, cycle + 1)
    st.results_buffer = [r for r in st.results_buffer if not wrong(r.rob)]
    if st.mem_load is not None and wrong(st.mem_load):
        st.mem_load = None
        st.mem_busy_until = cycle       # memory free again from the next cycle
    '''3. RAT: rebuilt from the architectural registers and the ROB entries
    that remain (all older than the branch, in program order): a register
    maps to its youngest remaining producer, as a value if that producer has
    already broadcast, else as its ROB tag'''
    st.rat_int = list(st.reg_int)
    st.rat_fp = list(st.reg_fp)
    for rob in st.ROB:
        if rob.dest_tag is None:
            continue
        content = rob.value if rob.done else rob.ROB_tag
        if rob.dest_tag[0] == 'F':
            st.rat_fp[int(rob.dest_tag[1:])] = content
        else:
            st.rat_int[int(rob.dest_tag[1:])] = content
    '''fetch from the correct PC in cycle n+2'''
    st.PC = branch.actual_next
    st.fetch_resume = cycle + 2
