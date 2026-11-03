"""Paired same-question comparisons; public exports contain aggregates only."""
import json
import math
from pathlib import Path
import random
from cloud.comparison_metrics import score, summarize

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]


def paired(reference, candidate, *, seed=20261103, resamples=20000):
    def index(rows):
        indexed = {r['id']: r for r in rows}
        if len(indexed) != len(rows):
            raise ValueError('Duplicate question IDs')
        return indexed
    left, right = index(reference), index(candidate)
    if not left or left.keys() != right.keys():
        raise ValueError('Paired comparisons require identical question IDs')
    differences = []
    corrected = regressed = 0
    for key in sorted(left):
        if str(left[key]['gold_answer']) != str(right[key]['gold_answer']):
            raise ValueError('Mismatched reference answers')
        old, new = int(score(left[key])['correct']), int(score(right[key])['correct'])
        corrected += new > old
        regressed += old > new
        differences.append(new - old)
    n = len(differences)
    rng = random.Random(seed)
    draws = sorted(100 * sum(rng.choices(differences, k=n)) / n for _ in range(resamples))
    discordant = corrected + regressed
    p = min(1.0, 2 * sum(math.comb(discordant, k) for k in range(min(corrected, regressed)+1)) / 2**discordant) if discordant else 1.0
    return {'count': n, 'corrected': corrected, 'regressed': regressed,
            'difference_percentage_points': 100*sum(differences)/n,
            'paired_bootstrap_95_interval_pp': [draws[int(.025*(resamples-1))], draws[int(.975*(resamples-1))]],
            'mcnemar_exact_two_sided_p': p, 'bootstrap_seed': seed,
            'bootstrap_resamples': resamples,
            'limitations': 'Exploratory development comparison, single training seed, no multiplicity correction. Bootstrap covers question sampling, not training-seed variation. Numeric final-answer verification does not verify reasoning steps.'}


def build():
    folder = ROOT/'runs/matched_eval64_v1'
    result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    evaluations = result['evaluations']
    expected = set(json.loads((folder/'plan.json').read_text())['development_ids'])
    if len(expected) != 64 or any({r['id'] for r in rows} != expected for rows in evaluations.values()):
        raise ValueError('Expected frozen64 development questions')
    full = ROOT/'runs/granite_full120_v1/result.json'
    if full.exists():
        extra = json.loads(full.read_text(encoding='utf-8'))
        if set(extra['plan']['development_ids']) != expected:
            raise ValueError('Full120 evaluation question mismatch')
        evaluations.update(extra['evaluations'])
    public = {'evaluation_set':'frozen64 development monitoring questions', 'official_test_used':False,
              'metrics':{name:summarize(rows) for name, rows in evaluations.items()},
              'versus_original':{name:paired(evaluations['baseline'], rows)
                for name, rows in evaluations.items() if name != 'baseline'},
              'ranked_vs_random':paired(evaluations['random32'],evaluations['ranked32'])}
    (WORKSPACE/'docs/paired-results.json').write_text(json.dumps(public,indent=2)+'\n',encoding='utf-8')
    lines=['# Shared64 development comparison','','All checkpoints use identical64 questions and a512-token output cap. Official test data remains unused. DeepSeek separately scored63/64 using thinking mode and a4096-token cap.','',
           '| Checkpoint | Correct | Truncated | Corrected vs original | Regressed vs original | Accuracy change |',
           '|---|---:|---:|---:|---:|---:|']
    for name, m in public['metrics'].items():
        delta=public['versus_original'].get(name,{})
        lines.append(f"| {name} | {m['numeric_correct']}/64 | {m['truncated']} | {delta.get('corrected','—')} | {delta.get('regressed','—')} | {delta.get('difference_percentage_points',0):+.2f} pp |")
    lines += ['','## Paired uncertainty','']
    for name, d in public['versus_original'].items():
        low, high=d['paired_bootstrap_95_interval_pp']
        lines.append(f"- {name}: paired question-bootstrap95% interval [{low:+.2f},{high:+.2f}] percentage points; exact two-sided McNemar p={d['mcnemar_exact_two_sided_p']:.4f}.")
    lines += ['','Exploratory development results, one training seed and no multiplicity correction. Intervals cover question sampling, not training-seed variation. Current32-example arms both regressed from the original; neither establishes a selection advantage. Equal accuracy does not establish equivalent behavior. More-data training, new token-matched controls and a frozen final evaluation are distinct stages.','',
              'The original64 attempt timed out; its completed generations were retained and a separately reserved resume filled only missing outcomes. Different question sets must not be joined into an improvement curve.','']
    (WORKSPACE/'progress/BENCHMARK64.md').write_text('\n'.join(lines),encoding='utf-8')
    return public


if __name__=='__main__':
    print(json.dumps(build()['versus_original']))
