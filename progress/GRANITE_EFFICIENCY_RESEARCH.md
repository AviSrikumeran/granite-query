# Granite weights and efficiency research plan

**Priority: High. Reviewed November 3, 2026. Status: artifact audit complete; new performance experiments and sparse conversion are proposals.**

Granite Query should measure whether verified, student-aware training data improves useful mathematical work per unit of training and inference cost. A universal claim that Granite is ten times less efficient is not established. The immediate research question is narrower: **Where does this exact Granite checkpoint spend resources without producing correct answers, and which affordable intervention changes that tradeoff?**

## Which Granite we have

The training student is `ibm-granite/granite-4.2-3b`, revision `4e9c275e232f10211ec88644d106a1f6a1b60e06`. The earlier local Ollama demonstration used `granite4.2:8b` in Q4_K_M format. Those artifacts are different sizes and precisions; do not join their results into one baseline.

The pinned 3B checkpoint is now downloaded locally: two BF16 Safetensors shards totaling **7,319,517,120 bytes**, each verified against Hugging Face's LFS SHA-256. Header inspection counts **3,659,737,600 stored parameters**, 40 transformer blocks, width 2560, MLP width 8192 and vocabulary 100352. The complete local scalar audit and download receipts are included in the downloadable evidence. No new model inference or training was required for this audit.

