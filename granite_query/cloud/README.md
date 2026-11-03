> Historical pilot notes. The hosted32B teacher experiment below was superseded by the DeepSeek API and pinned Granite4.2 3B research pipeline. Use [SUPERVISOR.md](SUPERVISOR.md) and the [current project README](../../README.md). Do not replay the historical launch commands as current work. Current local research dependencies are in requirements-research.txt.

# Granite Query: bounded teacher pilot

The approved pilot uses `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` on one A100 80GB. Its immutable Hugging Face revision is `711ad2ea6aa40cfca18895e8aca02ab92df1a746`.

The pilot contains 16 uniformly sampled questions from all 7,344 eligible GSM8K training prompts, using seed 42. It does not sample only the BM25-ranked arm. It is a compatibility, formatting, and throughput check; it is too small to establish the teacher's accuracy advantage or provide two 128-example training sets.

## Current state

- Modal SDK 1.6.2 is installed in the isolated project-local `.venv-modal` environment.
- `runs/deepseek32b_pilot16_seed42/plan.json` freezes question IDs, input hashes, model, GPU and limits.
- Local source references/gold answers are in `local_sources.jsonl`. `requests.jsonl` contains only question IDs and question text.
- The cloud image includes Python source only. Human references, local pilot data, ranking data and held-out test files are not mounted.
- No cloud job is launched by imports, pilot preparation, preflight, or offline tests.

## Local Modal authentication

1. Create or sign in to a [Modal account](https://modal.com/). GPU use requires a valid payment method on the account. Review the workspace budget before running paid compute. [GPU setup](https://modal.com/docs/guide/gpu), [budgets](https://modal.com/docs/guide/budgets).
2. Create a Modal API token in the dashboard's workspace settings. The two values are named `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`.
3. In Windows, search for **Edit environment variables for your account**. Add those two names under user variables, with the respective values from Modal. Do not put their values in this repository or in chat.
4. The launcher reads both process and user environment variables, without displaying or persisting their values. No app restart is needed for user variables set through that dialog. [Authentication configuration](https://modal.com/docs/sdk/py/latest/config).

This public DeepSeek checkpoint does not require a Hugging Face token.

## Preflight and launch

From the project workspace (`Granite Query`):

```powershell
# Local preflight only: no account or GPU required.
.\granite_query\cloud\launch_pilot.ps1

# Run the already-approved 16-question pilot after configuring credentials.
.\granite_query\cloud\launch_pilot.ps1 -Launch
```

Do not start a second launcher while the first runs. `call.json` blocks accidental relaunches; keep it for recovery rather than deleting it. The local process must remain running for its cancellation watchdog to operate.

## Runtime controls and cost

- One ephemeral Modal app, one GPU container, no warm pool, no deployed endpoint.
- Application retries are zero. Modal infrastructure failures can still reschedule work; this is not a mathematical cap on all charges.
- Function timeout: 900 seconds. Container startup timeout: 60 seconds. Imports, model download and model initialization occur inside the timed function body.
- Application stops starting new two-question batches after 840 seconds.
- The local watchdog requests call cancellation and container termination at its 900-second deadline, including time spent waiting locally. Cancellation is best effort and can take additional time.
- vLLM 0.13.0, huggingface-hub 0.36.0, BF16, context 8,192 tokens, at most two concurrent sequences, at most 2,048 generated tokens per question. Sampling: temperature 0.6, top-p 0.95, seed 42.
- Model downloads are ephemeral; no persistent model volume is created. A small named Modal Dict stores progress so completed batches can be recovered.

At the checked GPU price of $0.000694/second, 900 seconds of A100 80GB GPU time is approximately **$0.625**, plus CPU/RAM, startup, image/build, network and any other applicable charges. Execution timeouts are not exact invoice caps; use a Modal workspace budget for a financial limit. [Pricing](https://modal.com/pricing), [timeouts](https://modal.com/docs/guide/timeouts), [failure handling](https://modal.com/docs/guide/retries).

## Outputs and verification

The worker preserves original output, finish reason, token counts, teacher revision, sampling settings and runtime versions. It checkpoints after each two-question batch. Wrong answers are not silently retried.

Results are checked locally using the same numeric final-answer verifier as the ranking pipeline. The teacher must provide nonempty solution text and conclude with `#### <numeric answer>`. Wrong answers, missing markers and truncated outputs stay in raw results with rejection reasons. Matching a final answer does not prove all reasoning steps are valid.

Outputs under the pilot directory include `call.json`, `raw_checkpoint.json`, `teacher_results.jsonl`, `verified_teacher.jsonl` and `summary.json`. If execution fails, inspect `error.log` and any `partial_checkpoint.json`; the runner stops rather than starting another job.

After the pilot, review formatting, verification rate, latency and cost before scaling to a shared teacher pool. Re-run ranked/random selection on the same verified pool before fine-tuning. This pilot neither launches Granite training nor evaluates on held-out GSM8K test questions.

## Offline tests

From `granite_query`, using the isolated Modal environment:

```powershell
.\.venv-modal\Scripts\python.exe -B -m unittest cloud.test_pilot -v
```

The eight pilot tests use local fixtures and mocked remote handles. They exercise payload isolation, reproducibility, failure/truncation preservation, preflight gates, deadline cancellation and polling-versus-execution timeouts. They do not establish that the unexecuted cloud image will build or fit the model on the GPU; that is what the pilot must verify.
