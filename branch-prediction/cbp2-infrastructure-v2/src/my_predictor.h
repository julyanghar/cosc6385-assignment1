// my_predictor.h
// This file contains a sample gshare_predictor class.
// It is a simple 32,768-entry gshare with a history length of 15.

class gshare_update : public branch_update {
public:
	unsigned int index;
};

class gshare_predictor : public branch_predictor {
public:
#define HISTORY_LENGTH	15
#define TABLE_BITS	15
	gshare_update u;
	branch_info bi;
	unsigned int history;
	unsigned char tab[1<<TABLE_BITS];

	gshare_predictor (void) : history(0) { 
		memset (tab, 0, sizeof (tab));
	}

	branch_update *predict (branch_info & b) {
		bi = b;
		if (b.br_flags & BR_CONDITIONAL) {
			u.index = 
				  (history << (TABLE_BITS - HISTORY_LENGTH)) 
				^ (b.address & ((1<<TABLE_BITS)-1));
			u.direction_prediction (tab[u.index] >> 1);
		} else {
			u.direction_prediction (true);
		}
		u.target_prediction (0);
		return &u;
	}

	void update (branch_update *u, bool taken, unsigned int target) {
		if (bi.br_flags & BR_CONDITIONAL) {
			unsigned char *c = &tab[((gshare_update*)u)->index];
			if (taken) {
				if (*c < 3) (*c)++;
			} else {
				if (*c > 0) (*c)--;
			}
			history <<= 1;
			history |= taken;
			history &= (1<<HISTORY_LENGTH)-1;
		}
	}
};

//
// Pentium M hybrid branch predictors
// This class implements a simple hybrid branch predictor based on the Pentium M branch outcome prediction units.
// Instead of implementing the complete Pentium M branch outcome predictors, the class below implements a hybrid
// predictor that combines a bimodal predictor and a global predictor.
//
// Bimodal: 2-bit counters indexed by the low PC bits.
// Global:  set-associative table of {valid, tag, 2-bit counter}, LRU replacement.
//          HASH = PC xor GHR; set = upper bits of HASH, tag = lower bits of HASH.
// Final prediction: the global counter on a global hit, else the bimodal counter.
//
// The parameters below are the main configuration (figures on pages 2 and 6 of
// the assignment).  They can be overridden with -D; test_pm.cc uses that to build
// the tiny predictor of the worked example in the appendix.

#ifndef PM_BIM_BITS
#define PM_BIM_BITS	12	// bimodal table: 2^12 = 4096 counters, index = PC[11:0]
#endif
#ifndef PM_PC_SHIFT
#define PM_PC_SHIFT	0	// low PC bits dropped before indexing (x86: none)
#endif
#ifndef PM_SET_BITS
#define PM_SET_BITS	9	// global table: 2^9 = 512 sets, set = HASH[14:6]
#endif
#ifndef PM_TAG_BITS
#define PM_TAG_BITS	6	// global tag = HASH[5:0]
#endif
#ifndef PM_WAYS
#define PM_WAYS		4	// global table associativity
#endif
#ifndef PM_HIST_BITS
#define PM_HIST_BITS	15	// global history register length
#endif
#ifndef PM_CTR_INIT
#define PM_CTR_INIT	2	// initial value of every 2-bit counter (weakly taken)
#endif
#ifndef PM_USE_GLOBAL
#define PM_USE_GLOBAL	1	// 0 = bimodal-only baseline
#endif

#define PM_SETS		(1 << PM_SET_BITS)
#define PM_HASH_BITS	(PM_SET_BITS + PM_TAG_BITS)

#if PM_HIST_BITS > PM_HASH_BITS
#error "PM_HIST_BITS must not exceed PM_SET_BITS + PM_TAG_BITS"
#endif

class pm_update : public branch_update {
public:
        bool cond;			// conditional branch?
        unsigned int bim_index;		// bimodal counter used for this branch
        unsigned int set, tag;		// global set and tag, computed with the history before this branch
        int hit_way;			// global way that hit, or -1 on a global miss
};

class pm_predictor : public branch_predictor {
public:
        pm_update u;
        unsigned int ghr;				// global history, newest outcome in bit 0
        unsigned char bim[1 << PM_BIM_BITS];		// bimodal 2-bit counters
        unsigned char valid[PM_SETS][PM_WAYS];
        unsigned char tag[PM_SETS][PM_WAYS];
        unsigned char ctr[PM_SETS][PM_WAYS];		// global 2-bit counters
        unsigned char age[PM_SETS][PM_WAYS];		// LRU age: 0 = most recently used
#ifdef PM_STATS
        long long n_cond, n_hit, n_hit_right, n_hit_bim_right, n_miss_right;
#endif

