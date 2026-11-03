# Full teacher to Granite improvement cycle

The project is not complete merely because a ranked/random pilot finished.

1. Matched16 bridge: evaluate DeepSeek on exactly the existing16 development questions, with the same user prompt. Preserve all outcomes. Result: DeepSeek15/16 versus Granite13/16. DeepSeek thinking/max4096 and Granite non-thinking/max512 differ; timing and token scopes also differ.
2. Freeze a new64-question monitoring set from official GSM8K training data, excluding the128 ranking probes,16 pilot prompts,128 teacher candidates, and previous16 development questions. Never include monitoring answers as training examples. Keep official test untouched.
3. Evaluate DeepSeek, untouched Granite, and both saved32-example adapters on those exact64 questions. Record failures/truncation and configuration differences. Use a bounded resume if the initial900-second GPU task cannot finish all192 generations; completed outputs are preserved rather than rerun.
4. Train a fresh pinned Granite4.2 3B LoRA adapter on all120 verified teacher examples, shuffled with seed42. Save/reload it and evaluate the same64 questions. This measures the effect of more training data, not a ranking advantage.
5. Update measured-only accuracy figures, teacher/student gap, output-length summaries, and same-set learning history. Never join scores across different evaluation sets or invent pending improvement points. Independent final-test evaluation follows only after choosing a checkpoint.
6. If the larger round still does not improve accuracy, the supervisor may execute at most one additional preplanned skill-targeted round within remaining budgets, with new training examples and a matched random/token-budget control. It must record the plan before evaluating, preserve broad coverage, and avoid copying monitoring answers into training. Failure to improve remains a result, not permission to manufacture success.

Budgets remain $30 Modal and $20 DeepSeek total. Current new reservations: bridge16 $0.50 (now measured below$0.04); DeepSeek64 $2; GPU64 $3; full120 GPU $3. At most one extra$3 evaluation resume is permitted if needed. Additional targeted-round ceilings are$3 DeepSeek and$6 Modal only if remaining service budgets permit. No perpetual GPU endpoint is deployed.

All64 monitoring questions are development data. The older BM25 index contained their question texts in its corpus statistics, though not their answers/outcomes; this limitation remains disclosed. Subsequent adaptation must be described as development-guided, not held-out final-test evidence.
