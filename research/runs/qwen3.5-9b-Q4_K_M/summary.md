# qwen3.5-9b-Q4_K_M

| method | P (lenient/strict) | R | F1 | affinity | halluc.names | type_P | type_R | pole_acc | not_trait | speed |
|---|---|---|---|---|---|---|---|---|---|---|
| rel_cooccur | 0.97 / 0.56 | 1.00 | 0.98 | 0.34 | 0.0% | 0.00 | 0.00 |  |  | 0.0s/para, 0 calls |
| rel_free | 1.00 / 0.73 | 0.84 | 0.91 | 0.00 | 4.2% | 0.78 | 0.26 |  |  | 25.0s/para, 173 calls |
| rel_anchored | 1.00 / 0.77 | 0.90 | 0.95 | 0.89 | 0.0% | 0.71 | 0.75 |  |  | 64.4s/para, 158 calls |
| rel_pairwise | 1.00 / 0.75 | 0.88 | 0.94 | 0.89 | 0.0% | 0.78 | 0.21 |  |  | 95.1s/para, 226 calls |
| rel_verify | 1.00 / 0.94 | 0.50 | 0.67 | 0.85 | 0.0% | 0.91 | 0.10 |  |  | 24.7s/para, 202 calls |
| traits_lexicon | 0.65 | 0.28 | 0.39 |  | 0.0% (not in text) |  |  | 0.98 | 2 | 0.0s/para, 0 calls |
| traits_llm | 0.32 | 0.34 | 0.33 |  | 32.6% (not in text) |  |  | 0.73 | 0 | 110.6s/para, 7 calls |
| traits_anchored | 0.63 | 0.71 | 0.67 |  | 0.0% (not in text) |  |  | 0.85 | 0 | 97.0s/para, 32 calls |
| traits_verify | 0.84 | 0.58 | 0.69 |  | 0.0% (not in text) |  |  | 0.86 | 0 | 64.2s/para, 198 calls |