The selected family also offers 8B and 30B releases. Their inspected inventories contain about 8.79B and 29.28B elements, respectively. The 30B reference requires about 58.55 GB for its BF16 weight files alone. It is a larger capability reference, not a proven best choice for every workload. Keep the 3B student to preserve continuity and affordability. [Official family](https://huggingface.co/collections/ibm-granite/granite-42-language-models).

## What Granite does and what weights mean

Granite predicts the next token from the preceding context. Post-training makes that mechanism useful for answering questions, following instructions, reasoning and emitting tool requests. A host program must execute tools. Granite 4.2 supports thinking, non-thinking and low-effort modes; its official card recommends temperature 1.0 and top-p 0.95. Our historical greedy non-thinking 512-token protocol is a specific operating point. [IBM model card](https://huggingface.co/ibm-granite/granite-4.2-3b).

Weights are learned numerical arrays. The architecture specifies how to use them; the tokenizer maps text to token IDs; the chat template marks roles and reasoning modes. The weight files are neither a readable rule book nor a reconstruction of the training corpus. Different models learn different coordinate systems, so comparing the same array position across independently trained models cannot identify the same concept.

For this Granite checkpoint, `model.layers.0.self_attn.q_proj.weight` has shape `[2560, 2560]`; `k_proj` and `v_proj` each have shape `[512, 2560]`. The MLP contains two `[8192, 2560]` projections and one `[2560, 8192]` projection. These are concrete inspection targets. Scalar samples and heatmaps show actual values, but their magnitudes and colors do not rank intelligence or establish a cause of inefficiency.

Granite **4.2 is dense**, whereas some **4.0 releases are hybrid Mamba and MoE models**. The family name alone does not specify architecture. IBM documents pretraining inherited from Granite 4.1, supervised fine-tuning and staged reinforcement learning; the 8B and 30B variants additionally receive agentic RL. [IBM technical walkthrough](https://huggingface.co/blog/ibm-granite/granite-4-2), [4.0 architecture](https://www.ibm.com/granite/docs/models/granite4-0).

## Non Chinese comparison models

These are selected scientific controls and references, not a ranking of every current open model. The interactive page exposes pinned revisions, actual tensor layouts and tokenizer counts. Only Granite 3B was downloaded in full; other accessible models supplied configs, tokenizers and headers, with tiny scalar samples for selected BF16 models.

| Model and developer | What it can do and why compare it | Main comparison limits |
| --- | --- | --- |
| Granite 4.2 3B, IBM, United States | Current reasoning and instruction-following student; dense; 3.660B inspected elements | Current project development results are task-specific |
| Ministral 3 3B Instruct, Mistral AI, France | Text and image assistant, function calling and structured output; small deployment comparator | Includes a vision encoder; selected checkpoint mixes FP8 and BF16; 3.849B stored elements include scale tensors |
| Falcon H1 3B Instruct, TII, Abu Dhabi, UAE | Hybrid attention and Mamba model; tests a different inference architecture at a similar scale | Custom Falcon license; different engine support and cache behavior |
| Olmo 3 7B Instruct, Ai2, United States | Instruction assistant with published training artifacts; valuable for studying data and post-training choices | About twice the student's size; distinguish Instruct from Think |
| Llama 3.2 3B Instruct, Meta, United States | Established small multilingual instruction model; useful ecosystem control | Custom Llama license and gated file access; headers and tokenizer were unavailable in this unauthenticated audit |

Ministral's paper documents cascade distillation through pruning and continued training. It also reports a 3B reasoning case where ordinary SFT produced repetition and excessive verbosity, and logit distillation helped stabilize it. This directly motivates a controlled study of teacher traces and response length; it does not establish that Granite has the same defect. [Ministral paper, sections 3 and 5](https://arxiv.org/html/2601.08584v1), [model card](https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512).

Falcon is an architectural contrast, while Olmo is particularly useful for training transparency. Open weights do not automatically mean the training corpus, full recipe or license terms are identical. [Falcon card](https://huggingface.co/tiiuae/Falcon-H1-3B-Instruct), [Olmo card](https://huggingface.co/allenai/Olmo-3-7B-Instruct), [Llama card](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct).

## Chinese models and public methods

| Reference | Publicly documented mechanism | Relevance to Granite Query |
| --- | --- | --- |
| Qwen3 4B, Alibaba | Small dense model with thinking and non-thinking control; family report describes off-policy response distillation and on-policy teacher-logit alignment | Similar-scale control. Test mode and budget explicitly. Completion-only API supervision does not reproduce logit distillation |
| DeepSeek R1 Distill Qwen 7B | Dense Qwen-derived student trained on R1-generated examples | A larger distilled reasoning control. It is not a miniature copy of DeepSeek's MoE architecture |
| DeepSeek V3 | 671B total / 37B active; MLA, routed/shared experts, load balancing, FP8 training and multi-token prediction | Architectural mechanisms can motivate hypotheses, but they are not a plug-in conversion recipe for Granite |
| DeepSeek V4 Pro | Published card lists 1.6T total / 49B active; mixed FP4/FP8; specialist post-training and on-policy consolidation | Current project API teacher reference; far outside local hardware and not a size-matched control |

Qwen3's report compares on-policy distillation with RL from a common distilled 8B starting point, reporting 1800 versus 17920 GPU-hours in that experiment. That approximately tenfold figure concerns **post-training compute under their setup**, not a universal token-efficiency ratio between Qwen and Granite. [Qwen3 report, sections 4.5 and 4.7](https://arxiv.org/html/2505.09388v1), [4B card](https://huggingface.co/Qwen/Qwen3-4B).

R1 describes correctness/readability filtering and supervised transfer into smaller Qwen and Llama students. V3 separates inference architecture from data and post-training choices. V4 describes aligning a student's own trajectories to specialist teacher distributions. Public reports disclose useful mechanisms, not every training datum or proof of why Granite differs. [R1 report](https://arxiv.org/html/2501.12948v1), [V3 report](https://arxiv.org/html/2412.19437v1), [V4 report](https://arxiv.org/html/2606.19348v1), [V4 Pro card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro).

## Four separate efficiency questions

| Question | Measure | Required controls |
| --- | --- | --- |
| Does text fragment into too many input tokens? | Raw tokens per UTF-8 byte, plus native chat-template overhead | Identical text, language and formatting; show distributions by task |
| Does answering consume too many tokens? | Correctness versus total generated tokens, including failed attempts, reasoning and retries | Same questions and explicit output caps; comparable stopping and answer extraction |
| Does each token cost too much to compute? | Warm prefill/decode time, time to first token, GPU seconds and peak memory | Same device, precision, batch, context, engine and cache policy; report cold start separately |
| Does training use examples inefficiently? | Held-out gain versus supervised tokens, total forwarded tokens, GPU hours and dollars | Independent starts, matched pools and settings, random controls and repeated seeds |

Track **total generated tokens across every attempt / number of correct questions**, alongside accuracy and total time. Set this ratio undefined when no answer is correct. Also report characters or bytes: token units differ between tokenizers. A tenfold claim requires a named metric, task, denominator and matched quality target.

### What the local tokenizer diagnostic found

Fifteen newly authored strings cover math, prose, code, structured text, French, Chinese and Arabic. They contain no benchmark questions. Six English math strings encode to 162 Granite tokens, 179 Ministral tokens, 177 Falcon tokens, 162 Olmo tokens, 175 Qwen3 tokens, 175 R1-Distill-Qwen tokens, and 162 tokens under each inspected DeepSeek V3/V4 tokenizer. Granite therefore used about 7.4% fewer input tokens than Qwen3 on this small subset.

This is a reproducible probe, not a representative benchmark or inference result. It excludes role templates, generated reasoning, answer correctness and execution speed. It argues against treating an assumed tenfold input-token penalty as the starting fact.

The single Chinese diagnostic string goes the other way: Granite uses 40 tokens, Qwen3 uses 25, and DeepSeek V3/V4 use 22. That is a reason to stratify tokenization by workload and language, not to generalize from the English subset.

## Evidence and testable explanations

The existing separate 200-question development comparison measured untouched Granite 179/200, random-trained 174/200, skill-trained 171/200 and DeepSeek 194/200 under the matched non-thinking 512-token cap. Granite truncations fell from eight to two after either adapter, while correctness fell. Shorter or more complete outputs alone are insufficient. These are development observations, not final-test scores. [Project evidence](DEVELOPMENT_TEACHER200.md), [human study](HUMAN_STUDY_RESULTS.md).

| Hypothesis | Diagnostic that could support or reject it |
| --- | --- |
| Native reasoning mode or output cap hides available capability | Accuracy and total-cost curves for native non-thinking, low-effort and thinking modes on the same development IDs |
| Teacher traces mismatch the student or output protocol | Verified concise versus native-reasoning traces from the same source questions; compare masks, truncation and paired regressions |
| Labels or serialization damage learning | Inspect rendered assistant boundaries, EOS, loss masks, finite values and reload identity before interpreting training quality |
| The selector amplifies noise or misses useful skills | Random versus selected data from the same eligible pool at equal tokens and updates; repeat seeds |
| Dense compute dominates cost | Matched local inference profiling versus small dense and hybrid controls; separate kernel support from architecture |
| Tokenization hurts specific languages or schemas | Expand byte-normalized probes and real permitted workload text by language, numbers and code |

Weight inspection can identify structure, numerical corruption and changes from a shared checkpoint. It cannot causally attribute a model's behavior to a particular training decision. That requires an intervention with controls. Hugging Face download counts are not counts of unique users, production deployments or market adoption.

## Sparse upcycling proposal

Sparse upcycling copies selected dense feed-forward blocks into multiple experts and adds a router selecting a subset per token. It reuses the pretrained checkpoint and adds capacity. It is different from pruning weights, quantization and LoRA. The original paper evaluates T5 and vision models, including substantial continued training; its savings relative to starting over are not a guarantee of a cheap Granite run. [Sparse Upcycling](https://arxiv.org/html/2212.05055v2).

An illustrative first topology replaces **eight of forty** Granite MLP blocks with **four cloned experts**, routing **top one**. Each MLP has `3 × 2560 × 8192 = 62,914,560` parameters. Three extra copies across eight layers add 1,509,949,440 parameters; bias-free routers add 81,920. Total capacity becomes **5,169,768,960 parameters**, approximately **10.34 GB of BF16 weights** before caches, activations, gradients or optimizer state. Top-one routing keeps the selected MLP arithmetic near the dense baseline while adding routing and dispatch overhead. It promises neither fewer tokens nor faster inference.

Before training, use identical clones, dropout disabled, no dropped tokens, and a selected-expert output normalized to coefficient one. Verify logits against the original model on synthetic inputs within numerical tolerance; save/reload and verify tensor identity. Merely multiplying a copied expert by its unnormalized router probability can break preservation. Then test routing balance, expert usage, overflow, specialization and basic instruction retention. A later partial reinitialization ablation can test diversification only after the cloned baseline is sound. [Drop-Upcycling](https://arxiv.org/html/2502.19261v1).

The router's training rule needs its own design: renormalized hard top-one routing can remove the main-loss gradient to gate scores. Before a paid experiment, demonstrate a differentiable or straight-through routing recipe, its balance objective and nonzero intended gradients on synthetic cases. Initial function preservation is a conversion check, not a complete learning algorithm. Cloning alone adds no new knowledge.

The local GPU is an RTX 3060 with 12 GB VRAM. Raw weights fitting does not imply full training fits. Estimate activation/optimizer memory and supported sparse kernels before any funded run. The existing $30 Modal and $20 DeepSeek ceilings are shared with ongoing project work; do not budget them a second time.

## Staged plan and decision gates

1. **Freeze artifact evidence.** Retain revisions, hashes, canonical tensor inventories, tokenizer probes and scalar samples. Keep raw checkpoints private and outside Git. This audit completes that step for the downloaded Granite student and the stated comparison scope.
2. **Locate the bottleneck.** Expand tokenization diagnostics on training/development text only. Plan native-mode cost curves and a paired error taxonomy. Keep the official test sealed and preserve existing studies as separate protocols.
3. **Try the least expensive intervention first.** Resolve template/masking defects if present. Compare complete concise and reasoning supervision with unchanged data controls. Existing independently versioned training work must retain its own ownership, reservation and reporting.
4. **Evaluate the original data-valuation hypothesis.** Compare selected and random subsets at equal supervised tokens and updates. Report accuracy change, uncertainty, input exposure and selection overhead. A useful checkpoint and evidence that ranking helps are separate claims.
5. **Gate sparse conversion on evidence and resources.** Require a working conversion/reload test and a funded memory/runtime estimate. Compare continued dense training with upcycled training under a shared data recipe. Use both an equal-token comparison and a separate equal-GPU-budget comparison; MoE overhead can prevent matching both at once.
6. **Freeze and evaluate.** Select the candidate using development data, freeze hashes and inference settings, then use the reserved official-test protocol once. Publish paired corrections/regressions, accuracy-cost curves, failures and reproducible commands. No gain is guaranteed.

An initial proposed usefulness target is at least three percentage points of development improvement at similar measured inference cost, or at least 20% lower measured inference cost with no more than one percentage point of accuracy loss. These are planning targets, not achieved results or statistical proof. Require paired uncertainty and additional seeds before stronger claims; use final evaluation for the frozen conclusion.

The capstone contribution can be a reliable account of **which verified examples improve a fixed student under a budget**, backed by controlled evidence. Matching a frontier teacher or rebuilding a foundation model is unnecessary. A negative selector or upcycling result remains informative if the protocol isolates the cause and the evidence is reproducible.

## Reproduce the artifact audit

Use the existing project Python environment with `requests`, `numpy` and `tokenizers` installed. From the repository root:

```text
python research/inspect_models.py metadata
python research/inspect_models.py download
python research/analyze_artifacts.py
python research/sample_weights.py
```

The metadata command resolves comparison `main` revisions at execution time; this report's exact observed revisions remain in `research/model_inventory.json` and the public evidence bundle. Repeating the comparison later may inspect a newer release state. Granite's download is fixed to the existing project revision. These scripts make public HF requests and perform file inspection only; they do not train or execute remote model code.

To reuse the exact comparison revisions from this audit, run `python research/inspect_models.py metadata --manifest research/model_inventory.json` instead of the unpinned metadata command. The page builder additionally uses `markdown-it-py`: `python research/build_research_page.py` regenerates the HTML after all audit outputs exist.
