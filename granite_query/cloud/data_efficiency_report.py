"""Aggregate-only report for the NEW matched random/skill/gradient budget grid.

Reads frozen development-study artifacts, never test data or model weights. A
pending/failed/invalid arm contributes no accuracy point. The earlier four32k
arms remain a separate historical study. No publishing or paid work occurs.
"""
import argparse
import ast
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent))
from cloud import data_efficiency_control as control
from cloud.comparison_metrics import summarize
from cloud.evaluation_stats import paired

SELECTORS=('random','skill','gradient')
PAIRINGS=(('skill','random'),('gradient','random'),('gradient','skill'))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_child(parent,relative):
    result=(parent/relative).resolve()
    if not result.is_relative_to(parent.resolve()):
        raise ValueError('Grid artifact path escapes its frozen study')
    return result


def wilson(correct,count):
    z=1.959963984540054; p=correct/count; d=1+z*z/count
    center=(p+z*z/(2*count))/d
    half=z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/d
    return [100*max(0,center-half),100*min(1,center+half)]


def baseline_context(folder,*,expected_development_sha256=None,expected_ids=None,expected_gold=None,expected_prompts=None,source_root=ROOT):
    """Validate the NEW zero-training batch8 base control; never use old58/64."""
    folder,source_root=Path(folder),Path(source_root)
    public={'status':'not_prepared','training_performed':False,
        'note':'The earlier serial58/64 result is separate history and is not substituted for this batch8 control.'}
    if not (folder/'plan.json').exists():
        return public,None
    try:
        plan=read(folder/'plan.json');data=read(folder/'input.json')
        fixed=dict(mode='evaluate_saved',model=control.skill.MODEL,revision=control.skill.REVISION,
            evaluation_batch_size=8,max_new_tokens=512,context_limit=2048,enable_thinking=False,
            do_sample=False,evaluation_kind='development',checkpoint_name='baseline',training_performed=False)
        if any(plan.get(key)!=value for key,value in fixed.items()) or 'adapter_from' not in plan or plan['adapter_from'] is not None:
            raise ValueError('Base control must not train or load an adapter')
        protocol={key:value for key,value in plan.items() if key not in ('run_id','protocol_hash','resume_from')}
        if control.digest(protocol)!=plan.get('protocol_hash') or file_hash(folder/'input.json')!=plan.get('input_sha256'):
            raise ValueError('Frozen base-control input/protocol changed')
        source=plan.get('source_code_sha256',{})
        if any(source.get(name)!=file_hash(source_root/name) for name in ('modal_valuation.py','valuation_contract.py')):
            raise ValueError('Base-control worker or label implementation changed')
        tree=ast.parse((source_root/'modal_valuation.py').read_text(encoding='utf-8-sig'))
        prefix=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
            and any(isinstance(target,ast.Name) and target.id=='PREFIX' for target in node.targets))
        if prefix!=control.skill.PREFIX:
            raise ValueError('Base-control user prompt differs')
        rows=data.get('development',[]);frozen={r['id']:r for r in rows}
        ids=plan.get('development_ids',[])
        if len(rows)!=64 or len(frozen)!=64 or [r['id'] for r in rows]!=ids:
            raise ValueError('Base control requires the exact64 frozen development rows')
        if expected_development_sha256 is not None and plan.get('development_source_sha256')!=expected_development_sha256:
            raise ValueError('Base control uses different development provenance')
        if expected_ids is not None and set(ids)!=set(expected_ids):
            raise ValueError('Base control question identities differ')
        if expected_gold is not None and any(str(row['gold_answer'])!=str(expected_gold[row['id']]) for row in rows):
            raise ValueError('Base-control references differ')
        if expected_prompts is not None and any(row['prompt']!=expected_prompts[row['id']] for row in rows):
            raise ValueError('Base-control question text differs')
        public.update(status='prepared',protocol={k:plan[k] for k in fixed},
                      worker_source_sha256=source['modal_valuation.py'],development_source_sha256=plan.get('development_source_sha256'))
    except (KeyError,TypeError,ValueError,OSError,StopIteration):
        public.update(status='invalid_plan',detail='The batch8 base control failed pinned-model, zero-training, prompt-source or question checks.')
        return public,None
    launch=read(folder/'launch.json') if (folder/'launch.json').exists() else {}
    status=read(folder/'remote_status.json') if (folder/'remote_status.json').exists() else {}
    result=read(folder/'result.json') if (folder/'result.json').exists() else {}
    if result.get('stage')!='completed':
        public['status']=('failed' if status.get('stage')=='failed' else 'running' if launch.get('call_id')
                          else 'ambiguous_launch' if launch else 'prepared')
        return public,None
    try:
        actual=result.get('plan',{})
        if (result.get('supervised_tokens')!=0 or result.get('optimizer_updates')!=0
                or result.get('arm')!='evaluation_only' or result.get('held_out_test_used') is not False
                or any(actual.get(k)!=v for k,v in plan.items() if k not in ('run_id','resume_from'))
                or set(result.get('evaluations',{}))!={'baseline'}):
            raise ValueError('A base-control result claims training or a different checkpoint')
        evaluated=result['evaluations']['baseline']
        if len(evaluated)!=64 or len({r['id'] for r in evaluated})!=64 or {r['id'] for r in evaluated}!=set(ids):
            raise ValueError('Base-control evaluation is incomplete or mismatched')
        if any(str(row['gold_answer'])!=str(frozen[row['id']]['gold_answer']) for row in evaluated):
            raise ValueError('Base-control evaluation references changed')
        metrics=summarize(evaluated)
        public.update(status='completed',metrics=metrics,accuracy_percent=100*metrics['numeric_correct']/64,
                      actual_supervised_tokens=0,actual_optimizer_updates=0)
        return public,evaluated
    except (KeyError,TypeError,ValueError):
        public.update(status='invalid_result',detail='Base-control completion failed zero-training or exact-question checks; no accuracy is assigned.')
        return public,None


