# Triage validation

## Pilot

- Known adopted methods labelled `rl_method`: 30/32
- Same, leaving out the 2 named as examples in the v1 rules: 29/30
- Misses: [('2505.22312', 'rl_application'), ('2512.02556', 'rl_application')]
- `rl_method` in the random sample by scope: general 77, embedded 18
- Confidence over all pilot papers: high 324, low 36
- Model reports in the pilot: 33
- Random pilot sample (300 papers) by label: rl_application 99, rl_method 95, other 66, analysis 19, distillation 12, preference_offline 6, systems 3
- Review sample written to `review_sample.csv` (200 papers: 95 labelled `rl_method`, the rest not). Repeats are scored after `merge`.

## Full run

- Papers labelled: 6455
- By label: rl_method 2158, rl_application 1882, other 1628, analysis 419, distillation 140, preference_offline 140, systems 88
- `rl_method`: 2158; scope general 1551, embedded 607; general without low confidence 1440
- Model reports (any label): 644; of those labelled `rl_method`: 152
- Repeated papers with the same label both times: 92/100
- Label changes on repeats (8): [('2602.11792', 'other', 'analysis'), ('2601.16486', 'rl_method', 'rl_application'), ('2504.09488', 'rl_application', 'rl_method'), ('2506.05619', 'other', 'preference_offline'), ('2606.15099', 'rl_method', 'rl_application'), ('2505.16401', 'rl_application', 'rl_method'), ('2508.09521', 'rl_application', 'rl_method'), ('2508.18642', 'rl_application', 'rl_method')]
- `rl_method` per month: 2025-01 16, 2025-02 33, 2025-03 40, 2025-04 43, 2025-05 141, 2025-06 94, 2025-07 64, 2025-08 100, 2025-09 146, 2025-10 209, 2025-11 85, 2025-12 87, 2026-01 150, 2026-02 221, 2026-03 139, 2026-04 139, 2026-05 269, 2026-06 182
- Components: other 544, sampling 519, credit_assignment 260, advantage 255, length 131, offpolicy 128, multi_reward 99, entropy 76, clipping 53, kl 47, aggregation 41, moe 5

## Review sample (200/200 labelled)

| review / labels | general | embedded | no |
|---|---|---|---|
| general | 68 | 3 | 1 |
| embedded | 6 | 12 | 32 |
| no | 2 | 1 | 75 |

- Exact agreement: 155/200
- Labelled general, reviewed as no: 2; reviewed as general, labelled no: 1
- Split that defines the denominator (general vs everything else): 188/200 agree. Of 76 papers labelled general, 68 were general on review; of 72 papers general on review, 68 were labelled general.
- Main disagreement: 32 papers labelled as applications were judged embedded methods on review. This boundary affects only the all-`rl_method` count, so the analysis uses the general denominator.
- Reweighting the sample rates to the pool (68/76 of 1,551 papers labelled general, plus 4/124 of the 4,904 others) gives about 1,550 general papers, in line with the label count.

## Full run

- Papers labelled: 6939
- By label: rl_method 2235, rl_application 2029, other 1798, analysis 461, distillation 161, preference_offline 154, systems 101
- `rl_method`: 2235; scope general 1598, embedded 637; general without low confidence 1480
- Model reports (any label): 704; of those labelled `rl_method`: 158
- Repeated papers with the same label both times: 129/140
- Label changes on repeats (11): [('2602.11792', 'other', 'analysis'), ('2601.16486', 'rl_method', 'rl_application'), ('2504.09488', 'rl_application', 'rl_method'), ('2506.05619', 'other', 'preference_offline'), ('2606.15099', 'rl_method', 'rl_application'), ('2505.16401', 'rl_application', 'rl_method'), ('2508.09521', 'rl_application', 'rl_method'), ('2508.18642', 'rl_application', 'rl_method'), ('2511.01470', 'rl_method', 'distillation'), ('2505.14810', 'other', 'analysis'), ('2512.20661', 'other', 'rl_method')]
- `rl_method` per month: 2025-01 18, 2025-02 36, 2025-03 41, 2025-04 44, 2025-05 147, 2025-06 98, 2025-07 68, 2025-08 101, 2025-09 149, 2025-10 216, 2025-11 88, 2025-12 87, 2026-01 158, 2026-02 230, 2026-03 144, 2026-04 146, 2026-05 277, 2026-06 187
- Components: other 570, sampling 534, credit_assignment 269, advantage 257, length 137, offpolicy 132, multi_reward 107, entropy 77, clipping 54, kl 49, aggregation 44, moe 5

## Full run

- Papers labelled: 6939
- By label: rl_method 2235, rl_application 2029, other 1798, analysis 461, distillation 161, preference_offline 154, systems 101
- `rl_method`: 2235; scope general 1598, embedded 637; general without low confidence 1480
- Model reports (any label): 704; of those labelled `rl_method`: 158
- Repeated papers with the same label both times: 129/140
- Label changes on repeats (11): [('2602.11792', 'other', 'analysis'), ('2601.16486', 'rl_method', 'rl_application'), ('2504.09488', 'rl_application', 'rl_method'), ('2506.05619', 'other', 'preference_offline'), ('2606.15099', 'rl_method', 'rl_application'), ('2505.16401', 'rl_application', 'rl_method'), ('2508.09521', 'rl_application', 'rl_method'), ('2508.18642', 'rl_application', 'rl_method'), ('2511.01470', 'rl_method', 'distillation'), ('2505.14810', 'other', 'analysis'), ('2512.20661', 'other', 'rl_method')]
- `rl_method` per month: 2025-01 18, 2025-02 36, 2025-03 41, 2025-04 44, 2025-05 147, 2025-06 98, 2025-07 68, 2025-08 101, 2025-09 149, 2025-10 216, 2025-11 88, 2025-12 87, 2026-01 158, 2026-02 230, 2026-03 144, 2026-04 146, 2026-05 277, 2026-06 187
- Components: other 570, sampling 534, credit_assignment 269, advantage 257, length 137, offpolicy 132, multi_reward 107, entropy 77, clipping 54, kl 49, aggregation 44, moe 5
