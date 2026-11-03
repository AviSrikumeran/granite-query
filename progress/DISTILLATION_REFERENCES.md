# Distillation references for Granite Query

Verified 2026-11-03 against authors' model cards, papers, code and public Hugging Face metadata. These are external reference results, not Granite Query results. Model cards were researched; no model weights were downloaded and no additional training or inference was launched for this audit.

## Actual open weights

| Release | Verified revision and files | Relevance |
| --- | --- | --- |
| [armand0e/Granite-4.2-30B-Fable-Distill-LoRA](https://huggingface.co/armand0e/Granite-4.2-30B-Fable-Distill-LoRA) | `fed66b05e9ab644c6e7fc39e8fa14715ba6a8b73`; `adapter_config.json` and `adapter_model.safetensors` | An actual third-party Granite student adapter trained on teacher-generated chat/tool traces. |
| [armand0e/Granite-4.2-30B-Fable-Distill](https://huggingface.co/armand0e/Granite-4.2-30B-Fable-Distill) | `193b67a24588e46bded683b5f9a680634593bdb2`; 11 Safetensors shards | Merged weights corresponding to that adapter, rather than a quantization-only release. |
| [HuggingFaceH4/zephyr-7b-beta](https://huggingface.co/HuggingFaceH4/zephyr-7b-beta) | `892b3d7a7b1cf10c7a701c60881cd93df615734c`; 8 Safetensors shards | Mistral-7B student trained using synthetic conversations and distilled preferences. |
| [deepseek-ai/DeepSeek-R1-Distill-Llama-8B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B) | `6a6f4aa4197940add57724a7707d069478df56b1`; 2 Safetensors shards | Llama-3.1-8B student trained on R1-curated responses. |

File inventories and revisions were checked using the public Hugging Face model metadata endpoint for each named repository. This verifies that weight files are published; it does not independently validate their quality or reproduce their training. The user's earlier unspecified Granite-distill reference cannot be identified uniquely from its description.

## Granite recipes and what they establish

The Fable adapter author reports 773 examples, 8.78M rendered tokens, a 40,960-token context, QLoRA r=32/alpha=32 on attention and MLP projections, LR 8e-5, two epochs/194 steps, batch 1 with accumulation 8, and Unsloth/TRL on one 64GB GPU for about 24 hours. Reasoning spans are supervised; tool calls dominate the supervision. The card reports training loss, not a controlled mathematics benchmark or a measured improvement over base Granite. The useful reproducibility detail is its assistant-turn boundary masking correction. [Author's training and limitations](https://huggingface.co/armand0e/Granite-4.2-30B-Fable-Distill-LoRA#training).

The author links the open [Teich data-formatting and masking code](https://github.com/TeichAI/teich). That supports inspecting span construction; it is not a complete independently reproduced training run.

IBM's official Granite 4.2 recipe is broader post-training, not documented there as an R1 teacher-distillation experiment: 7.2M SFT samples, approximately 100B input/65B trainable tokens, quality filtering, SHA256 deduplication, global shuffle, packed 128K sequences, LR 1e-5, 2.5% warmup and about two epochs. Its 30B specialization phase uses LR 3e-6 and roughly 16% replay. SFT is followed by staged GRPO/RLHF using NeMo-RL and NeMo-Gym. These resources are far beyond this project's budget. [IBM technical recipe](https://huggingface.co/blog/ibm-granite/granite-4-2#sft-data-preparation--quality-control).

The official 3B card reports AIME25 78.33 and GPQA 54.80 under IBM's evaluation, using a NeMo Evaluator-based framework. It recommends temperature 1.0/top-p 0.95 and distinguishes thinking, non-thinking and low-effort modes; example limits are 8192 thinking tokens or 2048 non-thinking tokens. Our greedy, 512-token, non-thinking monitoring runs use a different protocol. They do not establish Granite's overall capability ceiling. IBM does not provide a directly comparable GSM8K score in that card. [Official 3B evaluation and inference settings](https://huggingface.co/ibm-granite/granite-4.2-3b#evaluation-results).

For historical context, IBM explicitly described Granite 3.2 reasoning as direct reinforcement learning on Granite 3.1, rather than DeepSeek-R1 distillation. That statement is about that release, not a universal restriction on training Granite. [IBM's reasoning announcement](https://www.ibm.com/new/announcements/bringing-reasoning-to-granite).

Two easily confused references need different labels. [constructai/Granite-v4.1-Distilled-15K](https://huggingface.co/datasets/constructai/Granite-v4.1-Distilled-15K/blob/main/README.md) is a dataset generated **by** a Granite-4.1-8B teacher; its name does not establish a better Granite student. [ramendik/granite-4.0-h-tiny-stonebnb](https://huggingface.co/ramendik/granite-4.0-h-tiny-stonebnb) is a quantized training base, not evidence of distillation gains. Neither was trained on or imported by this reference audit.

## Mistral and Llama comparisons

Zephyr-7B-beta starts from Mistral-7B-v0.1. Its authors use filtered ChatGPT-generated UltraChat conversations for SFT, then GPT-4-ranked UltraFeedback preferences for DPO. Their reported scores are MT-Bench 7.34 and AlpacaEval 90.60%; these measure chat alignment, not mathematical accuracy. The release's DPO card records LR 5e-7 and three epochs. [Zephyr model card](https://huggingface.co/HuggingFaceH4/zephyr-7b-beta#performance).

The maintained reproduction recipe differs from the original release: full SFT uses LR 2e-5, cosine scheduling, 10% warmup, length 2048 and one epoch; its QLoRA variant uses LR 2e-4. The maintainers explain that corrected preference labels and an SFT scheduler bug led to revised hyperparameters. Use a pinned recipe, not a mixture of original and corrected settings. [Full SFT configuration](https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/sft/config_full.yaml), [QLoRA configuration](https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/sft/config_qlora.yaml), [maintainers' correction note and executable commands](https://github.com/huggingface/alignment-handbook/blob/main/recipes/zephyr-7b-beta/README.md).

DeepSeek-R1's Llama-8B student uses sequence SFT on 800K curated examples, with no student RL stage. The collection contains about 600K reasoning examples retained after correctness/readability filtering and 200K other examples. The paper reports Llama-8B AIME2024 pass@1 50.4 and MATH-500 89.1. Evaluation permits much longer reasoning than our short-answer trial. The paper's distillation section does not publish a complete student LR/token-budget/trainer recipe; the teacher's two-epoch setting must not be silently attributed to every student. [R1 paper sections 2.3.3, 2.4 and 3.2](https://arxiv.org/html/2501.12948v1#S2.S4), [published student card](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B).

## Application to the current bounded experiment

The following are our engineering inferences, not claims that an external recipe guarantees improvement:

1. Keep verified, complete, concise teacher responses, exact tokenizer/chat-template rendering, and correct assistant-only label masking. Preserve original responses and rejection reasons. Inspect truncation and correctness separately from style.
2. Test the frozen 32,768-supervised-token random versus valued arms before changing their optimization or inference settings. A lower training loss is insufficient; compare paired accuracy against untouched Granite and the random control.
3. Keep the frozen LR 2e-5 and equal 1024-supervised-token optimizer batches for those new arms. Similar numerical LR values in external recipes are context, not proof that they are optimal for LoRA here. Do not replace this experiment with a 30B, 40K-context or multi-stage RL run within $30 Modal/$20 DeepSeek.
4. Separate a later thinking/low-effort inference ablation from training improvement, with identical question IDs and an explicit latency/token allowance. Do not silently change the current evaluation protocol to obtain a larger number.
5. API-completion training is sequence distillation/SFT. Full-logit or on-policy distillation requires additional capabilities; public weight availability alone does not provide teacher logits from our API.
6. More datasets only help if their verified traces teach the target task within the context/budget. Audit sources and overlaps, then measure downstream gains. Do not equate source count, parameter count, loss reduction or an attractive model-card title with a successful student.

