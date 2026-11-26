# Matching results

25 sampled historical listings (seed 5), ranked as at their creation time; first-choice NGO per strategy.

| strategy | listings | avg distance km | capacity fit | time score | weighted score |
|---|---|---|---|---|---|
| weighted | 25 | 3.2 | 0.959 | 0.811 | 0.826 |
| nearest | 25 | 3.06 | 0.955 | 0.813 | 0.822 |
| random | 25 | 5.67 | 0.94 | 0.766 | 0.738 |

The weighted ranker trades a little distance for capacity and reliability. Capacity state is the current DB state, so this is indicative, not a historical replay.
