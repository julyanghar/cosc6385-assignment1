// test_pm.cc
// Tests for pm_predictor in my_predictor.h.  Not part of the simulator.
//
// 1. Appendix replay (only with the tiny configuration of the worked example):
//    replays the 22 branches of the assignment PDF, pages 7-11, and compares
//    before every branch the GHR, the bimodal table and the whole global table,
//    and after predict() the set, tag, global hit/miss and final prediction.
//      g++ -O2 -Wall -DPM_BIM_BITS=4 -DPM_PC_SHIFT=2 -DPM_SET_BITS=2 -DPM_TAG_BITS=2 -DPM_WAYS=2 -DPM_HIST_BITS=4 -o test_pm test_pm.cc
// 2. Checks for any configuration: non-conditional branches change nothing,
//    2-bit counters saturate, LRU replacement order.  Also run them with the
//    default (main experiment, 4-way) configuration:
//      g++ -O2 -Wall -o test_pm4 test_pm.cc

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "branch.h"
#include "predictor.h"
#include "my_predictor.h"

int failures = 0;

void check (bool ok, const char *what) {
	printf ("  %-4s %s\n", ok ? "ok" : "FAIL", what);
	if (!ok) failures++;
}

branch_info cond_branch (unsigned int address) {
	branch_info b;
	b.address = address;
	b.opcode = 0;
	b.br_flags = BR_CONDITIONAL;
	return b;
}

bool same_state (pm_predictor *a, pm_predictor *b) {
	return a->ghr == b->ghr
	    && memcmp (a->bim, b->bim, sizeof (a->bim)) == 0
	    && memcmp (a->valid, b->valid, sizeof (a->valid)) == 0
	    && memcmp (a->tag, b->tag, sizeof (a->tag)) == 0
	    && memcmp (a->ctr, b->ctr, sizeof (a->ctr)) == 0
	    && memcmp (a->age, b->age, sizeof (a->age)) == 0;
}

// the ages of a set must always be a permutation of 0 .. PM_WAYS-1
bool ages_ok (pm_predictor *p, int set) {
	int seen[PM_WAYS] = { 0 };
	for (int w = 0; w < PM_WAYS; w++) {
		if (p->age[set][w] >= PM_WAYS || seen[p->age[set][w]]) return false;
		seen[p->age[set][w]] = 1;
	}
	return true;
}

#if PM_BIM_BITS == 4 && PM_PC_SHIFT == 2 && PM_SET_BITS == 2 && PM_TAG_BITS == 2 \
 && PM_WAYS == 2 && PM_HIST_BITS == 4

// One row of the worked example.  Except for taken, everything is the state
// BEFORE the branch is predicted.  Sources in the PDF:
//   page 8:      outcome, GHR (Col-4), set and tag (Col-6), global hit (Col-7),
//                final prediction (Col-8)
//   page 9:      bimodal counters 1, 4 and 11 (the ones b1, b3 and b2 use)
//   pages 10-11: global table; per set "valid tag 2bc LRU" of way 0, then way 1
struct appendix_row {
	int row;
	const char *br;
	int taken;
	const char *ghr;
	int set;
	const char *tag;
	int bim1, bim4, bim11;
	const char *global;		// "miss", "hit T" or "hit NT"
	const char *final;		// final prediction
	const char *table[4];
};