def summarize_arm(study,manifest,job):
    folder=private_child(study,job['folder'])
    plan=read(folder/'plan.json'); data=read(folder/'input.json')
    selector,seed,budget=job['selector'],job['seed'],manifest['token_budget']
    public=dict(selector=selector,seed=seed,token_budget=budget,status='prepared',
        checkpoint_name=job['checkpoint_name'],worker_arm_slot=job['worker_arm_slot'])
    launch=read(folder/'launch.json') if (folder/'launch.json').exists() else {}
    status=read(folder/'remote_status.json') if (folder/'remote_status.json').exists() else {}
    result=read(folder/'result.json') if (folder/'result.json').exists() else {}
    if result.get('stage')!='completed':
        if status.get('stage')=='failed' or result.get('stage')=='failed':
            public['status']='failed'
        elif launch.get('call_id'):
            public['status']='running'
        elif launch:
            public['status']='ambiguous_launch'
        public['detail']='No complete matched result is available; no accuracy is assigned.'
        return public,None
    try:
        expected_ids=plan['development_ids']; expected={row['id']:row for row in data['development']}
        if len(expected_ids)!=64 or set(expected_ids)!=set(expected) or len(expected)!=64:
            raise ValueError('Incomplete frozen development identities')
        actual=result.get('plan',{})
        if (actual.get('protocol_hash')!=plan['protocol_hash'] or actual.get('seed')!=seed
                or any(actual.get(key)!=value for key,value in plan.items() if key not in ('run_id','resume_from','protocol_hash'))
                or actual.get('token_budget')!=budget or actual.get('common_pool_sha256')!=manifest['common_pool']['sha256']
                or actual.get('development_ids')!=expected_ids or actual.get('selector_name')!=selector
                or actual.get('checkpoint_name')!=selector or actual.get('arm')!=control.SLOT[selector]
                or result.get('arm')!=control.SLOT[selector]
                or result.get('supervised_tokens')!=budget or result.get('optimizer_updates')!=budget//1024
                or result.get('held_out_test_used') is not False):
            raise ValueError('Actual exposure/checkpoint/seed/pool differs from frozen plan')
        # The generic worker uses a legacy valued training slot for BOTH skill
        # and gradient. Only checkpoint_name identifies the evaluation label.
        evaluations=result.get('evaluations',{})
        if set(evaluations)!={selector}:
            raise ValueError('Evaluation checkpoint label differs from selector')
        rows=evaluations[selector]
        if not isinstance(rows,list) or len(rows)!=64 or len({r['id'] for r in rows})!=64 or {r['id'] for r in rows}!=set(expected):
            raise ValueError('Completed evaluation has missing/duplicate/different questions')
        for row in rows:
            if str(row['gold_answer'])!=str(expected[row['id']]['gold_answer']):
                raise ValueError('Evaluation reference differs from frozen question')
        metrics=summarize(rows)
        exposure=manifest['exposures'][str(seed)][selector]
        public.update(status='completed',metrics=metrics,accuracy_percent=100*metrics['numeric_correct']/64,
            question_wilson_95_interval_percent=wilson(metrics['numeric_correct'],64),
            actual_supervised_tokens=result['supervised_tokens'],actual_optimizer_updates=result['optimizer_updates'],
            exposure={key:exposure[key] for key in ('examples','partial_supervised_tails','input_tokens_once',
                'input_tokens_forwarded','source_counts','reference_origin_counts','supervised_tokens_by_source')},
            worker_elapsed_seconds=result.get('elapsed_seconds'),
            detail='Completed matched development evaluation; question uncertainty does not measure training-seed uncertainty.')
        return public,rows
    except (KeyError,TypeError,ValueError):
        public.update(status='invalid_result',detail='Completed-result claims failed frozen checkpoint, exposure, or question checks; no accuracy is assigned.')
        return public,None


