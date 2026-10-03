# Qing 
# 29th May 2017 
# COSC 6385, Oct 2026: up to cdb_buses broadcasts per cycle; RAT written only
# if it still maps the register to this tag.

'''
1. pick up to cdb_buses results produced in earlier cycles: the earliest
   produced first, then the oldest instruction first
2. broadcast each one: RAT, reservation stations, ld_sd_queue, ROB
3. remove it from the results queue
'''

# function: broadcast
# rat_int, rat_fp, reservation stations, ld_sd_queue, ROB
def broadcast(st, rob, value, cycle):
    dest_tag = rob.ROB_tag
    # RAT: only if no younger instruction has renamed the register since
    # (the original code wrote the value unconditionally, so an old result
    # could overwrite the mapping of a newer one)
    reg_tag = rob.dest_tag
    if reg_tag is not None:
        if reg_tag[0] == 'R' and st.rat_int[int(reg_tag[1:])] == dest_tag:
            st.rat_int[int(reg_tag[1:])] = value
        if reg_tag[0] == 'F' and st.rat_fp[int(reg_tag[1:])] == dest_tag:
            st.rat_fp[int(reg_tag[1:])] = value
    # rs list
    for kind in st.rs:
        for element in st.rs[kind]:
            if element.busy == 0:
                continue
            if (element.tag_1st == dest_tag) & (element.valid_1st == 0):
                element.value_1st = value
                element.valid_1st = 1
            if (element.tag_2nd == dest_tag) & (element.valid_2nd == 0):
                element.value_2nd = value
                element.valid_2nd = 1
    # ld_sd_queue
    for element in st.ld_sd_queue:
        if (element.op == 'Sd') & (element.data_valid == 0) & (element.data == dest_tag):
            element.data = value
            element.data_valid = 1
            element.data_cycle = cycle
        if (element.reg_tag == dest_tag) & (element.valid == 0):
            element.reg_value = value
            element.valid = 1
    # ROB
    rob.value = value
    rob.done = 1
    rob.cdb.append(cycle)

# function: wb
def wb(cycle, st):
    waiting = [r for r in st.results_buffer if r.ready < cycle]
    waiting.sort(key=lambda r: (r.ready, r.rob.seq))
    for result in waiting[:st.cdb_buses]:
        st.results_buffer.remove(result)
        broadcast(st, result.rob, result.value, cycle)
