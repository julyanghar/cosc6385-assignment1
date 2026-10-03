#!/bin/bash
# Regenerates results/: the output of every test input at issue widths 1-4,
# the summary table of REPORT.md and the logs of the verification scripts.
# Takes about two minutes. Needs Python 3 (standard library only) and git
# (compare_original.py reads the original code from the repository history).
cd "$(dirname "$0")"
mkdir -p results
for t in tests/*.txt; do
    name=$(basename "$t" .txt)
    max=10000
    [ "$name" = pdf_sample ] && max=40      # loops forever; keep the output short
    for w in 1 2 3 4; do
        (cd code && python3 main.py "../$t" --width "$w" --max-cycles "$max") > "results/${name}_w${w}.txt"
    done
done
(cd verify && python3 summary.py) > results/summary.md
(cd verify && python3 check_all.py) > results/check_all.txt
(cd verify && python3 fuzz.py 2000 1) > results/fuzz.txt
(cd verify && python3 mutants.py) > results/mutants.txt
(cd verify && python3 compare_original.py) > results/compare_original.txt
tail -n 1 results/check_all.txt results/fuzz.txt results/mutants.txt