def seed_summary(seed_records):
    complete=[row for row in seed_records if all(row['arms'][s]['status']=='completed' for s in SELECTORS)]
    result=dict(complete_seed_triples=len(complete),planned_seeds=2,
        interpretation='Two seeds support a descriptive sensitivity check, not a precise estimate of training-seed uncertainty.')
    if len(complete)!=2:
        return result
    result['selectors']={selector:dict(n_seeds=2,
        mean_accuracy_percent=statistics.mean(row['arms'][selector]['accuracy_percent'] for row in complete),
        sample_sd_accuracy_percent=statistics.stdev(row['arms'][selector]['accuracy_percent'] for row in complete),
        min_correct=min(row['arms'][selector]['metrics']['numeric_correct'] for row in complete),
        max_correct=max(row['arms'][selector]['metrics']['numeric_correct'] for row in complete)) for selector in SELECTORS}
    result['mean_paired_differences_pp']={f'{candidate}_vs_{reference}':statistics.mean(
        row['comparisons'][f'{candidate}_vs_{reference}']['difference_percentage_points'] for row in complete)
        for candidate,reference in PAIRINGS}
    return result


def feature_overhead(plan_path):
    """Sum observed worker durations across the SAME-protocol resume lineage.

    These are recorded worker times, not invoices and not container-startup
    times. Unique committed warmup progress is a maximum, never planned8192
    multiplied by call count. Partial/uncommitted repeated work can add cost.
    """
    current=Path(plan_path).resolve();first=read(current);identity=first['protocol_hash']
    seen=set();attempts=[];warmup=[]
    while True:
        if current in seen or len(seen)>=16:
            raise ValueError('Invalid/cyclic feature resume lineage')
        seen.add(current);plan=read(current)
        if plan['protocol_hash']!=identity or plan['protocol']!=first['protocol']:
            raise ValueError('Feature continuation changed the frozen selection protocol')
        folder=current.parent
        result=read(folder/'result.json') if (folder/'result.json').exists() else {}
        status=read(folder/'remote_status.json') if (folder/'remote_status.json').exists() else {}
        terminal=read(folder/'terminal.json') if (folder/'terminal.json').exists() else {}
        summary=result.get('public_summary',{})
        observed=[value for value in (summary.get('elapsed_seconds'),result.get('elapsed_seconds'),status.get('elapsed_seconds'))
                  if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0]
        reported=summary.get('selector_warmup_tokens')
        if isinstance(reported,int) and 0<=reported<=plan['protocol']['config']['warmup_tokens']:
            warmup.append(reported)
        attempts.append(dict(run_id=folder.name,stage=result.get('stage',status.get('stage','not_reported')),
            elapsed_seconds=max(observed) if observed else None,
            timing_basis='Observed worker duration; excludes container startup and may be a lower bound for failed/partial attempts.',
            confirmed_terminal=terminal.get('confirmed_terminal') is True or result.get('stage') in ('completed','bounded_stop','calibration_refused')))
        previous=plan.get('resume_from')
        if not previous:
            break
        if not isinstance(previous,str) or Path(previous).name!=previous or previous in ('.','..'):
            raise ValueError('Feature resume path is not a safe sibling run ID')
        current=folder.parent/previous/'plan.json'
    attempts.reverse()
    known=[attempt['elapsed_seconds'] for attempt in attempts if attempt['elapsed_seconds'] is not None]
    return dict(method=first['protocol']['config']['method'],feature_stage=attempts[-1]['stage'],
        attempts=attempts,attempt_count=len(attempts),
        prior_incomplete_attempts=[a for a in attempts[:-1] if a['stage']!='completed'],
        feature_worker_elapsed_seconds=sum(known) if known else None,
        timing_coverage=dict(attempts_with_observed_duration=len(known),total_attempts=len(attempts)),
        selector_warmup_supervised_tokens=max(warmup) if warmup else None,
        planned_selector_warmup_supervised_tokens=first['protocol']['config']['warmup_tokens'],
        warmup_accounting='Unique committed warmup progress counted once across restored checkpoints; uncommitted repeated work is not measured as extra tokens.',
        monetary_cost='Not inferred from elapsed time or reservations in this report. Incomplete/failed attempt durations remain itemized.',
        interpretation='All observed feature-attempt durations, including incomplete predecessors, are additional gradient-selector overhead shared across budgets/seeds. Arm token matching does not equalize end-to-end compute.')


