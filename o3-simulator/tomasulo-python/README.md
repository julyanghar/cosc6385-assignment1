Tomasulo Algorithm Simulation
* includes instructions of int_add, fp_add, fp_multi, load, store, branch;
* implements ROB, RAT, load-store-queue;
* implements out-of-order processing and memory disambiguation; 
* issues 1 to 4 instructions per cycle, in order (added for COSC 6385);
* predicts branches with a 1-bit predictor and an 8-entry BTB and squashes wrong-path instructions (added for COSC 6385).

How to run:
cd code;
python3 main.py [input file] [--width N]

The input file format, the tests and the verification scripts are described in part 2 of ../../README.md.
