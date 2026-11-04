"""Development-only compatibility plans/receipts, never a final-data permit.

Imports are pure. Explicit prepare reads only the one existing human TRAIN
development artifact and teaching metadata; it neither chooses a checkpoint or
test count nor launches, reserves, downloads weights or touches the access registry.
"""
from pathlib import Path
import hashlib
import json
import math
import re
import unicodedata

from cloud import final_scale_contract as contract
from cloud import final_scale_seal as seal
from cloud import final_scale_execution as execution
from cloud import granite_lora_layout as layout
from cloud.valuation_contract import trim_generation
from cloud.comparison_metrics import score

ROOT=Path(__file__).resolve().parent
HUMAN=ROOT/'runs/human_math_cohort2048_dev200_v1'
COHORT_PLAN_SHA='ad7bff24399125f09ad9b66a5965f11f641b74a86ae0c3b6f0a15f63836cd103'
DEVELOPMENT_SHA='cccdce864d728e6b43d9d4de866e719bfd9c706cc735a3a3d429095835c767c7'
TEACHING_SHA='36a508f957e0d244d9ac6529370c9cc1ce36339e5e7e1e8fa47d2b0ccf9e1c94'
VERSION='final-scale-development-compat-v1'
ROLE='development_runtime_compatibility'
DEPENDENCIES={'torch':'2.6.0','transformers':'4.57.1','peft':'0.17.1','accelerate':'1.10.1','safetensors':'0.6.2'}
REQUIRED={'granite_executor':{'final_scale_compat.py','modal_final_compat.py','modal_final_scale.py','final_scale_execution.py'},
    'checkpoint_validator':{'final_scale_artifacts.py','granite_lora_layout.py'},'model_image':{'modal_train.py'},
    'scoring':{'comparison_metrics.py'}}
FIXED={'development_count':200,'training_performed':False,'official_test_used':False,'max_new_tokens':512,
    'enable_thinking':False,'do_sample':False,'evaluation_batch_size':8,'max_input_tokens':1536,'context_limit':2048,
    'hard_timeout_seconds':1800,'application_guard_seconds':1600,'hard_cpu_cores':4,'hard_memory_gib':32,'automatic_retries':0}


def digest(value):return contract.digest(value)
def encoded(value):return execution.payload_bytes(value)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def record(value,key):return dict(value,**{key:digest(value)})
def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0
def read_rows(path):return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]


def check(value,key):
    contract.require_hash(value.get(key))
    if digest({k:v for k,v in value.items() if k!=key})!=value[key]:raise ValueError('Compatibility hash differs: '+key)


def validate_sources(value):
    contract.validate(value);p=value['protocol'];contract.validate_sources(value,p['source_hashes'],complete=True)
    for role,names in REQUIRED.items():
        if not names<=set(p['source_roles'][role]):raise ValueError('Compatibility producer/helpers are not source-bound')


def input_hash(row,prefix):
    return digest({'id':row['id'],'source_index':row['source_index'],
        'messages':[{'role':'user','content':prefix+row['prompt']}]})