def chart(points,workspace,baseline=None):
    if not points:
        return []
    cache=ROOT/'runs/mplcache-data-efficiency';cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(cache))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    from matplotlib.ticker import FuncFormatter
    colors={'random':'#5c6f82','skill':'#cf7b2c','gradient':'#167f80'}
    present=[selector for selector in SELECTORS if any(p['selector']==selector for p in points)]
    figure,axes=plt.subplots(1,len(present),figsize=(4.3*len(present),4.8),
                             layout='constrained',sharey=True,squeeze=False)
    ticks=sorted({p['token_budget'] for p in points})
    lower=max(0,5*math.floor(min(p['question_wilson_95_interval_percent'][0] for p in points)/5)-5)
    names={'random':'Random selection','skill':'Skill and diversity','gradient':'Gradient alignment'}
    for selector,axis in zip(present,axes[0]):
        if baseline and baseline.get('status')=='completed':
            axis.axhline(baseline['accuracy_percent'],color='#29313b',linestyle=':',linewidth=1.2,
                         label='Untouched base: '+str(baseline['metrics']['numeric_correct'])+'/64')
        for seed,marker,style in ((42,'o','-'),(43,'s','--')):
            rows=sorted((p for p in points if p['selector']==selector and p['seed']==seed),key=lambda p:p['token_budget'])
            if not rows:
                continue
            x=[p['token_budget'] for p in rows];y=[p['accuracy_percent'] for p in rows]
            low=[p['question_wilson_95_interval_percent'][0] for p in rows]
            high=[p['question_wilson_95_interval_percent'][1] for p in rows]
            axis.errorbar(x,y,yerr=[[v-l for v,l in zip(y,low)],[h-v for h,v in zip(high,y)]],
                color=colors[selector],marker=marker,linestyle=style,capsize=3,alpha=.9,
                markerfacecolor=colors[selector] if seed==42 else 'white',
                label=f'{selector}, seed {seed}')
        axis.set(title=names[selector],xlabel='Supervised answer tokens',ylim=(lower,100))
        axis.set_xscale('log',base=2);axis.set_xticks(ticks)
        axis.xaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value:,.0f}'))
        axis.set_xlim(ticks[0]/1.35,ticks[-1]*1.35)
        axis.grid(axis='y',alpha=.18);axis.legend(loc='lower left',fontsize=8)
    axes[0][0].set_ylabel('Numeric accuracy on 64 development questions (%)')
    figure.suptitle('New math cohort: completed results only\nZoomed accuracy scale; question-level 95% intervals do not measure seed uncertainty',fontsize=11)
    destination=workspace/'docs/figures';destination.mkdir(parents=True,exist_ok=True)
    paths=[]
    for extension in ('svg','png'):
        name='data-efficiency-development.'+extension
        figure.savefig(destination/name,dpi=180)
        paths.append('figures/'+name)
    plt.close(figure)
    return paths