appendix_row rows[22] = {
	{  1, "b1", 1, "0000", 0, "01", 1, 0, 3, "miss",   "NT", { "0 00 0 1  0 00 3 0", "0 00 1 1  0 00 2 0", "0 00 2 1  0 00 1 0", "0 00 3 1  0 00 0 0" } },
	{  2, "b3", 1, "0001", 1, "01", 2, 0, 3, "miss",   "NT", { "1 01 1 0  0 00 3 1", "0 00 1 1  0 00 2 0", "0 00 2 1  0 00 1 0", "0 00 3 1  0 00 0 0" } },
	{  3, "b1", 0, "0011", 0, "10", 2, 1, 3, "miss",   "T",  { "1 01 1 0  0 00 3 1", "1 01 2 0  0 00 2 1", "0 00 2 1  0 00 1 0", "0 00 3 1  0 00 0 0" } },
	{  4, "b2", 0, "0110", 3, "01", 1, 1, 3, "miss",   "T",  { "1 01 1 1  1 10 2 0", "1 01 2 0  0 00 2 1", "0 00 2 1  0 00 1 0", "0 00 3 1  0 00 0 0" } },
	{  5, "b3", 1, "1100", 2, "00", 1, 1, 2, "miss",   "NT", { "1 01 1 1  1 10 2 0", "1 01 2 0  0 00 2 1", "0 00 2 1  0 00 1 0", "1 01 2 0  0 00 0 1" } },
	{  6, "b1", 1, "1001", 2, "00", 1, 2, 2, "hit T",  "T",  { "1 01 1 1  1 10 2 0", "1 01 2 0  0 00 2 1", "1 00 3 0  0 00 1 1", "1 01 2 0  0 00 0 1" } },
	{  7, "b3", 1, "0011", 1, "11", 2, 2, 2, "miss",   "T",  { "1 01 1 1  1 10 2 0", "1 01 2 0  0 00 2 1", "1 00 3 0  0 00 1 1", "1 01 2 0  0 00 0 1" } },
	{  8, "b1", 0, "0111", 1, "10", 2, 3, 2, "miss",   "T",  { "1 01 1 1  1 10 2 0", "1 01 2 1  1 11 3 0", "1 00 3 0  0 00 1 1", "1 01 2 0  0 00 0 1" } },
	{  9, "b2", 0, "1110", 1, "01", 1, 3, 2, "miss",   "T",  { "1 01 1 1  1 10 2 0", "1 10 1 0  1 11 3 1", "1 00 3 0  0 00 1 1", "1 01 2 0  0 00 0 1" } },
	{ 10, "b3", 1, "1100", 2, "00", 1, 3, 1, "hit T",  "T",  { "1 01 1 1  1 10 2 0", "1 10 1 1  1 01 2 0", "1 00 3 0  0 00 1 1", "1 01 2 0  0 00 0 1" } },
	{ 11, "b1", 0, "1001", 2, "00", 1, 3, 1, "hit T",  "T",  { "1 01 1 1  1 10 2 0", "1 10 1 1  1 01 2 0", "1 00 3 0  0 00 1 1", "1 01 2 0  0 00 0 1" } },
	{ 12, "b2", 1, "0010", 2, "01", 0, 3, 1, "miss",   "NT", { "1 01 1 1  1 10 2 0", "1 10 1 1  1 01 2 0", "1 00 2 0  0 00 1 1", "1 01 2 0  0 00 0 1" } },
	{ 13, "b1", 0, "0101", 1, "00", 0, 3, 2, "miss",   "NT", { "1 01 1 1  1 10 2 0", "1 10 1 1  1 01 2 0", "1 00 2 1  1 01 2 0", "1 01 2 0  0 00 0 1" } },
	{ 14, "b2", 0, "1010", 0, "01", 0, 3, 2, "hit NT", "NT", { "1 01 1 1  1 10 2 0", "1 00 0 0  1 01 2 1", "1 00 2 1  1 01 2 0", "1 01 2 0  0 00 0 1" } },
	{ 15, "b3", 1, "0100", 0, "00", 0, 3, 1, "miss",   "T",  { "1 01 0 0  1 10 2 1", "1 00 0 0  1 01 2 1", "1 00 2 1  1 01 2 0", "1 01 2 0  0 00 0 1" } },
	{ 16, "b1", 1, "1001", 2, "00", 0, 3, 1, "hit T",  "T",  { "1 01 0 1  1 00 3 0", "1 00 0 0  1 01 2 1", "1 00 2 1  1 01 2 0", "1 01 2 0  0 00 0 1" } },
	{ 17, "b3", 1, "0011", 1, "11", 1, 3, 1, "miss",   "T",  { "1 01 0 1  1 00 3 0", "1 00 0 0  1 01 2 1", "1 00 3 0  1 01 2 1", "1 01 2 0  0 00 0 1" } },
	{ 18, "b1", 0, "0111", 1, "10", 1, 3, 1, "miss",   "NT", { "1 01 0 1  1 00 3 0", "1 00 0 1  1 11 3 0", "1 00 3 0  1 01 2 1", "1 01 2 0  0 00 0 1" } },
	{ 19, "b2", 0, "1110", 1, "01", 0, 3, 1, "miss",   "NT", { "1 01 0 1  1 00 3 0", "1 10 0 0  1 11 3 1", "1 00 3 0  1 01 2 1", "1 01 2 0  0 00 0 1" } },
	{ 20, "b3", 1, "1100", 2, "00", 0, 3, 0, "hit T",  "T",  { "1 01 0 1  1 00 3 0", "1 10 0 1  1 01 2 0", "1 00 3 0  1 01 2 1", "1 01 2 0  0 00 0 1" } },
	{ 21, "b1", 1, "1001", 2, "00", 0, 3, 0, "hit T",  "T",  { "1 01 0 1  1 00 3 0", "1 10 0 1  1 01 2 0", "1 00 3 0  1 01 2 1", "1 01 2 0  0 00 0 1" } },
	{ 22, "b3", 1, "0011", 1, "11", 1, 3, 0, "miss",   "T",  { "1 01 0 1  1 00 3 0", "1 10 0 1  1 01 2 0", "1 00 3 0  1 01 2 1", "1 01 2 0  0 00 0 1" } },
};

