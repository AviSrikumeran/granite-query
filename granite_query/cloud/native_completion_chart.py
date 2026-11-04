"""Plot two validated, explicitly different Granite inference conditions."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build():
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'granite_query/cloud/runs/supervisor/mpl-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    human = json.loads((ROOT / 'docs/human-study-results.json').read_text(encoding='utf-8'))
    native = json.loads((ROOT / 'progress/NATIVE_REASONING_CONFIG_RECOVERY.json').read_text(encoding='utf-8'))
    old = human['jobs']['baseline']; new = native['jobs'][0]
    if old['status'] != 'completed' or new['status'] != 'completed':
        raise ValueError('Both actual baselines must validate before plotting')
    metrics = [old['metrics'], new['metrics']]
    if any(row['count'] != 200 for row in metrics):
        raise ValueError('Require the same fixed 200-question development denominator')
    correct = [row['numeric_correct'] for row in metrics]
    capped = [row['truncated'] for row in metrics]
    incorrect = [200 - good - cap for good, cap in zip(correct, capped)]
    if min(incorrect) < 0: raise ValueError('Outcome categories overlap')
    labels = ['Nonthinking\n512-token cap', 'Native thinking\n1,024-token cap']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'svg.hashsalt': 'granite-completion-v1'})
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 5.6), gridspec_kw={'width_ratios': [1.35, 1]})
    fig.patch.set_facecolor('#f7f9fc')
    for ax in axes:
        ax.set_facecolor('#f7f9fc')
        ax.spines[['top', 'right']].set_visible(False)
        ax.set_axisbelow(True); ax.grid(axis='y', alpha=.16)
    axes[0].bar(labels, correct, color='#19765a', label='Correct, completed')
    axes[0].bar(labels, incorrect, bottom=correct, color='#94a3b8', label='Incorrect, completed')
    axes[0].bar(labels, capped, bottom=[a+b for a,b in zip(correct, incorrect)], color='#d68a28', label='Truncated (failure)')
    for index, (good, cap) in enumerate(zip(correct, capped)):
        axes[0].text(index, good / 2, f'{good}/200\n{good/2:.1f}% correct', ha='center', va='center', color='white', weight='bold')
        axes[0].text(index, 203, f'{cap} truncated', ha='center', color='#815019', fontsize=10)
    axes[0].set_ylabel('Questions'); axes[0].set_ylim(0, 219)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='lower left', bbox_to_anchor=(.07, .12), ncol=3, frameon=False, fontsize=9)
    token_counts = [row['generated_tokens'] for row in metrics]
    axes[1].bar(labels, [n/1000 for n in token_counts], color=['#456b9a', '#7198bf'])
    for index, (count, row) in enumerate(zip(token_counts, metrics)):
        axes[1].text(index, count/1000 + 4, f'{count:,} tokens\n{row["latency_seconds_total"]:.1f}s generation', ha='center', fontsize=9)
    axes[1].set_ylabel('Generated tokens (thousands)'); axes[1].set_ylim(0, max(token_counts)/1000*1.25)
    fig.suptitle('Completion limits in two Granite inference conditions', x=.07, ha='left', fontsize=16, weight='bold')
    fig.text(.07, .89, 'Same 200 TRAIN-development questions; untouched pinned Granite 4.2 3B; batch 8.', fontsize=10)
    fig.text(.07, .045, 'Different thinking modes and output caps. This is not a training improvement curve.\nAll truncated cases stay in the denominator as failures; batched GPU timing is not API latency.', fontsize=9, color='#42526a')
    fig.subplots_adjust(left=.08, right=.98, top=.81, bottom=.28, wspace=.36)
    target = ROOT / 'docs/figures/native-completion-budget.svg'; target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, metadata={'Date': None})
    preview = ROOT / 'granite_query/cloud/runs/supervisor/native-completion-budget.png'
    fig.savefig(preview, dpi=150); plt.close(fig)
    return target, preview


if __name__ == '__main__':
    print('\n'.join(str(path) for path in build()))
