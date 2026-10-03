Default setting: CDB buses and commit width equal to the issue width (unless the input file sets them: `cdb_limit` and `squash_cdb` have one CDB).

| Test | Instructions | Cycles W=1 | W=2 | W=3 | W=4 | IPC W=1 | W=2 | W=3 | W=4 | Mispredicted branches | Memory-order violations | Squashed W=1 / W=4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| btb_alias | 4 | 10 | 10 | 10 | 10 | 0.40 | 0.40 | 0.40 | 0.40 | 1 | 0 | 2 / 4 |
| bug1_rat_overwrite | 7 | 37 | 36 | 36 | 36 | 0.19 | 0.19 | 0.19 | 0.19 | 0 | 0 | 0 / 0 |
| bug2_store_before_commit | 3 | 23 | 23 | 23 | 23 | 0.13 | 0.13 | 0.13 | 0.13 | 0 | 0 | 0 / 0 |
| bug3_forward_same_cycle | 3 | 14 | 13 | 13 | 13 | 0.21 | 0.23 | 0.23 | 0.23 | 0 | 0 | 0 / 0 |
| bug4_double_advance | 3 | 26 | 25 | 25 | 25 | 0.12 | 0.12 | 0.12 | 0.12 | 0 | 0 | 0 / 0 |
| bug5_empty_rob_crash | 7 | 20 | 20 | 20 | 20 | 0.35 | 0.35 | 0.35 | 0.35 | 2 | 0 | 4 / 4 |
| cdb_limit | 8 | 11 | 11 | 11 | 11 | 0.73 | 0.73 | 0.73 | 0.73 | 0 | 0 | 0 / 0 |
| chain | 6 | 22 | 22 | 22 | 22 | 0.27 | 0.27 | 0.27 | 0.27 | 0 | 0 | 0 / 0 |
| daxpy | 28 | 41 | 32 | 31 | 31 | 0.68 | 0.88 | 0.90 | 0.90 | 2 | 0 | 2 / 4 |
| dispatch_order | 4 | 8 | 8 | 8 | 8 | 0.50 | 0.50 | 0.50 | 0.50 | 0 | 0 | 0 / 0 |
| independent | 6 | 12 | 9 | 8 | 8 | 0.50 | 0.67 | 0.75 | 0.75 | 0 | 0 | 0 / 0 |
| loop | 6 | 16 | 16 | 16 | 16 | 0.38 | 0.38 | 0.38 | 0.38 | 2 | 0 | 4 / 5 |
| memory | 7 | 16 | 14 | 14 | 14 | 0.44 | 0.50 | 0.50 | 0.50 | 0 | 0 | 0 / 0 |
| memory_violation | 4 | 18 | 18 | 18 | 18 | 0.22 | 0.22 | 0.22 | 0.22 | 0 | 1 | 2 / 2 |
| original | 15 | 41 | 35 | 34 | 34 | 0.37 | 0.43 | 0.44 | 0.44 | 2 | 0 | 2 / 4 |
| precision | 7 | 14 | 13 | 13 | 13 | 0.50 | 0.54 | 0.54 | 0.54 | 0 | 0 | 0 / 0 |
| r0 | 6 | 12 | 10 | 10 | 10 | 0.50 | 0.60 | 0.60 | 0.60 | 1 | 0 | 2 / 2 |
| sample_tc1 | 17 | 36 | 33 | 33 | 33 | 0.47 | 0.52 | 0.52 | 0.52 | 0 | 0 | 0 / 0 |
| sample_tc2 | 17 | 49 | 47 | 47 | 47 | 0.35 | 0.36 | 0.36 | 0.36 | 0 | 0 | 0 / 0 |
| squash_cdb | 6 | 14 | 12 | 12 | 11 | 0.43 | 0.50 | 0.50 | 0.55 | 1 | 0 | 3 / 3 |
| structural | 8 | 20 | 19 | 18 | 18 | 0.40 | 0.42 | 0.44 | 0.44 | 0 | 0 | 0 / 0 |
| unaligned | 7 | 17 | 15 | 15 | 15 | 0.41 | 0.47 | 0.47 | 0.47 | 0 | 0 | 0 / 0 |
| violation_forward | 5 | 17 | 16 | 15 | 15 | 0.29 | 0.31 | 0.33 | 0.33 | 0 | 1 | 1 / 1 |
| wide | 8 | 11 | 7 | 6 | 5 | 0.73 | 1.14 | 1.33 | 1.60 | 0 | 0 | 0 / 0 |

One CDB, as the handout lists: cycles with one CDB bus and the commit width equal to the issue width, and with one CDB bus and one commit per cycle (then only the issue width changes).

| Test | One CDB: W=1 | W=2 | W=3 | W=4 | One CDB, one commit: W=1 | W=2 | W=3 | W=4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| btb_alias | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| bug1_rat_overwrite | 37 | 36 | 36 | 36 | 37 | 37 | 37 | 37 |
| bug2_store_before_commit | 23 | 23 | 23 | 23 | 23 | 23 | 23 | 23 |
| bug3_forward_same_cycle | 14 | 13 | 13 | 13 | 14 | 14 | 14 | 14 |
| bug4_double_advance | 26 | 25 | 25 | 25 | 26 | 25 | 25 | 25 |
| bug5_empty_rob_crash | 20 | 20 | 20 | 20 | 20 | 20 | 20 | 20 |
| cdb_limit | 11 | 11 | 11 | 11 | 11 | 11 | 11 | 11 |
| chain | 22 | 22 | 22 | 22 | 22 | 22 | 22 | 22 |
| daxpy | 41 | 34 | 33 | 33 | 41 | 41 | 41 | 41 |
| dispatch_order | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 |
| independent | 12 | 9 | 9 | 9 | 12 | 10 | 10 | 10 |
| loop | 16 | 16 | 16 | 16 | 16 | 16 | 16 | 16 |
| memory | 16 | 14 | 14 | 14 | 16 | 15 | 15 | 15 |
| memory_violation | 18 | 18 | 18 | 18 | 18 | 18 | 18 | 18 |
| original | 41 | 35 | 34 | 34 | 41 | 41 | 41 | 41 |
| precision | 14 | 13 | 13 | 13 | 14 | 13 | 13 | 13 |
| r0 | 12 | 10 | 10 | 10 | 12 | 10 | 10 | 10 |
| sample_tc1 | 36 | 35 | 35 | 35 | 36 | 36 | 36 | 36 |
| sample_tc2 | 49 | 47 | 47 | 47 | 49 | 47 | 47 | 47 |
| squash_cdb | 14 | 12 | 12 | 11 | 14 | 12 | 12 | 11 |
| structural | 20 | 19 | 18 | 18 | 20 | 20 | 20 | 20 |
| unaligned | 17 | 15 | 15 | 15 | 17 | 17 | 17 | 17 |
| violation_forward | 17 | 17 | 16 | 16 | 17 | 17 | 16 | 16 |
| wide | 11 | 11 | 11 | 11 | 11 | 11 | 11 | 11 |
