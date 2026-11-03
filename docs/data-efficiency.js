// Current multi-source study only. Earlier GSM-only results stay in results.js.
(() => {
  const get = id => document.getElementById(id);
  const integer = value => Number.isInteger(value) && value >= 0;
  const number = value => Number.isFinite(value) ? value.toLocaleString() : 'not reported';
  const labels = {random: 'Random', skill: 'Skill and diversity', gradient: 'Model-gradient selection'};
  let loaded = false;
  const deferred = arm => arm.budget_role === 'near_all_data_reference'
    && arm.token_budget === 131072 && arm.status === 'prepared';

  function counts(arms) {
    const result = {completed: 0, running: 0, pending: 0, deferred: 0, issues: 0};
    for (const arm of arms) {
      if (arm.status === 'completed' && arm.metrics && integer(arm.metrics.numeric_correct) && arm.metrics.count === 64) result.completed++;
      else if (arm.status === 'running') result.running++;
      else if (['failed', 'invalid_result', 'ambiguous_launch'].includes(arm.status)) result.issues++;
      else if (deferred(arm)) result.deferred++;
      else result.pending++;
    }
    return result;
  }

  function render(data) {
    if (!data || !Array.isArray(data.budgets) || !integer(data.planned_arms)) throw Error('Invalid study snapshot');
    const arms = [], budgets = [], pairs = [];
    for (const budget of data.budgets) {
      const records = [];
      for (const seed of budget.seeds || []) {
        for (const selector of ['random', 'skill', 'gradient']) {
          const arm = seed.arms?.[selector];
          if (arm) {
            const record = {...arm, seed: seed.seed, selector, token_budget: budget.token_budget, budget_role: budget.budget_role};
            arms.push(record); records.push(record);
          }
        }
        if (seed.comparisons?.skill_vs_random?.count === 64 || seed.comparisons?.gradient_vs_random?.count === 64) pairs.push(seed);
      }
      budgets.push({budget, records, counts: counts(records)});
    }
    const status = counts(arms), completed = arms.filter(arm => arm.status === 'completed' && arm.metrics?.count === 64 && integer(arm.metrics.numeric_correct));
    const primary = arms.filter(arm => arm.budget_role !== 'near_all_data_reference'), primaryStatus = counts(primary);
    get('efficiency-panel').hidden = false;
    get('efficiency-completed').textContent = `${primaryStatus.completed} / ${primary.length}`;
    get('efficiency-running').textContent = String(status.running);
    get('efficiency-pending').textContent = String(status.pending);
    get('efficiency-deferred').textContent = String(status.deferred);
    get('efficiency-scope').textContent = primaryStatus.completed === primary.length
      ? 'Multi-source study · reviewed primary arms complete' : 'Multi-source study · primary evaluations in progress';
    get('efficiency-issues').hidden = status.issues === 0;
    get('efficiency-issues').textContent = status.issues ? `${status.issues} run(s) need failure or launch reconciliation. They have no assigned accuracy.` : '';
    const pool = data.cohort?.available_supervised_tokens;
    get('efficiency-summary').textContent = `${primaryStatus.completed}/${primary.length} reviewed primary arms are complete; ${data.planned_arms} prepared plans are retained in total. `
      + `${status.deferred} prepared 131,072-token reference plans are deferred, with limited selection contrast; they are not imminent queued work. `
      + `Random, skill and gradient use the same multi-source math pool and two seeds.${Number.isFinite(pool) ? ' Available answer tokens: ' + number(pool) + '.' : ''} `
      + 'Each comparison uses the same 64 monitoring questions, separately from the human study’s 200 questions. This is adaptive development evidence, not final-test accuracy. Prepared plans do not establish funding or launch readiness.';
    const active = arms.filter(arm => arm.status === 'running');
    const describe = arm => `${labels[arm.selector]} · seed ${arm.seed} · ${number(arm.token_budget)} training tokens`;
    get('efficiency-action').textContent = active.length
      ? 'Running now: ' + active.map(describe).join('; ') + '. Scores appear only after a full evaluation is saved.'
      : primaryStatus.completed === primary.length && status.pending === 0 && status.issues === 0
        ? `All ${primary.length} reviewed primary training evaluations are complete. ${status.deferred} larger reference plans remain deferred. The independent human-reference study is shown above; final evaluation and serving require separate review.`
      : status.completed === data.planned_arms
        ? 'All planned training evaluations are complete. Final checkpoint evaluation and model serving remain separate stages.'
        : 'Awaiting review or dispatch: ' + (arms.find(arm => !deferred(arm) && ['prepared', 'queued', 'not_prepared'].includes(arm.status)) ? describe(arms.find(arm => !deferred(arm) && ['prepared', 'queued', 'not_prepared'].includes(arm.status))) : 'review the incomplete attempts') + '. Preparation alone does not establish funding readiness.';
    get('efficiency-interpretation').textContent = pairs.length
      ? `${pairs.length} budget/seed comparison(s) now include a completed selected arm and its random control. Use the paired report to assess corrected answers, regressions and uncertainty; a higher individual score alone does not establish robust improvement.`
      : 'No matched selector comparison is complete yet. A completed random arm alone cannot show that skill or gradient selection adds value.';

    const body = get('efficiency-rows'); body.replaceChildren();
    for (const arm of completed) {
      const row = document.createElement('tr');
      const values = [number(arm.token_budget), String(arm.seed), labels[arm.selector],
        `${arm.metrics.numeric_correct}/64 (${(100 * arm.metrics.numeric_correct / 64).toFixed(2)}%)`,
        number(arm.metrics.truncated), number(arm.actual_supervised_tokens), number(arm.actual_optimizer_updates)];
      for (const value of values) { const cell = document.createElement('td'); cell.textContent = value; row.append(cell); }
      body.append(row);
    }
    get('efficiency-table-wrap').hidden = completed.length === 0;
    get('efficiency-empty').hidden = completed.length > 0;
    get('efficiency-empty').textContent = 'No new-cohort training evaluation has completed yet. Pending runs are not scored as zero.';
    const imagePath = 'figures/data-efficiency-development.svg';
    const hasFigure = completed.length > 0 && Array.isArray(data.points) && data.points.length > 0 && data.figures?.includes(imagePath);
    get('efficiency-figure-wrap').hidden = !hasFigure;
    if (hasFigure) get('efficiency-image').src = imagePath + '?t=' + Date.now();
    else get('efficiency-image').removeAttribute('src');

    const budgetList = get('efficiency-budgets'); budgetList.replaceChildren();
    for (const entry of budgets) {
      const {budget, counts: c} = entry, item = document.createElement('li');
      const role = budget.budget_role === 'near_all_data_reference' ? ' Near-all-data reference: limited selection contrast.' : '';
      item.textContent = `${number(budget.token_budget)} tokens: ${c.completed}/${budget.planned_arms} complete, ${c.running} running, ${c.pending} pending, ${c.deferred} deferred.${role}`;
      budgetList.append(item);
    }
    const base = data.batched_base_control;
    get('efficiency-base').textContent = base?.status === 'completed' && base.metrics
      ? `Matched untouched-base control: ${base.metrics.numeric_correct}/64, batch 8, non-thinking with 512 output tokens, zero training tokens or updates.`
      : 'Matched untouched-base control: ' + (base?.status?.replaceAll('_', ' ') || 'awaiting a published result') + '. No baseline accuracy is assumed.';
    const overhead = data.selector_overhead || {}, seconds = overhead.feature_worker_elapsed_seconds;
    const minutes = Number.isFinite(seconds) ? (seconds / 60).toFixed(1) + ' worker minutes' : 'worker time not reported';
    get('efficiency-overhead').textContent = `Gradient-selection setup is extra: ${number(overhead.selector_warmup_supervised_tokens)} unique committed warmup tokens; ${minutes} across ${number(overhead.attempt_count)} attempt(s), including incomplete predecessors. This is outside each arm's training-token budget and is not an invoice or an equal-compute claim.`;
    get('efficiency-updated').textContent = 'Current-study evidence: ' + new Date(data.generated_at_utc).toLocaleString() + '. This is a published snapshot.';
    get('efficiency-fetch').textContent = '';
    loaded = true;
    return {counts: status, completedRows: completed.length, matchedComparisons: pairs.length, figureShown: hasFigure};
  }

  async function refresh() {
    try {
      const response = await fetch('data-efficiency-results.json?t=' + Date.now(), {cache: 'no-store'});
      if (!response.ok) throw Error('Snapshot unavailable');
      render(await response.json());
    } catch (error) {
      get('efficiency-fetch').textContent = loaded
        ? 'Could not refresh the current-study snapshot; the last loaded evidence remains visible.'
        : 'Current-study snapshot is not available yet. Results below belong to the earlier GSM-only study.';
    }
  }
  globalThis.GraniteDataEfficiency = {render, counts};
  refresh(); setInterval(refresh, 60000);
})();
