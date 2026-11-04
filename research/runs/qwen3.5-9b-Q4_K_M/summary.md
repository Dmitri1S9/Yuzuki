# qwen3.5-9b-Q4_K_M

| method | P (lenient/strict) | R | F1 | affinity | halluc.names | type_P | type_R | pole_acc | not_trait | speed |
|---|---|---|---|---|---|---|---|---|---|---|
| rel_cooccur | 0.94 / 0.54 | 1.00 | 0.97 | 0.30 | 0.0% | 0.00 | 0.00 |  |  | 0.0s/para, 0 calls |
| rel_free | 1.00 / 0.69 | 0.88 | 0.93 | 0.00 | 5.5% | 0.90 | 0.58 |  |  | 26.5s/para, 81 calls |
| rel_anchored | 1.00 / 0.71 | 0.89 | 0.94 | 0.86 | 0.0% | 0.71 | 0.95 |  |  | 60.8s/para, 67 calls |
| rel_verify | 1.00 / 0.94 | 0.50 | 0.67 | 0.85 | 0.0% | 0.91 | 0.42 |  |  | 24.7s/para, 202 calls |