unsigned int bits (const char *s) {
	return strtoul (s, NULL, 2);
}

// the low n bits of v as a binary string
void to_bin (unsigned int v, int n, char *out) {
	for (int i = 0; i < n; i++) out[i] = (v >> (n - 1 - i)) & 1 ? '1' : '0';
	out[n] = 0;
}

bool same_global_table (pm_predictor *p, const char * const table[4]) {
	for (int s = 0; s < 4; s++) {
		int v0, c0, l0, v1, c1, l1;
		char t0[3], t1[3];
		if (sscanf (table[s], "%d %2s %d %d %d %2s %d %d", &v0, t0, &c0, &l0, &v1, t1, &c1, &l1) != 8) return false;
		if (p->valid[s][0] != v0 || p->tag[s][0] != bits (t0) || p->ctr[s][0] != c0 || p->age[s][0] != l0
		 || p->valid[s][1] != v1 || p->tag[s][1] != bits (t1) || p->ctr[s][1] != c1 || p->age[s][1] != l1)
			return false;
	}
	return true;
}

void appendix_replay (void) {
	printf ("appendix replay (PDF pages 7-11)\n");
	pm_predictor *p = new pm_predictor ();

	// initial state of the example (row 1 of pages 9 and 10)
	for (int i = 0; i < 16; i++) p->bim[i] = i % 4;
	for (int s = 0; s < 4; s++) {
		p->valid[s][0] = p->valid[s][1] = 0;
		p->tag[s][0] = p->tag[s][1] = 0;
		p->ctr[s][0] = s;
		p->ctr[s][1] = 3 - s;
		p->age[s][0] = 1;	// way 0 is the LRU way
		p->age[s][1] = 0;
	}
	p->ghr = 0;

	printf ("  row br  outcome GHR  set tag global final  result\n");
	int matched = 0;
	for (int r = 0; r < 22; r++) {
		appendix_row & e = rows[r];
		unsigned int address = strcmp (e.br, "b1") == 0 ? 0x44 : strcmp (e.br, "b2") == 0 ? 0x6C : 0x90;
		char why[200] = "";
		char ghr[5], tag[3];
		to_bin (p->ghr, 4, ghr);

		// state before the branch
		if (p->ghr != bits (e.ghr)) strcat (why, " GHR");
		bool bim_ok = true;
		for (int i = 0; i < 16; i++) {
			int want = i == 1 ? e.bim1 : i == 4 ? e.bim4 : i == 11 ? e.bim11 : i % 4;
			if (p->bim[i] != want) bim_ok = false;
		}
		if (!bim_ok) strcat (why, " bimodal-table");
		if (!same_global_table (p, e.table)) strcat (why, " global-table");

		// prediction
		branch_info b = cond_branch (address);
		pm_update *u = (pm_update *) p->predict (b);
		const char *global = u->hit_way < 0 ? "miss" : p->ctr[u->set][u->hit_way] >= 2 ? "hit T" : "hit NT";
		const char *final = u->direction_prediction () ? "T" : "NT";
		to_bin (u->tag, 2, tag);
		if (u->set != (unsigned int) e.set || u->tag != bits (e.tag)) strcat (why, " set/tag");
		if (strcmp (global, e.global) != 0) strcat (why, " global-hit");
		if (strcmp (final, e.final) != 0) strcat (why, " final");

		p->update (u, e.taken, 0);

		// the printed values are what the predictor did; "ok" means all of them,
		// and the state before the branch, equal the PDF
		if (why[0] == 0) matched++;
		printf ("  %3d %s  %-7s %s %3d  %s  %-6s %-5s  %s%s\n", e.row, e.br, e.taken ? "T" : "NT", ghr,
			u->set, tag, global, final, why[0] ? "MISMATCH:" : "ok", why);
	}
	printf ("  %d/22 rows match the PDF\n", matched);
	if (matched != 22) failures++;
	delete p;
}

#endif

