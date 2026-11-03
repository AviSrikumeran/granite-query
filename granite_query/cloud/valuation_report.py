"""Aggregate-only audit/report for the immutable 32768-token valuation arms."""
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent))
from cloud.comparison_metrics import summarize
from cloud.evaluation_stats import paired
from cloud.valuation_contract import validate_arm

TEACHER='deepseek-v4-pro'
COMMON={'mode':'train_evaluate','model':'ibm-granite/granite-4.2-3b',
    'revision':'4e9c275e232f10211ec88644d106a1f6a1b60e06',
    'token_budget':32768,'tokens_per_update':1024,'learning_rate':2e-5,
    'lora_r':8,'lora_alpha':16,'context_limit':2048,'max_new_tokens':512,
    'enable_thinking':False,'do_sample':False,'evaluation_batch_size':8,
    'evaluation_kind':'development'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]


def ids_hash(ids):
    return hashlib.sha256(json.dumps(sorted(ids),separators=(',',':')).encode()).hexdigest()


def validate_plan(plan,*,seed,arm,dev_ids,dev_sha,selection_sha,arm_sha):
    for key,value in COMMON.items():
        if plan.get(key)!=value:
            raise ValueError('Frozen valuation protocol changed: '+key)
    if plan.get('seed')!=seed or plan.get('arm')!=arm:
        raise ValueError('Wrong training seed or selector arm')
    if plan.get('development_ids')!=dev_ids or plan.get('development_source_sha256')!=dev_sha:
        raise ValueError('Development question identity/order/source changed')
    if plan.get('selection_manifest_sha256')!=selection_sha or plan.get('arm_source_sha256')!=arm_sha:
        raise ValueError('Selection or arm source changed')
    protocol={key:value for key,value in plan.items() if key not in ('run_id','protocol_hash','resume_from')}
    expected=hashlib.sha256(json.dumps(protocol,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if plan.get('protocol_hash')!=expected:
        raise ValueError('Protocol hash does not match plan')


def teacher_provenance(prepared):
    manifest=load(prepared/'manifest.json')
    pool=prepared/'eligible.jsonl'
    if manifest.get('official_test_used') is not False or sha(pool)!=manifest['eligible_sha256']:
        raise ValueError('Prepared pool changed or official-test isolation not established')
    candidates=rows(pool)
    if len(candidates)!=manifest['counts']['eligible'] or len({row['id'] for row in candidates})!=len(candidates):
        raise ValueError('Duplicate shared-pool IDs')
    revisions=set()
    for row in candidates:
        settings=row.get('generation',{}).get('settings',{})
        if (row.get('teacher_model')!=TEACHER or settings.get('model')!=TEACHER
                or settings.get('thinking',{}).get('type')!='disabled'
                or settings.get('max_tokens')!=1024 or row.get('source_split')!='train'
                or row.get('verified_final_answer') is not True or row.get('trace_truncated') is True):
            raise ValueError('New-pool teacher identity or generation protocol differs')
        if hashlib.sha256(row['response'].encode()).hexdigest()!=row['raw_response_sha256']:
            raise ValueError('Teacher trace changed')
        revisions.add(str(row.get('teacher_revision','')))
    provenance={'shared_pool_count':len(candidates),'eligible_sha256':sha(pool),
        'prepared_manifest_sha256':sha(prepared/'manifest.json'),
        'teacher_model':TEACHER,'reported_revision_aliases':sorted(revisions),
        'thinking_mode':'disabled','max_output_tokens':1024,
        'teacher_identity_note':'API aliases are mutable; this pool is separate from earlier thinking-mode teacher traces and public R1 datasets.',
        'weakness_source_kind':manifest['weakness_provenance']['source_kind'],
        'adaptive_development':manifest['weakness_provenance']['source_kind']!='training_probe_predictions'}
    return manifest,provenance


def status_without_result(folder):
    remote=folder/'remote_status.json'
    if remote.exists():
        stage=load(remote).get('stage','unknown')
        return {'status':'failed' if stage=='failed' else 'running',
            'stage':'awaiting_result_download' if stage=='completed' else stage}
    return {'status':'running' if (folder/'launch.json').exists() else 'prepared',
            'stage':'queued' if (folder/'launch.json').exists() else 'not_launched'}


def summarize_arm(folder,manifest_path,prepared_manifest,canonical):
    plan=load(folder/'plan.json')
    manifest=load(manifest_path)
    seed,arm=plan['seed'],plan['arm']
    if manifest.get('seed')!=seed or manifest.get('token_budget')!=32768:
        raise ValueError('Selection seed or budget differs')
    if (manifest['prepared_manifest_sha256']!=prepared_manifest['manifest_sha256']
            or manifest['prepared_eligible_sha256']!=prepared_manifest['eligible_sha256']):
        raise ValueError('Arms do not share the frozen verified pool')
    arm_path=manifest_path.parent/(arm+'_input.json')
    if sha(arm_path)!=manifest['artifacts_sha256'][arm_path.name]:
        raise ValueError('Selector arm artifact changed')
    validate_plan(plan,seed=seed,arm=arm,dev_ids=canonical['ids'],dev_sha=canonical['sha256'],
        selection_sha=sha(manifest_path),arm_sha=sha(arm_path))
    input_path=folder/'input.json'
    if sha(input_path)!=plan['input_sha256']:
        raise ValueError('Worker input changed')
    worker_input=load(input_path)
    selected=load(arm_path)
    if worker_input['arm']!=selected:
        raise ValueError('Worker exposure differs from selector output')
    if selected['tokenizer']!=prepared_manifest['tokenizer']:
        raise ValueError('Selected tokenizer differs from the common prepared pool')
    indexed=validate_arm(selected)
    for key,row in indexed.items():
        original=prepared_manifest['candidate_index'].get(key)
        if original is None or any(row[field]!=original[field] for field in ('prompt','response','gold_answer','raw_response_sha256')):
            raise ValueError('Selected trace is not in the common verified teacher pool')
        if row['input_ids']!=original['prefix_ids']+original['answer_ids'] or row['prefix_tokens']!=len(original['prefix_ids']):
            raise ValueError('Selected tokenizer input differs from the common pool')
    if selected['token_budget']!=32768 or selected['optimizer_updates']!=32:
        raise ValueError('Unexpected actual exposure/update budget')
    if set(indexed)&set(canonical['ids']):
        raise ValueError('Training/development overlap')
    if [row['id'] for row in worker_input['development']]!=canonical['ids']:
        raise ValueError('Worker development set changed')
    if any(str(row['gold_answer'])!=str(canonical['by_id'][row['id']]['gold_answer'])
           or row['prompt']!=canonical['by_id'][row['id']]['prompt'] for row in worker_input['development']):
        raise ValueError('Worker development question or gold answer changed')
    exposure=manifest['arms'][arm]
    forwarded=sum(len(indexed[window['id']]['input_ids']) for update in selected['updates'] for window in update['microbatches'])
    if (exposure['supervised_tokens']!=32768 or exposure['optimizer_updates']!=32
            or exposure['examples']!=len(indexed) or exposure['input_tokens_forwarded']!=forwarded
            or exposure['selected_ids']!=list(indexed)
            or exposure['input_tokens_once']!=sum(len(row['input_ids']) for row in indexed.values())
            or exposure['partial_supervised_tails']!=sum(row['partial_supervised_tail'] for row in indexed.values())):
        raise ValueError('Exposure aggregate differs from actual frozen masks')
    result_path=folder/'result.json'
    public={'run_id':folder.name,'seed':seed,'arm':arm,**status_without_result(folder),
        'exposure':{key:exposure[key] for key in ('examples','supervised_tokens','optimizer_updates',
            'partial_supervised_tails','input_tokens_once','input_tokens_forwarded')},
        'sources':{'plan_sha256':sha(folder/'plan.json'),'input_sha256':sha(input_path),
            'selector_arm_sha256':sha(arm_path),'selection_manifest_sha256':sha(manifest_path),
            'development_ids_sha256':ids_hash(canonical['ids']),'protocol_hash':plan['protocol_hash']}}
    if not result_path.exists():
        return public,None
    result=load(result_path)
    if result.get('plan')!=plan:
        raise ValueError('Saved result differs from the immutable run plan')
    if (result.get('stage')!='completed' or result.get('arm')!=arm or result.get('supervised_tokens')!=32768
            or result.get('optimizer_updates')!=32 or result.get('held_out_test_used') is not False):
        raise ValueError('Completed result does not satisfy frozen token/update protocol')
    validate_plan(result['plan'],seed=seed,arm=arm,dev_ids=canonical['ids'],dev_sha=canonical['sha256'],
        selection_sha=sha(manifest_path),arm_sha=sha(arm_path))
    if set(result['evaluations'])!={arm}:
        raise ValueError('Unexpected evaluated checkpoint identity')
    outcomes=result['evaluations'][arm]
    if len(result.get('weighted_losses',[]))!=32 or any(not math.isfinite(value) for value in result['weighted_losses']):
        raise ValueError('Optimizer update history is incomplete or non-finite')
    if len(outcomes)!=64 or len({row['id'] for row in outcomes})!=64 or {row['id'] for row in outcomes}!=set(canonical['ids']):
        raise ValueError('Completed evaluation is not the identical frozen64 set')
    for row in outcomes:
        if str(row['gold_answer'])!=str(canonical['by_id'][row['id']]['gold_answer']):
            raise ValueError('Evaluation reference answers changed')
        if not (1<=row.get('batch_size',0)<=8) or 'batch_elapsed_seconds' not in row:
            raise ValueError('Expected matched batched evaluation timing')
        batch_elapsed=row['batch_elapsed_seconds']
        if (not math.isfinite(batch_elapsed) or batch_elapsed<0
                or not math.isclose(row['elapsed_seconds'],batch_elapsed/row['batch_size'],rel_tol=1e-9)
                or not 1<=row['generated_tokens']<=512):
            raise ValueError('Invalid amortized timing or generated-token count')
    public.update(status='completed',stage='completed',metrics=summarize(outcomes),
        worker_elapsed_seconds=result['elapsed_seconds'],latency_measurement=result['latency_measurement'])
    public['sources']['result_sha256']=sha(result_path)
    probe=result.get('student_probe')
    if probe:
        public['student_probe']={'complete':bool(probe['complete']),'completed':probe['completed'],
            'requested':probe['requested'],'used_to_change_this_selector':False,
            'interpretation':'Untouched-student response NLL diagnostic; not causal data value.'}
    return public,outcomes


def seed_variation(pairs):
    if len(pairs)!=2 or any(pair.get('status')!='completed' for pair in pairs.values()):
        return {'available':False,'reason':'Both matched seed 42 and seed 43 pairs must finish before seed variation is reported.'}
    answer={'available':True,'seeds':[42,43],'n_seeds':2,'same_development_questions':True,
        'limitation':'Two seeds give descriptive variation, not a robust estimate of training-seed uncertainty. The same 64 questions are not 128 independent test questions.'}
    for arm in ('random','valued'):
        values=[100*pair['arms'][arm]['metrics']['numeric_correct']/64 for pair in pairs.values()]
        answer[arm]={'mean_accuracy_pct':statistics.mean(values),'accuracy_range_pct':[min(values),max(values)],
            'sample_sd_accuracy_pct':statistics.stdev(values)}
    deltas=[pair['paired_valued_vs_random']['difference_percentage_points'] for pair in pairs.values()]
    answer['valued_minus_random']={'mean_difference_pp':statistics.mean(deltas),'range_pp':[min(deltas),max(deltas)]}
    return answer


def history(root,canonical):
    output=[]
    sources=[(root/'runs/matched_eval64_v1/result.json',('baseline','ranked32','random32')),
             (root/'runs/granite_full120_v1/result.json',('full120',))]
    for path,names in sources:
        if not path.exists():
            continue
        result=load(path)
        for name in names:
            outcomes=result['evaluations'][name]
            if len(outcomes)!=64 or {r['id'] for r in outcomes}!=set(canonical['ids']):
                raise ValueError('Historical question set differs')
            if any(str(row['gold_answer'])!=str(canonical['by_id'][row['id']]['gold_answer']) for row in outcomes):
                raise ValueError('Historical gold references differ')
            output.append({'checkpoint':name,'metrics':summarize(outcomes),'result_sha256':sha(path),
                'latency_measurement':'Earlier serial generation; not directly comparable with amortized batch 8 timing.',
                'interpretation':'Descriptive history. Earlier arms differ in data, learning rate, token budget, updates and inference batching.'})
    return output


def build(*,root=ROOT,workspace=WORKSPACE,paired_fn=paired):
    root,workspace=Path(root),Path(workspace)
    canonical_path=root/'runs/matched_eval64_v1/development.jsonl'
    dev=rows(canonical_path)
    canonical={'ids':[row['id'] for row in dev],'by_id':{row['id']:row for row in dev},'sha256':sha(canonical_path)}
    if len(dev)!=64 or len(canonical['by_id'])!=64:
        raise ValueError('Expected 64 unique canonical development questions')
    prepared=root/'runs/student_valuation_pool512_prepared_v1'
    manifest,provenance=teacher_provenance(prepared)
    proof={'manifest_sha256':sha(prepared/'manifest.json'),'eligible_sha256':sha(prepared/'eligible.jsonl'),
        'tokenizer':manifest['tokenizer'],
        'candidate_index':{row['id']:row for row in rows(prepared/'eligible.jsonl')}}
    pairs={}
    for seed in (42,43):
        selection=root/f'runs/student_valuation32768_seed{seed}_v1/manifest.json'
        pair={'seed':seed,'status':'not_prepared','arms':{}}
        private={}
        if selection.exists():
            pair['status']='partial'
            for arm in ('random','valued'):
                folder=root/f'runs/student_valuation32768_seed{seed}_{arm}_v1'
                if not (folder/'plan.json').exists():
                    pair['arms'][arm]={'status':'not_prepared','arm':arm,'seed':seed}
                    continue
                pair['arms'][arm],private[arm]=summarize_arm(folder,selection,proof,canonical)
            if all(private.get(arm) is not None for arm in ('random','valued')):
                pair['status']='completed'
                pair['paired_valued_vs_random']=paired_fn(private['random'],private['valued'])
                pair['difference_correct']=pair['arms']['valued']['metrics']['numeric_correct']-pair['arms']['random']['metrics']['numeric_correct']
        pairs[str(seed)]=pair
    complete=sum(pair['status']=='completed' for pair in pairs.values())
    public={'schema_version':1,'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'title':'Matched-token student-aware valuation development results',
        'status':'completed' if complete==2 else 'partial','completed_pairs':complete,'planned_pairs':2,
        'completed_arms':sum(arm.get('status')=='completed' for pair in pairs.values() for arm in pair['arms'].values()),
        'planned_arms':4,
        'protocol':dict(COMMON,optimizer_updates=32,development_count=64,
            development_ids_sha256=ids_hash(canonical['ids'])),
        'teacher_pool':provenance,'pairs':pairs,'seed_variation':seed_variation(pairs),
        'historical_checkpoints_separate':history(root,canonical),'official_test_used':False,
        'limitations':['Weakness signals were derived from these development outcomes; this is adaptive development monitoring, not independent final-test evidence.',
            'Equal supervised-token counts and optimizer updates do not imply equal examples, input computation, or wall-clock cost.',
            'The last supervised trace may have a masked answer tail; the full trace remains in the causal input unchanged.',
            'Candidate NLL was diagnostic only and did not change the frozen skill-based selector in these arms.',
            'The first random arm also ran the candidate-NLL diagnostic; whole-worker elapsed time therefore is not a matched training-cost comparison.',
            'Paired bootstrap intervals quantify question resampling, not training-seed uncertainty; p-values are exploratory without multiplicity correction.',
            'Seed changes can affect initialization, presentation order and random selection together; these runs do not isolate each source of variation.',
            'Batched timings are amortized generation wall time and cannot be advertised as single-request speedups over earlier serial runs.',
            'Numerical final-answer scoring does not establish reasoning-step or explanation quality.']}
    lines=['# Matched-token valuation results','',
        'These are adaptive development results on the same 64 monitoring questions. The official test split remains untouched. No direction of improvement is assumed.','',
        'Each arm starts from the same pinned Granite checkpoint, supervises exactly 32768 answer tokens through 32 effective 1024-token updates, and uses learning rate 0.00002. The shared teacher pool uses DeepSeek V4 Pro with thinking disabled and a 1024-token output limit.','',
        '| Seed | Arm | Status | Numeric matches | Strict matches | Truncated | Examples | Input tokens forwarded | Batched generation seconds | Generated tokens |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for pair in pairs.values():
        for arm in ('random','valued'):
            item=pair['arms'].get(arm,{'status':'not_prepared'})
            m=item.get('metrics',{})
            e=item.get('exposure',{})
            lines.append(f"| {pair['seed']} | {arm} | {item['status']} | {str(m['numeric_correct'])+'/64' if m else 'pending'} | {m.get('strict_format_correct','pending')} | {m.get('truncated','pending')} | {e.get('examples','pending')} | {e.get('input_tokens_forwarded','pending')} | {round(m['latency_seconds_total'],3) if m else 'pending'} | {m.get('generated_tokens','pending')} |")
    lines+=['','## Paired selection comparison','']
    for pair in pairs.values():
        if pair['status']!='completed':
            lines.append(f"- Seed {pair['seed']}: pair incomplete; no valued-versus-random result is reported.")
        else:
            p=pair['paired_valued_vs_random']
            lo,hi=p['paired_bootstrap_95_interval_pp']
            lines.append(f"- Seed {pair['seed']}: valued minus random {pair['difference_correct']:+d}/64 ({p['difference_percentage_points']:+.2f} percentage points); corrected {p['corrected']}, regressed {p['regressed']}; paired bootstrap 95% interval [{lo:+.2f}, {hi:+.2f}] pp; exact McNemar p={p['mcnemar_exact_two_sided_p']:.4f}.")
    lines+=['','## Seed variation','',
        json.dumps(public['seed_variation'],ensure_ascii=False),'',
        '## Earlier results are separate history','',
        '| Checkpoint | Numeric matches | Truncated | Timing basis |','|---|---:|---:|---|']
    for item in public['historical_checkpoints_separate']:
        m=item['metrics']
        lines.append(f"| {item['checkpoint']} | {m['numeric_correct']}/64 | {m['truncated']} | earlier serial generation |")
    lines+=['','Earlier runs differ in data, learning rate, optimization and batching. Their latency totals cannot be combined with batched timings into a speedup claim. A completed random arm alone is not a selection-strategy comparison.','',
        '## Limitations','',*['- '+value for value in public['limitations']],'',
        'Public artifacts contain aggregates and source hashes only. Original questions, teacher traces, model answers, and per-question outcomes remain private.','']
    (workspace/'docs').mkdir(parents=True,exist_ok=True)
    (workspace/'progress').mkdir(parents=True,exist_ok=True)
    (workspace/'docs/valuation-results.json').write_text(json.dumps(public,indent=2)+'\n',encoding='utf-8')
    (workspace/'progress/VALUATION_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    return public


if __name__=='__main__':
    result=build()
    print(json.dumps({'status':result['status'],'completed_pairs':result['completed_pairs'],
        'seed_variation_available':result['seed_variation']['available']}))
