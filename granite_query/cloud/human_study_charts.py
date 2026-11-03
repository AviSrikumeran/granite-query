"""Explicit standalone SVG export from the sanitized human-study report only.

Importing this module reads nothing and generates nothing. It is deliberately
not connected to a supervisor or report generator. Run this module explicitly
after all three200-question development results validate.
"""
from pathlib import Path
import json
import math
import os

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parents[1]/'docs/human-study-results.json'
OUTPUT = ROOT.parents[1]/'docs/figures/human-study-development.svg'
ORDER = ('baseline', 'random', 'skill')
LABELS = ('Untouched base', 'Random data', 'Skill and diversity')


def integer(value):
    return type(value) is int and value >= 0


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def chart_data(report):
    """Pure validation; pending, legacy64 and official-test rows are never drawn."""
    cohort = report.get('cohort', {})
    if (report.get('official_test_used') is not False or report.get('planned_jobs') != 3
            or cohort.get('development_count') != 200 or cohort.get('split') != 'train'
            or cohort.get('legacy64_included') is not False or cohort.get('legacy64_results_merged') is not False):
        raise ValueError('Require the independent200-question training-split development report')
    protocol = report.get('protocol', {})
    if (protocol.get('enable_thinking') is not False or protocol.get('max_new_tokens') != 512
            or not integer(protocol.get('seed'))):
        raise ValueError('Require the shared bounded nonthinking512 inference protocol')
    points = []
    for key, label in zip(ORDER, LABELS):
        job = report.get('jobs', {}).get(key, {})
        metrics = job.get('metrics') or {}
        if (job.get('status') != 'completed' or metrics.get('count') != 200
                or not integer(metrics.get('numeric_correct')) or metrics['numeric_correct'] > 200
                or not integer(metrics.get('truncated')) or metrics['truncated'] > 200
                or not integer(job.get('actual_supervised_tokens'))
                or not integer(job.get('actual_optimizer_updates'))):
            raise ValueError('All three complete validated outcomes and actual exposures are required')
        if key == 'baseline' and (job['actual_supervised_tokens'] or job['actual_optimizer_updates']):
            raise ValueError('Untouched base must have zero training exposure')
        accuracy = 100*metrics['numeric_correct']/200
        interval = job.get('question_wilson_95_interval_percent')
        if interval is not None and (not isinstance(interval, list) or len(interval) != 2
                or not all(finite(x) for x in interval) or not 0 <= interval[0] <= accuracy <= interval[1] <= 100):
            raise ValueError('Invalid reported Wilson interval')
        points.append({'selector': key, 'label': label, 'correct': metrics['numeric_correct'],
            'count': 200, 'accuracy': accuracy, 'interval': interval, 'truncated': metrics['truncated'],
            'tokens': job['actual_supervised_tokens'], 'updates': job['actual_optimizer_updates']})
    comparison = report.get('comparisons', {}).get('skill_vs_random') or {}
    stats = comparison.get('statistics')
    paired = None
    if comparison.get('status') == 'completed' and isinstance(stats, dict):
        interval = stats.get('paired_bootstrap_95_interval_pp')
        difference = stats.get('difference_percentage_points')
        if (stats.get('count') != 200 or not finite(difference) or not isinstance(interval, list)
                or len(interval) != 2 or not all(finite(x) for x in interval)
                or not -100 <= interval[0] <= difference <= interval[1] <= 100):
            raise ValueError('Invalid completed paired comparison')
        paired = {'difference': difference, 'interval': interval}
    return {'points': points, 'paired': paired, 'seed': report.get('protocol', {}).get('seed'),
        'max_output_tokens': report.get('protocol', {}).get('max_new_tokens')}


def generate():
    """The sole exporter: one fixed SVG path, no PNG or shared-report writes."""
    data = chart_data(json.loads(REPORT.read_text(encoding='utf-8-sig')))
    cache = ROOT/'runs/matplotlib_cache'
    cache.mkdir(parents=True, exist_ok=True)
    os.environ['MPLCONFIGDIR'] = str(cache)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype': 'none', 'svg.hashsalt': 'granite-human-study-development-v1',
        'font.family': 'DejaVu Sans', 'font.size': 11})
    bg, ink, muted = '#101311', '#e8ece6', '#a7b2a4'
    fig, ax = plt.subplots(figsize=(10, 6.7), facecolor=bg)
    ax.set_facecolor(bg)
    points = data['points']
    ax.bar(range(3), [p['accuracy'] for p in points], width=.55,
        color=['#9eaaa0', '#c5ed90', '#eab788'], zorder=3)
    for x, point in enumerate(points):
        interval = point['interval']
        if interval:
            ax.errorbar(x, point['accuracy'], yerr=[[point['accuracy']-interval[0]],
                [interval[1]-point['accuracy']]], fmt='none', ecolor=ink, capsize=6, linewidth=1.4, zorder=4)
        upper = interval[1] if interval else point['accuracy']
        ax.text(x, upper+2.1, f"{point['correct']}/200  ({point['accuracy']:.1f}%)",
            color=ink, ha='center', fontsize=11, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel('Numeric final-answer accuracy (%)', color=ink)
    ax.set_xticks(range(3), [f"{p['label']}\n{p['tokens']:,} actual training tokens\n{p['truncated']} truncated answers" for p in points])
    ax.tick_params(colors=muted, axis='both', length=0, pad=10)
    ax.yaxis.grid(True, color='#343e34', linewidth=.7)
    ax.set_axisbelow(True)
    for spine in ax.spines.values(): spine.set_visible(False)
    fig.suptitle('Granite on the same 200 development questions', x=.12, y=.97,
        ha='left', color=ink, fontsize=18, fontweight='bold')
    fig.text(.12, .91, f"Separate human-reference study · one training seed ({data['seed']}) · non-thinking {data['max_output_tokens']}-token cap",
        color=muted, fontsize=10)
    paired = data['paired']
    text = (f"Skill minus random: {paired['difference']:+.2f} percentage points; paired 95% interval "
        f"[{paired['interval'][0]:+.2f}, {paired['interval'][1]:+.2f}].") if paired else 'Skill-versus-random paired statistics are unavailable.'
    fig.text(.12, .14, text, color=ink, fontsize=10)
    fig.text(.12, .085, 'Whiskers, where available: reported 95% Wilson intervals. Paired interval: question bootstrap.\n'
        'Intervals do not cover training-seed variation. Development only; official final test not evaluated.',
        color=muted, fontsize=9, linespacing=1.65)
    fig.subplots_adjust(left=.12, right=.97, top=.84, bottom=.32)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, format='svg', facecolor=bg, metadata={'Date': None,
        'Title': 'Separate200-question human-reference development comparison',
        'Description': 'Completed-only untouched Granite, random-data and skill-selection outcomes. '
            'Zero-based accuracy axis; one training seed; no official-test or robust improvement claim.'})
    plt.close(fig)
    return {'output': str(OUTPUT), 'completed_jobs': 3, 'development_count': 200,
        'official_test_used': False, 'other_figures_generated': False}


if __name__ == '__main__':
    print(json.dumps(generate()))
