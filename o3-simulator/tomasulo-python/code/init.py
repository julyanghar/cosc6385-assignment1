# Qing 
# 21st May 2017 
# COSC 6385, Oct 2026: plain classes instead of namedtuple classes, input file
# parsing, machine state for multi-issue and branch prediction.

import re
from collections import deque

'''define data types'''
# The original code built a new namedtuple *class* per entry and stored values
# as class attributes; a field that was never set read back as a descriptor
# object. Plain classes with every field set to a default behave the same way
# for set fields and give None for unset ones.

# reservation station
class rs_entry:
    def __init__(self):
        self.busy = 0
        self.op = None
        self.tag_1st = None
        self.value_1st = None
        self.valid_1st = 0
        self.tag_2nd = None
        self.value_2nd = None
        self.valid_2nd = 0
        self.dest_tag = None    # ROB tag of the instruction held in this entry
        self.rob = None         # that ROB entry

# instruction in a functional unit (also used for the address adders)
class fu_entry:
    def __init__(self, rob, unit, end, value1, value2):
        self.rob = rob          # ROB entry of the instruction
        self.unit = unit        # the fu_unit executing it
        self.end = end          # last cycle of EX
        self.value1 = value1
        self.value2 = value2

# one functional unit: can start a new instruction in cycle c if next_free <= c
class fu_unit:
    def __init__(self):
        self.next_free = 1

# result waiting for a CDB
class fu_result:
    def __init__(self, rob, value, ready):
        self.rob = rob
        self.value = value
        self.ready = ready      # cycle the result was produced; broadcast at ready+1 or later

# ld/sd queue entry
class ld_sd_entry:
    def __init__(self):
        self.ld_sd_tag = None
        self.op = None          # 'Ld' or 'Sd'
        self.dest_tag = None    # ROB tag
        self.rob = None
        self.immediate = None
        self.reg_tag = None     # base register: tag or value
        self.reg_value = None
        self.valid = 0
        self.started = 0        # address calculation started
        self.ready = 0          # address calculated
        self.ready_cycle = None # cycle the address calculation finished
        self.address = None
        self.data = None        # Sd: value or tag of the data register
        self.data_valid = 0
        self.data_cycle = None  # Sd: cycle the data arrived
        self.in_memory = 0      # Ld: memory access started

# ROB entry
class ROB_entry:
    def __init__(self):
        self.ROB_tag = None
        self.seq = None         # program-order number of this dynamic instruction
        self.PC = None          # instruction index
        self.ins = None         # decoded instruction
        self.value = None
        self.done = 0           # value broadcast on a CDB
        self.dest_tag = None    # destination register name, None if no register result
        self.issue = []
        self.exe = []
        self.mem = []
        self.cdb = []
        self.commit = []
        self.lsq = None         # ld/sd queue entry of a load or store
        self.pred_next = None   # branch: predicted next PC
        self.actual_next = None # branch: resolved next PC
        self.taken = None
        self.mispredicted = 0
        self.forwarded = 0      # load got its data from a store in the queue
        self.error = None       # bad memory address, reported only if the instruction commits

# BTB entry
class btb_entry:
    def __init__(self):
        self.valid = 0
        self.pc = None          # PC of the branch (tag)
        self.target = None
        self.taken = 0          # 1-bit predictor: last outcome

# decoded instruction
class instruction:
    def __init__(self, text, op):
        self.text = text        # the line as written in the input file
        self.op = op
        self.dest = None        # destination register name
        self.src1 = None        # register names; src2 is None for Addi, Ld and Sd
        self.src2 = None
        self.imm = None         # Addi immediate, Ld/Sd offset, branch offset
        self.base = None        # Ld/Sd base register
        self.unit = None        # 'int', 'fpadd', 'fpmul' or 'ldsd'

class SimulationError(Exception):
    pass

'''input file'''
# canonical opcode names, as the original code spells them
OPS = {'ld': 'Ld', 'sd': 'Sd', 'beq': 'Beq', 'bne': 'Bne',
       'add': 'Add', 'addi': 'Addi', 'sub': 'Sub',
       'add.d': 'Add.d', 'sub.d': 'Sub.d', 'mult.d': 'Mult.d'}