def validate_metadata(plan,descriptor,authorization):
    check(plan,'plan_sha256');check(authorization,'authorization_sha256')
    value=authorization['sealed']['contract'];validate_sources(value)
    p=value['protocol'];checkpoint=authorization['sealed']['checkpoint']
    if p['selected'] is None or checkpoint['selected']!=p['selected']:raise ValueError('Explicit actual chosen inventory is required')
    hashes=checkpoint['adapter_files_sha256']
    if (not isinstance(hashes,dict) or not {'adapter_config.json','adapter_model.safetensors'}<=set(hashes)
            or any(not contract.HASH.fullmatch(v) for v in hashes.values())
            or digest(hashes)!=p['selected']['adapter_inventory_sha256']):raise ValueError('Actual adapter inventory differs')
    for name in hashes:execution.volume_path(name)
    execution.volume_path(authorization['adapter_path'])
    model_config=authorization['model_config'];execution.volume_path(model_config['volume_path'])
    if (model_config['sha256']!=layout.EVIDENCE['local_config']['sha256'] or type(model_config['bytes']) is not int
            or not 0<model_config['bytes']<=4*1024*1024):raise ValueError('Pinned staged model config differs')
    if (plan.get('version')!=VERSION or plan.get('role')!=ROLE or any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in FIXED.items())
            or plan.get('model')!=contract.MODEL or plan.get('revision')!=contract.REVISION
            or plan.get('authorization_sha256')!=authorization['authorization_sha256']
            or plan.get('source_bundle_sha256')!=digest(p['source_hashes'])
            or plan.get('inference_sha256')!=digest(p['inference'])
            or plan.get('adapter_model_sha256')!=hashes['adapter_model.safetensors']
            or plan.get('adapter_inventory_sha256')!=p['selected']['adapter_inventory_sha256']
            or plan.get('development_source_sha256')!=authorization['development_source_sha256']
            or plan.get('development_source_sha256')!=DEVELOPMENT_SHA
            or plan.get('source_cohort_plan_sha256')!=COHORT_PLAN_SHA or plan.get('teaching_source_sha256')!=TEACHING_SHA
            or plan.get('normalized_teaching_overlap')!=0):
        raise ValueError('Development-only compatibility recipe changed')
    if (not isinstance(plan.get('run_id'),str) or not contract.NAME.fullmatch(plan['run_id'])
            or type(plan.get('seed')) is not int or plan['seed']!=42):raise ValueError('Unsafe compatibility run/seed')
    expected={'volume_path':plan['input_volume_path'],'sha256':plan['input_sha256'],'bytes':plan['input_bytes'],'plan_sha256':plan['plan_sha256']}
    if descriptor!=expected or not descriptor['volume_path'].endswith('/development_input.json'):
        raise ValueError('Only the staged development payload is permitted')
    execution.volume_path(descriptor['volume_path'])
    if any(re.search(r'(^|[_-])(test|finaltest|official)([_-]|$)',part,re.I) for part in descriptor['volume_path'].split('/')):
        raise ValueError('Official-test paths are forbidden to compatibility work')
    if type(descriptor['bytes']) is not int or not 0<descriptor['bytes']<=4*1024*1024:raise ValueError('Development payload byte cap differs')
    return authorization


def validate_payload(payload,plan,authorization):
    if sha(encoded(payload))!=plan['input_sha256'] or len(encoded(payload))!=plan['input_bytes']:
        raise ValueError('Staged development payload differs')
    rows=payload.get('development');ids=plan['development_ids'];prefix=authorization['sealed']['contract']['protocol']['inference']['user_prefix']
    source_raw=payload.get('development_source_jsonl')
    if not isinstance(source_raw,str) or sha(source_raw.encode('utf-8'))!=DEVELOPMENT_SHA:
        raise ValueError('Actual original TRAIN development bytes differ')
    original=[json.loads(line) for line in source_raw.split('\n') if line.strip()]
    expected=[]
    for row in original:
        r={k:row[k] for k in ('id','prompt','gold_answer','source_split')}
        r['source_index']=int(row['id'].rsplit(':',1)[1]);r['input_sha256']=input_hash(r,prefix);expected.append(r)
    if rows!=expected:raise ValueError('Development model inputs/gold differ from original hashed source')
    if (payload.get('role')!=ROLE or payload.get('official_test_used') is not False or payload.get('training_performed') is not False
            or payload.get('development_source_sha256')!=plan['development_source_sha256']
            or payload.get('development_source_sha256')!=DEVELOPMENT_SHA
            or not isinstance(rows,list) or len(rows)!=200 or len(set(ids))!=200 or [r['id'] for r in rows]!=ids
            or digest(rows)!=plan['development_rows_sha256']):raise ValueError('Exact200 development identities differ')
    for row in rows:
        if (set(row)!={'id','source_index','prompt','gold_answer','source_split','input_sha256'}
                or not re.fullmatch(r'gsm8k:train:\d{5}',row['id']) or row['source_split']!='train'
                or type(row['source_index']) is not int or not 0<=row['source_index']<7473
                or row['source_index']!=int(row['id'].rsplit(':',1)[1])
                or not isinstance(row['prompt'],str) or not isinstance(row['gold_answer'],str)
                or row['input_sha256']!=input_hash(row,prefix)):
            raise ValueError('Only exact human TRAIN development inputs are permitted')
    return rows