def build(*,grid=None,workspace=WORKSPACE,paired_fn=paired,render=True):
    grid=Path(grid) if grid is not None else ROOT/'runs/data_efficiency_math_v1'
    workspace=Path(workspace)
    if not (grid/'grid_manifest.json').exists():
        return dict(status='not_prepared',public_files_written=False,completed_arms=0,points=[])
    control.verify(grid)
    frozen=read(grid/'grid_manifest.json')
    first_study=private_child(grid,frozen['studies'][0]['folder'])
    first_manifest=read(first_study/'manifest.json')
    first_arm=private_child(first_study,first_manifest['jobs'][0]['folder'])
    first_plan=read(first_arm/'plan.json');first_data=read(first_arm/'input.json')
    baseline,baseline_rows=baseline_context(grid.parent/'student_baseline_batched64_v1',
        expected_development_sha256=first_plan['development_source_sha256'],expected_ids=first_plan['development_ids'],
        expected_gold={r['id']:r['gold_answer'] for r in first_data['development']},
        expected_prompts={r['id']:r['prompt'] for r in first_data['development']})
    budgets=[];points=[];identities=[];overhead=None
    for descriptor in frozen['studies']:
        study=private_child(grid,descriptor['folder']);manifest=read(study/'manifest.json')
        if (manifest['token_budget']!=descriptor['token_budget'] or manifest['common_pool']['sha256']!=frozen['common_pool_sha256']
                or manifest['sources']!=frozen['sources']):
            raise ValueError('Budget levels no longer share one frozen candidate/source cohort')
        seed_records=[]
        for seed in (42,43):
            item=dict(seed=seed,arms={},comparisons={},versus_batched_base={});private={}
            for selector in SELECTORS:
                job=next(j for j in manifest['jobs'] if j['seed']==seed and j['selector']==selector)
                item['arms'][selector],private[selector]=summarize_arm(study,manifest,job)
                if private[selector] is not None:
                    arm=item['arms'][selector]
                    point={k:arm[k] for k in ('seed','selector','token_budget','accuracy_percent',
                        'question_wilson_95_interval_percent','actual_supervised_tokens','actual_optimizer_updates')}
                    point.update(numeric_correct=arm['metrics']['numeric_correct'],count=64)
                    points.append(point)
                    if baseline_rows is not None:
                        item['versus_batched_base'][selector]=paired_fn(baseline_rows,private[selector])
            for candidate,reference in PAIRINGS:
                if private[candidate] is not None and private[reference] is not None:
                    item['comparisons'][f'{candidate}_vs_{reference}']=paired_fn(private[reference],private[candidate])
            seed_records.append(item)
        jobs=manifest['jobs']
        identities.extend(read(private_child(study,j['folder'])/'plan.json')['development_source_sha256'] for j in jobs)
        complete=sum(arm['status']=='completed' for item in seed_records for arm in item['arms'].values())
        budgets.append(dict(token_budget=manifest['token_budget'],budget_role=manifest['common_pool']['budget_role'],
            fraction_of_available_supervised_tokens=manifest['common_pool']['fraction_of_available_supervised_tokens'],
            completed_arms=complete,planned_arms=6,seeds=seed_records,seed_variation=seed_summary(seed_records)))
        if overhead is None:
            feature_result=read(manifest['source_paths']['feature_result'])
            feature_public=feature_result.get('public_summary',{})
            overhead=feature_overhead(manifest['source_paths']['feature_plan'])
            overhead['completed_projected_features']=feature_public.get('completed_features')
    if not identities or len(set(identities))!=1:
        raise ValueError('Grid arms do not bind identical development questions')
    completed=sum(budget['completed_arms'] for budget in budgets);planned=6*len(budgets)
    public=dict(schema_version=1,generated_at_utc=datetime.now(timezone.utc).isoformat(),
        title='New-cohort random, skill and gradient data-efficiency study',
        status='completed' if completed==planned else 'partial',study_id=grid.name,
        completed_arms=completed,planned_arms=planned,official_test_used=False,
        grid_manifest_sha256=file_hash(grid/'grid_manifest.json'),
        cohort=dict(common_pool_sha256=frozen['common_pool_sha256'],available_supervised_tokens=frozen['common_available_tokens'],
                    development_source_sha256=identities[0],development_count=64,
                    selectors=list(SELECTORS),seeds=[42,43]),
        budgets=budgets,points=points,selector_overhead=overhead,batched_base_control=baseline,historical_four_arms_included=False,
        figures=chart(points,workspace,baseline) if render else [],
        limitations=['Only complete matched evaluations enter plots; pending or failed arms are not zero scores.',
            'This new multi-source cohort is separate from the earlier four32768-token GSM8K arms.',
            'Shared supervised-token budgets and update counts do not match examples, forwarded input tokens, source mixture, runtime or selector overhead.',
            'Paired bootstrap intervals resample questions, not training seeds; p-values are exploratory and have no multiplicity correction.',
            'Two-seed summaries are descriptive; no128-independent-question or precise seed-uncertainty claim is made.',
            'Targets and skill information are development signals; results on these64 monitoring questions are adaptive, not final-test accuracy.',
            'Reference matching and numeric final-answer accuracy do not prove every explanation step correct.',
            'Near-all-data budget levels provide limited selection contrast because selected token exposures substantially overlap.'])
    (workspace/'docs').mkdir(parents=True,exist_ok=True);(workspace/'progress').mkdir(parents=True,exist_ok=True)
    (workspace/'docs/data-efficiency-results.json').write_text(json.dumps(public,indent=2)+'\n',encoding='utf-8')
    lines=['# New-cohort data-efficiency results','',
        f"Completed {completed}/{planned} arms. Only completed matched evaluations appear below. Earlier four-arm results remain separate history.",'',
        'Untouched-base batch8 control: '+(str(baseline['metrics']['numeric_correct'])+'/64, with zero training tokens/updates.' if baseline.get('status')=='completed' else baseline['status']+'; no accuracy assigned.'),'',
        '| Supervised tokens | Seed | Selector | Status | Numeric correct | Truncated | Actual tokens | Updates | Examples | Forwarded input tokens |',
        '|---:|---:|---|---|---:|---:|---:|---:|---:|---:|']
    for budget in budgets:
        for item in budget['seeds']:
            for selector,arm in item['arms'].items():
                metrics=arm.get('metrics',{});exposure=arm.get('exposure',{})
                lines.append(f"| {budget['token_budget']:,} | {item['seed']} | {selector} | {arm['status']} | {str(metrics['numeric_correct'])+'/64' if metrics else 'pending'} | {metrics.get('truncated','pending')} | {arm.get('actual_supervised_tokens','pending')} | {arm.get('actual_optimizer_updates','pending')} | {exposure.get('examples','pending')} | {exposure.get('input_tokens_forwarded','pending')} |")
    lines+=['','## Paired comparisons','']
    for budget in budgets:
        for item in budget['seeds']:
            for label,value in item['comparisons'].items():
                lo,hi=value['paired_bootstrap_95_interval_pp']
                lines.append(f"- {budget['token_budget']:,} tokens, seed {item['seed']}, {label}: {value['difference_percentage_points']:+.2f} pp; corrected {value['corrected']}, regressed {value['regressed']}; paired bootstrap95% [{lo:+.2f}, {hi:+.2f}] pp; exploratory McNemar p={value['mcnemar_exact_two_sided_p']:.4f}.")
    if not any(item['comparisons'] for b in budgets for item in b['seeds']):
        lines.append('No completed same-budget, same-seed selector pair is available yet.')
    lines+=['','## Two-seed sensitivity','']
    for budget in budgets:
        result=budget['seed_variation']
        if 'selectors' not in result:
            lines.append(f"- {budget['token_budget']:,} tokens: both complete seed triples are still required for a two-seed summary.")
        else:
            for selector,value in result['selectors'].items():
                lines.append(f"- {budget['token_budget']:,} tokens, {selector}: mean {value['mean_accuracy_percent']:.2f}%, sample SD {value['sample_sd_accuracy_percent']:.2f} pp across two seeds; range {value['min_correct']}�{value['max_correct']}/64. Descriptive only.")
    lines+=['','## Selector overhead','',overhead['interpretation'],'',
        f"Planned selector warmup: {overhead['planned_selector_warmup_supervised_tokens']:,} supervised tokens; actual recorded: {overhead['selector_warmup_supervised_tokens'] if overhead['selector_warmup_supervised_tokens'] is not None else 'not reported'}. Feature-worker elapsed seconds: {overhead['feature_worker_elapsed_seconds'] if overhead['feature_worker_elapsed_seconds'] is not None else 'not reported'}. Monetary cost is not estimated here.",'',
        overhead['warmup_accounting'],'',
        *[f"- Feature attempt {a['run_id']}: {a['stage']}; observed worker seconds {a['elapsed_seconds'] if a['elapsed_seconds'] is not None else 'not reported'}." for a in overhead['attempts']],'',
        '## Limits','',*['- '+value for value in public['limitations']],'',
        'Public exports contain aggregates and hashes only; questions, model responses, per-question outcomes and private source paths remain local.','']
    (workspace/'progress/DATA_EFFICIENCY_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    return public


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--grid',type=Path,default=ROOT/'runs/data_efficiency_math_v1')
    args=parser.parse_args();result=build(grid=args.grid)
    print(json.dumps({key:result[key] for key in ('status','completed_arms')}))
