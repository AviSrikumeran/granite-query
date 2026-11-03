"""Prepare/poll a separately reviewed bounded gradient-feature stage; no auto-launch.

Preparation only accepts a completed teacher pool. New targets are held out from
that new cohort; existing477/four-arm artifacts are never edited. Resume requires
a terminal saved Modal call and exactly identical frozen input/protocol.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import shutil
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud.gradient_feature_contract import (MODEL,REVISION,canonical,sha,fixed_config,
    build_warmup,calibration_ids,validate_input,validate_resume)
from cloud.student_valuation import (read_jsonl,load_tokenizer,encode_example,_verified,
    normalized_question,skill_tags)
from cloud.prepare_verified_math import EXCLUSION_PATHS


def write_new(path,value):
    with Path(path).open('xb') as handle:
        handle.write(canonical(value))


def save(path,value):
    path=Path(path); temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(canonical(value)); temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def prepare(pool,output,*,target_count=24,candidate_limit=1800,seed=20261103,dimension=1024,exclude_paths=(),tokenizer=None):
    pool,output=Path(pool).resolve(),Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new immutable feature-stage directory')
    if not output.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('Private inputs/features must remain under ignored cloud/runs')
    if not 1<=target_count<=32:
        raise ValueError('At most32 selection-development targets')
    if not 24<=candidate_limit<=1800:
        raise ValueError('Candidate limit must be between24 and1800')
    summary_path=pool/'teacher_summary.json'; eligible_path=pool/'eligible.jsonl'
    if any((pool/name).exists() for name in ('collector.lock','teacher.lock')):
        raise ValueError('Teacher collector lock remains; inspect its process before freezing features')
    summary_raw=summary_path.read_bytes(); summary=json.loads(summary_raw)
    if summary.get('stage')!='completed' or summary.get('official_test_accessed') is not False:
        raise ValueError('Wait for a completed frozen teacher pool with no official-test access')
    eligible_raw=eligible_path.read_bytes(); rows=read_jsonl(eligible_path)
    if summary.get('eligible')!=len(rows):
        raise ValueError('Teacher summary and eligible-row count differ')
    if any(row.get('source_split')!='train' for row in rows) or len({r['id'] for r in rows})!=len(rows):
        raise ValueError('Only distinct official-training-split teacher rows are allowed')
    forbidden_ids,forbidden_hashes,exclusions=set(),set(),[]
    for path in (*EXCLUSION_PATHS,ROOT.parent/'ranking/runs/gsm8k_preview_128_seed42/target_queries.jsonl',*exclude_paths):
        path=Path(path)
        if not path.exists():
            raise FileNotFoundError('Required exclusion artifact is missing: '+path.name)
        excluded=read_jsonl(path)
        if any(row.get('source_split','train')!='train' for row in excluded):
            raise ValueError('Selection exclusions must not open official-test data')
        forbidden_ids.update(row['id'] for row in excluded)
        forbidden_hashes.update(sha(normalized_question(row['prompt']).encode()) for row in excluded)
        exclusions.append(dict(sha256=sha(path.read_bytes()),count=len(excluded)))
    config=fixed_config(seed,dimension); tokenizer=tokenizer or load_tokenizer(local_files_only=True)
    encoded=[]; seen_hashes=set(); removed=[]
    for row in sorted(rows,key=lambda r:r['id']):
        question_hash=sha(normalized_question(row['prompt']).encode())
        if row['id'] in forbidden_ids or question_hash in forbidden_hashes or question_hash in seen_hashes:
            removed.append(dict(id=row['id'],reason='reserved_or_duplicate_question')); continue
        if not _verified(row):
            raise ValueError('Eligible file contains an unverifiable/incomplete response: '+row['id'])
        response_hash=sha(row['response'].encode())
        recorded=row.get('raw_response_sha256',row.get('generation',{}).get('raw_response_sha256'))
        if recorded is not None and recorded!=response_hash:
            raise ValueError('Teacher trace differs from its recorded original response hash')
        tokens=encode_example(row,tokenizer)
        if tokens['input_tokens']>config['context_limit'] or tokens['response_tokens']>config['max_response_tokens']:
            raise ValueError('Frozen eligible trace exceeds gradient context cap: '+row['id'])
        independent=(row.get('reference_match_is_independent_gold') is True or
                     (row.get('reference_type')=='human_dataset_answer' and
                      row.get('reference_match_is_independent_gold') is not False))
        encoded.append(dict(row,**tokens,question_sha256=question_hash,
            raw_response_sha256=response_hash,verified_final_answer=True,
            reference_match_is_independent_gold=independent))
        seen_hashes.add(question_hash)
    target_options=[r for r in encoded if r['reference_match_is_independent_gold']]
    if len(target_options)<target_count:
        raise ValueError('Insufficient independently referenced human-data targets; do not use majority-vote labels as gold')
    # Stable round-robin groups reduce accidental domination by the largest tag.
    groups={}
    random.Random(seed+1).shuffle(target_options)
    for row in target_options:
        group=sorted(skill_tags(row['prompt']))[0]
        groups.setdefault(group,[]).append(row)
    targets=[]
    while len(targets)<target_count:
        for group in sorted(groups):
            if groups[group] and len(targets)<target_count:
                targets.append(dict(groups[group].pop(),group=group))
    target_ids={r['id'] for r in targets}
    candidates=[r for r in encoded if r['id'] not in target_ids]
    random.Random(seed+2).shuffle(candidates)
    unused=max(0,len(candidates)-candidate_limit)
    candidates=sorted(candidates[:candidate_limit],key=lambda r:r['id'])
    targets=sorted(targets,key=lambda r:r['id'])
    if len(candidates)<24:
        raise ValueError('Need at least24 disjoint candidates after target holdout')
    warmup_rows=list(candidates); random.Random(seed+3).shuffle(warmup_rows)
    warmup=build_warmup(warmup_rows[:24],config)
    data=dict(candidates=candidates,targets=targets,warmup=warmup,
              calibration_ids=calibration_ids(candidates,config['calibration_examples']))
    backend=getattr(tokenizer,'backend_tokenizer',None)
    provenance=dict(teacher_summary_sha256=sha(summary_raw),eligible_sha256=sha(eligible_raw),
                    teacher_run_id=summary.get('run_id'),exclusions=exclusions,
                    target_selection='Seeded human-reference candidates balanced across frozen lexical groups; held out from every arm',
                    target_groups={g:sum(r['group']==g for r in targets) for g in sorted({r['group'] for r in targets})},
                    selected_candidates=len(candidates),heldout_targets=len(targets),unused_due_to_cap=unused,
                    removed_overlap=len(removed),official_test_used=False,
                    tokenizer={'model':MODEL,'revision':REVISION,
                        'backend_sha256':sha(backend.to_str().encode()) if backend else 'test-tokenizer',
                        'chat_template_sha256':sha(str(tokenizer.chat_template).encode())})
    protocol=dict(config=config,input_sha256=sha(canonical(data)),sources=provenance,
        candidate_ids=[r['id'] for r in candidates],target_ids=[r['id'] for r in targets])
    plan=dict(run_id=output.name,protocol=protocol,protocol_hash=sha(canonical(protocol)),
              resume_from=None,created_at_utc=datetime.now(timezone.utc).isoformat(),stage='prepared',
              reviewed_for_launch=False)
    validate_input(data,plan)
    if eligible_path.read_bytes()!=eligible_raw or summary_path.read_bytes()!=summary_raw:
        raise ValueError('Teacher artifacts changed during freeze; wait for collection to finish')
    output.mkdir(parents=True)
    write_new(output/'input.json',data); write_new(output/'plan.json',plan)
    write_new(output/'cohort_manifest.json',dict(provenance,protocol_hash=plan['protocol_hash']))
    # These are the NEW shared candidate/target cohorts for matched controls;
    # they never replace previous pool files.
    for filename,records in [('candidates.jsonl',candidates),('targets.jsonl',targets)]:
        with (output/filename).open('xb') as handle:
            for row in records:
                handle.write(canonical(row))
    write_new(output/'public_summary.json',dict(stage='prepared',method=config['method'],
        candidates=len(candidates),selection_development_targets=len(targets),
        projected_features_complete=False,paid_work_launched=False,official_test_used=False,
        limitation='LESS-inspired CountSketch proxy; no model gradients or gains measured yet'))
    return plan


def prepare_resume(folder,output):
    folder,output=Path(folder).resolve(),Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('Resume requires a new private run directory')
    launch=read(folder/'launch.json'); terminal=read(folder/'terminal.json')
    if not launch.get('call_id') or terminal.get('call_id')!=launch['call_id'] or terminal.get('confirmed_terminal') is not True:
        raise ValueError('Reconcile the existing call before preparing any resume')
    if terminal.get('stage')=='completed':
        raise ValueError('Completed feature collection must not be resumed')
    from cloud.gradient_recovery import verify_execution_sources,assess_continuation
    verify_execution_sources(folder)
    decision=assess_continuation(folder) if terminal.get('stage')=='calibration_refused' else None
    previous=read(folder/'plan.json'); current=dict(previous,run_id=output.name,resume_from=folder.name,
        stage='prepared_resume',reviewed_for_launch=False,created_at_utc=datetime.now(timezone.utc).isoformat())
    validate_resume(previous,current); validate_input(read(folder/'input.json'),current)
    current['execution_sources_sha256']=sha((folder/'execution_sources.json').read_bytes())
    if decision is not None:
        current['recovery_evidence_manifest_sha256']=sha((folder/'recovery_remote_manifest.json').read_bytes())
    output.mkdir(parents=True)
    for name in ('input.json','cohort_manifest.json','candidates.jsonl','targets.jsonl'):
        shutil.copyfile(folder/name,output/name)
    shutil.copyfile(folder/'execution_sources.json',output/'execution_sources.json')
    shutil.copytree(folder/'execution_sources',output/'execution_sources')
    if decision is not None:
        write_new(output/'recovery_decision.json',dict(decision,parent_run_id=folder.name,parent_call_id=launch['call_id']))
    write_new(output/'plan.json',current)
    write_new(output/'public_summary.json',dict(stage='prepared_resume',method=current['protocol']['config']['method'],
        projected_features_complete=False,paid_work_launched=False,official_test_used=False))
    return current


def poll(folder):
    import modal
    folder=Path(folder); launch=read(folder/'launch.json')
    if not launch.get('call_id'):
        raise ValueError('Ambiguous launch: reconcile it instead of retrying')
    state=modal.Dict.from_name('granite-query-training-progress')
    status=state.get(folder.name,None)
    if status is None:
        owner=state.get('gradient-owner:'+folder.name,None)
        if owner and owner.get('call_id')==launch['call_id']:
            plan=read(folder/'plan.json')
            status={'stage':'restoring_saved_artifacts' if plan.get('resume_from') else 'initializing',
                'call_id':launch['call_id'],'ownership_evidence':'durable_gradient_owner'}
        else:
            status={'stage':'queued'}
    save(folder/'remote_status.json',status)
    try:
        result=modal.FunctionCall.from_id(launch['call_id']).get(timeout=0)
    except TimeoutError:
        return dict(stage=status.get('stage'),call_id=launch['call_id'],confirmed_terminal=False)
    except Exception as error:
        terminal=(isinstance(error,(modal.exception.FunctionTimeoutError,modal.exception.UserCodeException)) or
                  (status.get('call_id')==launch['call_id'] and status.get('stage')=='failed' and
                   status.get('error_type')==type(error).__name__))
        value=dict(stage='failed' if terminal else 'monitoring_error',error_type=type(error).__name__,
                   call_id=launch['call_id'],confirmed_terminal=terminal)
        if terminal:
            save(folder/'terminal.json',value)
        return value
    save(folder/'result.json',result)
    save(folder/'terminal.json',dict(call_id=launch['call_id'],confirmed_terminal=True,stage=result['stage']))
    save(folder/'public_summary.json',result['public_summary'])
    return result['public_summary']


def download(folder):
    """Private projected features only; never download them into public docs."""
    import modal
    folder=Path(folder); result=read(folder/'result.json')
    if result.get('stage')!='completed' or not result.get('projected_features_complete'):
        raise ValueError('Partial feature stores cannot be scored as completed collection')
    target=folder/'features_payload.json'
    if target.exists():
        if sha(target.read_bytes())!=result['feature_payload_sha256']:
            raise ValueError('Local feature export changed')
        return {'downloaded':True,'existing':True}
    volume=modal.Volume.from_name('granite-query-training-artifacts')
    temporary=folder/'features_payload.download'
    total=0
    with temporary.open('wb') as handle:
        for block in volume.read_file(folder.name+'/features_payload.json'):
            total+=len(block)
            if total>200*1024*1024:
                raise ValueError('Projected feature export exceeds200MiB cap')
            handle.write(block)
    if sha(temporary.read_bytes())!=result['feature_payload_sha256']:
        raise ValueError('Remote feature payload hash mismatch')
    temporary.replace(target)
    return {'downloaded':True,'bytes':total}


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare'); prep.add_argument('--pool',type=Path,required=True); prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--target-count',type=int,default=24); prep.add_argument('--seed',type=int,default=20261103)
    prep.add_argument('--candidate-limit',type=int,default=1800)
    prep.add_argument('--dimension',type=int,default=1024); prep.add_argument('--exclude-questions',type=Path,action='append',default=[])
    resume=sub.add_parser('prepare-resume'); resume.add_argument('--folder',type=Path,required=True); resume.add_argument('--output',type=Path,required=True)
    for action in ('poll','download','download-recovery-evidence'):
        item=sub.add_parser(action); item.add_argument('--folder',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='prepare':
        value=prepare(args.pool,args.output,target_count=args.target_count,candidate_limit=args.candidate_limit,seed=args.seed,
                      dimension=args.dimension,exclude_paths=args.exclude_questions)
        print(json.dumps(dict(stage=value['stage'],protocol_hash=value['protocol_hash'],paid_work_launched=False)))
    elif args.action=='prepare-resume':
        value=prepare_resume(args.folder,args.output); print(json.dumps(dict(stage=value['stage'],paid_work_launched=False)))
    elif args.action=='download-recovery-evidence':
        from cloud.gradient_recovery import download_evidence
        print(json.dumps(download_evidence(args.folder)))
    else:
        print(json.dumps(poll(args.folder) if args.action=='poll' else download(args.folder)))


if __name__=='__main__':
    main()
