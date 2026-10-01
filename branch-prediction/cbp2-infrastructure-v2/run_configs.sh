#!/bin/bash
# Rebuilds src/predict for every predictor configuration in the report and
# runs the framework's run script on all traces.  The raw output of each run
# goes to results/<name>.txt.  csh and dc must be on PATH (see README.md).
#
# Usage, from cbp2-infrastructure-v2/:  bash run_configs.sh
#
# B0_always_taken.txt is not produced here: it is the output of the unmodified
# skeleton (see README.md).

set -e
cd "$(dirname "$0")"
mkdir -p results

# build src/predict with extra compiler flags.  The framework's 8 known warnings
# (trace.cc, trace.h) are hidden; on an error, rerun the printed command to see it.
# -B: make cannot see that only the flags changed.
build () {
	if ! (cd src && make -B predict CXXFLAGS="-g -O3 -Wall $*" > /dev/null 2>&1); then
		echo "build failed: (cd src && make -B predict CXXFLAGS=\"-g -O3 -Wall $*\")" >&2
		exit 1
	fi
}

# build with extra compiler flags, then run all traces
run_config () {
	name=$1
	shift
	build "$@"
	csh ./run traces > results/$name.txt
	echo "$name ($*): $(tail -1 results/$name.txt)"
}

(cd src && make > /dev/null 2>&1) || { echo "build failed: (cd src && make)" >&2; exit 1; }

# main result and baselines
run_config R1_pm_4way
run_config R2_pm_2way        -DPM_WAYS=2
run_config B1_bimodal_only   -DPM_USE_GLOBAL=0
run_config B2_gshare         -DPREDICTOR=gshare_predictor

# sensitivity of the main configuration
run_config S_ctr_init1       -DPM_CTR_INIT=1
run_config S_hist8           -DPM_HIST_BITS=8
run_config S_hist10          -DPM_HIST_BITS=10
run_config S_hist12          -DPM_HIST_BITS=12
run_config S_hist14          -DPM_HIST_BITS=14

# diagnostics (global hit rate and accuracy), printed to stderr by -DPM_STATS
for ways in 4 2; do
	build -DPM_STATS -DPM_WAYS=$ways
	for t in $(find traces -name '*.trace.*' | sort); do
		echo "$t $(./src/predict $t 2>&1 | tr '\n' ' ')"
	done > results/stats_pm_${ways}way.txt
	echo "stats_pm_${ways}way: done"
done

# leave the default build in place
(cd src && make -B > /dev/null 2>&1) || { echo "build failed: (cd src && make -B)" >&2; exit 1; }