        pm_predictor (void) : ghr(0) {
                memset (bim, PM_CTR_INIT, sizeof (bim));
                memset (valid, 0, sizeof (valid));
                memset (tag, 0, sizeof (tag));
                memset (ctr, PM_CTR_INIT, sizeof (ctr));
                // way 0 starts as the least recently used way, so an empty set fills way 0, 1, ...
                for (int s = 0; s < PM_SETS; s++)
                        for (int w = 0; w < PM_WAYS; w++)
                                age[s][w] = PM_WAYS - 1 - w;
#ifdef PM_STATS
                n_cond = n_hit = n_hit_right = n_hit_bim_right = n_miss_right = 0;
#endif
        }

        // saturating 2-bit counter update
        void train (unsigned char & c, bool taken) {
                if (taken) {
                        if (c < 3) c++;
                } else {
                        if (c > 0) c--;
                }
        }

        // least recently used way of a set
        int victim (unsigned int set) {
                int v = 0;
                for (int w = 1; w < PM_WAYS; w++)
                        if (age[set][w] > age[set][v]) v = w;
                return v;
        }

        // make way w the most recently used way of its set
        void touch (unsigned int set, int w) {
                for (int i = 0; i < PM_WAYS; i++)
                        if (age[set][i] < age[set][w]) age[set][i]++;
                age[set][w] = 0;
        }

        branch_update *predict (branch_info & b) {
                // target prediction is not implemented
                u.target_prediction (0);

                // only conditional branches use the tables and the history
                // (the driver scores only conditional branches)
                u.cond = b.br_flags & BR_CONDITIONAL;
                if (!u.cond) {
                        u.direction_prediction (true);
                        return &u;
                }

                unsigned int pc = b.address >> PM_PC_SHIFT;
                u.bim_index = pc & ((1 << PM_BIM_BITS) - 1);
                unsigned int h = (pc ^ ghr) & ((1 << PM_HASH_BITS) - 1);
                u.set = h >> PM_TAG_BITS;
                u.tag = h & ((1 << PM_TAG_BITS) - 1);

                u.hit_way = -1;
#if PM_USE_GLOBAL
                for (int w = 0; w < PM_WAYS; w++)
                        if (valid[u.set][w] && tag[u.set][w] == u.tag) {
                                u.hit_way = w;
                                break;
                        }
#endif
                if (u.hit_way >= 0)
                        u.direction_prediction (ctr[u.set][u.hit_way] >= 2);
                else
                        u.direction_prediction (bim[u.bim_index] >= 2);
                return &u;
        }

        void update (branch_update *u, bool taken, unsigned int target) {
                pm_update *p = (pm_update *) u;
                if (!p->cond) return;
#ifdef PM_STATS
                // the tables still hold the values predict() used
                n_cond++;
                if (p->hit_way >= 0) {
                        n_hit++;
                        n_hit_right += p->direction_prediction () == taken;
                        n_hit_bim_right += (bim[p->bim_index] >= 2) == taken;
                } else {
                        n_miss_right += p->direction_prediction () == taken;
                }
#endif

                // the bimodal counter is trained on every conditional branch,
                // also when the final prediction came from the global table
                train (bim[p->bim_index], taken);

#if PM_USE_GLOBAL
                int w = p->hit_way;
                if (w < 0) {
                        // global miss: always allocate, replacing the LRU way.
                        // The replaced way keeps its old counter value, which is then trained.
                        w = victim (p->set);
                        valid[p->set][w] = 1;
                        tag[p->set][w] = p->tag;
                }
                train (ctr[p->set][w], taken);
                touch (p->set, w);
#endif

                // shift the outcome into the history only after the tables are trained
                ghr = ((ghr << 1) | taken) & ((1 << PM_HIST_BITS) - 1);
        }

#ifdef PM_STATS
        ~pm_predictor (void) {
                fprintf (stderr, "pm_stats cond %lld hit %lld acc_hit %lld bim_acc_hit %lld acc_miss %lld\n",
                        n_cond, n_hit, n_hit_right, n_hit_bim_right, n_miss_right);
        }
#endif
};

//
// Complete Pentium M branch predictors for extra credit
// This class implements the complete Pentium M branch prediction units. 
// It implements both branch target prediction and branch outcome predicton. 
class cpm_update : public branch_update {
public:
        unsigned int index;
};

class cpm_predictor : public branch_predictor {
public:
        cpm_update u;

        cpm_predictor (void) {
        }

        branch_update *predict (branch_info & b) {
            u.direction_prediction (true);
            u.target_prediction (0);
            return &u;
        }

        void update (branch_update *u, bool taken, unsigned int target) {
        }

};


