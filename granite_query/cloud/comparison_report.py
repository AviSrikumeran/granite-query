"""Generate public aggregate results without copying private question/response logs."""
import json
from pathlib import Path
from comparison_metrics import score, summarize

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'runs/ranked_random_32_seed42_v1'
WORKSPACE=ROOT.parents[1]

def build_report():
    result=json.loads((RUN/'result.json').read_text())
    rows={'baseline':result['baseline'],**{name:a['evaluation'] for name,a in result['arms'].items()}}
    metrics={name:summarize(items) for name,items in rows.items()}
    for name in ('ranked','random'):
        metrics[name]['supervised_tokens']=result['arms'][name]['supervised_tokens']
    outcomes={name:{r['id']:score(r)['correct'] for r in items} for name,items in rows.items()}
    ids=set(outcomes['ranked'])
    if any(set(o)!=ids for o in outcomes.values()):
        raise ValueError('Evaluation question sets do not match')
    paired={
        'ranked_only_correct':sum(outcomes['ranked'][i] and not outcomes['random'][i] for i in ids),
        'random_only_correct':sum(outcomes['random'][i] and not outcomes['ranked'][i] for i in ids),
        'both_correct':sum(outcomes['ranked'][i] and outcomes['random'][i] for i in ids),
        'both_incorrect':sum(not outcomes['ranked'][i] and not outcomes['random'][i] for i in ids)}
    summary={'run_id':result['run_id'],'count':len(ids),'metrics':metrics,'paired':paired,
        'ranked_minus_random_correct':metrics['ranked']['numeric_correct']-metrics['random']['numeric_correct'],
        'elapsed_seconds':result['elapsed_seconds'],'official_test_used':False,
        'limitations':['One seed and 16 training-split development questions.',
            'Equal examples and updates, not equal supervised training tokens.',
            'Selection and training order are entangled.',
            'Development question text contributed to the fixed BM25 index corpus statistics; development answers and outcomes were not used in ranking.',
            'Numeric extraction is heuristic and does not grade explanation quality.',
            'Latency is exploratory: sequential evaluation without repeated randomized timing.']}
    table=['| Model | Numeric matches | Strict format | Truncated | Training tokens | Mean response seconds |',
           '|---|---:|---:|---:|---:|---:|']
    for name in ('baseline','ranked','random'):
        m=metrics[name]
        table.append(f"| {name.title()} | {m['numeric_correct']}/{m['count']} ({100*m['numeric_correct']/m['count']:.2f}%) | {m['strict_format_correct']}/{m['count']} | {m['truncated']} | {m.get('supervised_tokens','—')} | {m['latency_seconds_total']/m['count']:.2f} |")
    delta=summary['ranked_minus_random_correct']
    outcome=('Ranked and random selection tied on this development set.' if delta==0 else
             ('Ranked selection scored higher in this pilot.' if delta>0 else 'Random selection scored higher in this pilot.'))
    token_difference=100*(metrics['ranked']['supervised_tokens']/metrics['random']['supervised_tokens']-1)
    lines=['# First ranked versus random results','',
        'This is a single-seed development pilot, not a final-test benchmark. Each arm trained on 32 examples from the same 120 verified teacher candidates. Both were evaluated on the same 16 separate training-split development questions.','',
        *table,'',f'Ranked minus random: {delta:+d} correct answers, or {100*delta/len(ids):+.2f} percentage points. One question changes the percentage by 6.25 points.','',
        '## Paired comparison','',f"Ranked only correct: {paired['ranked_only_correct']}; random only correct: {paired['random_only_correct']}; both correct: {paired['both_correct']}; both incorrect: {paired['both_incorrect']}.",'',
        '## What this means','',
        outcome+f" Ranked used {token_difference:.2f}% more supervised training tokens than random. This run therefore provides no demonstrated fixed-token data-efficiency advantage for ranking.",'',
        'Compare each trained adapter with the original model to assess the observed effect of this small fine-tuning run. Compare ranked with random to assess the observed selection strategy difference. Neither comparison establishes a robust causal effect from this one pilot.','',
        '## Manual answer audit','',
        'All 48 outputs were manually reviewed: each has a plain numeric final-answer marker, with no truncation. Strict-format and numerical scoring agree. Ranked training fixes one rate-inversion error but introduces one cost-accounting error, leaving the total unchanged. Random correctness matches the original model question-for-question. Two errors persist in both trained arms; one benchmark item has ambiguous wording relative to its reference interpretation. Its frozen score is retained without post-hoc exclusion.','',
        '## Limitations','',*['- '+x for x in summary['limitations']],'',
        'The numerical scorer uses the last numeric value after the final answer marker, or on the final nonempty line when no marker is present. Truncated generations are never counted correct. Audit disagreements against the preserved original outputs before interpreting a small score difference.','',
        '## Next confirmatory experiment','',
        'Use multiple selection/training seeds; fit relevance statistics without the evaluation questions; shuffle both arms using the same order policy; match supervised-token budgets; and keep a final test set untouched until the method is frozen. No additional paid run is automatically launched.','']
    for directory,name in [(WORKSPACE/'progress','RESULTS.md'),(WORKSPACE/'docs','results.md')]:
        (directory/name).write_text('\n'.join(lines),encoding='utf-8')
    (RUN/'public_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

if __name__=='__main__':
    print(json.dumps(build_report()))
