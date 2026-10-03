#!/bin/bash
# Regenerates results/: the output of every test input at issue widths 1-4,
# the summary tables and the logs of the verification scripts; then checks
# that the generated tables in REPORT.md are current. Exits with status 1 if
# anything failed. Takes about two minutes. Needs Python 3 (standard library
# only) and git (compare_original.py reads the original code from the
# repository history).
cd "$(dirname "$0")" || exit 1
mkdir -p results
status=0
fail() { echo "FAILED: $*"; status=1; }
for t in tests/*.txt; do
    name=$(basename "$t" .txt)
    max=10000
    expected=0
    if [ "$name" = pdf_sample ]; then
        max=40          # loops forever: main.py stops at the limit and exits with 2
        expected=2
    fi
    for w in 1 2 3 4; do
        (cd code && python3 main.py "../$t" --width "$w" --max-cycles "$max") > "results/${name}_w${w}.txt"
        rc=$?
        [ "$rc" -eq "$expected" ] || fail "main.py $t --width $w exited with $rc, expected $expected"
    done
done
(cd verify && python3 report_tables.py) > results/summary.md || fail "report_tables.py"
(cd verify && python3 check_all.py) > results/check_all.txt || fail "check_all.py (see results/check_all.txt)"
(cd verify && python3 fuzz.py 2000 1) > results/fuzz.txt || fail "fuzz.py (see results/fuzz.txt)"
(cd verify && python3 mutants.py) > results/mutants.txt || fail "mutants.py (see results/mutants.txt)"
(cd verify && python3 compare_original.py) > results/compare_original.txt || fail "compare_original.py"
(cd verify && python3 report_tables.py --check ../../REPORT.md) || fail "tables in REPORT.md"
tail -n 1 results/check_all.txt results/fuzz.txt results/mutants.txt
if [ "$status" -eq 0 ]; then echo "run_all.sh: all checks passed"; fi
exit $status
