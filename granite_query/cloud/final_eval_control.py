"""Offline final-protocol sealing and durable access permits; no test loader.

This module never opens/downloads official test data, launches compute, contacts
an API, or mutates the budget. The later reviewed loader must claim access before
reading the split, persist a hash receipt and reuse that receipt on recovery.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import random
import re
import sys
import uuid

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'runs/supervisor'
ACCESS=STATE/'final_test_access.json'
sys.path.insert(0,str(ROOT.parent))
from cloud.student_valuation import MODEL,REVISION,PREFIX
from cloud.comparison_metrics import summarize
from cloud.serving_control import LIMITS as SERVING_LIMITS

VERSION='sealed256-final-v1'
SEED=20261110
POPULATION=1319
COUNT=256
ROLES={'test_loader','granite_evaluator','deepseek_evaluator'}
CAPABILITIES={
    'test_loader':{'permit_before_read':True,'hash_checked_persisted_resume':True},
    'granite_evaluator':{'adapter_hashes_before_load':True,'supports_base_and_chosen':True,
        'questions':256,'max_new_tokens':512,'enable_thinking':False,'evaluation_batch_size':8},
    'deepseek_evaluator':{'questions':256,'max_attempts':256,'max_tokens':512,
        'thinking_enabled':False,'automatic_retries':0,'same_user_prompt':True}}


def now():return datetime.now(timezone.utc).isoformat()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def safe_hash(value):return isinstance(value,str) and bool(re.fullmatch('[a-f0-9]{64}',value))
def safe_name(value):return isinstance(value,str) and bool(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',value))


def write_once(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(json.dumps(value,indent=2,ensure_ascii=False)+'\n');handle.flush();os.fsync(handle.fileno())


def private(path):
    value=Path(path).resolve()
    if not value.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('Final artifacts must stay under ignored cloud/runs')
    return value


def execution_sources(review_path):
    if review_path is None:return None
    review=load(review_path)
    if (review.get('reviewed') is not True or review.get('protocol_version')!=VERSION
            or set(review.get('roles',{}))!=ROLES):
        raise ValueError('An explicit reviewed final-execution source bundle is required')
    for role,entry in review['roles'].items():
        path=Path(entry.get('path',''))
        if path.suffix!='.py' or not path.is_file() or sha(path)!=entry.get('sha256'):
            raise ValueError('Reviewed execution source changed: '+role)
        if entry.get('capabilities')!=CAPABILITIES[role]:
            raise ValueError('Final executor does not establish the required bounded contract: '+role)
    return review


def chosen_checkpoint(folder,adapter):
    folder,adapter=private(folder),private(adapter)
    if not adapter.is_relative_to(folder) or adapter.name!='adapter':
        raise ValueError('Require the actual downloaded adapter directory inside its chosen run')
    plan=load(folder/'plan.json');result=load(folder/'result.json')
    if (result.get('stage')!='completed' or result.get('plan')!=plan
            or result.get('held_out_test_used') is not False or plan.get('mode')!='train_evaluate'
            or plan.get('model')!=MODEL or plan.get('revision')!=REVISION
            or plan.get('run_id')!=folder.name):
        raise ValueError('Choose a completed pinned-base development checkpoint before opening test data')
    checkpoint=plan.get('checkpoint_name',plan.get('arm'))
    if not safe_name(checkpoint) or not safe_name(folder.name):
        raise ValueError('Chosen checkpoint and artifact run require stable safe identities')
    evaluations=result.get('evaluations',{})
    if set(evaluations)!={checkpoint} or len(evaluations[checkpoint])!=64:
        raise ValueError('Chosen checkpoint needs its completed 64-question development result')
    if [r['id'] for r in evaluations[checkpoint]]!=plan['development_ids'] or len(set(plan['development_ids']))!=64:
        raise ValueError('Chosen development result identity/order differs')
    config=load(adapter/'adapter_config.json')
    if (config.get('base_model_name_or_path')!=MODEL or config.get('r')!=8
            or config.get('lora_alpha')!=16 or config.get('lora_dropout')!=0
            or set(config.get('target_modules',[]))!={'q_proj','v_proj'}):
        raise ValueError('Selected adapter configuration differs from the evaluated LoRA contract')
    inventory={}
    for path in sorted(adapter.rglob('*')):
        if path.is_symlink():raise ValueError('Checkpoint inventory cannot contain symlinks')
        if path.is_file():inventory[path.relative_to(adapter).as_posix()]=sha(path)
    if (not all(name in inventory for name in ('adapter_config.json','adapter_model.safetensors'))
            or (adapter/'adapter_model.safetensors').stat().st_size==0):
        raise ValueError('Actual selected adapter configuration and nonempty weights are required')
    return {'final_choice':True,'checkpoint_id':checkpoint,'run_id':folder.name,'adapter_subpath':'adapter',
        'local_adapter_path':str(adapter),'files_sha256':inventory,
        'plan_path':str(folder/'plan.json'),'plan_sha256':sha(folder/'plan.json'),
        'development_result_path':str(folder/'result.json'),'development_result_sha256':sha(folder/'result.json'),
        'development_metrics':summarize(evaluations[checkpoint])}


def freeze(chosen_run,adapter_directory,output,*,execution_review=None):
    output=private(output);access_path=private(ACCESS)
    if access_path.exists():raise ValueError('Final access already began; no new checkpoint/protocol or tuning is allowed')
    if output.exists():raise FileExistsError('Final protocol directories are immutable; verify the existing freeze')
    selected=chosen_checkpoint(chosen_run,adapter_directory)
    review=execution_sources(execution_review)
    indices=sorted(random.Random(SEED).sample(range(POPULATION),COUNT))
    source_paths={'control':Path(__file__).resolve(),'granite_worker':ROOT/'modal_valuation.py',
        'scoring':ROOT/'comparison_metrics.py','paired_statistics':ROOT/'evaluation_stats.py',
        'prompt_tokenization':ROOT/'student_valuation.py','serving_limits':ROOT/'serving_control.py'}
    sources={name:{'path':str(path.resolve()),'sha256':sha(path)} for name,path in source_paths.items()}
    token=uuid.uuid4().hex
    protocol={'version':VERSION,'selected':selected,'base':{'model':MODEL,'revision':REVISION},
        'dataset':{'repository':'openai/grade-school-math','revision':'3101c7d5072418e28b9008a6636bde82a006892c',
            'relative_path':'grade_school_math/data/test.jsonl','source_split':'test',
            'expected_population':POPULATION,'sample_count':COUNT,'sampling_seed':SEED,
            'sampling_algorithm':'sorted(random.Random(seed).sample(range(1319),256))',
            'indices':indices,'indices_sha256':digest(indices),'full_test_evaluation':False},
        'inference':{'user_prefix':PREFIX,'max_new_tokens':512,'enable_thinking':False,
            'do_sample':False,'granite_evaluation_batch_size':8,'granite_padding_side':'left',
            'granite_context_limit':2048,'same_question_ids_for_all_checkpoints':True,
            'latency_note':'Granite timings are amortized batch8 GPU generation; teacher timings are API round trips and cannot establish a matched latency ranking.'},
        'teacher':{'enabled':True,'model':'deepseek-v4-pro','thinking':{'type':'disabled'},
            'max_tokens':512,'temperature':0,'max_attempts':256,'automatic_retries':0,
            'max_concurrent_requests':4,'max_input_tokens_bound':2000,
            'peak_request_cost_bound_usd':256*(2000*1.32+512*3.96)/1000000,
            'reported_revision_policy':'Save actual response model; API alias is mutable',
            'input_bound_policy':'Enforce at most 1900 serialized-message UTF8 bytes before dispatch; retain bounded failures and never resample a different question',
            'api_requests_are_not_gpu_batches':True,'filter_on_answer_correctness':False},
        'granite_worker_template':{'module':'cloud.modal_valuation','mode':'evaluate_saved',
            'evaluation_kind':'final_test','evaluation_batch_size':8,'max_new_tokens':512,
            'timeout_seconds':1800,'application_evaluation_guard_seconds':1600,
            'hard_cpu_cores':4,'hard_memory_gib':32,'max_containers':1,'automatic_retries':0},
        'execution_sources':review,'execution_ready':review is not None,'source_code':sources,
        'access_owner_sha256':digest(token),'access_registry_path':str(access_path),
        'policy':{'freeze_choice_before_test':True,'no_tuning_after_access':True,
            'access_permit_before_source_read':True,'one_tracked_dataset_access_with_hash_matched_resume':True,
            'paired_all_attempts_including_failures':True,'raw_outputs_retained':True},
        'serving_trial_separate':{'max_requests':SERVING_LIMITS['max_requests'],
            'max_output_tokens':SERVING_LIMITS['max_output_tokens'],'benchmark_output_tokens':512,
            'nominal_output_cap_matches_benchmark':SERVING_LIMITS['max_output_tokens']==512,
            'execution_configuration_matches_benchmark':False,
            'deployment_status':'prepared_only','evaluation_does_not_deploy_api':True},
        'budget':{'protected_modal_usd':5,'includes_final_evaluation_and_capped_api':True,
            'funds_reserved_by_this_control':False,'paid_work_launched':False},
        'limitations':['This seeded 256-question subset is not the full 1319-question GSM8K test set.',
            'Numerical final-answer checks do not verify all reasoning steps.',
            'The API shares the nominal512-token output cap but cold-start, single-request L4 time bounds are a separate serving configuration; benchmark-equivalent performance is not established.',
            'The existing generic Granite worker needs reviewed adapter-hash enforcement before reuse for the selected final checkpoint.',
            'The older matched_teacher collector uses thinking/4096 and caps128 rows; it cannot execute this protocol unchanged.']}
    manifest={'schema_version':1,'created_at_utc':now(),'protocol':protocol,'freeze_sha256':digest(protocol),
        'stage':'frozen_ready_for_authorized_access' if review else 'prepared_waiting_execution_review',
        'official_test_accessed_by_this_control':False}
    output.mkdir(parents=True)
    write_once(output/'access_owner.json',{'owner_token':token,'freeze_sha256':manifest['freeze_sha256']})
    write_once(output/'freeze.json',manifest)
    return manifest


def verify(folder):
    folder=private(folder);manifest=load(folder/'freeze.json');protocol=manifest['protocol']
    if digest(protocol)!=manifest.get('freeze_sha256') or protocol.get('version')!=VERSION:
        raise ValueError('Frozen final protocol changed')
    for source in protocol['source_code'].values():
        if sha(source['path'])!=source['sha256']:raise ValueError('Frozen final source code changed')
    selected=protocol['selected'];adapter=Path(selected['local_adapter_path'])
    if sha(selected['plan_path'])!=selected['plan_sha256'] or sha(selected['development_result_path'])!=selected['development_result_sha256']:
        raise ValueError('Chosen checkpoint provenance changed after final freeze')
    for name,expected in selected['files_sha256'].items():
        path=(adapter/name).resolve()
        if PurePosixPath(name).is_absolute() or not path.is_relative_to(adapter.resolve()) or sha(path)!=expected:
            raise ValueError('Selected adapter changed after final freeze')
    if protocol['execution_sources'] is not None:
        # Review content is frozen in protocol; verify each exact executable.
        for entry in protocol['execution_sources']['roles'].values():
            if sha(entry['path'])!=entry['sha256']:raise ValueError('Reviewed final executor changed')
    owner=load(folder/'access_owner.json')
    if owner.get('freeze_sha256')!=manifest['freeze_sha256'] or digest(owner.get('owner_token'))!=protocol['access_owner_sha256']:
        raise ValueError('Access owner identity changed')
    return manifest


def begin_access(folder,*,owner_token,loader_authorized=False):
    """Future loader calls this BEFORE any official-test source read/download."""
    manifest=verify(folder);protocol=manifest['protocol'];path=private(protocol['access_registry_path'])
    if not loader_authorized or not protocol['execution_ready']:
        raise ValueError('Final execution sources and actual loader authorization are required before access')
    if digest(owner_token)!=protocol['access_owner_sha256']:
        raise ValueError('Final access belongs to a different durable owner')
    identity={'freeze_sha256':manifest['freeze_sha256'],'owner_sha256':digest(owner_token)}
    value=dict(identity,stage='access_begun_before_source_read',began_at_utc=now(),test_access_count=1,
        note='The permit precedes loading; after an interruption the data may have been read. Only the same sealed protocol/owner may recover persisted artifacts.')
    try:write_once(path,value)
    except FileExistsError:
        prior=load(path)
        if any(prior.get(key)!=expected for key,expected in identity.items()):
            raise ValueError('Another final protocol/owner already accessed the sealed split')
        return dict(prior,resume=True)
    return dict(value,resume=False)


def bind_dataset_receipt(folder,*,owner_token,dataset_sha256,population_count,sample_rows_sha256,indices):
    """Record metadata from the future loader, without opening any dataset here."""
    manifest=verify(folder);protocol=manifest['protocol'];registry=private(protocol['access_registry_path'])
    if not registry.exists():
        raise ValueError('Dataset receipt cannot precede the durable access permit')
    prior=load(registry)
    if (prior.get('freeze_sha256')!=manifest['freeze_sha256'] or prior.get('owner_sha256')!=digest(owner_token)
            or digest(owner_token)!=protocol['access_owner_sha256']):
        raise ValueError('Dataset receipt lacks the sealed access owner')
    if (not safe_hash(dataset_sha256) or not safe_hash(sample_rows_sha256)
            or population_count!=POPULATION or indices!=protocol['dataset']['indices']):
        raise ValueError('Official source/sample identity differs from the predeclared final protocol')
    receipt={'freeze_sha256':manifest['freeze_sha256'],'owner_sha256':digest(owner_token),
        'dataset_sha256':dataset_sha256,'population_count':population_count,
        'sample_rows_sha256':sample_rows_sha256,'indices_sha256':digest(indices),'test_access_count':1}
    path=registry.with_name(registry.stem+'.dataset_receipt.json')
    try:write_once(path,receipt)
    except FileExistsError:
        if load(path)!=receipt:raise ValueError('Persisted official-test dataset/sample changed; fresh reads are not authorized')
        return dict(receipt,resume=True)
    return dict(receipt,resume=False)


def public_summary(manifest):
    protocol=manifest['protocol']
    return {'stage':manifest['stage'],'sample_count':COUNT,'official_population':POPULATION,
        'full_test_evaluation':False,'max_output_tokens':512,'granite_batch_size':8,
        'thinking_enabled':False,'execution_ready':protocol['execution_ready'],
        'test_read_by_preparation':False,'paid_work_launched':False,
        'api_trial_request_cap':protocol['serving_trial_separate']['max_requests'],
        'api_trial_output_cap':protocol['serving_trial_separate']['max_output_tokens'],
        'api_nominal_output_cap_matches_benchmark':protocol['serving_trial_separate']['nominal_output_cap_matches_benchmark'],
        'api_execution_configuration_matches_benchmark':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    create=sub.add_parser('freeze');create.add_argument('--chosen-run',type=Path,required=True)
    create.add_argument('--adapter-directory',type=Path,required=True);create.add_argument('--output',type=Path,required=True)
    create.add_argument('--execution-review',type=Path)
    check=sub.add_parser('verify');check.add_argument('--folder',type=Path,required=True)
    args=parser.parse_args()
    value=(freeze(args.chosen_run,args.adapter_directory,args.output,execution_review=args.execution_review)
        if args.action=='freeze' else verify(args.folder))
    print(json.dumps(public_summary(value)))