def prepare(value,checkpoint,development_artifact,output,*,source_paths,adapter_volume_path,model_config,authorized=False):
    if authorized is not True:raise ValueError('Explicit existing TRAIN development read authorization is required')
    validate_sources(value)
    source_paths,_=seal._source_inventory(value,source_paths)
    development_artifact=seal._safe(development_artifact,private=True)
    if development_artifact!=(HUMAN/'development.jsonl').resolve():raise ValueError('Use only the existing immutable human200 holdout')
    cohort=HUMAN.resolve();plan_path=cohort/'plan.json';teaching_path=cohort/'candidates.jsonl'
    if sha(plan_path.read_bytes())!=COHORT_PLAN_SHA or sha(development_artifact.read_bytes())!=DEVELOPMENT_SHA or sha(teaching_path.read_bytes())!=TEACHING_SHA:
        raise ValueError('Existing human cohort/source hashes differ')
    source_plan=json.loads(plan_path.read_text(encoding='utf-8'));development=read_rows(development_artifact);teaching=read_rows(teaching_path)
    if (source_plan.get('official_test_accessed') is not False or source_plan.get('development_count')!=200
            or source_plan.get('teaching_count')!=2048 or len(development)!=200 or len(teaching)!=2048
            or [r['id'] for r in development]!=source_plan['development_ids']
            or [r['id'] for r in teaching]!=source_plan['teaching_ids']
            or set(source_plan['development_ids'])&set(source_plan['teaching_ids'])):
        raise ValueError('Existing teaching/development split identity differs')
    norm=lambda s:' '.join(unicodedata.normalize('NFKC',s).casefold().split())
    if {norm(r['prompt']) for r in development}&{norm(r['prompt']) for r in teaching}:raise ValueError('Development prompt overlaps teaching')
    prefix=value['protocol']['inference']['user_prefix'];rows=[]
    for row in development:
        r={k:row[k] for k in ('id','prompt','gold_answer','source_split')};r['source_index']=int(row['id'].rsplit(':',1)[1]);r['input_sha256']=input_hash(r,prefix);rows.append(r)
    output=seal._safe(output,private=True,exists=False);run_id=output.name
    auth=record({'schema_version':1,'role':ROLE,'sealed':{'contract':value,'checkpoint':{
        'selected':checkpoint['selected'],'adapter_files_sha256':checkpoint['adapter_files_sha256']}},
        'adapter_path':adapter_volume_path,'model_config':model_config,'development_source_sha256':DEVELOPMENT_SHA},'authorization_sha256')
    payload={'schema_version':1,'role':ROLE,'official_test_used':False,'training_performed':False,
        'development_source_sha256':DEVELOPMENT_SHA,'development_source_jsonl':development_artifact.read_bytes().decode('utf-8'),'development':rows}
    plan=record({'schema_version':1,'version':VERSION,'role':ROLE,'run_id':run_id,'seed':42,**FIXED,
        'model':contract.MODEL,'revision':contract.REVISION,'authorization_sha256':auth['authorization_sha256'],
        'source_bundle_sha256':digest(value['protocol']['source_hashes']),'inference_sha256':digest(value['protocol']['inference']),
        'adapter_model_sha256':checkpoint['adapter_files_sha256']['adapter_model.safetensors'],
        'adapter_inventory_sha256':value['protocol']['selected']['adapter_inventory_sha256'],
        'development_source_sha256':DEVELOPMENT_SHA,'development_ids':[r['id'] for r in rows],
        'development_rows_sha256':digest(rows),'source_cohort_plan_sha256':COHORT_PLAN_SHA,
        'teaching_source_sha256':TEACHING_SHA,'normalized_teaching_overlap':0,
        'input_volume_path':'final-compat/'+run_id+'/development_input.json','input_sha256':sha(encoded(payload)),
        'input_bytes':len(encoded(payload))},'plan_sha256')
    descriptor={'volume_path':plan['input_volume_path'],'sha256':plan['input_sha256'],'bytes':plan['input_bytes'],'plan_sha256':plan['plan_sha256']}
    validate_metadata(plan,descriptor,auth);validate_payload(payload,plan,auth)
    output.mkdir(parents=True,exist_ok=True)
    from cloud.final_scale_loader import ensure_json,ensure_bytes
    for name,data in (('plan.json',plan),('authorization.json',auth),('input_descriptor.json',descriptor)):
        ensure_json(output/name,data)
    ensure_bytes(output/'input.json',encoded(payload))
    return {'stage':'prepared_development_only_not_dispatched','run_id':run_id,'development_count':200,
        'plan_sha256':plan['plan_sha256'],'provider_called':False,'official_test_used':False,'training_performed':False}


