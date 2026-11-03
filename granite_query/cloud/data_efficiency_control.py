"""Prepare prospective random/skill/gradient token-matched arms; never launch.

All three selectors use the same finalized verified pool, excluding the new
gradient targets. This is a new study; earlier 32768-token artifacts stay frozen.
The existing generic Modal worker trains one fresh adapter per separately funded
call. Its legacy ``valued`` slot is explicitly mapped to skill or gradient by
checkpoint_name/selector_method rather than being reported as a single method.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud import student_valuation as skill
from cloud.gradient_feature_contract import validate_input,validate_feature,canonical as feature_canonical
from cloud.gradient_valuation import score_projected,METHOD as SCORE_METHOD
from cloud.valuation_contract import validate_arm

VERSION='common-pool-data-efficiency-v1'
SELECTORS=('random','skill','gradient')
WEIGHTS={'weakness':.65,'lexical_novelty':.20,'skill_coverage':.15,'length_power':.25}
SLOT={'random':'random','skill':'valued','gradient':'valued'}
COMMON={'mode':'train_evaluate','model':skill.MODEL,'revision':skill.REVISION,
    'tokens_per_update':1024,'learning_rate':2e-5,'lora_r':8,'lora_alpha':16,
    'context_limit':2048,'max_new_tokens':512,'enable_thinking':False,'do_sample':False,
    'evaluation_batch_size':8,'evaluation_kind':'development','gpu':'A100-80GB',
    'timeout_seconds':1800,'application_training_guard_seconds':1400,
    'application_evaluation_guard_seconds':1600,'hard_cpu_cores':4,'hard_memory_gib':32,
    'reserved_usd':3,'latency_measurement':'amortized batched GPU wall time; not single-request latency'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def write_rows(path,rows):
    with Path(path).open('x',encoding='utf-8',newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')


def method(selector):
    if selector=='random':
        return {'name':'seeded-uniform-candidate-permutation-v1','until':'token-budget-covered'}
    if selector=='skill':
        return {'name':skill.VERSION,'weights':WEIGHTS,
            'interpretation':'Frozen lexical weakness/novelty/coverage heuristic; no gradient information.'}
    return {'name':'less-inspired-countsketch-v1','scoring_method':SCORE_METHOD,
        'projection_family':'countsketch_shake256_v1','reduction':'mean_per_target_cosine',
        'group_aggregation':'max_after_checkpoint_sum',
        'interpretation':'Projected LoRA gradient-alignment proxy, not a LESS reproduction or observed causal data value.'}


def complete_teacher(pool):
    if any((pool/name).exists() for name in ('collector.lock','teacher.lock')):
        raise ValueError('Teacher collection remains locked; do not freeze a growing pool')
    summary=load(pool/'teacher_summary.json')
    if (summary.get('stage')!='completed' or summary.get('completed')!=summary.get('requested')
            or summary.get('official_test_accessed') is not False):
        raise ValueError('Require finalized complete teacher attempts and explicit official-test isolation')
    eligible=skill.read_jsonl(pool/'eligible.jsonl')
    originals=skill.read_jsonl(pool/'teacher_results.jsonl')
    if (len(eligible)!=summary.get('eligible') or len(originals)!=summary['completed']
            or len({r['id'] for r in originals})!=len(originals)):
        raise ValueError('Teacher receipt/summary counts differ')
    by_id={row['id']:row for row in originals}
    seen=set()
    for row in eligible:
        source=by_id.get(row['id'])
        if source is None or row['id'] in seen:
            raise ValueError('Duplicate eligible ID or missing original teacher receipt')
        seen.add(row['id'])
        for field in ('prompt','response','gold_answer','source','source_split','reference_type',
                      'reference_match_is_independent_gold','teacher_model','teacher_revision','finish_reason'):
            if row.get(field)!=source.get(field):
                raise ValueError('Eligible trace differs from its original saved teacher receipt')
        settings=row.get('generation',{}).get('settings',{})
        independent=row.get('reference_type')=='human_dataset_answer'
        if (row.get('source_split')!='train' or row.get('teacher_model')!='deepseek-v4-pro'
                or settings.get('model')!='deepseek-v4-pro' or settings.get('max_tokens')!=1024
                or settings.get('thinking',{}).get('type')!='disabled'
                or row.get('finish_reason')!='stop' or row.get('eligible') is not True
                or row.get('reference_type') not in ('human_dataset_answer','procedurally_generated_result','synthetic_majority_vote_answer')
                or row.get('reference_match_is_independent_gold') is not independent
                or not skill._verified(row)):
            raise ValueError('Incorrect/incomplete teacher response or source/teacher provenance differs')
        expected=hashlib.sha256(row['response'].encode()).hexdigest()
        recorded=row.get('raw_response_sha256',row.get('generation',{}).get('raw_response_sha256'))
        # The teacher collector preserves full raw receipts, but does not write
        # a response hash. Feature preparation derives one from those originals.
        # An explicitly recorded hash must still match; absence is not tampering.
        if recorded is not None and recorded!=expected:
            raise ValueError('Recorded original response hash changed')
        raw=(source.get('raw') or {}).get('choices',[])
        if not raw or raw[0].get('message',{}).get('content')!=row['response']:
            raise ValueError('Response differs from the preserved provider receipt')
    return summary,{row['id']:row for row in eligible}


def gradient_sources(pool,features,scores,development,weakness):
    """Audit the completed gradient export, its scores and the shared teacher pool."""
    paths={'teacher_summary':pool/'teacher_summary.json','teacher_eligible':pool/'eligible.jsonl',
        'teacher_results':pool/'teacher_results.jsonl','feature_plan':features/'plan.json',
        'feature_input':features/'input.json','feature_result':features/'result.json',
        'feature_payload':features/'features_payload.json','score_manifest':scores/'manifest.json',
        'scores':scores/'scores.jsonl','development':development,'weakness':weakness}
    # Selection never opens a file explicitly named as official test data.
    for path in paths.values():
        if path.name.casefold() in {'test.json','test.jsonl','official_test.json','official_test.jsonl'}:
            raise ValueError('Official test files cannot enter this development study')
    hashes={name:sha(path) for name,path in paths.items()}
    summary,teachers=complete_teacher(pool)
    plan=load(paths['feature_plan']); data=load(paths['feature_input'])
    config=validate_input(data,plan); result=load(paths['feature_result']);payload=load(paths['feature_payload'])
    if (result.get('stage')!='completed' or result.get('projected_features_complete') is not True
            or result.get('protocol_hash')!=plan['protocol_hash']
            or result.get('feature_payload_sha256')!=hashes['feature_payload']
            or payload.get('protocol_hash')!=plan['protocol_hash']):
        raise ValueError('Wait for a completed immutable gradient export; partial stores are insufficient')
    provenance=plan['protocol']['sources']
    if (provenance.get('eligible_sha256')!=hashes['teacher_eligible']
            or provenance.get('teacher_summary_sha256')!=hashes['teacher_summary']
            or provenance.get('official_test_used') is not False
            or len(data['targets'])!=24):
        raise ValueError('Feature stage must bind this completed pool and exactly 24 new held-out targets')
    tokenizer=provenance['tokenizer']
    if (tokenizer.get('model')!=skill.MODEL or tokenizer.get('revision')!=skill.REVISION
            or len(tokenizer.get('backend_sha256',''))!=64 or len(tokenizer.get('chat_template_sha256',''))!=64):
        raise ValueError('Pinned tokenizer provenance is incomplete')
    development_rows=skill.read_jsonl(development)
    if (len(development_rows)!=64 or len({r['id'] for r in development_rows})!=64
            or any(r.get('source_split')!='train' for r in development_rows)):
        raise ValueError('Require the distinct 64 training-split development monitoring questions')
    dev_ids={r['id'] for r in development_rows}
    dev_hashes={hashlib.sha256(skill.normalized_question(r['prompt']).encode()).hexdigest() for r in development_rows}
    candidate_ids={r['id'] for r in data['candidates']};target_ids={r['id'] for r in data['targets']}
    if len({r['question_sha256'] for r in data['candidates']+data['targets']})!=len(data['candidates'])+len(data['targets']):
        raise ValueError('Common candidates and targets must contain distinct normalized questions')
    for row in data['candidates']+data['targets']:
        teacher=teachers.get(row['id'])
        if teacher is None or any(row.get(field)!=teacher.get(field) for field in
                ('prompt','response','gold_answer','source','source_split','reference_type','reference_match_is_independent_gold')):
            raise ValueError('Gradient candidate/target no longer matches its original teacher record')
        if row['id'] in dev_ids or row['question_sha256'] in dev_hashes:
            raise ValueError('Training/selection target overlaps monitoring development questions')
        if row['question_sha256']!=hashlib.sha256(skill.normalized_question(row['prompt']).encode()).hexdigest():
            raise ValueError('Normalized question hash differs')
        if row['raw_response_sha256']!=hashlib.sha256(row['response'].encode()).hexdigest():
            raise ValueError('Feature response hash differs')
    if candidate_ids&target_ids or any(not r['reference_match_is_independent_gold'] for r in data['targets']):
        raise ValueError('The 24 human-reference gradient targets must be excluded from every training arm')
    if payload.get('projection',{}).get('family')!='countsketch_shake256_v1':
        raise ValueError('This separately declared study uses CountSketch, not an interchangeable projector')
    projection=payload['projection']
    if (projection['dimension']!=config['projection_dimension'] or projection['seed']!=config['projection_seed']
            or [c['id'] for c in payload['checkpoints']]!=[f'update{s:03}' for s in config['checkpoint_updates']]):
        raise ValueError('Gradient checkpoints or projection configuration differ')
    for checkpoint in payload['checkpoints']:
        step=int(checkpoint['id'].removeprefix('update'))
        expected_weight=math.fsum(config['learning_rate']*min(1,index/config['lr_warmup_updates'])
            for index in range(step-3,step+1))/4
        if not math.isclose(checkpoint['weight'],expected_weight,rel_tol=1e-12):
            raise ValueError('Checkpoint weight differs from the frozen warmup learning-rate schedule')
        for role,records in (('candidate',data['candidates']),('target',data['targets'])):
            saved=checkpoint['candidates' if role=='candidate' else 'targets']
            if [r['id'] for r in saved]!=[r['id'] for r in records]:
                raise ValueError('Checkpoint gradient identities/order differ')
            for feature,row in zip(saved,records):
                validate_feature(feature,row,checkpoint['id'],projection['parameter_layout_sha256'],
                    projection['mapping_sha256'],projection['dimension'])
                if (feature.get('protocol_hash')!=plan['protocol_hash'] or feature.get('role')!=role
                        or feature.get('gradient_type')!=('less_adam' if role=='candidate' else 'sgd')):
                    raise ValueError('Gradient feature role/protocol differs')
    score_manifest=load(paths['score_manifest']); score_rows=skill.read_jsonl(paths['scores'])
    if (score_manifest.get('source_sha256')!=hashes['feature_payload']
            or score_manifest.get('scores_sha256')!=hashes['scores']
            or score_manifest.get('method')!=SCORE_METHOD
            or score_manifest.get('reduction')!='mean_per_target_cosine'
            or score_manifest.get('group_aggregation')!='max_after_checkpoint_sum'
            or score_manifest.get('projection')!=projection or score_manifest.get('official_test_used') is not False):
        raise ValueError('Scoring protocol or immutable source hash differs')
    audited=score_projected(payload,reduction='mean_per_target_cosine')
    if score_rows!=audited or {r['id'] for r in score_rows}!=candidate_ids:
        raise ValueError('Gradient scores differ from the audited complete feature payload')
    signal=load(weakness); weak_provenance=signal.get('provenance',{})
    if (weak_provenance.get('source_split')!='train' or weak_provenance.get('official_test_used') is not False
            or weak_provenance.get('source_kind') not in ('training_probe_predictions','development_predictions','development_skill_aggregates')
            or not signal.get('skills')):
        raise ValueError('Frozen skill baseline needs explicit training/development weakness provenance')
    common=[]
    for row in data['candidates']:
        tags=skill.skill_tags(row['prompt'])
        rates=[float(signal['skills'].get(tag,{}).get('smoothed_error_rate',.5)) for tag in tags]
        if any(not math.isfinite(rate) or not 0<=rate<=1 for rate in rates):
            raise ValueError('Frozen weakness rates must be finite probabilities')
        common.append(dict(row,skills=sorted(set(tags)),weakness_score=sum(rates)/len(rates),
            response_tokens=len(row['answer_ids']),input_tokens=len(row['prefix_ids'])+len(row['answer_ids'])))
    return dict(paths=paths,hashes=hashes,summary=summary,feature_plan=plan,feature_config=config,
        projection=projection,tokenizer=tokenizer,rows=common,targets=data['targets'],
        scores=score_rows,development=development_rows,weakness=signal)


def take_until(rows,budget):
    selected=[];total=0
    for row in rows:
        selected.append(row);total+=row['response_tokens']
        if total>=budget:
            return selected
    raise ValueError('Shared pool cannot supply this supervised-token budget without repeated data')


def expose(selected,budget,seed,tokenizer,selector):
    training,updates=skill._exposure(selected,budget,seed,1024)
    arm={'schema_version':1,'arm':SLOT[selector],'selector_name':selector,'selector_method':method(selector),
        'token_budget':budget,'tokens_per_update':1024,'optimizer_updates':len(updates),
        'tokenizer':tokenizer,'training':training,'updates':updates,
        'worker_contract':'Backprop each response-window mean loss multiplied by exposed_tokens/1024; step once per complete effective update.'}
    indexed=validate_arm(arm)
    if len(updates)!=budget//1024 or sum(r['supervised_tokens'] for r in training)!=budget:
        raise ValueError('Exact supervised token/update exposure failed')
    by_id={r['id']:r for r in selected}
    source_counts=Counter(by_id[r['id']]['source'] for r in training)
    origin_counts=Counter(by_id[r['id']]['reference_type'] for r in training)
    source_tokens=defaultdict(int)
    for row in training:
        source_tokens[by_id[row['id']]['source']]+=row['supervised_tokens']
    summary={'examples':len(training),'selected_ids':[r['id'] for r in training],
        'supervised_tokens':budget,'optimizer_updates':len(updates),
        'partial_supervised_tails':sum(r['partial_supervised_tail'] for r in training),
        'input_tokens_once':sum(len(r['input_ids']) for r in training),
        'input_tokens_forwarded':sum(len(indexed[w['id']]['input_ids']) for u in updates for w in u['microbatches']),
        'source_counts':dict(source_counts),'reference_origin_counts':dict(origin_counts),
        'supervised_tokens_by_source':dict(source_tokens),
        'unexposed_preselected_ids':[r['id'] for r in selected if r['id'] not in indexed]}
    return arm,summary


def prepare(teacher_pool,gradient_folder,scores,weakness,development,output,*,token_budget=131072,seeds=(42,43)):
    teacher_pool,gradient_folder,scores,weakness,development,output=map(Path,
        (teacher_pool,gradient_folder,scores,weakness,development,output))
    output=output.resolve()
    if output.exists():
        raise FileExistsError('Prepared studies are immutable; verify this directory or choose a new study ID')
    if not output.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('All private study artifacts must remain under ignored cloud/runs')
    if (type(token_budget) is not int or not 1024<=token_budget<=524288 or token_budget%1024
            or tuple(seeds)!=(42,43)):
        raise ValueError('Use a positive reviewed 1024-token multiple and the prospective seeds 42 and 43')
    proof=gradient_sources(teacher_pool,gradient_folder,scores,development,weakness)
    rows=proof['rows'];by_id={r['id']:r for r in rows}
    if sum(r['response_tokens'] for r in rows)<token_budget:
        raise ValueError('Shared pool cannot supply requested supervised tokens without repetition; no plan was created')
    skill_selected,decisions=skill._choose_valued(rows,token_budget)
    gradient_selected=take_until([by_id[r['id']] for r in proof['scores']],token_budget)
    jobs=[];artifacts={};per_seed={};prepared=[]
    worker_sha=sha(ROOT/'modal_valuation.py')
    source_code={'training_worker_sha256':worker_sha,'selection_code_sha256':sha(Path(__file__)),
        'skill_code_sha256':sha(ROOT/'student_valuation.py'),'gradient_score_code_sha256':sha(ROOT/'gradient_valuation.py')}
    tokenizer=dict(proof['tokenizer'],encoding='apply_chat_template enable_thinking=False; exact response+EOS, add_special_tokens=False')
    common_hash=digest([{'id':r['id'],'question_sha256':r['question_sha256'],'raw_response_sha256':r['raw_response_sha256'],
        'prefix_ids':r['prefix_ids'],'answer_ids':r['answer_ids']} for r in rows])
    for seed in seeds:
        permutation=sorted(rows,key=lambda r:r['id']);random.Random(seed).shuffle(permutation)
        choices={'random':take_until(permutation,token_budget),'skill':skill_selected,'gradient':gradient_selected}
        summaries={}
        for selector in SELECTORS:
            arm,summary=expose(choices[selector],token_budget,seed,tokenizer,selector)
            summaries[selector]=summary
            data={'arm':arm,'development':[{k:r[k] for k in ('id','prompt','gold_answer')} for r in proof['development']]}
            input_raw=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
            run_id=f'{output.name}_seed{seed}_{selector}'
            protocol=dict(COMMON,seed=seed,arm=SLOT[selector],checkpoint_name=selector,selector_name=selector,
                selector_method=method(selector),token_budget=token_budget,optimizer_updates=token_budget//1024,
                development_ids=[r['id'] for r in proof['development']],development_source_sha256=proof['hashes']['development'],
                input_sha256=hashlib.sha256(input_raw).hexdigest(),common_pool_sha256=common_hash,
                sources=proof['hashes'],source_code=source_code,gradient_protocol_hash=proof['feature_plan']['protocol_hash'],
                study_version=VERSION,official_test_used=False,prospective=True,
                optimizer={'name':'torch.optim.AdamW','betas':[.9,.999],'eps':1e-8,'weight_decay':.01,
                    'max_grad_norm':1.0,'lr_schedule':'constant'},
                lora={'r':8,'alpha':16,'dropout':0.0,'target_modules':['q_proj','v_proj']},
                fresh_base=True,data_repetition=False)
            plan=dict(protocol,run_id=run_id,protocol_hash=digest(protocol))
            relative=Path('arms')/run_id
            prepared.append((relative,plan,input_raw))
            jobs.append({'seed':seed,'selector':selector,'worker_arm_slot':SLOT[selector],
                'checkpoint_name':selector,'run_id':run_id,'folder':relative.as_posix(),
                'status':'prepared','paid_work_launched':False,'required_reservation_usd':3,
                'protocol_hash':plan['protocol_hash'],'input_sha256':plan['input_sha256']})
        summaries['overlap_examples']={f'{a}_vs_{b}':len(set(summaries[a]['selected_ids'])&set(summaries[b]['selected_ids']))
            for a,b in (('random','skill'),('random','gradient'),('skill','gradient'))}
        per_seed[str(seed)]=summaries
    for name,path in proof['paths'].items():
        if sha(path)!=proof['hashes'][name]:
            raise ValueError('Source artifacts changed during freeze: '+name)
    if any((teacher_pool/name).exists() for name in ('collector.lock','teacher.lock')):
        raise ValueError('Teacher collection restarted during freeze')
    output.mkdir(parents=True)
    write_rows(output/'common_candidates.jsonl',rows)
    write_new(output/'skill_selection_decisions.json',decisions)
    for relative,plan,input_raw in prepared:
        folder=output/relative;folder.mkdir(parents=True)
        write_new(folder/'plan.json',plan)
        (folder/'input.json').write_bytes(input_raw)
    for path in sorted(output.rglob('*')):
        if path.is_file():artifacts[path.relative_to(output).as_posix()]=sha(path)
    manifest={'schema_version':1,'version':VERSION,'stage':'prepared',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'prospective':True,
        'token_budget':token_budget,'tokens_per_update':1024,'optimizer_updates':token_budget//1024,
        'seeds':list(seeds),'selectors':{s:method(s) for s in SELECTORS},'jobs':jobs,
        'common_pool':{'candidates':len(rows),'available_response_tokens':sum(r['response_tokens'] for r in rows),
            'fraction_of_available_supervised_tokens':token_budget/sum(r['response_tokens'] for r in rows),
            'budget_role':'near_all_data_reference' if token_budget>=.8*sum(r['response_tokens'] for r in rows) else 'selection_contrast',
            'sha256':common_hash,'source_counts':dict(Counter(r['source'] for r in rows)),
            'reference_origin_counts':dict(Counter(r['reference_type'] for r in rows)),
            'heldout_gradient_targets':len(proof['targets']),
            'target_ids_sha256':digest(sorted(r['id'] for r in proof['targets']))},
        'exposures':per_seed,'sources':proof['hashes'],'source_paths':{k:str(p.resolve()) for k,p in proof['paths'].items()},
        'source_code':source_code,'tokenizer':tokenizer,'gradient_projection':proof['projection'],
        'weakness_provenance':proof['weakness']['provenance'],'official_test_used':False,
        'paid_work_launched':False,'gpu_launched':False,'artifacts_sha256':artifacts,
        'limitations':['Three selectors share candidates and exact supervised tokens/updates, but source composition, example counts, input compute and elapsed cost may differ.',
            'The last exposure may mask a response tail while retaining the complete input trace.',
            'Skill weakness and gradient targets are selection-development signals; monitoring on adaptive development is not independent final-test evidence.',
            'CountSketch optimizer-aware alignment is a LESS-inspired proxy, not a reproduction or causal estimate.',
            'Gradient warmup/feature-collection overhead is separate from arm training and belongs in end-to-end cost comparisons.',
            'Every arm starts from the pinned base. The feature-stage warmup adapter is never loaded for training.',
            'The unchanged 1400-second training and 1600-second evaluation guards may preserve a partial adapter; a separate reviewed recovery is required.']}
    write_new(output/'manifest.json',manifest)
    return manifest


def prepare_grid(teacher_pool,gradient_folder,scores,weakness,development,output,*,token_budgets=(32768,65536,131072)):
    """Freeze all declared data-efficiency levels before observing arm outcomes."""
    output=Path(output).resolve()
    budgets=tuple(token_budgets)
    if (output.exists() or not output.is_relative_to((ROOT/'runs').resolve())
            or not budgets or len(set(budgets))!=len(budgets)
            or any(type(b) is not int or not 1024<=b<=524288 or b%1024 for b in budgets)):
        raise ValueError('Use a new private study ID and distinct positive 1024-token budget levels')
    # Audit capacity before creating any directories; never repeat data to fill.
    proof=gradient_sources(Path(teacher_pool),Path(gradient_folder),Path(scores),Path(development),Path(weakness))
    capacity=sum(r['response_tokens'] for r in proof['rows'])
    if max(budgets)>capacity:
        raise ValueError('Declared budget grid exceeds the common verified capacity; no study created')
    output.mkdir(parents=True)
    studies=[]
    for budget in budgets:
        folder=output/f'{output.name}_tokens{budget}'
        manifest=prepare(teacher_pool,gradient_folder,scores,weakness,development,folder,token_budget=budget)
        if manifest['sources']!=proof['hashes']:
            raise ValueError('Study sources changed during prospective grid freeze')
        studies.append({'token_budget':budget,'folder':folder.name,'manifest_sha256':sha(folder/'manifest.json'),
            'budget_role':manifest['common_pool']['budget_role'],'jobs':len(manifest['jobs'])})
    grid={'schema_version':1,'version':VERSION,'stage':'prospective_grid_prepared',
        'token_budgets':list(budgets),'seeds':[42,43],'selectors':list(SELECTORS),
        'common_pool_sha256':manifest['common_pool']['sha256'],'common_available_tokens':capacity,
        'sources':proof['hashes'],'studies':studies,'paid_work_launched':False,'official_test_used':False,
        'interpretation':'Budget levels are frozen before any arm outcomes. Near-all-data levels are reference arms and offer limited selection contrast.'}
    write_new(output/'grid_manifest.json',grid)
    return grid


def verify(output):
    output=Path(output).resolve()
    if (output/'grid_manifest.json').exists():
        grid=load(output/'grid_manifest.json')
        if grid.get('version')!=VERSION or grid.get('paid_work_launched') is not False:
            raise ValueError('Wrong prospective grid identity')
        total=0
        for study in grid['studies']:
            folder=(output/study['folder']).resolve()
            if not folder.is_relative_to(output) or sha(folder/'manifest.json')!=study['manifest_sha256']:
                raise ValueError('Prospective budget grid manifest changed')
            total+=verify(folder)['jobs']
        return {'stage':'verified_prospective_grid','jobs':total,'token_budgets':grid['token_budgets'],'paid_work_launched':False}
    manifest=load(output/'manifest.json')
    if manifest.get('version')!=VERSION or manifest.get('paid_work_launched') is not False:
        raise ValueError('Wrong prepared-study identity')
    for relative,expected in manifest['artifacts_sha256'].items():
        path=(output/relative).resolve()
        if not path.is_relative_to(output) or sha(path)!=expected:
            raise ValueError('Immutable prepared artifact changed: '+relative)
    for name,path in manifest['source_paths'].items():
        if sha(path)!=manifest['sources'][name]:
            raise ValueError('Source artifact changed since preparation: '+name)
    code=manifest['source_code']
    for path,key in ((ROOT/'modal_valuation.py','training_worker_sha256'),(Path(__file__),'selection_code_sha256'),
                     (ROOT/'student_valuation.py','skill_code_sha256'),(ROOT/'gradient_valuation.py','gradient_score_code_sha256')):
        if sha(path)!=code[key]:raise ValueError('Reviewed source implementation changed: '+path.name)
    for job in manifest['jobs']:
        folder=output/job['folder'];plan=load(folder/'plan.json');data=load(folder/'input.json')
        validate_arm(data['arm'])
        if plan['protocol_hash']!=digest({k:v for k,v in plan.items() if k not in ('run_id','protocol_hash','resume_from')}):
            raise ValueError('Prepared plan protocol changed')
        if plan['selector_name']!=job['selector'] or plan['checkpoint_name']!=job['selector'] or data['arm']['arm']!=SLOT[job['selector']]:
            raise ValueError('Legacy worker slot must not obscure selector identity')
        if any(plan.get(key)!=value for key,value in COMMON.items()):
            raise ValueError('Common training or inference protocol changed')
        if (plan['token_budget']!=manifest['token_budget'] or plan['optimizer_updates']!=manifest['token_budget']//1024
                or plan['seed']!=job['seed'] or data['arm']['token_budget']!=manifest['token_budget']):
            raise ValueError('Matched token/update/seed protocol changed')
    if {(job['seed'],job['selector']) for job in manifest['jobs']}!={(seed,selector) for seed in (42,43) for selector in SELECTORS} or len(manifest['jobs'])!=6:
        raise ValueError('Require all six prospective matched-arm plans')
    return {'stage':'verified_prepared','jobs':len(manifest['jobs']),'paid_work_launched':False,
        'token_budget':manifest['token_budget'],'selectors':list(SELECTORS)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare')
    prep.add_argument('--teacher-pool',type=Path,required=True);prep.add_argument('--gradient-folder',type=Path,required=True)
    prep.add_argument('--scores',type=Path,required=True);prep.add_argument('--weakness',type=Path,required=True)
    prep.add_argument('--development',type=Path,required=True);prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--token-budget',type=int,default=131072)
    check=sub.add_parser('verify');check.add_argument('--output',type=Path,required=True)
    grid=sub.add_parser('prepare-grid')
    for name in ('teacher-pool','gradient-folder','scores','weakness','development','output'):
        grid.add_argument('--'+name,type=Path,required=True)
    grid.add_argument('--token-budgets',type=int,nargs='+',default=[32768,65536,131072])
    args=parser.parse_args()
    if args.action=='verify':result=verify(args.output)
    elif args.action=='prepare-grid':
        result=prepare_grid(args.teacher_pool,args.gradient_folder,args.scores,args.weakness,args.development,args.output,token_budgets=args.token_budgets)
        result={key:result[key] for key in ('stage','token_budgets','common_available_tokens','paid_work_launched')}
    else:
        manifest=prepare(args.teacher_pool,args.gradient_folder,args.scores,args.weakness,args.development,args.output,token_budget=args.token_budget)
        result={'stage':'prepared','jobs':len(manifest['jobs']),'token_budget':manifest['token_budget'],
            'shared_candidates':manifest['common_pool']['candidates'],'paid_work_launched':False}
    print(json.dumps(result))
