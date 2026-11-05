# Research C: distillation for IE, psych taxonomies, ordinals from comparisons

Checked 2026-11-03. Every link was opened or came back from a search. Where I only had a secondary source, or worked a number out myself, the note says so.

---

## 1. Distilling a custom extraction schema into a small model

### (a) How many labelled examples are needed

| Work | What was distilled | How much data |
|---|---|---|
| Distilling step-by-step (Hsieh et al. 2023) [arXiv 2305.02301](https://arxiv.org/abs/2305.02301) | LLM rationales used as extra supervision (multi-task) | A 770M T5 beat few-shot 540B PaLM using 80% of one benchmark's data. Rationales reduce the data needed compared with labels alone. |
| UniversalNER (Zhou et al. 2023) [arXiv 2308.03279](https://arxiv.org/abs/2308.03279), [site](https://universal-ner.github.io) | ChatGPT labelled 50k Pile passages, 45,889 kept, 13,020 entity types | Open-domain NER. Reports no ablation on data size. |
| NuExtract (NuMind) [blog](https://numind.ai/blog/nuextract-a-foundation-model-for-structured-extraction) | Llama-3-70B labelled 300k C4 passages, 50k kept after filtering (values must appear in the text) | Fine-tuning on **40 examples** for one task moved NuExtract-tiny (0.5B) to "a bit better than GPT-4o" (small benchmark). |
| GoLLIE (Sainz et al., ICLR 2024) [arXiv 2310.03668](https://arxiv.org/abs/2310.03668) | Code-style schema plus annotation guidelines | Ablation: detailed guidelines matter most. Useful design pattern: write the schema as Python dataclasses with docstrings. |
| GLiREL [arXiv 2501.03172](https://arxiv.org/abs/2501.03172) (GLiNER-style encoder for zero-shot relation classification), [GLiNER](https://github.com/urchade/GLiNER) | Trained on LLM-generated synthetic data | Takes entities as given and accepts any label set at inference. Cheap CPU/GPU baseline. |
| Christou & Tsoumakas 2026 [arXiv 2606.22606](https://arxiv.org/abs/2606.22606) | Fine-tuned 0.36B–3B models, run in 4-bit on one consumer GPU | Fine-tuned Qwen2.5-0.5B: 0.83 micro-F1 against 0.69 for zero-shot GPT-5.4. On literary RE: 0.833 against 0.578. An in-domain RoBERTa also beat the frontier models. |
| LIMA [arXiv 2305.11206](https://arxiv.org/abs/2305.11206) | 1,000 curated SFT pairs | Teaches format and style, not knowledge. This is the argument for why ~1k examples are enough for a narrow output format. |

**Practical number.** For one fixed JSON schema over one text genre, **500–2,000 teacher-labelled paragraphs** is consistent with NuExtract (40 examples was already enough to beat GPT-4o), LIMA, and arXiv 2606.22606. No paper I found gives a clean learning curve at 500/1k/2k for an IE schema. Hold out about 150 paragraphs that you hand-check and plot your own curve.

### (b) QLoRA in 8 GB VRAM

- Unsloth's minimum table ([requirements](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements)):
  - QLoRA: 3B needs 3.5 GB, 7B needs 5 GB, 8B needs 6 GB, 9B needs 6.5 GB.
  - 16-bit LoRA: 8B needs 22 GB, 9B needs 24 GB.
  - Unsloth calls these the "absolute minimum".
- **Problem for Qwen3.5.** Unsloth's [Qwen3.5 fine-tune guide](https://unsloth.ai/docs/models/qwen3.5/fine-tune) says QLoRA is **"not recommended" for any Qwen3.5 model** because of higher-than-normal quantization differences. Its bf16 LoRA figures are 0.8B 3 GB, 2B 5 GB, 4B 10 GB, 9B 22 GB, so **Qwen3.5-9B cannot be trained on 8 GB**. What fits:
  1. **Qwen3.5-2B or 0.8B with bf16 LoRA.** This is the recommended route.
  2. **Qwen3-8B with QLoRA** at about 6 GB: max_seq_len 1024–2048, batch 1, gradient accumulation, `use_gradient_checkpointing="unsloth"`.
  3. Rent a 24 GB cloud GPU for the 9B run (prices not researched).
- Sequence length: the guide's default is 2048. A 150-token paragraph plus a compact prompt plus JSON output is under 1k tokens, so this is not a constraint.
- Training time: **my estimate, not measured.** 1k examples × ~700 tokens is about 0.7M tokens per epoch. At roughly 1–3k tokens/s for an 8B QLoRA on a laptop GPU, that is about 5–15 min per epoch. Plan for 2–3 epochs.

### (c) Cost of teacher labelling (official price pages)

Prices from [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), USD per million tokens (input / output). The Batch API takes 50% off; cache hits cost 0.05–0.1× the input price.
- Sonnet 5.5: $2 / $10
- Opus 5.5: $4 / $20
- Haiku 5.5: $0.10 / $0.50
- Sonnet 4.6: $3 / $15

Caveat: Claude 4.7 and later use a new tokenizer that produces about 30% more tokens for the same text.

[Gemini pricing](https://aistudio.google.com/docs/pricing):
- Gemini 3.8 Flash: $0.75 / $3.75 until 2026-12-31, then doubles to $1.50 / $7.50.
- 3.5 Flash-Lite: $0.30 / $2.50.
- Batch is 50% off. There is a free tier.

**Estimate for 1,000 paragraphs.** Each paragraph is 150 text tokens + 1,500 instruction/schema tokens = 1.65M input total, plus about 300 output tokens each = 0.3M output total.

| Model | Standard | Batch | Notes |
|---|---|---|---|
| Sonnet 5.5 | 3.3 + 3.0 ≈ **$6.3** | ≈ **$3.2** | Caching the shared instructions reduces this further |
| Opus 5.5 | ≈ $12.6 | — | |
| Gemini 3.8 Flash | ≈ $2.4 | — | |
| Haiku 5.5 | ≈ $0.3 | — | |

Thinking or rationale output (step-by-step style) can multiply output tokens 3–5×. Even then it costs under $30. **Cost does not limit this. The time to hand-check a gold set does.**

### (d) Getting the model back into Ollama

- Ollama [Modelfile `ADAPTER`](https://ollama.readthedocs.io/en/modelfile) accepts a Safetensors LoRA **only for Llama, Mistral and Gemma**, or a GGUF LoRA (`ADAPTER ./x.gguf`). The docs warn against QLoRA-quantized adapters and mismatched bases. **Qwen is not on the Safetensors list.**
- Simplest route: merge the adapter and export a GGUF with Unsloth `model.save_pretrained_gguf(dir, tok, quantization_method="q4_k_m")` ([guide](https://unsloth.ai/docs/models/qwen3.5/fine-tune)). Then use `FROM ./model.gguf` ([Modelfile FROM](https://docs.ollama.com/modelfile)).
- Unsloth's [Saving to Ollama](https://unsloth.ai/docs/basics/inference-and-deployment/saving-to-ollama) page generates the Modelfile automatically.
- The most common failure is a chat-template or EOS mismatch. Keep the training template.

---

## 2. Psychological taxonomies and what can be extracted from wiki text

### Traits

- **Big Five, Goldberg (1992).** 100 unipolar markers. *Psych. Assessment* 4(1):26–42 ([psychTools doc](https://personality-project.org/r/psych/help/big5.100.adjectives.html); unofficial form listing all 100: [psytests](https://psytests.org/big5/umen-bl.html)).
- **Saucier (1994) Mini-Markers.** 40 adjectives, 8 per factor ([JPA 63:506](https://scilit.com/publications/0354fb7d1d0f0eeedd7c811d4feac6cc), [form](https://psytests.org/big5/minimen-bl.html)). The list below is from memory, checked against those reproductions:
  - **E**: bold, energetic, extraverted, talkative / bashful, quiet, shy, withdrawn
  - **A**: cooperative, kind, sympathetic, warm / cold, harsh, rude, unsympathetic
  - **C**: efficient, organized, practical, systematic / careless, disorganized, inefficient, sloppy
  - **N (Emotional Stability)**: relaxed, unenvious / envious, fretful, jealous, moody, temperamental, touchy
  - **O (Intellect)**: complex, creative, deep, imaginative, intellectual, philosophical / uncreative, unintellectual
- **HEXACO** ([hexaco.org](https://hexaco.org), [Wikipedia](https://en.wikipedia.org/wiki/HEXACO_model_of_personality_structure)). Honesty-Humility adjectives: sincere, honest, faithful, loyal, modest / sly, deceitful, greedy, pretentious, hypocritical, boastful, pompous. H is the factor that best captures "villain versus hero" morality, which Big Five covers poorly.
- **Dark Triad.** Paulhus & Williams 2002, *J. Res. Pers.* 36:556 (doi:10.1016/S0092-6566(02)00505-6). The SD3 questionnaire is Jones & Paulhus 2014 (doi:10.1177/1073191113514105). Both are self-report questionnaires, not adjective lists.
- **Interpersonal Circumplex** (Wiggins IAS, 64 adjectives). The octants are Assured-Dominant, Arrogant-Calculating, Cold-hearted, Aloof-Introverted, Unassured-Submissive, Unassuming-Ingenuous, Warm-Agreeable, Gregarious-Extraverted. The item list is **proprietary** ([PAR](https://www.parinc.com/products/IAS)). The public alternative is IPIP-IPC, 32 items. The two axes are dominance (agency) × warmth (communion).
- **Allport & Odbert (1936).** About 18k trait terms. This is the origin of the lexical tradition, not a usable vocabulary.
- **Open-Source Psychometrics "Statistical Which Character".** **2,000 fictional characters**, more than 3M ratings on bipolar adjective sliders such as "messy/neat" ([quiz](https://openpsychometrics.org/tests/characters/), [docs](https://openpsychometrics.org/tests/characters/documentation/); raw data mirror lists 400 items, 1,600 characters: [haghish/openpsychometrics](https://github.com/haghish/openpsychometrics); derived set: [tashapiro](https://github.com/tashapiro/open-psychometrics)). **This is ready-made ground truth to evaluate trait extraction for characters that appear in both sources.**

### Relations

- **Wish, Deutsch & Kaplan (1976)**, *JPSP* 33(4):409. Four dimensions:
  - cooperative/friendly vs competitive/hostile
  - equal vs unequal
  - intense vs superficial
  - socioemotional/informal vs task-oriented/formal
  - (Summary: [Psychology Today](https://psychologytoday.com/blog/the-five-percent/201709/what-are-the-fundamental-dimensions-social-relationships))
- **Fiske (1992) Relational Models.** *Psych. Rev.* 99(4):689. Communal Sharing, Authority Ranking, Equality Matching, Market Pricing ([p2p summary](https://wiki.p2pfoundation.net/Four_Elementary_Forms_of_Sociality)).
- **Bugental (2000).** *Psych. Bull.* 126(2):187 (doi:10.1037/0033-2909.126.2.187). Five domains: attachment, hierarchical power, coalitional group, reciprocity, mating. Already used as a relation taxonomy in computer vision ([Sun et al., arXiv 1704.06456](https://arxiv.org/abs/1704.06456)). Note how the domains map:
  - Bugental ↔ Fiske: power ≈ AR, reciprocity ≈ EM, coalition/attachment ≈ CS.
  - Bugental ↔ Wish: power ≈ the equal/unequal axis.
- **Massey et al. 2015**, literary relationships ([arXiv 1512.00728](https://arxiv.org/abs/1512.00728)). Coarse category, then fine type, plus affinity (positive / negative / neutral):
  - *Social*: friend, enemy, acquaintance, lovers, unrequited love, rivals
  - *Professional*: employer, employee, colleague, servant, master, student, teacher, client
  - *Familial*: spouse, sibling, cousin, uncle/aunt, niece/nephew, child, parent, grand-, foster, step-, in-law, half-
  - **This is the closest existing scheme to Fandom character pairs.**
- **DialogRE** ([arXiv 2004.08056](https://arxiv.org/abs/2004.08056)). 36 types on *Friends* transcripts, e.g. per:boss / per:subordinate, per:girl/boyfriend, per:alumni, with explicit inverse pairs. Useful as a pattern for directed and inverse relation pairs.
- **Proposed design:** one neutral `type` word (Massey fine type) + `affinity` (+/0/−) + `power` (equal / above / below, from Wish and Fiske AR). Every type maps to a Bugental domain. Example: "rival": affinity −, power equal, domain coalitional/reciprocity.

### Actions

- **WordNet verb supersenses** ([lexnames](https://wordnet.princeton.edu/documentation/lexnames5wn)): `verb.social`, `verb.competition`, `verb.communication`, `verb.possession`, `verb.contact`. Use them as the coarse layer.
- **VerbNet classes** (Levin 1993 lineage). Verified in the NLTK VerbNet 3 data:
  - battle-36.4, meet-36.3, marry-36.2, correspond-36.1.1
  - help-72.1, defend-72.3, cooperate-73.1, conspire-71
  - murder-42.1, poison-42.2, subjugate-42.3, hurt-40.8.3, hit-18.1, destroy-44
  - steal-10.5, cheat-10.6.1, free-10.6.3, banish-10.2
  - chase-51.6, escape-51.1, accompany-51.7
  - hire-13.5.3, appoint-29.1, captain-29.8
  - advise-37.9, order-58.3, urge-58.1, forbid-64.4
  - bully-59.5, confront-98, succeed-74, admire-31.2, care-88.1, give-13.1
- **FrameNet 1.7 frames** (verified in the NLTK `framenet_v17` frame list; [FrameNet](https://framenet.icsi.berkeley.edu)):
  - Attack, Hostile_encounter, Fighting_activity, **Beat_opponent**, Conquering, Competition
  - Killing, Cause_harm, Kidnapping, Imprisonment, Revenge
  - Assistance, Rescuing, Protecting, Defending, Collaboration, Alliance, Taking_sides
  - Personal_relationship, Forming_relationships, Kinship, Social_connection, Friendly_or_hostile
  - Membership, Leadership, Subordinates_and_superiors, Being_employed, Hiring, Education_teaching
  - Manipulate_into_doing, Prevarication (deception), Abandonment, Sacrificing_for, Resurrection, Death, Giving_birth
  - There is **no "Betrayal" frame**. Use Prevarication with Taking_sides, or treat it as your own type.
- **Proposed vocabulary:** about 25 neutral verbs, each mapped to `{fn_frame, vn_class, wn_supersense}`. Examples: fights→Hostile_encounter/battle-36.4, defeats→Beat_opponent, kills→Killing/murder-42.1, saves→Rescuing/free-10.6.3, helps→Assistance/help-72.1, teaches→Education_teaching/advise-37.9, serves→Subordinates_and_superiors, marries→Forming_relationships/marry-36.2.

### What a 9B model can realistically extract from wiki text

- **High reliability**, because these are stated explicitly in infoboxes and prose:
  - kinship
  - membership/affiliation
  - master/apprentice and teacher
  - employer/servant
  - romance/marriage
  - "rival"/"enemy"/"ally" when the text uses those words
  - who fought, killed, saved or defeated whom
- **Medium reliability:** Big Five and HEXACO **adjectives that appear verbatim in "Personality" sections**. Extract the word as it appears, then map it to a factor with a fixed lexicon (Mini-Markers, the 100 markers, HEXACO markers). Do not ask the model to score the factor. Rare adjectives survive if every lexicon hit is kept (no frequency cut-off). Unmapped words get an `other` bucket.
- **Low reliability**, because these are latent constructs that need inference across many situations:
  - Machiavellianism, narcissism, psychopathy
  - IPC octant scores
  - Fiske model and Wish intensity, unless stated explicitly
  - Store these only if the text names them ("manipulative", "narcissistic" are fine as adjectives) and keep the evidence span.

---

## 3. Ordinals from pairwise comparisons

- **Bradley–Terry (BT)**, P(i beats j) = s_i / (s_i + s_j). Fitted with Hunter's MM algorithm (*Ann. Stat.* 32:384, 2004, [PSU](https://pure.psu.edu/en/publications/mm-algorithms-for-generalized-bradley-terry-models/)).
  - Plain maximum likelihood fails when a character has only wins, or when the graph is not strongly connected. **Fix: an L2/Gaussian prior (MAP).**
- **Davidson (1970)** ties extension, *JASA* 65:317 (doi:10.1080/01621459.1970.10481082). P(tie) ∝ ν·√(s_i s_j). R implementation: [BradleyTerry2::GenDavidson](https://rdrr.io/cran/BradleyTerry2/man/GenDavidson.html).
- **Rank Centrality** (Negahban, Oh & Shah, [arXiv 1209.1688](https://arxiv.org/abs/1209.1688)). A random-walk stationary distribution with good sample complexity on sparse graphs. It still needs connectivity.
- **[choix](https://github.com/lucasmaystre/choix)** (pip `choix`). Includes MM, Luce Spectral Ranking, Rank Centrality, and EP (Bayesian), with an `alpha` regularization parameter. **No native ties**: either encode a tie as half a win each way, or write Davidson in about 30 lines of scipy.
- **Elo and Glicko.** Online and order-dependent, designed for repeated matches over time. Text-derived comparisons have no meaningful order, so these are a poor fit.
- **TrueSkill** ([pypi trueskill](https://pypi.org/project/trueskill/)) and **TrueSkill 2** (Minka, Cleven & Zaykov 2018, [MSR](https://www.microsoft.com/en-us/research/publication/trueskill-2-improved-bayesian-skill-rating-system/)). Gaussian μ/σ with draw support. TrueSkill 2 adds game-specific features that are irrelevant here.
- **[openskill](https://pypi.org/project/openskill/)** (Weng–Lin, JMLR 2011). Open-license TrueSkill-like ratings with BradleyTerry/Thurstone/PlackettLuce variants, `predict_draw`, and μ/σ uncertainty.
- **Disconnected universes.** Fit each connected component separately. Scores are only identified up to a constant **within a component**. Do not report cross-universe ranks unless a bridge edge exists.
- **VS Battles Wiki can supply those bridges** (CC-BY-SA, 39,657 articles, MediaWiki API open; checked `api.php?action=parse` with prop=sections/wikitext):
  - [Tiering System](https://vsbattles.fandom.com/wiki/Tiering_System) has 11-C … 10-C (Below Average Human), 10-B (Human), 10-A (Athlete), 9-C (Street) … 8-C (Building) … 7-B (City) … 5-B (Planet) … 4-B (Solar System) … 3-A (Universe) … 2-A … 1-A (Outerverse), High 1-A, 0 (Boundless), including "Low/High" sub-steps. That is about 65 ordered levels.
  - Character profiles include structured `Tier:`, `Attack Potency:`, `Speed:`, `Durability:` and `Intelligence:` fields.
  - Profiles also have a **"Notable Matchups" section with Victories / Losses / Inconclusive tabs, linking to cross-verse debate threads**. These are ready-made cross-universe bridge edges, including draws.
  - Caveat: these are fan-consensus verdicts based on feats, not canon. Store them with `source="vsbw"` and keep them apart from wiki-text edges.

**Recommendation for ordinals.** Use a **Bayesian / MAP Bradley–Terry–Davidson** model, fitted per connected component:
- **Edges:** each text-extracted outcome ("defeated", "stronger than", "evenly matched" = tie) is one edge. Weight edges by extraction confidence and count repeated mentions once per source.
- **Prior:** use the VS Battles tier mapped to an ordinal number as the prior mean where it exists, and otherwise N(0, σ²). This keeps all-win characters finite and puts different universes on a rough common scale.
- **Output:** the posterior mean ± SD, and only rank pairs whose intervals separate.
- **Tools:** openskill (ThurstoneMosteller/BradleyTerryFull with draws) is an acceptable shortcut. choix is fine if ties are encoded as half wins each way.
- **Intellect:** same approach, using the `Intelligence:` field only as a weak prior.

---

## Verdict

1. **Distill. Do not train 9B locally.** Use a strong teacher (Sonnet 5.5 via Batch: about $3 per 1k paragraphs; Gemini Flash is cheaper) to label 1–2k paragraphs with a GoLLIE-style schema that has guidelines. Hand-check about 150 for a gold set.
   - On 8 GB, QLoRA on Qwen3.5 is officially discouraged and bf16 LoRA on 9B needs 22 GB. Train **Qwen3.5-2B bf16 LoRA** (5 GB) or **Qwen3-8B QLoRA** (about 6 GB, seq ≤ 2k), or rent a 24 GB GPU for one 9B run.
   - Export a merged GGUF and load it with `FROM` in a Modelfile. Ollama's Safetensors `ADAPTER` does not support Qwen.
   - Also try GLiNER/GLiREL as a cheap encoder baseline.
2. **Taxonomies.**
   - Relation `type`: Massey et al. 2015 fine types, plus Wish/Fiske `affinity` and `power` attributes, with a Bugental domain.
   - Actions: about 25 verbs mapped to FrameNet frame, VerbNet class and WordNet supersense.
   - Traits: extract verbatim adjectives, map them to Big Five Mini-Markers and HEXACO H markers with a fixed lexicon, keep every hit, and do not score latent Dark Triad or IPC constructs.
   - Validate against the Open-Source Psychometrics character ratings.
3. **Ordinals.** Use MAP Bradley–Terry–Davidson per component, with VS Battles tiers and Notable Matchups as the cross-universe prior and bridges, keeping that source separate. Do not use Elo or Glicko, because they depend on match order.
