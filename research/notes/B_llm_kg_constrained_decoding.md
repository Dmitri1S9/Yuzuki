# Research B: LLM KG extraction and making a 7-9B model stop hallucinating names

Context: per-paragraph "list relations of X" makes qwen3.5:9b invent or drag in names, abstract judgment questions give garbage, and whole page in context plus per-name questions failed.
Everything below was checked by fetch or search on 2026-11-03. Where a point rests on only one secondary source, it says so.

## 1. Existing KG extraction systems

| System | Schema | How it extracts | Hallucination guard | Entity resolution / relation merging | Reported quality |
|---|---|---|---|---|---|
| **MS GraphRAG** ([prompt](https://raw.githubusercontent.com/microsoft/graphrag/main/packages/graphrag/graphrag/prompts/index/extract_graph.py)) | Closed entity types, open relation text | One pass over each chunk: entities first, then "pairs ... *clearly related*", output as delimited tuples | Weak. Relations must use step-1 names. No check against the source text | Merges by exact (uppercased) name. An LLM summarizes the list of descriptions per entity | KGGen paper: **0% of 100 sampled GraphRAG triples were valid triples** (they are descriptions, not S-P-O) |
| **LightRAG** ([arXiv 2410.05779](https://arxiv.org/abs/2410.05779), [prompt.py](https://raw.githubusercontent.com/HKUDS/LightRAG/main/lightrag/prompt.py)) | Same as GraphRAG plus relation keywords | Tuple format modeled on GraphRAG | Prompt rules: "Only output relationship rows whose source and target entities are both included in the selected entity rows"; "Output fewer rows if fewer high-value items are present. Do not try to fill the limit." | Exact-name dedup, then an LLM profile per entity | RAG win rates only, no IE precision |
| **KGGen** ([arXiv 2502.09956](https://arxiv.org/abs/2502.09956), [code](https://raw.githubusercontent.com/stair-lab/kg-gen/main/README.md)) | Open | **Two steps:** (1) entities, (2) relations given the text and the entity list. DSPy structured output | **Code builds `Literal[tuple(entities)]` for subject and object**, which is a JSON-schema enum, and falls back to filtering out invalid names ([_2_get_relations.py](https://raw.githubusercontent.com/stair-lab/kg-gen/main/src/kg_gen/steps/_2_get_relations.py)) | S-BERT, then k-means clusters of 128, then top-16 neighbours per item by BM25+embedding, then the LLM picks exact duplicates and a canonical alias. Repeats until each cluster is empty. Entities and edges are resolved separately | MINE-1: KGGen 66%, GraphRAG 48%, OpenIE 30%. Triple validity 98% vs OpenIE 55% |
| **EDC** (Zhang & Soh, EMNLP 2024, [arXiv 2404.03868](https://arxiv.org/abs/2404.03868), [code](https://raw.githubusercontent.com/clear-nus/edc/main/README.md)) | Open, then canonicalized to a schema (given or self-built) | Open IE triples, then the LLM writes a one-line *definition* of each relation, then vector search over the schema's definitions, then the LLM picks the closest match or rejects | Canonicalization step can reject | **The direct fix for relation synonyms**: compare definitions, not surface strings | High quality on WebNLG, REBEL and Wiki-NRE without tuning |
| **iText2KG** ([arXiv 2409.03284](https://arxiv.org/abs/2409.03284)) | Open, incremental | Distill the document into semantic blocks, then entities, then relations restricted to the extracted entities | Entities passed to the relation step | Cosine similarity of embeddings against the existing graph (merge above a threshold) | Lower false-discovery rate than LangChain and LlamaIndex baselines |
| **Graphiti / Zep** ([arXiv 2501.13956](https://arxiv.org/abs/2501.13956), [extract_nodes.py](https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/prompts/extract_nodes.py)) | Optional typed schema | Entities first, then edges, with time validity | Prompt: "extract entity nodes that are **explicitly** mentioned in the CURRENT MESSAGE"; "Exclude entities mentioned only in the PREVIOUS MESSAGES (they are for context only)" | Embedding/BM25 candidate search, then an LLM dedup call per node and per edge | Memory benchmarks only |
| **LangChain LLMGraphTransformer** ([ref](https://reference.langchain.com/python/langchain-neo4j/graph_transformers/llm/LLMGraphTransformer)) | `allowed_nodes`, `allowed_relationships` | Tool call or JSON | `strict_mode=True` only post-filters types, not entity identity | None | None reported |
| **Neo4j LLM Graph Builder** ([repo](https://raw.githubusercontent.com/neo4j-labs/llm-graph-builder/main/README.md), [blog](https://neo4j.com/blog/developer/unstructured-text-to-knowledge-graph/)) | Optional schema | Built on LLMGraphTransformer | Same as above | LLM or similarity merge as a separate step | None reported |
| **REBEL** ([ACL 2021](https://aclanthology.org/2021.findings-emnlp.204), [HF](https://huggingface.co/Babelscape/rebel-large)) | Closed, about 200 Wikidata relations | BART seq2seq outputs linearized triplets | Closed vocabulary. Entities are mostly copied spans | None | NYT F1 93.4. Non-commercial licence. Wikidata relations do not fit fandom social ties well |
| **GLiNER / GLiREL** ([GLiREL 2501.03172](https://arxiv.org/abs/2501.03172), [GLiNER-multitask 2406.12925](https://arxiv.org/abs/2406.12925), [GLiNER2 2507.18546](https://arxiv.org/abs/2507.18546)) | Labels given at inference | Span or pair classifier | Cannot invent names: it scores spans that exist in the text | None | SOTA zero-shot on FewRel and WikiZSL. You already saw little gain |
| **AutoKG** ([2305.13168](https://arxiv.org/abs/2305.13168)) | Multi-agent | GPT-4 agents | None | None | Finding: GPT-4 is fine at KG construction but behind fine-tuned SOTA on extraction |
| **CodeKGC** ([2304.09048](https://arxiv.org/abs/2304.09048)) | Closed schema written as Python classes | The LLM writes code instantiating the classes | Schema typing | None | Beats text prompts on CoNLL04, ADE, SciERC |
| **Text2KGBench** ([2308.02357](https://arxiv.org/abs/2308.02357)) | Benchmark | Ontology-guided | Has explicit **subject/object/relation hallucination metrics** | None | 13B models: much room for improvement. Use its metric design for your eval |

GraphRAG prompt fragment (verbatim):
```
Format each entity as ("entity"<|><entity_name><|><entity_type><|><entity_description>)
...identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
Format each relationship as ("relationship"<|><source_entity><|><target_entity><|><relationship_description><|><relationship_strength>)
```
GraphRAG "gleanings" (verbatim):
- CONTINUE: `"MANY entities and relationships were missed in the last extraction. ..."`
- LOOP: `"...Answer Y if there are still entities or relationships that need to be added, or N..."`

Gleanings trade precision for recall. Telling a 9B model "MANY were missed" invites exactly the fabrication you see, so **don't copy them**.

**Takeaway.** No mature system trusts free-form name generation. The ones that work (KGGen, iText2KG, Graphiti, LightRAG) all (a) fix the entity set first, (b) restrict relation endpoints to that set, and (c) do resolution as a separate clustering step with embeddings plus an LLM yes/no. EDC adds (d): canonicalize relations by comparing definitions.

## 2. Ways to stop a 7-9B model from inventing names

### 2a. Constrained decoding: is `enum` enforced in Ollama? **Yes, locally.**
- Ollama `format` takes a JSON schema ([blog](https://ollama.com/blog/structured-outputs), [docs](https://docs.ollama.com/capabilities/structured-outputs)). The examples use Pydantic `Literal[...]`, which serializes to `enum`. Docs say **Ollama Cloud does not support structured outputs**. Pydantic-AI points to [ollama#12362](https://github.com/ollama/ollama/issues/12362): the cloud accepts the schema but does not enforce it.
- The current Ollama main runs GGUF models through the upstream **llama-server** subprocess ([llm/server.go](https://raw.githubusercontent.com/ollama/ollama/main/llm/server.go): "All GGUF models are served via the upstream llama-server subprocess"). The schema therefore goes through llama.cpp's `json-schema-to-grammar`, which handles `KIND_ENUM` by building a GBNF alternation of the literal strings ([source](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/json-schema-to-grammar.cpp)).
- **Thinking interplay:**
  - In current code, `CompletionRequest.ThinkingClose` holds "the strings any of which ends the thinking the response begins with, **which Format leaves free**". So the grammar applies only after `</think>`.
  - Reported bug [ollama#14645](https://github.com/ollama/ollama/issues/14645) (v0.17.6, qwen3.5:35b-a3b): **format ignored when think=false**. I could only see this through a search summary. Test your version with a deliberately out-of-enum prompt.
  - An older report has output landing in `thinking` instead of `content` ([ollama-python#597](https://github.com/ollama/ollama-python/issues/597)).
- **Caveats:**
  1. `uniqueItems` is unsupported and "Unsupported features are skipped silently" ([grammars README](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/grammars/README.md)), so dedupe in code.
  2. An enum stops *invented* strings but **not wrong choices**: the model can still pick a name that is present in the paragraph but unrelated. You still need verification (2c).
  3. Use temperature 0. NuMind warns that Ollama's default of 0.7 hurts extraction.
  4. An empty list is only possible if the schema allows `[]`, so always allow it.
- Alternatives if you leave Ollama:
  - [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs.html) (`choice`, `json`, `regex`, `grammar`; XGrammar backend)
  - [XGrammar](https://raw.githubusercontent.com/mlc-ai/xgrammar/main/README.md)
  - [Outlines](https://raw.githubusercontent.com/dottxt-ai/outlines/main/README.md)
  - [lm-format-enforcer](https://raw.githubusercontent.com/noamgat/lm-format-enforcer/main/README.md)

  All support enum or choice. None is needed: Ollama's GBNF route already does it.
- Schema sketch, built per paragraph from a deterministic name matcher (alias dictionary from the wiki's character list):
  ```json
  {"type":"object","properties":{"relations":{"type":"array","items":{"type":"object",
   "properties":{"other":{"enum":["Kyoka Jiro","Denki Kaminari"]},
                 "relation":{"enum":["friend","classmate","family","rival","mentor","enemy","romantic","other"]},
                 "evidence":{"type":"string"}},
   "required":["other","relation","evidence"]}}},"required":["relations"]}
  ```
  The `evidence` field should be checked in code to be a substring of the paragraph. This is cheap grounding.

### 2b. Entity markers and pairwise classification instead of generation
- Typed entity markers (Zhou & Chen, [2102.01373](https://arxiv.org/abs/2102.01373)) give TACRED F1 74.6 and Re-TACRED 91.1. The "punct" variant, e.g. `@ * person * Kyoka Jiro @`, needs no new tokens.
- With an LLM, mark only the two candidates in the paragraph (`[A]...[/A]`, `[B]...[/B]`) and ask a closed question.
- This turns open generation into N×(N-1)/2 closed classification calls per paragraph, which is usually small for fandom paragraphs.

### 2c. Verify instead of generate
- **NLI-based relation extraction** (Sainz et al., EMNLP 2021, [ACL](https://aclanthology.org/2021.emnlp-main.92/), [arXiv 2109.03659](https://arxiv.org/abs/2109.03659), code [Ask2Transformers](https://raw.githubusercontent.com/osainz59/Ask2Transformers/master/README.md)):
  - Verbalize each relation as a hypothesis template, e.g. "{A} is {B}'s mentor." Score P(entailment | paragraph) with an MNLI model.
  - Add type and "no relation" thresholds.
  - Results: **63% F1 zero-shot and 69% with 16 examples per relation on TACRED**. Writing templates took under 15 minutes per relation.
  - Model: e.g. [DeBERTa-v3-large-mnli-fever-anli-ling-wanli](https://huggingface.co/MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli) (435M parameters; fast on GPU, fine on CPU). Structurally it cannot hallucinate names.
- **CoVe** (Dhuliawala et al., [2309.11495](https://arxiv.org/abs/2309.11495), ACL Findings 2024): draft, plan verification questions, answer them *independently* without the draft, then revise. A summary reports Wikidata list precision rising from 0.17 to 0.36. The key ingredient is that verification questions don't see the draft. For you: each extracted (X, Y, rel) becomes a separate yes/no prompt over the paragraph only.
- **Ma et al. 2023** ([2303.08559](https://arxiv.org/abs/2303.08559), EMNLP Findings): "LLM is not a good few-shot information extractor, but a good reranker for hard samples." A small model filters, and the LLM reranks the small model's top-N labels on hard cases only, for +2.4 F1 on average. **This is direct evidence for "small model proposes, LLM chooses from a closed list".**
- **Guideline-following IE**: GoLLIE ([2310.03668](https://arxiv.org/abs/2310.03668), ICLR 2024) writes the schema as Python classes with docstring guidelines and finds that detailed guidelines are key for zero-shot. CodeKGC is similar. Even without GoLLIE weights, docstring-style definitions per relation label are what turn "abstract judgment" into a decidable question.
- **NuExtract 2.0** ([8B](https://huggingface.co/numind/NuExtract-2.0-8B), [8B-GGUF](https://huggingface.co/numind/NuExtract-2.0-8B-GGUF), [2B](https://huggingface.co/numind/NuExtract-2.0-2B)): a Qwen2.5-VL-7B fine-tune for template-to-JSON extraction. Templates support verbatim-string and enum fields. It is a drop-in alternative to qwen3.5:9b for the extraction step.
- ChatIE ([2302.10205](https://arxiv.org/abs/2302.10205)): splitting IE into multi-turn sub-questions (types first, then arguments) beats single-shot ChatGPT. Same lesson: decompose.

### 2d. Throughput on an 8 GB card, and prompt caching
- llama.cpp CUDA scoreboard ([discussion #15013](https://github.com/ggml-org/llama.cpp/discussions/15013)), Llama-2-7B Q4_0:

  | GPU | Prompt eval, pp512 (t/s) | Generation, tg128 (t/s) |
  |---|---|---|
  | **RTX 5060 8GB** (user comment) | ~3270 (FA off), ~3800 (FA on) | ~97 (FA off), ~100 (FA on) |
  | 4060 Ti 8GB | ~3400 | ~64 |

  For a 9B Q4_K_M, expect roughly 0.6-0.7× those numbers. That is my estimate; measure with `ollama run --verbose`.
- So prompt eval of a 1-2k-token paragraph-plus-question takes about 0.5 s or less. Generation dominates, so short outputs (labels, Y/N, enum JSON) are what make thousands of calls feasible.
- Prefix cache: in llama-server, `cache_prompt` defaults to true and "only the suffix that differs" is evaluated ([server README](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md)). To get hits:
  - Put the shared page or paragraph **first** and the varying question **last**.
  - Keep `num_ctx` constant (a change forces a reload).
  - Set a long `keep_alive` (e.g. `-1`).

  Per a [Leanpub Ollama chapter](https://leanpub.com/read/ollama/prompt-caching), `prompt_eval_count` does not reveal cache hits; time it instead. Note the server README warns that cached and uncached logits may differ slightly.
- Ollama exposes `logprobs` / `top_logprobs` on `/api/chat` ([API docs](https://docs.ollama.com/api/chat); also fields in server.go). Use P("Yes") as a calibrated confidence for thresholding instead of a hard answer.

## 3. Verdict: ranking for this problem

1. **Deterministic candidates plus enum-constrained JSON (the KGGen pattern).**
   - Build the paragraph's name list in code (alias dictionary or string match, optionally GLiNER as recall backup).
   - Pass it as `enum` in Ollama `format`, together with a closed relation-label enum and an `evidence` substring check.
   - Why first: it *removes* the main failure (invented names) by construction, it costs one call per paragraph, it is already enforced by llama.cpp GBNF, and KGGen's own code does exactly this.
   - Test the think=false bug (#14645) first, and allow an empty array.
2. **Pairwise closed-label classification with marked entities, plus a logprob threshold (Sainz-style verbalized definitions).**
   - For each candidate pair in a paragraph, ask: "Per this paragraph, which best describes [A]→[B]: {labels with one-line definitions} | none". Use an enum and read top_logprobs.
   - Why: the Ma et al. 2023 and NLI-RE evidence says small models are good at choosing among options and bad at open listing. It also replaces "abstract judgment" with a definition-backed choice. Put the paragraph first to get prefix-cache hits.
   - Use this as the verifier for #1 (CoVe-style independent checks), or instead of #1 when precision matters most.
3. **NLI entailment relation extraction with DeBERTa-MNLI as a cheap second opinion or ensemble.**
   - Zero hallucination, runs alongside the LLM on GPU or CPU, and gives TACRED-level zero-shot ~63 F1 with 15-minute templates.
   - Accept an edge only when the LLM and NLI agree, or route disagreements to the LLM (Ma et al.'s filter-then-rerank).
4. **Post-hoc resolution: KGGen-style clustering for aliases, EDC-style definition canonicalization for relation labels.**
   - Do these globally after extraction, not inside the extraction prompt.
   - If #1 and #2 use a closed relation set, EDC is only needed for an "other"/free-text tail.

**Avoid:** GraphRAG-style gleaning ("MANY were missed"), whole-page "list all relations of X" prompts, and free-text name fields anywhere in the schema.

**Evaluate** with Text2KGBench-style hallucination metrics (subject or object not in the text, relation not in the schema) on about 50 hand-labelled paragraphs before and after each step.