int main (void) {
	printf ("configuration: bimodal 2^%d, global %d sets x %d ways, tag %d bits, GHR %d bits, PC >> %d\n",
		PM_BIM_BITS, PM_SETS, PM_WAYS, PM_TAG_BITS, PM_HIST_BITS, PM_PC_SHIFT);

#if PM_BIM_BITS == 4 && PM_PC_SHIFT == 2 && PM_SET_BITS == 2 && PM_TAG_BITS == 2 \
 && PM_WAYS == 2 && PM_HIST_BITS == 4
	appendix_replay ();
#else
	printf ("appendix replay: skipped (needs the tiny configuration of the worked example)\n");
#endif

	// non-conditional branches: predicted taken, no table or history changes
	printf ("non-conditional branches\n");
	{
		pm_predictor *p = new pm_predictor ();
		for (int i = 0; i < 1000; i++) {
			branch_info b = cond_branch (0x1000 + 4 * (i % 37));
			branch_update *u = p->predict (b);
			p->update (u, i % 3 == 0, 0);
		}
		pm_predictor *before = new pm_predictor (*p);
		int flags[5] = { 0, BR_INDIRECT, BR_CALL, BR_CALL | BR_INDIRECT, BR_RETURN };
		bool all_taken = true;
		for (int i = 0; i < 5; i++) {
			branch_info b;
			b.address = 0x1000;
			b.opcode = 0;
			b.br_flags = flags[i];
			branch_update *u = p->predict (b);
			all_taken = all_taken && u->direction_prediction ();
			p->update (u, i % 2, 0x2000);
		}
		check (all_taken, "predicted taken");
		check (same_state (p, before), "tables and GHR unchanged");
		delete p;
		delete before;
	}

	// 2-bit counters saturate at 0 and 3 (bimodal and global, through predict/update).
	// The GHR is reset before every predict() so the branch maps to the same global entry.
	printf ("2-bit counter saturation\n");
	{
		pm_predictor *p = new pm_predictor ();
		branch_info b = cond_branch (0x44);
		p->ghr = 0;
		p->update (p->predict (b), false, 0);		// global miss: allocates an entry

		p->ghr = 0;
		pm_update *u = (pm_update *) p->predict (b);
		check (u->hit_way >= 0, "second access hits the allocated global entry");
		int s = u->set, w = u->hit_way, i = u->bim_index;
		p->bim[i] = 0;
		p->ctr[s][w] = 0;
		p->update (u, false, 0);
		check (p->bim[i] == 0 && p->ctr[s][w] == 0, "0 stays 0 on not taken");

		p->ghr = 0;
		u = (pm_update *) p->predict (b);
		p->bim[i] = 3;
		p->ctr[s][w] = 3;
		p->update (u, true, 0);
		check (p->bim[i] == 3 && p->ctr[s][w] == 3, "3 stays 3 on taken");
		delete p;
	}

	// LRU: an empty set fills way 0, 1, 2, ...; then the least recently used way is replaced
	printf ("LRU replacement (%d ways)\n", PM_WAYS);
	{
		pm_predictor *p = new pm_predictor ();
		bool fill_ok = true, perm_ok = true;
		for (int k = 0; k < PM_WAYS; k++) {
			int v = p->victim (0);
			if (v != k) fill_ok = false;
			p->touch (0, v);
			perm_ok = perm_ok && ages_ok (p, 0);
		}
		check (fill_ok, "empty set fills ways in order 0, 1, ...");
		check (p->victim (0) == 0, "after touching ways 0..W-1 in order, victim is way 0");
		p->touch (0, 0);
		perm_ok = perm_ok && ages_ok (p, 0);
		check (p->victim (0) == 1, "after touching way 0 again, victim is way 1");
		check (perm_ok, "ages stay a permutation of 0..W-1");
		delete p;
	}

	// the same LRU order through predict/update: with PC = 0 the hash equals the
	// GHR, so GHR = t selects set 0 with tag t.  Fill tags 0..W-1, reuse tag 0,
	// insert tag W: tag 1 (least recently used) must be the one replaced.
	printf ("LRU replacement through predict/update\n");
	{
		pm_predictor *p = new pm_predictor ();
		branch_info b = cond_branch (0);
		for (int t = 0; t < PM_WAYS; t++) {
			p->ghr = t;
			p->update (p->predict (b), true, 0);
		}
		p->ghr = 0;
		pm_update *u = (pm_update *) p->predict (b);
		check (u->hit_way == 0, "tag 0 hits way 0");
		p->update (u, true, 0);
		p->ghr = PM_WAYS;
		u = (pm_update *) p->predict (b);
		check (u->hit_way < 0, "new tag misses");
		p->update (u, true, 0);
		bool hits_ok = true;
		for (int t = 0; t <= PM_WAYS; t++) {
			p->ghr = t;
			u = (pm_update *) p->predict (b);	// predict() alone changes no state
			if ((u->hit_way >= 0) != (t != 1)) hits_ok = false;
		}
		check (hits_ok, "only tag 1 was replaced");
		check (p->tag[0][1] == PM_WAYS, "the new tag went into way 1");
		delete p;
	}

	if (failures) {
		printf ("FAILED: %d check(s)\n", failures);
		return 1;
	}
	printf ("all checks passed\n");
	return 0;
}