def validate_dispatch(plan,authorization,dispatch):
    check(dispatch,'dispatch_sha256')
    if (dispatch.get('role')!='development_compatibility_dispatch' or dispatch.get('reviewed') is not True
            or dispatch.get('run_id')!=plan['run_id'] or dispatch.get('plan_sha256')!=plan['plan_sha256']
            or dispatch.get('authorization_sha256')!=authorization['authorization_sha256']
            or dispatch.get('source_bundle_sha256')!=plan['source_bundle_sha256']
            or dispatch.get('reserved_modal_usd')!='1.75' or dispatch.get('protected_final_modal_usd')!='12.25'
            or dispatch.get('protected_api_modal_usd')!='1' or dispatch.get('official_access_authorized') is not False):
        raise ValueError('A separately reviewed protected compatibility dispatch is required')
    if not re.fullmatch(r'[a-f0-9]{32}',str(dispatch.get('claim_id',''))):raise ValueError('Unique future GPU owner claim is required')
    return dispatch


def derive_batch(rows,raw,decode):
    start=raw['start']
    if type(start) is not int or not 0<=start<200 or start%8:raise ValueError('Invalid development batch start')
    subset=rows[start:start+8];eos=raw['eos_token_ids']
    if (raw.get('role')!=ROLE or raw.get('checkpoint') not in ('base','chosen')
            or not re.fullmatch(r'fc-[A-Za-z0-9-]+',str(raw.get('call_id','')))
            or not isinstance(eos,list) or 100257 not in eos or any(type(n) is not int or not 0<=n<100352 for n in eos)
            or raw['count']!=len(subset) or raw['question_ids']!=[r['id'] for r in subset]
            or len(raw['input_tokens'])!=len(subset) or any(type(n) is not int or n<1 for n in raw['input_tokens'])):
        raise ValueError('Development raw batch identity differs')
    eligible=sum(n<=1536 for n in raw['input_tokens']);tokens=raw['generated_ids'];failed=raw['generation_failed'];elapsed=raw['generation_elapsed_seconds']
    if (type(failed) is not bool or not finite(elapsed) or not isinstance(tokens,list)
            or failed and (not eligible or tokens) or not failed and len(tokens)!=eligible or not eligible and elapsed):
        raise ValueError('Development raw generated subset differs')
    outcomes=[];offset=0
    for source,n in zip(subset,raw['input_tokens']):
        row={k:source[k] for k in ('id','gold_answer','input_sha256')}
        row.update(response='',outcome='input_limit' if n>1536 else 'failed' if failed else 'generated',
            truncated=False,generated_tokens=0,elapsed_seconds=elapsed/eligible if n<=1536 and eligible else 0)
        if n<=1536 and not failed:
            seq=tokens[offset];offset+=1
            if not isinstance(seq,list) or not 1<=len(seq)<=512 or any(type(t) is not int or not 0<=t<100352 for t in seq):raise ValueError('Raw output token bound differs')
            tail,truncated=trim_generation(seq,raw['eos_token_ids'],512)
            row.update(response=decode(tail),generated_tokens=len(tail),truncated=truncated)
        outcomes.append(row)
    return record({'role':ROLE,'checkpoint':raw['checkpoint'],'call_id':raw['call_id'],'plan_sha256':raw['plan_sha256'],
        'start':start,'count':len(subset),'rows':outcomes,'raw_sha256':sha(encoded(raw))},'batch_sha256')


