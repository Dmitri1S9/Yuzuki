# qwen3.5-9b-Q4_K_M

| method | P (lenient/strict) | R | F1 | affinity | halluc.names | type_P | type_R | pole_acc | not_trait | speed |
|---|---|---|---|---|---|---|---|---|---|---|
| rel_cooccur | 0.94 / 0.54 | 1.00 | 0.97 | 0.30 | 0.0% | 0.00 | 0.00 |  |  | 0.0s/para, 0 calls |
| rel_free | 1.00 / 0.69 | 0.88 | 0.93 | 0.00 | 5.5% | 0.90 | 0.58 |  |  | 26.5s/para, 81 calls |
| rel_anchored | 1.00 / 0.71 | 0.89 | 0.94 | 0.86 | 0.0% | 0.71 | 0.95 |  |  | 60.8s/para, 67 calls |
| rel_pairwise | 1.00 / 0.75 | 0.88 | 0.94 | 0.89 | 0.0% | 0.78 | 0.95 |  |  | 95.1s/para, 226 calls |
| rel_verify | 1.00 / 0.94 | 0.50 | 0.67 | 0.85 | 0.0% | 0.91 | 0.42 |  |  | 24.7s/para, 202 calls |
| traits_lexicon | 0.79 | 0.27 | 0.40 |  | 0.0% (not in text) |  |  | 1.00 | 1 | 0.0s/para, 0 calls |
| traits_llm | 0.32 | 0.72 | 0.45 |  | 32.6% (not in text) |  |  | 0.73 | 0 | 110.6s/para, 7 calls |
| traits_anchored | 0.61 | 0.71 | 0.66 |  | 0.0% (not in text) |  |  | 0.84 | 0 | 87.8s/para, 16 calls |
| traits_verify | 0.86 | 0.51 | 0.64 |  | 0.0% (not in text) |  |  | 0.86 | 0 | 63.2s/para, 95 calls |
