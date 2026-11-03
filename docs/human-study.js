// The separate200-question human-reference study. Never combine legacy64 rows.
(() => {
  const get = id => document.getElementById(id);
  const integer = value => Number.isInteger(value) && value >= 0;
  const number = value => Number.isFinite(value) ? value.toLocaleString() : 'not reported';
  const names = {baseline: 'Untouched Granite', random: 'Random data', skill: 'Skill and diversity'};
  const comparisons = {
    skill_vs_random: ['skill', 'random', 'Skill minus random'],
    random_vs_baseline: ['random', 'baseline', 'Random minus untouched base'],
    skill_vs_baseline: ['skill', 'baseline', 'Skill minus untouched base']
  };
  let loaded = false;

  function complete(job) {
    const m = job?.metrics;
    return job?.status === 'completed' && m?.count === 200 && integer(m.numeric_correct)
      && m.numeric_correct <= 200 && integer(m.truncated) && m.truncated <= 200
      && integer(job.actual_supervised_tokens) && integer(job.actual_optimizer_updates);
  }

  function paired(data, key) {
    const [candidate, reference] = comparisons[key], value = data.comparisons?.[key];
    const stats = value?.statistics, interval = stats?.paired_bootstrap_95_interval_pp;
    return value?.status === 'completed' && complete(data.jobs[candidate]) && complete(data.jobs[reference])
      && stats?.count === 200 && Number.isFinite(stats.difference_percentage_points)
      && Array.isArray(interval) && interval.length === 2 && interval.every(Number.isFinite)
      && integer(stats.corrected) && integer(stats.regressed) ? stats : null;
  }

  function status(job) {
    if (complete(job)) return 'Completed · validated 200 outcomes';
    if (job?.status === 'completed') return 'Result requires review';
    if (job?.status === 'running') return 'Running · last observed';
    if (job?.status === 'queued') return 'Queued · dispatch unconfirmed';
    return job?.status?.replaceAll('_', ' ') || 'Not reported';
  }

  function render(data) {
    if (!data || data.official_test_used !== false || data.cohort?.development_count !== 200
        || data.cohort?.split !== 'train' || data.cohort?.legacy64_included !== false
        || data.cohort?.legacy64_results_merged !== false || !data.jobs || data.planned_jobs !== 3) {
      throw Error('Invalid independent human-study snapshot');
    }
    const keys = ['baseline', 'random', 'skill'];
    const completed = keys.filter(key => complete(data.jobs[key])).length;
    get('human-summary').textContent = `${completed}/3 evaluations complete on the same 200 development questions. `
      + `${number(data.cohort.candidate_examples)} eligible DeepSeek solutions form this separate human-reference training pool. `
      + 'Status reflects validated local receipts in the published snapshot, not a live provider or funding check.';
    const body = get('human-rows'); body.replaceChildren();
    for (const key of keys) {
      const job = data.jobs[key], valid = complete(job), row = document.createElement('tr');
      const heading = document.createElement('th'); heading.scope = 'row'; heading.textContent = names[key]; row.append(heading);
      const values = [status(job), valid ? `${job.metrics.numeric_correct}/200 (${(job.metrics.numeric_correct/2).toFixed(1)}%)` : 'Unavailable',
        valid ? number(job.metrics.truncated) : 'Unavailable', valid ? number(job.actual_supervised_tokens) : 'Unavailable',
        valid ? number(job.actual_optimizer_updates) : 'Unavailable'];
      values.forEach((value, index) => {
        const cell = document.createElement('td'); cell.textContent = value;
        if (index === 0) cell.className = 'human-status';
        row.append(cell);
      });
      body.append(row);
    }
    const random = data.jobs.random, skill = data.jobs.skill;
    get('human-plan').textContent = 'Planned training exposure: random '
      + `${number(random?.planned_supervised_tokens)} tokens / ${number(random?.planned_optimizer_updates)} updates; skill `
      + `${number(skill?.planned_supervised_tokens)} tokens / ${number(skill?.planned_optimizer_updates)} updates. `
      + 'Plans are not actual completed exposure. The untouched baseline performs no training.';
    const list = get('human-comparisons'); list.replaceChildren();
    for (const key of Object.keys(comparisons)) {
      const stats = paired(data, key);
      if (!stats) continue;
      const item = document.createElement('li'), interval = stats.paired_bootstrap_95_interval_pp;
      item.textContent = `${comparisons[key][2]}: ${stats.difference_percentage_points.toFixed(2)} percentage points `
        + `(paired question bootstrap 95% interval ${interval[0].toFixed(2)} to ${interval[1].toFixed(2)}); `
        + `${stats.corrected} corrected, ${stats.regressed} regressed.`;
      list.append(item);
    }
    list.hidden = list.children.length === 0;
    const selection = paired(data, 'skill_vs_random');
    get('human-interpretation').textContent = selection
      ? (selection.difference_percentage_points > 0
        ? 'Skill has higher observed accuracy than random in this one training seed. Assess the paired interval and regressions; this does not establish a robust selection benefit or final-test gain.'
        : 'Skill does not outscore random in this one training seed. The paired comparison, including uncertainty and regressions, is now available.')
        + ' Question-bootstrap uncertainty does not cover training-seed variation.'
      : list.children.length
        ? 'A completed training arm can now be compared with the untouched base. The skill-versus-random interpretation remains unavailable until that paired report exists.'
        : 'Paired results are unavailable until both matching evaluations and their comparison are validated. The baseline score alone cannot show a training gain or a selection benefit.';
    const stamp = Date.parse(data.generated_at_utc);
    get('human-updated').textContent = 'Human-study evidence: ' + (Number.isFinite(stamp) ? new Date(stamp).toLocaleString() : 'timestamp not reported')
      + '. Refreshes from the published snapshot every 60 seconds.';
    get('human-fetch').textContent = ''; loaded = true;
    return {completed, displayedRows: keys.length, pairedComparisons: list.children.length, selectionComparisonAvailable: Boolean(selection)};
  }

  async function refresh() {
    try {
      const response = await fetch('human-study-results.json?t=' + Date.now(), {cache: 'no-store'});
      if (!response.ok) throw Error('Snapshot unavailable');
      render(await response.json());
    } catch (error) {
      get('human-fetch').textContent = loaded
        ? 'Could not refresh the human-study snapshot; the last loaded evidence remains visible and may be stale.'
        : 'Human-study results are not available yet. Pending evaluations have no assigned accuracy.';
    }
  }
  globalThis.GraniteHumanStudy = {render, complete};
  refresh(); setInterval(refresh, 60000);
})();