# values of the PDF's sample input, used for anything the input file leaves out
DEFAULT_CONFIG = {
    'int_rs': 2, 'int_ex': 1, 'int_fu': 1,
    'fpadd_rs': 3, 'fpadd_ex': 3, 'fpadd_fu': 1,
    'fpmul_rs': 2, 'fpmul_ex': 20, 'fpmul_fu': 1,
    'ldsd_rs': 3, 'ldsd_ex': 1, 'ldsd_mem': 4, 'ldsd_fu': 1,
    'rob': 128, 'issue_width': 1, 'cdb': None, 'commit_width': None,
}

def register(name, kind, line):
    # name: e.g. 'r1' or 'f2'; kind: 'R' or 'F'
    m = re.match(r'^([rf])(\d+)$', name.lower())
    if not m or int(m.group(2)) > 31:
        raise SimulationError('bad register %r in: %s' % (name, line))
    if m.group(1).upper() != kind:
        raise SimulationError('%s needs an %s register, got %r in: %s' % (
            'FP' if kind == 'F' else 'integer', kind, name, line))
    return kind + m.group(2)

def parse_instruction(line):
    tokens = line.replace(',', ' ').split()
    op = OPS.get(tokens[0].lower())
    if op is None:
        raise SimulationError('unknown instruction: %s' % line)
    ins = instruction(line, op)
    args = tokens[1:]
    try:
        if op in ('Ld', 'Sd'):
            m = re.match(r'^(-?\d+)\(([rR]\d+)\)$', args[1])
            if len(args) != 2 or not m:
                raise SimulationError('expected "%s Fa, offset(Ra)": %s' % (op, line))
            ins.imm = int(m.group(1))
            ins.base = register(m.group(2), 'R', line)
            if op == 'Ld':
                ins.dest = register(args[0], 'F', line)
            else:
                ins.src1 = register(args[0], 'F', line)    # data to store
            ins.unit = 'ldsd'
        elif op in ('Beq', 'Bne'):
            if len(args) != 3:
                raise SimulationError('expected "%s Rs, Rt, offset": %s' % (op, line))
            ins.src1 = register(args[0], 'R', line)
            ins.src2 = register(args[1], 'R', line)
            ins.imm = int(args[2])
            ins.unit = 'int'
        elif op == 'Addi':
            if len(args) != 3:
                raise SimulationError('expected "Addi Rt, Rs, immediate": %s' % line)
            ins.dest = register(args[0], 'R', line)
            ins.src1 = register(args[1], 'R', line)
            ins.imm = int(args[2])
            ins.unit = 'int'
        else:
            kind = 'F' if op.endswith('.d') else 'R'
            if len(args) != 3:
                raise SimulationError('expected "%s %sd, %ss, %st": %s' % (op, kind, kind, kind, line))
            ins.dest = register(args[0], kind, line)
            ins.src1 = register(args[1], kind, line)
            ins.src2 = register(args[2], kind, line)
            ins.unit = {'Add': 'int', 'Sub': 'int', 'Add.d': 'fpadd',
                        'Sub.d': 'fpadd', 'Mult.d': 'fpmul'}[op]
    except (IndexError, ValueError):
        raise SimulationError('cannot parse: %s' % line)
    return ins

def parse_number(text, line):
    try:
        if re.match(r'^-?\d+$', text):
            return int(text)
        return float(text)
    except ValueError:
        raise SimulationError('bad number %r in: %s' % (text, line))