def validate_result(value,plan,payload,result):
    validate_sources(value);check(plan,'plan_sha256')
    if (plan.get('role')!=ROLE or plan.get('version')!=VERSION
            or any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in FIXED.items())
            or plan.get('development_source_sha256')!=DEVELOPMENT_SHA
            or plan.get('source_cohort_plan_sha256')!=COHORT_PLAN_SHA or plan.get('teaching_source_sha256')!=TEACHING_SHA
            or plan.get('model')!=contract.MODEL or plan.get('revision')!=contract.REVISION):
        raise ValueError('Exact development-only compatibility plan differs')
    validate_payload(payload,plan,{'sealed':{'contract':value}})
    if plan['source_bundle_sha256']!=digest(value['protocol']['source_hashes']) or plan['inference_sha256']!=digest(value['protocol']['inference']):
        raise ValueError('Compatibility result source/inference contract differs')
    if (result.get('run_id')!=plan['run_id'] or result.get('plan_sha256')!=plan['plan_sha256']
            or result.get('official_test_used') is not False or result.get('training_performed') is not False):raise ValueError('Compatibility result identity differs')
    expected_ids=plan['development_ids']
    for role in ('base','chosen'):
        rows=result['evaluations'][role]
        derived=[]
        if len(result['batches'][role])!=25:raise ValueError('All25 durable development batches are required')
        for start,batch in zip(range(0,200,8),result['batches'][role]):
            check(batch,'batch_sha256');contract.require_hash(batch['raw_sha256'])
            if (batch['start']!=start or batch['count']!=8 or batch.get('checkpoint')!=role
                    or batch.get('call_id')!=result.get('call_id') or batch.get('plan_sha256')!=plan['plan_sha256']):
                raise ValueError('Development batch identity/role differs')
            derived.extend(batch['rows'])
        if derived!=rows:raise ValueError('Complete outcomes differ from durable batches')
        if len(rows)!=200 or [r['id'] for r in rows]!=expected_ids:raise ValueError('Both complete200-role results are required')
        for r,source in zip(rows,payload['development']):
            if (r['gold_answer']!=source['gold_answer'] or r['input_sha256']!=source['input_sha256']
                    or r['outcome'] not in ('generated','input_limit','failed') or type(r['truncated']) is not bool
                    or type(r['generated_tokens']) is not int or not 0<=r['generated_tokens']<=512 or not finite(r['elapsed_seconds'])):
                raise ValueError('Development outcome differs from source/fixed bounds')
        if any(r['outcome']=='failed' for r in rows):raise ValueError('Generation failures cannot establish completed runtime compatibility')
    e=result.get('runtime_evidence');check(e,'evidence_sha256')
    p=value['protocol'];expected={'role':ROLE,'stage':'completed','official_test_used':False,'training_performed':False,
        'model':contract.MODEL,'revision':contract.REVISION,'adapter_inventory_sha256':p['selected']['adapter_inventory_sha256'],
        'adapter_model_sha256':plan['adapter_model_sha256'],
        'source_bundle_sha256':digest(p['source_hashes']),'model_config_sha256':layout.EVIDENCE['local_config']['sha256'],
        'layout_policy_version':layout.VERSION,'model_image_source_sha256':p['source_hashes']['modal_train.py'],
        'dependency_versions':DEPENDENCIES,'inference_sha256':digest(p['inference']),'development_count':200,
        'development_source_sha256':plan['development_source_sha256'],'peft_load_succeeded':True,
        'runtime_layout_verified':True,'loaded_adapter_values_verified':True}
    if result.get('stage')!='completed' or any(e.get(k)!=v for k,v in expected.items()) or e.get('call_id')!=result.get('call_id'):
        raise ValueError('Completed actual-runtime evidence differs')
    measured=calibration_record(value,result['evaluations'],result['runtime_timings'],result['elapsed_seconds'])
    if e.get('calibration')!=measured:raise ValueError('Runtime calibration differs from actual retained row/batch timing')
    return e


