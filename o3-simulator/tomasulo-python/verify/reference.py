# Functional reference: runs the program one instruction at a time, in program
# order, with no timing, no renaming and no speculation. The simulator must end
# with the same registers and memory and commit the same instruction sequence.
# Only the input parser (init.read_input) is shared with the simulator.

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'code'))
from init import read_input


def run_reference(path, max_steps=100000):
    config, reg_init, mem_init, instructions = read_input(path)
    R = [0] * 32
    F = [0.0] * 32
    for reg, value in reg_init.items():
        (R if reg[0] == 'R' else F)[int(reg[1:])] = value
    M = [0] * 256
    for address, value in mem_init.items():
        M[address] = value

    def get(reg):
        return R[int(reg[1:])] if reg[0] == 'R' else F[int(reg[1:])]

    def put(reg, value):
        if reg == 'R0':
            return
        if reg[0] == 'R':
            R[int(reg[1:])] = value
        else:
            F[int(reg[1:])] = value

    def address_of(ins):
        address = get(ins.base) + ins.imm
        if not (0 <= address < 256):
            raise ValueError('invalid address %d in "%s"' % (address, ins.text))
        return address

    trace = []          # instruction indexes in execution order
    pc = 0
    while 0 <= pc < len(instructions) and len(trace) < max_steps:
        ins = instructions[pc]
        trace.append(pc)
        op = ins.op
        next_pc = pc + 1
        if op == 'Ld':
            put(ins.dest, float(M[address_of(ins)]))
        elif op == 'Sd':
            M[address_of(ins)] = get(ins.src1)
        elif op == 'Beq':
            if get(ins.src1) == get(ins.src2):
                next_pc = pc + 1 + ins.imm
        elif op == 'Bne':
            if get(ins.src1) != get(ins.src2):
                next_pc = pc + 1 + ins.imm
        elif op == 'Addi':
            put(ins.dest, get(ins.src1) + ins.imm)
        elif op in ('Add', 'Add.d'):
            put(ins.dest, get(ins.src1) + get(ins.src2))
        elif op in ('Sub', 'Sub.d'):
            put(ins.dest, get(ins.src1) - get(ins.src2))
        elif op == 'Mult.d':
            put(ins.dest, get(ins.src1) * get(ins.src2))
        else:
            raise ValueError(op)
        pc = next_pc
    finished = not (0 <= pc < len(instructions))
    return trace, R, F, M, finished