# function: read the input file (configuration, initial values, program)
def read_input(path):
    config = dict(DEFAULT_CONFIG)
    reg_init = {}       # 'R1' -> 10, 'F2' -> 30.1
    mem_init = {}       # byte address -> value
    instructions = []
    rows = {'integer adder': 'int', 'fp adder': 'fpadd',
            'fp multiplier': 'fpmul', 'load/store unit': 'ldsd'}
    settings = {'rob entries': 'rob', 'issue width': 'issue_width',
                'cdb buses': 'cdb', 'commit width': 'commit_width'}
    with open(path) as f:
        lines = f.read().splitlines()
    for raw in lines:
        line = raw.strip()
        low = line.lower()
        if line == '' or line.startswith('#'):     # blank line, comment, table header
            continue
        row = [r for r in rows if low.startswith(r)]
        setting = [s for s in settings if low.startswith(s)]
        if row:
            unit = rows[row[0]]
            numbers = [int(x) for x in re.findall(r'\d+', low[len(row[0]):])]
            fields = ['rs', 'ex', 'mem', 'fu'] if unit == 'ldsd' else ['rs', 'ex', 'fu']
            if len(numbers) != len(fields):
                raise SimulationError('expected %d numbers (%s): %s' % (
                    len(fields), ', '.join(fields), line))
            for field, number in zip(fields, numbers):
                if number < 1:
                    raise SimulationError('%s must be at least 1: %s' % (field, line))
                config[unit + '_' + field] = number
        elif setting:
            m = re.match(r'^[a-z ]+=\s*(\d+)$', low)
            if not m or int(m.group(1)) < 1:
                raise SimulationError('expected "%s = N" with N >= 1: %s' % (setting[0], line))
            config[settings[setting[0]]] = int(m.group(1))
        elif re.match(r'^[rf]\d+\s*=', low):
            for item in line.split(','):
                name, _, value = item.partition('=')
                name = name.strip().upper()
                reg = register(name, name[:1], line)
                if reg == 'R0':
                    raise SimulationError('R0 is hardwired to 0: %s' % line)
                value = parse_number(value.strip(), line)
                if reg[0] == 'R' and type(value) != int:
                    raise SimulationError('integer register needs an integer: %s' % line)
                reg_init[reg] = value if reg[0] == 'R' else float(value)
        elif low.startswith('mem['):
            for item in line.split(','):
                m = re.match(r'^mem\[(\d+)\]\s*=\s*(\S+)$', item.strip().lower())
                if not m:
                    raise SimulationError('expected "Mem[address]=value": %s' % line)
                address = int(m.group(1))
                if address >= 256:
                    raise SimulationError('memory address must be below 256: %s' % line)
                mem_init[address] = float(parse_number(m.group(2), line))
        else:
            instructions.append(parse_instruction(line))
    if config['issue_width'] > 4:
        raise SimulationError('issue width must be 1 to 4')
    return config, reg_init, mem_init, instructions

'''machine state'''
class State:
    def __init__(self, config, reg_init, mem_init, instructions):
        self.config = config
        self.instructions = instructions
        self.issue_width = config['issue_width']
        # CDB buses and commit width default to the issue width
        self.cdb_buses = config['cdb'] or config['issue_width']
        self.commit_width = config['commit_width'] or config['issue_width']
        # integer and FP registers, 32 each; RAT entries hold a value or a ROB tag
        self.reg_int = [0] * 32
        self.reg_fp = [0.0] * 32
        for reg, value in reg_init.items():
            if reg[0] == 'R':
                self.reg_int[int(reg[1:])] = value
            else:
                self.reg_fp[int(reg[1:])] = value
        self.rat_int = list(self.reg_int)
        self.rat_fp = list(self.reg_fp)
        # memory: 256 byte addresses; as in the original code each address holds
        # one value (a value is not split into bytes), so any address 0-255 works
        self.memory = [0] * 256
        for address, value in mem_init.items():
            self.memory[address] = value
        # reservation stations and functional units
        self.rs = {}
        self.fu = {}
        for unit in ('int', 'fpadd', 'fpmul'):
            self.rs[unit] = [rs_entry() for _ in range(config[unit + '_rs'])]
        for unit in ('int', 'fpadd', 'fpmul', 'ldsd'):
            self.fu[unit] = [fu_unit() for _ in range(config[unit + '_fu'])]
        self.ex_cycles = {unit: config[unit + '_ex'] for unit in ('int', 'fpadd', 'fpmul', 'ldsd')}
        # the integer adder and the address adders are not pipelined; FP adder and multiplier are
        self.pipelined = {'int': False, 'fpadd': True, 'fpmul': True, 'ldsd': False}
        self.in_flight = []         # fu_entry list: instructions in EX
        self.results_buffer = []    # fu_result list: results waiting for a CDB
        # load/store queue and the single-ported, non-pipelined memory
        self.ld_sd_queue = deque()
        self.size_ld_sd_queue = config['ldsd_rs']
        self.time_mem = config['ldsd_mem']
        self.mem_busy_until = 0     # last cycle of the current memory access
        self.mem_load = None        # ROB entry of the load using the memory, if any
        # ROB
        self.ROB = deque()
        self.size_ROB = config['rob']
        self.seq = 0
        # fetch
        self.PC = 0
        self.fetch_resume = 1       # no issue before this cycle (misprediction recovery)
        self.BTB = [btb_entry() for _ in range(8)]
        # results
        self.committed = []         # committed ROB entries in order
        self.squashed = 0           # wrong-path instructions removed from the ROB
        self.cycles = 0
        self.stop_reason = None