def calibration_record(value,evaluations,timings,total_seconds):
    if not finite(total_seconds) or set(timings)!={'base','chosen'}:raise ValueError('Invalid actual worker duration/role set')
    for role in ('base','chosen'):
        rows=evaluations[role];timing=timings[role]
        sizes=[sum(row['outcome']=='generated' for row in rows[start:start+8]) for start in range(0,200,8)]
        measured=sum(row['elapsed_seconds'] for row in rows)
        if (len(rows)!=200 or timing['retained_count']!=200 or timing['actual_generation_batch_sizes']!=sizes
                or not finite(timing['generation_seconds']) or timing['generation_seconds']<=0
                or not finite(timing['role_wall_seconds']) or timing['role_wall_seconds']+.001<timing['generation_seconds']
                or not math.isclose(measured,timing['generation_seconds'],rel_tol=1e-9,abs_tol=1e-6)):
            raise ValueError('Actual per-role generation/row/subset timing differs')
    if sum(timings[r]['role_wall_seconds'] for r in timings)>total_seconds+.001:
        raise ValueError('Sequential role durations exceed actual worker time')
    load=max(80,max(timings[r]['role_wall_seconds']-timings[r]['generation_seconds'] for r in ('base','chosen'))+15)
    forecasts={r:[load+1.25*timings[r]['generation_seconds']*(s['stop']-s['start'])/200
        for s in value['protocol']['shards']] for r in ('base','chosen')}
    return {'base_generation_seconds':timings['base']['generation_seconds'],
        'chosen_generation_seconds':timings['chosen']['generation_seconds'],'load_allowance_seconds':load,
        'load_io_buffer_seconds':15,'load_allowance_scope':'Maximum per-role non-generation wall time plus15s; not the sum of sequential role loads.',
        'total_compatibility_worker_seconds':total_seconds,'forecasts_seconds_by_role':forecasts,
        'runtime_feasible':max(x for xs in forecasts.values() for x in xs)<=1250,
        'source':'Actual compatibility reload; not a physical final_scale_contract calibration record.',
        'completed_rows_by_role':{r:len(evaluations[r]) for r in evaluations},
        'role_outcomes_sha256':{r:digest(evaluations[r]) for r in evaluations}}


def make_evidence(value,plan,authorization,*,call_id,proofs,calibration,evaluations=None):
    if not re.fullmatch(r'fc-[A-Za-z0-9-]+',str(call_id)):raise ValueError('Actual Modal call identity is required')
    if (not isinstance(evaluations,dict) or set(evaluations)!={'base','chosen'}
            or any(len(rows)!=200 or [r['id'] for r in rows]!=plan['development_ids'] for rows in evaluations.values())
            or calibration.get('completed_rows_by_role')!={'base':200,'chosen':200}
            or calibration.get('role_outcomes_sha256')!={r:digest(evaluations[r]) for r in evaluations}):
        raise ValueError('Both actual complete200-role outcomes must precede evidence construction')
    if (set(proofs)!={'base','chosen'} or any(proof.get(k) is not True for proof in proofs.values()
            for k in ('peft_load_succeeded','runtime_layout_verified','loaded_adapter_values_verified','finite_saved_cpu_values'))
            or proofs['base'].get('baseline_adapter_unloaded') is not True):raise ValueError('Actual PEFT/layout/value checks are incomplete')
    p=value['protocol']
    expected={'dependency_versions':DEPENDENCIES,'source_bundle_sha256':digest(p['source_hashes']),
        'model_config_sha256':layout.EVIDENCE['local_config']['sha256'],
        'adapter_inventory_sha256':p['selected']['adapter_inventory_sha256'],
        'adapter_model_sha256':authorization['sealed']['checkpoint']['adapter_files_sha256']['adapter_model.safetensors'],
        'tensor_count':160,'parameter_count':layout.PARAMETER_COUNT}
    if any(proof.get(k)!=v for proof in proofs.values() for k,v in expected.items()):
        raise ValueError('Observed runtime dependency/artifact/layout identities differ')
    return record({'role':ROLE,'stage':'completed','official_test_used':False,'training_performed':False,
        'model':contract.MODEL,'revision':contract.REVISION,'adapter_inventory_sha256':p['selected']['adapter_inventory_sha256'],
        'adapter_model_sha256':authorization['sealed']['checkpoint']['adapter_files_sha256']['adapter_model.safetensors'],
        'source_bundle_sha256':digest(p['source_hashes']),'model_config_sha256':layout.EVIDENCE['local_config']['sha256'],
        'layout_policy_version':layout.VERSION,'model_image_source_sha256':p['source_hashes']['modal_train.py'],
        'dependency_versions':DEPENDENCIES,'inference_sha256':digest(p['inference']),'development_count':200,
        'development_source_sha256':plan['development_source_sha256'],'call_id':call_id,
        'peft_load_succeeded':True,'runtime_layout_verified':True,'loaded_adapter_values_verified':True,
        'proofs_by_role':proofs,'calibration':calibration},'evidence_sha256')


if __name__=='__main__':
    print(json.dumps({'stage':'implementation_only_no_launch_cli','provider_called':False,'official_test_used':False}))
