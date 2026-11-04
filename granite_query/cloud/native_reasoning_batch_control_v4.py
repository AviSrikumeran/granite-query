"""Bounded native-reasoning study controller; inspection is local and unpaid.

Teacher collection has its own controller and reservation. This module owns
only the separately reviewed student envelope and unique GPU dispatches. No
official test data or model endpoint is accessed by any command here.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime,timezone
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
import uuid
from cloud import native_reasoning_batch_contract_v4 as contract
from cloud.comparison_control import require_fresh_modal_budget

ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'runs'
STATE=PRIVATE/'supervisor'
DEFAULT=PRIVATE/'native_reasoning16k_dev200_seed42_batch32_v4'
ORIGINAL=PRIVATE/'native_reasoning16k_dev200_seed42_config_v3_final'
DEV=PRIVATE/'human_math_cohort2048_dev200_v1/development.jsonl'
VERSION='native-reasoning-batch32-controller-v4'
MIGRATION_VERSION='native-reasoning-completed-parent-batch-funding-v4'
TRANSFER=3.50
ADDITIONAL=1.75
PRIOR_CONFIG_SHA='65105f30da56ea03465f7424540a51b66f3a77bcff2af06f6288d093c65905b0'
PRIOR_CONFIG_BYTES=940
FAILURE_VERSION='native-provider-positive-failure-v2'
EXPECTED_ORIGINAL_CALL='fc-01M6J8VCFC8ABNCMESZ30FS9ZZ'
ROLES=('baseline','concise','thinking')
ENVELOPE=5.25
PER_CALL=1.75
PROTECTED=5.0
SOURCES=('native_reasoning_batch_contract_v4.py','native_reasoning_contract.py','native_reasoning_collection.py',
    'native_reasoning_batch_control_v4.py','modal_native_reasoning_batch_v4.py','modal_native_batch_launch_v4.py',
    'native_reasoning_control_v3.py','native_reasoning_control_v2.py','native_reasoning_control.py',
    'modal_native_reasoning_v3.py','modal_native_reasoning_v2.py','modal_train.py','final_scale_artifacts.py',
    'granite_lora_layout.py','comparison_control.py','budget_reconcile.py','native_budget_reconcile.py',
    'native_batch_budget_reconcile_v4.py','comparison_metrics.py','valuation_contract.py','student_valuation.py')

def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return contract.digest(value)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def safe(path):
    path=Path(os.path.abspath(path));root=Path(os.path.abspath(PRIVATE))
    if not path.is_relative_to(root) or path==root:raise ValueError('Use a distinct private run directory')
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Linked private paths forbidden')
        if part==root:break
    return path

def read(path):
    path=safe(path)
    if path.stat().st_size>64*1024*1024:raise ValueError('Oversized private JSON')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('Duplicate JSON key')
            out[k]=v
        return out
    return json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,
        parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def write(path,value,*,immutable=False):
    path=safe(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
    if immutable:
        try:
            with path.open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
        except FileExistsError:
            if read(path)!=value:raise ValueError('Immutable artifact already differs')
    else:
        tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
        with tmp.open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
        tmp.replace(path)

@contextmanager
def exclusive(path):
    path=safe(path);fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:os.write(fd,str(os.getpid()).encode());os.fsync(fd);yield
    finally:os.close(fd);path.unlink()

def source_inventory():return {name:sha(ROOT/name) for name in SOURCES}


def _money(value):
    amount=Decimal(str(value))
    if not amount.is_finite() or amount<0:raise ValueError('Finite nonnegative USD required')
    return amount


def _matched_graph_node(call_id,graph):
    if (not isinstance(graph,dict) or graph.get('queried_call_id')!=call_id
            or not isinstance(graph.get('inputs'),list) or len(graph['inputs'])>128):
        raise ValueError('Supported exact-call graph evidence required')
    matches=[];pending=list(graph['inputs']);nodes=0
    while pending:
        node=pending.pop();nodes+=1
        if nodes>128 or not isinstance(node,dict) or not isinstance(node.get('children'),list):
            raise ValueError('Bounded actual provider input graph required')
        if node.get('function_call_id')==call_id:matches.append(node)
        pending.extend(node['children'])
    if len(matches)!=1:raise ValueError('Exactly one actual matching provider input required')
    return matches[0]


def validate_failure_graph(call_id,graph):
    """Exact positive FAILURE/TIMEOUT only; never infer terminal absence."""
    node=_matched_graph_node(call_id,graph)
    statuses={'FAILURE':2,'TIMEOUT':4}
    if (node.get('status') not in statuses or type(node.get('status_value')) is not int
            or node['status_value']!=statuses[node['status']]):
        raise ValueError('Provider has not positively confirmed matching FAILURE or TIMEOUT')
    return node


def failure_evidence(call_id,graph,error_bytes,*,error_type,observed_at_utc):
    node=validate_failure_graph(call_id,graph)
    if (not isinstance(error_bytes,bytes) or not 0<len(error_bytes)<=4*1024*1024
            or not isinstance(error_type,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',error_type)):
        raise ValueError('Original bounded exception evidence is required')
    stamp=datetime.fromisoformat(observed_at_utc.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('Zoned failure observation required')
    body={'version':FAILURE_VERSION,'call_id':call_id,'provider_status':node['status'],'provider_status_value':node['status_value'],
        'provider_call_graph_sha256':digest(graph),'provider_exception_trace_sha256':hashlib.sha256(error_bytes).hexdigest(),
        'error_type':error_type,'observed_at_utc':observed_at_utc,'positive_provider_failure_status':True}
    return dict(body,evidence_sha256=digest(body))


def _parent_tokenizer():
    from cloud.student_valuation import load_tokenizer
    tokenizer=load_tokenizer(local_files_only=True)
    from cloud import native_reasoning_contract as original_contract
    original_contract.tokenizer_identity(tokenizer)
    return tokenizer


def _replay_parent(job,result,dispatch,old_design,*,tokenizer=None):
    """Read-only replay of the actual saved V3 raw bytes, never provider wrappers."""
    from cloud import modal_native_reasoning_v3 as worker
    from cloud import native_reasoning_control_v3 as old
    tokenizer=tokenizer if tokenizer is not None else _parent_tokenizer()
    entries=result.get('raw_batches')
    if not isinstance(entries,list) or len(entries)!=25:raise ValueError('Parent needs all25 actual raw batches')
    batches=[];folder=job['folder_path']
    for start,entry in zip(range(0,200,8),entries):
        if entry.get('start')!=start or entry.get('stop')!=start+8:raise ValueError('Parent raw coverage changed')
        path=safe(folder/'wire'/f'batch{start:04d}.json')
        if not path.is_file() or not 0<path.stat().st_size<=8*1024*1024:raise ValueError('Parent original raw wire missing')
        raw_bytes=path.read_bytes();raw=read(path)
        if (sha(path)!=entry.get('sha256') or raw_bytes!=worker.encoded(raw)
                or read(folder/'raw'/f'batch{start:04d}.json')!=raw):
            raise ValueError('Parent actual raw bytes/hash changed')
        derived=worker.derive_with_tokenizer(raw,job['data'],job['plan'],dispatch,tokenizer,expected_call_id=result['call_id'])
        if derived['raw_sha256']!=entry['sha256']:raise ValueError('Parent raw replay hash changed')
        batches.append(derived)
    rows=[r for batch in batches for r in batch['rows']]
    if result.get('batches')!=batches or result.get('evaluations')!={'baseline':rows}:
        raise ValueError('Parent results differ from all original raw tokens')
    metrics=old.validate_result(job,result)
    if result.get('outcomes')!={'generated':200} or any(r.get('outcome')!='generated' for r in rows) or metrics['latency_seconds_total']>result['elapsed_seconds']:
        raise ValueError('Only actual generated full200 within worker time calibrate a parent')
    proof=result.get('runtime_model_verification') or {};source=result.get('source_verification') or {}
    if (proof.get('fresh_base') is not True or proof.get('adapter_loaded') is not False
            or proof.get('base_geometry_verified') is not True
            or proof.get('model')!=contract.MODEL or proof.get('revision')!=contract.REVISION
            or proof.get('model_config_sha256')!=worker.OFFICIAL_RAW_CONFIG_SHA
            or proof.get('inference')!={'enable_thinking':True,'max_new_tokens':1024,'input_limit':1536,'evaluation_batch_size':8}
            or result.get('tokenizer_verification')!=contract.TOKENIZER
            or source.get('dependency_versions')!=worker.DEPENDENCIES
            or source.get('physical',{}).get('packaged_source_hashes_verified') is not True
            or source.get('physical',{}).get('source_hashes')!=old_design['source_sha256']
            or source.get('physical',{}).get('source_bundle_sha256')!=digest(old_design['source_sha256'])
            or result.get('metrics')!={'baseline':metrics}):
        raise ValueError('Parent fresh-base runtime/source/metric proof differs')
    expected={'raw_batches_verified':25,'fixed_denominator':200,'metrics':metrics,'dispatch_sha256':digest(dispatch)}
    if read(folder/'raw_validation.json')!=expected:raise ValueError('Parent saved physical replay proof differs')
    return metrics


def _completed_parent(original):
    """Require completed V3 evidence and its actual frozen runtime gate failure."""
    from cloud import native_reasoning_control_v3 as old
    original=safe(original);old_design=old.verify_design(original)
    jobs=old._parent_jobs(original,old_design,old);job=jobs[0];folder=job['folder_path']
    dispatch=old.Controller(original)._dispatch(job)
    launch=old.validate_launch(folder,job,dispatch,read(folder/'launch.json'))
    terminal=read(folder/'provider_terminal.json');result=read(folder/'result.json')
    if (launch['call_id']!=EXPECTED_ORIGINAL_CALL or terminal.get('kind')!='completed'
            or terminal.get('call_id')!=launch['call_id'] or terminal.get('claim_id')!=dispatch['claim_id']
            or terminal.get('intent_sha256')!=dispatch['intent_sha256']
            or terminal.get('result_sha256')!=sha(folder/'result.json')
            or terminal.get('raw_validation_sha256')!=sha(folder/'raw_validation.json')
            or read(folder/'provider_result.json')!=result or result.get('call_id')!=launch['call_id']
            or result.get('dispatch')!=dispatch or result.get('dispatch_sha256')!=digest(dispatch)
            or result.get('protocol_hash')!=job['plan']['protocol_hash']
            or result.get('outcomes',{}).get('failed',0) or result.get('outcomes',{}).get('input_limit',0)):
        raise ValueError('Actual completed parent call/result/full physical replay proof required')
    metrics=_replay_parent(job,result,dispatch,old_design)
    generation=metrics['latency_seconds_total']
    forecasts={j['role']:round(80+1.25*generation+.0032*j['forwarded_input_tokens'],3) for j in jobs[1:]}
    expected={'version':old.VERSION,'design_sha256':sha(original/'design.json'),'baseline_call_id':launch['call_id'],
        'baseline_result_sha256':terminal['result_sha256'],'raw_validation_sha256':terminal['raw_validation_sha256'],
        'baseline_elapsed_seconds':result['elapsed_seconds'],'baseline_generation_seconds':generation,
        'baseline_truncated':metrics['truncated'],'forecast_seconds':forecasts,'formula':old_design['calibration_formula'],
        'pair_runtime_feasible':result['elapsed_seconds']<1550 and max(forecasts.values())<=1250,
        'limitations':'Planning forecast, not runtime guarantee. Longer adapted generations may fail guards; all partial artifacts remain.',
        'guards':{'training':1400,'evaluation':1600,'hard':1800}}
    if read(original/'calibration.json')!=expected or expected['pair_runtime_feasible'] is not False:
        raise ValueError('Completed exact frozen parent calibration must actually fail runtime gate')
    prior=read(original/'funding.json')
    if prior!=old.funding_record_for_report(original,prior.get('created_at_utc')):
        raise ValueError('Preserve actual full V1/V2/V3 funding history')
    return {'original_output':original.relative_to(PRIVATE).as_posix(),
        'original_design_sha256':sha(original/'design.json'),'original_manifest_sha256':sha(original/'study_manifest.json'),
        'original_job_files_sha256':{j['role']:{name:sha(j['folder_path']/name) for name in ('plan.json','input.json')} for j in jobs},
        'original_source_sha256':old_design['source_sha256'],'original_collection':old_design['collection'],
        'original_collection_plan_sha256':old_design['collection_plan_sha256'],'original_baseline_run_id':job['run_id'],
        'original_launch_sha256':sha(folder/'launch.json'),'original_claim_id':dispatch['claim_id'],
        'original_intent_sha256':dispatch['intent_sha256'],'original_call_id':launch['call_id'],
        'original_provider_terminal_sha256':sha(folder/'provider_terminal.json'),
        'original_provider_result_sha256':sha(folder/'provider_result.json'),'original_result_sha256':sha(folder/'result.json'),
        'original_raw_validation_sha256':sha(folder/'raw_validation.json'),
        'original_raw_inventory_sha256':digest(result['raw_batches']),'original_calibration_sha256':sha(original/'calibration.json'),
        'original_forwarded_input_tokens':{j['role']:j['forwarded_input_tokens'] for j in jobs[1:]},
        'original_calibration':expected,'parent_completed':True,'validated_outputs':200,
        'runtime_infeasible':True,'parent_funding_receipt':prior,'parent_funding_receipt_sha256':sha(original/'funding.json'),
        'prior_failure_source':old_design['migration_source'],'config_proof':old_design['config_proof']}


def supported_accounting(ledger):
    """Pure recheck of saved actual provider observations and native transfers."""
    from cloud import native_batch_budget_reconcile_v4 as accounting
    return accounting.reconcile(ledger,read(STATE/'modal_billing_snapshot.json'),
        apps=read(STATE/'modal_app_status_snapshot.json').get('apps',[]))


def fresh_funding(ledger):
    ledger=supported_accounting(ledger)
    account=ledger.get('modal_budget_accounting')
    if (not isinstance(account,dict) or not ledger.get('modal_observation')
        or account.get('new_paid_launches_allowed') is not True or account.get('issues')):
        raise ValueError('Fresh supported Modal accounting is required')
    if ledger.get('limits',{}).get('modal')!=30:raise ValueError('Original30USD Modal ceiling required')
    require_fresh_modal_budget(ledger,new_reservation=True)
    return ledger

def development():
    if sha(DEV)!=contract.DEVELOPMENT_SOURCE_SHA256:raise ValueError('Frozen TRAIN development bytes changed')
    rows=[json.loads(x) for x in DEV.read_text(encoding='utf-8').split('\n') if x.strip()]
    rows=[{k:r[k] for k in ('id','prompt','gold_answer','source_split')} for r in rows]
    if digest(rows)!=contract.DEVELOPMENT_PROJECTION_SHA256:raise ValueError('Development projection changed')
    return rows

def _new_namespace(output,original,collection):
    output,original,collection=safe(output),safe(original),safe(collection)
    if any(output==reserved or output.is_relative_to(reserved) or reserved.is_relative_to(output)
            for reserved in (original,collection,STATE,DEV.parent)):
        raise ValueError('Batch32 requires a distinct sibling namespace, outside source/state/development artifacts')


def prepare_design(collection,output=DEFAULT,*,original=ORIGINAL):
    from cloud import native_reasoning_collection as collector
    output=safe(output);collection=safe(collection);_new_namespace(output,original,collection)
    if contract.protocol().get('max_new_tokens')!=2048 or contract.protocol().get('evaluation_batch_size')!=32:
        raise ValueError('Only the declared batch32/output2048 follow-up is supported')
    collector.validate_run(collection)
    dev=development();parent_completed=_completed_parent(original)
    config_proof=parent_completed['config_proof']
    if (collection.relative_to(PRIVATE).as_posix()!=parent_completed['original_collection']
            or sha(collection/'plan.json')!=parent_completed['original_collection_plan_sha256']):
        raise ValueError('Recovery must preserve the same original teacher collection')
    value={'version':VERSION,'run_id':output.name,'protocol':contract.protocol(),
        'collection':collection.relative_to(PRIVATE).as_posix(),'collection_plan_sha256':sha(collection/'plan.json'),
        'development_source_sha256':sha(DEV),'development_projection_sha256':digest(dev),
        'source_sha256':source_inventory(),'roles':list(ROLES),'gpu_envelope_usd':ENVELOPE,
        'per_call_reservation_usd':PER_CALL,'protected_modal_usd':PROTECTED,
        'max_original_gpu_calls':3,'max_recoveries':0,'automatic_retries':0,
        'calibration_formula':'80+1.25*baseline_generation_seconds+0.0032*forwarded_input_tokens',
        'calibration_gate_seconds':1250,'official_test_used':False,
        'parent_completed':parent_completed,'config_proof':config_proof,
        'funding_policy':'completed_parent_unused_3.50_plus_explicit_new_1.75_for_batch32',
        'interpretation':'Whole-target supervision recipe at matched loss tokens; unequal question counts/forwarded compute. Batch32/output2048 changes both inference settings from the prior pilot. Compare only against the fresh matched baseline; closed-thinking reference remains distinct. Adaptive TRAIN development, no guaranteed broad model gain.'}
    write(output/'design.json',value,immutable=True)
    return value

def verify_design(output=DEFAULT):
    output=safe(output);d=read(output/'design.json')
    if (d.get('version')!=VERSION or d.get('run_id')!=output.name or d.get('protocol')!=contract.protocol()
        or d.get('protocol',{}).get('max_new_tokens')!=2048 or d.get('protocol',{}).get('evaluation_batch_size')!=32
        or d.get('roles')!=list(ROLES) or d.get('source_sha256')!=source_inventory()
        or d.get('gpu_envelope_usd')!=ENVELOPE or d.get('per_call_reservation_usd')!=PER_CALL
        or d.get('protected_modal_usd')!=PROTECTED or d.get('max_original_gpu_calls')!=3
        or d.get('max_recoveries')!=0 or d.get('automatic_retries')!=0 or d.get('official_test_used') is not False
        or d.get('development_source_sha256')!=contract.DEVELOPMENT_SOURCE_SHA256
        or d.get('development_projection_sha256')!=contract.DEVELOPMENT_PROJECTION_SHA256
        or d.get('calibration_gate_seconds')!=1250
        or d.get('funding_policy')!='completed_parent_unused_3.50_plus_explicit_new_1.75_for_batch32'
        or d.get('calibration_formula')!='80+1.25*baseline_generation_seconds+0.0032*forwarded_input_tokens'):
        raise ValueError('Native study design or frozen sources changed')
    collection=safe(PRIVATE/d['collection'])
    if sha(collection/'plan.json')!=d['collection_plan_sha256']:raise ValueError('Collection plan changed')
    development()
    original=safe(PRIVATE/d['parent_completed']['original_output'])
    _new_namespace(output,original,collection)
    if d['parent_completed']!=_completed_parent(original):raise ValueError('Completed parent execution/calibration evidence changed')
    if d.get('config_proof')!=d['parent_completed']['config_proof']:raise ValueError('Parent official-config proof changed')
    return d

def review(output,name):
    d=verify_design(output);r=read(Path(output)/('review_'+name+'.json'))
    if (r.get('reviewed') is not True or r.get('phase')!=name
        or r.get('design_sha256')!=sha(Path(output)/'design.json')
        or r.get('source_sha256')!=d['source_sha256'] or r.get('protected_modal_usd')!=PROTECTED):
        raise ValueError('Exact native phase implementation review missing')
    return r

def funding_review_template(output=DEFAULT):
    output=safe(output);d=verify_design(output)
    if not (output/'study_manifest.json').exists():raise ValueError('Prepare exact three-arm inputs before funding review')
    return {'reviewed':False,'phase':'batch_runtime','design_sha256':sha(output/'design.json'),
        'source_sha256':d['source_sha256'],'protected_modal_usd':PROTECTED,
        'study_manifest_sha256':sha(output/'study_manifest.json'),'parent_completed':d['parent_completed'],
        'transfer_unused_usd':TRANSFER,'additional_new_reservation_usd':ADDITIONAL,'funded_envelope_usd':ENVELOPE,
        'new_reservation_created':True,'additional_reservation_explicitly_approved':True,
        'total_commitment_increase_usd':ADDITIONAL,'historical_allowance_each_usd':PER_CALL,
        'parent_completed_and_runtime_infeasible':True,'parent_validated_outputs':200,
        'new_batch_size':32,'new_max_new_tokens':2048,'new_baseline_requires_actual_calibration':True,'accuracy_used_as_gate':False}


def _migration_review(output):
    actual=review(output,'batch_runtime');expected=dict(funding_review_template(output),reviewed=True)
    flags=('new_reservation_created','additional_reservation_explicitly_approved',
        'parent_completed_and_runtime_infeasible','new_baseline_requires_actual_calibration','accuracy_used_as_gate')
    if (actual!=expected or any(type(actual.get(key)) is not bool for key in flags)
            or type(actual.get('parent_validated_outputs')) is not int or type(actual.get('new_batch_size')) is not int
            or type(actual.get('new_max_new_tokens')) is not int):
        raise ValueError('Exact completed-parent batch32 and explicit NEW1.75 funding review required')
    return actual


def _one(ledger,run_id):
    matches=[j for j in ledger['jobs'] if j.get('run_id')==run_id and j.get('service','modal')=='modal']
    if len(matches)!=1:raise ValueError('Unique prior/new native funding identity required')
    return matches[0]


def _migration_record(output,d,approval,created_at_utc):
    parent=d['parent_completed']
    body={'version':MIGRATION_VERSION,'parent_envelope_id':Path(parent['original_output']).name+'-envelope',
        'new_envelope_id':output.name+'-envelope','transferred_unused_usd':TRANSFER,
        'additional_new_reservation_usd':ADDITIONAL,'funded_envelope_usd':ENVELOPE,
        'new_reservation_created':True,'total_commitment_increase_usd':ADDITIONAL,
        'parent_completed_child_run_id':parent['original_baseline_run_id'],
        'historical_allowance_each_usd':PER_CALL,'parent_completed':parent,
        'parent_funding_receipt_sha256':parent['parent_funding_receipt_sha256'],
        'new_design_sha256':sha(output/'design.json'),'new_manifest_sha256':sha(output/'study_manifest.json'),
        'batch_runtime_review_sha256':sha(output/'review_batch_runtime.json'),'new_source_sha256':d['source_sha256'],
        'parent_validated_outputs':200,'parent_runtime_infeasible':True,
        'new_batch_size':32,'new_max_new_tokens':2048,'accuracy_used_as_gate':False,'created_at_utc':created_at_utc}
    return dict(body,funding_sha256=digest(body))


def _prior_children(ledger,d):
    from cloud import native_reasoning_control_v3 as old
    parent=d['parent_completed'];prior_design={'migration_source':parent['prior_failure_source']}
    historical=old._prior_children(ledger,prior_design)
    child=_one(ledger,parent['original_baseline_run_id'])
    if (child.get('status')!='completed' or child.get('call_id')!=parent['original_call_id']
            or child.get('native_envelope_parent')!=Path(parent['original_output']).name+'-envelope'
            or child.get('native_design_sha256')!=parent['original_design_sha256']
            or child.get('native_claim_id')!=parent['original_claim_id']
            or child.get('native_intent_sha256')!=parent['original_intent_sha256']
            or child.get('native_terminal_sha256')!=parent['original_provider_terminal_sha256']
            or _money(child.get('reserved_usd',0))!=_money(PER_CALL)):
        raise ValueError('Successful parent allowance/call/terminal must stay completed')
    return historical+[child]


def _validate_migration_state(output,d,approval,ledger,record):
    if record!=_migration_record(output,d,approval,record.get('created_at_utc')):
        raise ValueError('Funding audit differs from exact transfer PLUS explicit new allowance')
    parent=_one(ledger,record['parent_envelope_id']);new=_one(ledger,record['new_envelope_id'])
    _prior_children(ledger,d)
    if (parent.get('status')!='superseded' or _money(parent['reserved_usd'])!=0
            or parent.get('native_config_funding')!=d['parent_completed']['parent_funding_receipt']
            or parent.get('native_batch_funding')!=record or new.get('native_batch_funding')!=record
            or new.get('native_design_sha256')!=sha(output/'design.json')
            or _money(new.get('initial_reserved_usd',0))!=_money(ENVELOPE)):
        raise ValueError('Parent transfer or newly funded envelope identity changed')
    children=[j for j in ledger['jobs'] if j.get('native_envelope_parent')==new['run_id']]
    if (len(children)>3 or len({j['run_id'] for j in children})!=len(children)
            or new.get('dispatches')!=[j['run_id'] for j in children]
            or _money(new['reserved_usd'])+sum((_money(j['reserved_usd']) for j in children),Decimal(0))!=_money(ENVELOPE)
            or any(_money(j['reserved_usd'])!=_money(PER_CALL) for j in children)):
        raise ValueError('Three-call batch32 envelope lost or duplicated allowances')
    return new


def validate_stage_funding(output,ledger):
    output=safe(output);d=verify_design(output);approval=_migration_review(output)
    return _validate_migration_state(output,d,approval,ledger,read(output/'funding.json'))


def validate_migration(output,ledger):return validate_stage_funding(output,ledger)


def fund_stage_envelope(output=DEFAULT,*,backend=None):
    """Transfer existing3.50 AND reserve a disclosed NEW1.75 exactly once."""
    output=safe(output);d=verify_design(output);approval=_migration_review(output);backend=backend or Backend()
    with exclusive(STATE/'native_reasoning_batch_v4_funding.lock'),exclusive(STATE/'gpu_launch.lock'):
        apps=backend.apps()
        if (not isinstance(apps,list) or any(not isinstance(a,dict) or type(a.get('tasks')) not in (int,str)
                or not str(a['tasks']).isdigit() or int(a['tasks']) for a in apps)):
            raise ValueError('No active/unknown GPU owner is permitted during batch32-stage funding')
        with exclusive(STATE/'budget_reconcile.lock'):
            ledger=read(STATE/'budget.json');parent_id=Path(d['parent_completed']['original_output']).name+'-envelope'
            existing=[j for j in ledger['jobs'] if j.get('run_id')==output.name+'-envelope']
            if existing:
                if len(existing)!=1:raise ValueError('Duplicate funding destination')
                record=existing[0].get('native_batch_funding')
                if not isinstance(record,dict):raise ValueError('Foreign existing funding destination')
                _validate_migration_state(output,d,approval,ledger,record)
                write(output/'funding.json',record,immutable=True);return record
            ledger=fresh_funding(ledger)
            if active_jobs(ledger):raise ValueError('Existing GPU calls must reconcile before new reservation')
            free=_money(ledger['limits']['modal'])-_money(ledger['estimated_spend']['modal'])-_money(ledger['reserved']['modal'])
            if free<_money(PROTECTED)+_money(ADDITIONAL):raise ValueError('NEW1.75 plus protected5 does not fit original30 ceiling')
            parent=_one(ledger,parent_id);children=_prior_children(ledger,d)
            if (parent.get('status')!='reserved' or parent.get('native_design_sha256')!=d['parent_completed']['original_design_sha256']
                    or _money(parent.get('initial_reserved_usd',0))!=_money(ENVELOPE)
                    or _money(parent['reserved_usd'])!=_money(TRANSFER)
                    or parent.get('dispatches')!=[d['parent_completed']['original_baseline_run_id']]
                    or parent.get('native_config_funding')!=d['parent_completed']['parent_funding_receipt']):
                raise ValueError('Only actual unused completed-parent three-fifty may transfer')
            intent=output/'funding_intent.json';stamp=read(intent)['created_at_utc'] if intent.exists() else now()
            record=_migration_record(output,d,approval,stamp);write(intent,record,immutable=True)
            old_reserved=deepcopy(ledger['reserved']);old_spend=deepcopy(ledger['estimated_spend']);old_children=deepcopy(children)
            parent.update(status='superseded',reserved_usd=0.0,native_batch_funding=record,
                superseded_by=record['new_envelope_id'],reason='Unused3.50 transferred; separate explicit NEW1.75 batch32-stage allowance')
            ledger['jobs'].append({'run_id':record['new_envelope_id'],'service':'modal','status':'reserved','reserved_usd':ENVELOPE,
                'initial_reserved_usd':ENVELOPE,'created_at_utc':stamp,'native_design_sha256':sha(output/'design.json'),
                'native_envelope':True,'dispatches':[],'native_batch_funding':record})
            ledger['reserved']['modal']=float(_money(ledger['reserved']['modal'])+_money(ADDITIONAL))
            ledger=supported_accounting(ledger)
            if (ledger['estimated_spend']!=old_spend or _prior_children(ledger,d)!=old_children
                    or _money(ledger['reserved']['modal'])-_money(old_reserved['modal'])!=_money(ADDITIONAL)
                    or ledger['reserved']['deepseek']!=old_reserved['deepseek']
                    or ledger['modal_budget_accounting'].get('issues')
                    or ledger['modal_budget_accounting'].get('new_paid_launches_allowed') is not True):
                raise ValueError('Funding must add exactly1.75 once and preserve failed and completed history/spend')
            _validate_migration_state(output,d,approval,ledger,record)
            write(STATE/'budget.json',ledger)
        write(output/'funding.json',record,immutable=True);return record


def migrate_envelope(output=DEFAULT,*,backend=None):
    """Compatibility spelling; still explicitly TRANSFER3.50 PLUS NEW1.75."""
    return fund_stage_envelope(output,backend=backend)


def allocate_envelope(output=DEFAULT):
    raise ValueError('Direct allocation forbidden; use explicitly reviewed fund_stage_envelope transfer3.50 PLUS NEW1.75')


def parent_for_report(output=DEFAULT):
    parent=verify_design(output)['parent_completed']
    return {'status':'completed','call_id':parent['original_call_id'],'validated_outputs':200,
        'runtime_infeasible':True,'result_sha256':parent['original_result_sha256'],
        'calibration_sha256':parent['original_calibration_sha256'],'accuracy_used_as_gate':False}


def funding_record_for_report(output,created_at_utc):
    """Read-only expected receipt reconstruction, with no ledger/provider query."""
    output=safe(output);d=verify_design(output);approval=_migration_review(output)
    return _migration_record(output,d,approval,created_at_utc)

def receipt_inventory(collection):
    from cloud import native_reasoning_collection as collector
    return collector.receipt_inventory(collection)['sha256']

def prepare_arms(output=DEFAULT):
    from cloud import native_reasoning_collection as collector
    output=safe(output);d=verify_design(output);collection=safe(PRIVATE/d['collection'])
    pairs=collector.finalized_pairs(collection)
    if not pairs:raise ValueError('No finalized common eligible pairs')
    bindings={'collection_plan_sha256':sha(collection/'plan.json'),'eligible_pairs_sha256':sha(collection/'eligible_pairs.jsonl'),
        'teacher_receipt_inventory_sha256':receipt_inventory(collection)}
    dev=development();jobs=[]
    original=safe(PRIVATE/d['parent_completed']['original_output'])
    original_jobs=read(original/'study_manifest.json')['jobs']
    for role in ROLES:
        data={'development':dev,'bindings':bindings,'arm':None}
        if role!='baseline':
            selected=contract.select_whole_targets([r[role] for r in pairs])
            data['arm']={'arm':role,'training':selected,'updates':contract.exposure_windows(selected),
                'token_budget':16384,'tokens_per_update':1024,'optimizer_updates':16,'tokenizer':contract.TOKENIZER}
        plan=dict(contract.protocol(),run_id=output.name+'_'+role,arm=role,
            mode='evaluate_base' if role=='baseline' else 'train_evaluate',
            token_budget=0 if role=='baseline' else 16384,optimizer_updates=0 if role=='baseline' else 16,
            input_sha256=digest(data),bindings_sha256=digest(bindings))
        plan['protocol_hash']=digest(plan);contract.validate_bundle(data,plan)
        old_job=next(j for j in original_jobs if j['role']==role)
        old_folder=safe(original/old_job['folder']);old_plan=read(old_folder/'plan.json')
        if (data!=read(old_folder/'input.json')
                or {k:v for k,v in plan.items() if k not in ('run_id','protocol_hash','version','max_new_tokens','evaluation_batch_size','evaluation_batch_count','evaluation_partition','evaluation_memory_policy')}
                !={k:v for k,v in old_plan.items() if k not in ('run_id','protocol_hash','version','max_new_tokens','evaluation_batch_size','evaluation_batch_count','evaluation_partition','evaluation_memory_policy')}):
            raise ValueError('Mount recovery must preserve exact original256 teacher,200 dev and16k recipe')
        folder=output/'arms'/plan['run_id'];write(folder/'input.json',data,immutable=True);write(folder/'plan.json',plan,immutable=True)
        tokens=0 if role=='baseline' else sum(len(r['input_ids']) for u in data['arm']['updates'] for w in u['microbatches'] for r in [next(x for x in data['arm']['training'] if x['id']==w['id'])])
        jobs.append({'role':role,'run_id':plan['run_id'],'folder':folder.relative_to(output).as_posix(),
            'plan_sha256':digest(plan),'input_sha256':digest(data),'forwarded_input_tokens':tokens,
            'examples':0 if role=='baseline' else len(data['arm']['training'])})
    manifest={'version':VERSION,'design_sha256':sha(output/'design.json'),'bindings':bindings,'jobs':jobs}
    write(output/'study_manifest.json',manifest,immutable=True);return manifest

def load_jobs(output=DEFAULT):
    from cloud import native_reasoning_collection as collector
    output=safe(output);verify_design(output);m=read(output/'study_manifest.json')
    if m.get('version')!=VERSION or m.get('design_sha256')!=sha(output/'design.json') or len(m.get('jobs',[]))!=3:
        raise ValueError('Study manifest changed')
    collection=safe(PRIVATE/read(output/'design.json')['collection'])
    if (m['bindings']['eligible_pairs_sha256']!=sha(collection/'eligible_pairs.jsonl')
        or m['bindings']['teacher_receipt_inventory_sha256']!=receipt_inventory(collection)):
        raise ValueError('Teacher pool/receipt inventory changed')
    pairs=collector.finalized_pairs(collection)
    original_dev=development()
    jobs=[]
    for role,j in zip(ROLES,m['jobs']):
        folder=safe(output/j['folder']);plan=read(folder/'plan.json');data=read(folder/'input.json')
        if j['role']!=role or plan['arm']!=role or j['run_id']!=plan['run_id'] or digest(plan)!=j['plan_sha256'] or digest(data)!=j['input_sha256'] or data['bindings']!=m['bindings']:
            raise ValueError('Study job identity or original receipt binding changed')
        contract.validate_bundle(data,plan);jobs.append(dict(j,folder_path=folder,plan=plan,data=data))
        if data['development']!=original_dev:raise ValueError('Original development payload changed')
        if role!='baseline':
            selected=contract.select_whole_targets([row[role] for row in pairs])
            if data['arm']['training']!=selected:raise ValueError('Selected whole targets differ from original paired teacher receipts')
        rows={r['id']:r for r in data['arm']['training']} if data['arm'] else {}
        actual_forwarded=sum(len(rows[w['id']]['input_ids']) for u in data['arm']['updates'] for w in u['microbatches']) if rows else 0
        if j.get('forwarded_input_tokens')!=actual_forwarded or j.get('examples')!=len(rows):
            raise ValueError('Recorded training exposure forecast differs from actual whole targets')
    if len({j['run_id'] for j in jobs})!=3:raise ValueError('Duplicate study run identity')
    return jobs

def make_dispatch(plan,data,source_sha256,funding_review_sha256,claim_id=None):
    value={'version':'native-reasoning-dispatch-v1','claim_id':claim_id or uuid.uuid4().hex,
        'run_id':plan['run_id'],'plan_sha256':digest(plan),'input_sha256':digest(data),
        'source_sha256':source_sha256,'funding_review_sha256':funding_review_sha256}
    value['intent_sha256']=digest(value);return value

def validate_result(job,result):
    if (not isinstance(result,dict) or result.get('stage')!='completed' or result.get('plan')!=job['plan']
        or result.get('run_id')!=job['run_id'] or result.get('supervised_tokens')!=job['plan']['token_budget']
        or result.get('optimizer_updates')!=job['plan']['optimizer_updates']
        or result.get('official_test_used') is not False or result.get('evaluation_complete') is not True
        or result.get('retained_evaluation_count')!=200 or result.get('raw_pending') is not False):raise ValueError('Native worker result contract differs')
    elapsed=result.get('elapsed_seconds')
    if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or not 0<elapsed<=1805:
        raise ValueError('Invalid worker elapsed time')
    expected=job['data']['development'];rows=result.get('evaluations',{}).get(job['role'])
    if not isinstance(rows,list) or len(rows)!=200 or [r.get('id') for r in rows]!=[r['id'] for r in expected]:
        raise ValueError('Fixed evaluation denominator changed')
    for row,ref in zip(rows,expected):
        if (str(row.get('gold_answer'))!=str(ref['gold_answer']) or not isinstance(row.get('response'),str)
            or type(row.get('truncated')) is not bool or type(row.get('generated_tokens')) is not int
            or not 0<=row['generated_tokens']<=contract.protocol()['max_new_tokens'] or not isinstance(row.get('elapsed_seconds'),(int,float))
            or isinstance(row['elapsed_seconds'],bool) or not math.isfinite(row['elapsed_seconds']) or row['elapsed_seconds']<0):
            raise ValueError('Invalid native evaluation row')
    from cloud.comparison_metrics import summarize
    return summarize(rows)

class Backend:
    def apps(self):
        r=subprocess.run([sys.executable,'-m','modal','app','list','--json'],capture_output=True,timeout=40,check=True,
            env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'))
        return json.loads(r.stdout.decode('utf-8'))
    def launch(self,folder):
        args=[sys.executable,'-m','modal','run','--detach','-m','cloud.modal_native_launch_v3','--folder',str(folder)]
        try:
            r=subprocess.run(args,cwd=ROOT.parent,capture_output=True,timeout=210,
                env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',MODAL_IMAGE_BUILDER_VERSION='2025.06'))
            out,err,code=r.stdout,r.stderr,r.returncode
        except subprocess.TimeoutExpired as exc:out,err,code=exc.stdout or b'',exc.stderr or b'',None
        (folder/'launch.stdout.private.log').write_bytes(out);(folder/'launch.stderr.private.log').write_bytes(err)
        app=re.search(rb'ap-[A-Za-z0-9]+',out+b'\n'+err)
        return {'return_code':code,'app_id':app.group().decode() if app else None}
    def poll(self,call_id):
        import modal
        call=None
        try:
            call=modal.FunctionCall.from_id(call_id)
            return {'kind':'completed','result':call.get(timeout=0)}
        except Exception as exc:
            error_type=type(exc).__name__;trace=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))
            try:
                if call is None:raise ValueError('No actual call handle')
                observed=now();nodes=call.get_call_graph();count=[0]
                def node(value,depth=0):
                    count[0]+=1
                    if count[0]>128 or depth>16:raise ValueError('Provider graph exceeds bound')
                    status=value.status
                    return {'input_id':value.input_id,'function_call_id':value.function_call_id,'task_id':value.task_id,
                        'status':status.name,'status_value':status.value,'function_name':value.function_name,
                        'module_name':value.module_name,'children':[node(child,depth+1) for child in value.children]}
                graph={'observed_at_utc':observed,'source':'Supported FunctionCall.get_call_graph()',
                    'queried_call_id':call_id,'inputs':[node(value) for value in nodes]}
                matched=_matched_graph_node(call_id,graph)
                if (isinstance(exc,TimeoutError) and matched.get('status')=='PENDING'
                        and type(matched.get('status_value')) is int and matched['status_value']==0):
                    return {'kind':'running'}
                evidence=failure_evidence(call_id,graph,trace.encode('utf-8',errors='backslashreplace'),
                    error_type=error_type,observed_at_utc=observed)
                return {'kind':'failed','error_type':error_type,'positive_failure':
                    {'evidence':evidence,'call_graph':graph,'exception_trace':trace}}
            except Exception:return {'kind':'monitoring_error','error_type':error_type,
                'reason':'SDK_exception_without_positive_matching_FAILURE_or_TIMEOUT_and_original_error'}
    def lookup(self,run_id):
        import modal
        return modal.Dict.from_name('granite-query-training-progress').get('native-reasoning-owner:'+run_id,None)
    def download(self,run_id,relative):
        import modal
        return b''.join(modal.Volume.from_name('granite-query-training-artifacts').read_file(run_id+'/'+relative))

def active_jobs(ledger):
    return [j for j in ledger['jobs'] if j.get('service','modal')=='modal'
        and j.get('status') not in ('completed','failed','cancelled','superseded','reserved')]

def _bind_child(ledger,job,output,dispatch):
    checked=fresh_funding(ledger);ledger.clear();ledger.update(checked)
    if active_jobs(ledger):raise ValueError('Another paid GPU job is open')
    if any(j['run_id']==job['run_id'] for j in ledger['jobs']):raise ValueError('Existing GPU identity; reconcile before action')
    if job.get('role') not in ROLES or job.get('run_id')!=output.name+'_'+job['role']:
        raise ValueError('Only three original versioned roles are funded; no recovery calls')
    envelope=validate_migration(output,ledger)
    if (envelope.get('status')!='reserved' or envelope.get('native_design_sha256')!=sha(output/'design.json')
        or envelope['reserved_usd']<PER_CALL):raise ValueError('Reviewed native envelope missing or exhausted')
    if ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']<PROTECTED:
        raise ValueError('Protected final/API funds no longer available')
    envelope['reserved_usd']=round(envelope['reserved_usd']-PER_CALL,2)
    envelope['dispatches'].append(job['run_id'])
    ledger['jobs'].append({'run_id':job['run_id'],'service':'modal','reserved_usd':PER_CALL,'status':'spawning',
        'created_at_utc':now(),'native_design_sha256':sha(output/'design.json'),
        'native_claim_id':dispatch['claim_id'],'native_intent_sha256':dispatch['intent_sha256'],
        'native_envelope_parent':envelope['run_id']})


def _persist_failure(folder,call_id,answer):
    value=answer.get('positive_failure')
    if not isinstance(value,dict) or not isinstance(value.get('exception_trace'),str):
        raise ValueError('SDK exception alone cannot establish provider termination')
    graph=value['call_graph'];error=value['exception_trace'].encode('utf-8',errors='backslashreplace')
    expected=failure_evidence(call_id,graph,error,error_type=answer['error_type'],
        observed_at_utc=value['evidence']['observed_at_utc'])
    if value['evidence']!=expected:raise ValueError('Positive failure evidence changed')
    write(folder/'provider_call_graph.private.json',graph,immutable=True)
    target=safe(folder/'provider_exception.private.log')
    try:
        with target.open('xb') as handle:handle.write(error);handle.flush();os.fsync(handle.fileno())
    except FileExistsError:
        if target.read_bytes()!=error:raise ValueError('Original provider exception changed')
    record=dict(expected,provider_call_graph_file_sha256=sha(folder/'provider_call_graph.private.json'),
        original_exception_file_sha256=sha(target))
    write(folder/'provider_failure_evidence.json',record,immutable=True)
    return record


def _check_failure(folder,call_id,terminal):
    proof=read(folder/'provider_failure_evidence.json');graph=read(folder/'provider_call_graph.private.json')
    trace=safe(folder/'provider_exception.private.log').read_bytes()
    expected=failure_evidence(call_id,graph,trace,error_type=proof['error_type'],observed_at_utc=proof['observed_at_utc'])
    expected=dict(expected,provider_call_graph_file_sha256=sha(folder/'provider_call_graph.private.json'),
        original_exception_file_sha256=sha(folder/'provider_exception.private.log'))
    if (proof!=expected or terminal.get('provider_failure_evidence_sha256')!=sha(folder/'provider_failure_evidence.json')
            or terminal.get('positive_provider_failure_status') is not True):
        raise ValueError('Stored provider failure proof changed')
    return proof

def validate_launch(folder,job,dispatch,launch):
    if (not isinstance(launch,dict) or launch.get('run_id')!=job['run_id']
        or launch.get('claim_id')!=dispatch['claim_id'] or launch.get('intent_sha256')!=dispatch['intent_sha256']
        or not re.fullmatch(r'fc-[A-Za-z0-9-]+',str(launch.get('call_id','')))):
        raise ValueError('Launch acknowledgement does not match immutable dispatch intent')
    return launch

def verify_raw_result(job,result,dispatch,backend,*,decode=None):
    """Re-read physical raw batches, replay tokens locally, keep all200 outcomes."""
    from cloud import modal_native_reasoning_batch_v4 as worker
    worker.validate_dispatch(job['data'],job['plan'],dispatch)
    if result.get('dispatch')!=dispatch or result.get('call_id') is None:raise ValueError('Result lost actual dispatch/call')
    tok=None
    if decode is None:
        from cloud.student_valuation import load_tokenizer
        tok=load_tokenizer(local_files_only=True);contract.tokenizer_identity(tok)
        decode=lambda ids:tok.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False)
    entries=result.get('raw_batches')
    if not isinstance(entries,list) or len(entries)!=7:raise ValueError('Require all7 immutable batch32 raw batches')
    batches=[]
    for start,entry in zip(range(0,200,32),entries):
        if entry.get('start')!=start or entry.get('stop')!=min(start+32,200):raise ValueError('Raw shard coverage/order changed')
        relative=f'raw/batch{start:04d}.json';raw_bytes=backend.download(job['run_id'],relative)
        if not isinstance(raw_bytes,bytes) or len(raw_bytes)>8*1024*1024 or hashlib.sha256(raw_bytes).hexdigest()!=entry.get('sha256'):
            raise ValueError('Physical raw batch hash/size differs')
        raw=json.loads(raw_bytes)
        if raw_bytes!=worker.encoded(raw):raise ValueError('Raw batch differs from frozen canonical wire bytes')
        if raw.get('call_id')!=result['call_id']:raise ValueError('Raw batch belongs to another actual provider call')
        derived=(worker.derive_with_tokenizer(raw,job['data'],job['plan'],dispatch,tok,expected_call_id=result['call_id'])
            if tok is not None else worker.derive_batch(raw,job['data'],job['plan'],dispatch,decode))
        if derived['raw_sha256']!=entry['sha256']:raise ValueError('Decoded receipt lost original raw byte identity')
        saved=backend.download(job['run_id'],f'batches/batch{start:04d}.json')
        if json.loads(saved)!=derived:raise ValueError('Saved derived rows differ from exact raw tokens')
        write(job['folder_path']/'raw'/f'batch{start:04d}.json',raw,immutable=True)
        # The worker's canonical byte representation, including LF, is kept
        # alongside its logical replay. Never reserialize the original bytes.
        bytepath=safe(job['folder_path']/'wire'/f'batch{start:04d}.json');bytepath.parent.mkdir(parents=True,exist_ok=True)
        if bytepath.exists():
            if bytepath.read_bytes()!=raw_bytes:raise ValueError('Retained original raw bytes changed')
        else:
            with bytepath.open('xb') as h:h.write(raw_bytes);h.flush();os.fsync(h.fileno())
        batches.append(derived)
    rows=[r for b in batches for r in b['rows']]
    if result.get('batches')!=batches or result.get('evaluations')!={job['role']:rows}:raise ValueError('Result differs from full physical raw replay')
    if result.get('cuda_memory')!=worker.aggregate_cuda_memory(batches):raise ValueError('CUDA memory summary differs from original raw measurements')
    timings=result.get('batch_timings')
    if not isinstance(timings,list) or len(timings)!=7 or any(
            item.get('start')!=batch['start'] or item.get('stop')!=batch['stop'] or item.get('cuda_memory')!=batch['cuda_memory']
            or item.get('cuda_memory_error')!=batch['cuda_memory_error']
            for item,batch in zip(timings,batches)):
        raise ValueError('Batch timing memory/coverage differs from original raw measurements')
    if (result.get('tokenizer_verification')!=contract.TOKENIZER
        or result.get('source_verification',{}).get('dependency_versions')!=worker.DEPENDENCIES):
        raise ValueError('Actual tokenizer/dependency verification is incomplete')
    proof=result.get('runtime_model_verification') or {}
    source=result.get('source_verification') or {}
    if (proof.get('model')!=contract.MODEL or proof.get('revision')!=contract.REVISION
            or proof.get('model_config_sha256')!=worker.OFFICIAL_RAW_CONFIG_SHA
            or proof.get('inference')!={'enable_thinking':True,'max_new_tokens':contract.protocol()['max_new_tokens'],'input_limit':1536,'evaluation_batch_size':32}
            or source.get('physical',{}).get('packaged_source_hashes_verified') is not True
            or source.get('physical',{}).get('source_hashes')!=dispatch['source_sha256']
            or source.get('physical',{}).get('source_bundle_sha256')!=digest(dispatch['source_sha256'])):
        raise ValueError('Actual batch32 model/inference/source proof differs')
    if job['role']=='baseline':
        if proof.get('fresh_base') is not True or proof.get('adapter_loaded') is not False or proof.get('base_geometry_verified') is not True:
            raise ValueError('Untouched native baseline proof differs')
    elif (proof.get('runtime_peft_load_verified') is not True or proof.get('loaded_adapter_values_verified') is not True
        or proof.get('checkpoint_hashed_before_evaluation') is not True or not result.get('adapter_inventory')):
        raise ValueError('Contemporaneous native adapter reload/value proof missing')
    metrics=validate_result(job,result)
    if result.get('metrics')!={job['role']:metrics}:raise ValueError('Worker metrics disagree with independent local scorer')
    return {'raw_batches_verified':7,'fixed_denominator':200,'metrics':metrics,'dispatch_sha256':digest(dispatch)}

class Controller:
    def __init__(self,output=DEFAULT,backend=None):self.output=safe(output);self.backend=backend or Backend()

    def jobs(self):return load_jobs(self.output)

    def _entry(self,ledger,run_id):
        entries=[j for j in ledger['jobs'] if j['run_id']==run_id]
        if len(entries)!=1 or entries[0].get('service')!='modal':raise ValueError('Unique native Modal funding job required')
        return entries[0]

    def _dispatch(self,job):
        from cloud import modal_native_reasoning_batch_v4 as worker
        d=read(job['folder_path']/'dispatch.json');worker.validate_dispatch(job['data'],job['plan'],d)
        if d['source_sha256']!=source_inventory():raise ValueError('Native dispatch sources changed')
        phase='baseline' if job['role']=='baseline' else 'pair'
        if d['funding_review_sha256']!=sha(self.output/('review_'+phase+'.json')):raise ValueError('Native dispatch approval changed')
        return d

    def _settle_terminal(self,job,dispatch,launch,record,result=None):
        if (record.get('call_id')!=launch['call_id'] or record.get('claim_id')!=dispatch['claim_id']
            or record.get('intent_sha256')!=dispatch['intent_sha256'] or record.get('kind') not in ('completed','failed')):
            raise ValueError('Terminal receipt does not bind exact paid intent and call')
        with exclusive(STATE/'budget_reconcile.lock'):
            ledger=read(STATE/'budget.json');entry=self._entry(ledger,job['run_id'])
            if (entry.get('native_claim_id')!=dispatch['claim_id']
                or entry.get('native_intent_sha256')!=dispatch['intent_sha256']
                or entry.get('call_id',launch['call_id'])!=launch['call_id']):
                raise ValueError('Native funding terminal claim/call changed')
            status=record['kind']
            if entry['status'] in ('completed','failed'):
                if entry['status']!=status or entry.get('native_terminal_sha256')!=sha(job['folder_path']/'provider_terminal.json'):
                    raise ValueError('Previously settled native terminal differs')
                return
            entry.update(status=status,call_id=launch['call_id'],terminal_observed_at_utc=record['observed_at_utc'],
                native_terminal_sha256=sha(job['folder_path']/'provider_terminal.json'),
                runtime_seconds=(result or {}).get('elapsed_seconds'),
                cost_basis='Provider terminal observed; allowance retained as pending billing liability, not converted to invoice')
            from cloud import native_batch_budget_reconcile_v4 as accounting
            ledger=accounting.reconcile(ledger,read(STATE/'modal_billing_snapshot.json'),
                apps=read(STATE/'modal_app_status_snapshot.json').get('apps',[]))
            write(STATE/'budget.json',ledger)

    def recover_dispatches(self):
        recovered=[];blocked=[]
        for job in self.jobs():
            folder=job['folder_path']
            if not (folder/'dispatch.json').exists():continue
            dispatch=self._dispatch(job)
            if (folder/'launch.json').exists():
                validate_launch(folder,job,dispatch,read(folder/'launch.json'));continue
            owner=self.backend.lookup(job['run_id'])
            if owner is None:blocked.append(job['run_id']);continue
            value=validate_launch(folder,job,dispatch,dict(owner,run_id=job['run_id']))
            write(folder/'launch.json',value,immutable=True);recovered.append(job['run_id'])
        return {'recovered':recovered,'blocked':blocked,'paid_work_launched':False}

    def poll(self):
        recovery=self.recover_dispatches()
        if recovery['blocked']:return dict(recovery,stage='ambiguous_dispatch_requires_reconciliation')
        changes=[];running=[];blocked=[]
        for job in self.jobs():
            folder=job['folder_path']
            if not (folder/'launch.json').exists():continue
            dispatch=self._dispatch(job);launch=validate_launch(folder,job,dispatch,read(folder/'launch.json'))
            terminal=folder/'provider_terminal.json'
            if terminal.exists():
                t=read(terminal)
                if t.get('call_id')!=launch['call_id']:raise ValueError('Provider terminal identity changed')
                retained=read(folder/'provider_result.json') if (folder/'provider_result.json').exists() else None
                if t['kind']=='completed':
                    if (t.get('result_sha256')!=sha(folder/'result.json')
                        or t.get('raw_validation_sha256')!=sha(folder/'raw_validation.json')
                        or retained!=read(folder/'result.json')):raise ValueError('Terminal result/raw proof bytes changed')
                    validate_result(job,read(folder/'result.json'))
                elif not t.get('partial_result_sha256'):
                    _check_failure(folder,launch['call_id'],t)
                elif t.get('partial_result_sha256') and t['partial_result_sha256']!=sha(folder/'provider_result.json'):
                    raise ValueError('Original failed worker result bytes changed')
                self._settle_terminal(job,dispatch,launch,t,retained)
                continue
            answer=self.backend.poll(launch['call_id'])
            if answer['kind']=='running':running.append(job['run_id']);continue
            if answer['kind']=='monitoring_error':blocked.append(job['run_id']);continue
            record={'kind':answer['kind'],'call_id':launch['call_id'],'observed_at_utc':now(),
                'claim_id':dispatch['claim_id'],'intent_sha256':dispatch['intent_sha256']}
            success=False
            if answer['kind']=='completed':
                result=answer['result'];write(folder/'provider_result.json',result,immutable=True)
                if result.get('call_id')!=launch['call_id']:raise ValueError('Provider result call identity differs')
                if result.get('stage')=='completed':
                    rawproof=verify_raw_result(job,result,dispatch,self.backend)
                    write(folder/'raw_validation.json',rawproof,immutable=True);write(folder/'result.json',result,immutable=True)
                    record.update(result_sha256=sha(folder/'result.json'),raw_validation_sha256=sha(folder/'raw_validation.json'))
                    success=True
                else:
                    record.update(kind='failed',worker_stage=result.get('stage'),partial_result_sha256=sha(folder/'provider_result.json'))
            else:
                proof=_persist_failure(folder,launch['call_id'],answer)
                record.update(error_type=proof['error_type'],positive_provider_failure_status=True,
                    provider_failure_evidence_sha256=sha(folder/'provider_failure_evidence.json'),
                    provider_call_graph_sha256=proof['provider_call_graph_file_sha256'],
                    provider_exception_trace_sha256=proof['original_exception_file_sha256'])
            write(terminal,record,immutable=True)
            self._settle_terminal(job,dispatch,launch,record,answer.get('result'))
            changes.append({'run_id':job['run_id'],'stage':record['kind']})
        return {'stage':'running' if running else 'reconciled','running':running,'blocked':blocked,'changes':changes,'paid_work_launched':False}

    def calibrate(self):
        jobs=self.jobs();base=jobs[0];folder=base['folder_path'];t=read(folder/'provider_terminal.json')
        if (t.get('kind')!='completed' or t.get('call_id')!=read(folder/'launch.json')['call_id']
            or t.get('result_sha256')!=sha(folder/'result.json')
            or t.get('raw_validation_sha256')!=sha(folder/'raw_validation.json')):
            raise ValueError('Actual native baseline call/result/raw calibration proof missing')
        result=read(folder/'result.json');metrics=validate_result(base,result)
        if result.get('outcomes',{}).get('failed',0) or result.get('outcomes',{}).get('input_limit',0):
            raise ValueError('Incomplete execution cannot calibrate the native training pair')
        generation=metrics['latency_seconds_total']
        forecasts={j['role']:round(80+1.25*generation+.0032*j['forwarded_input_tokens'],3) for j in jobs[1:]}
        value={'version':VERSION,'design_sha256':sha(self.output/'design.json'),'baseline_call_id':t['call_id'],
            'baseline_result_sha256':t['result_sha256'],'raw_validation_sha256':t['raw_validation_sha256'],
            'baseline_elapsed_seconds':result['elapsed_seconds'],'baseline_generation_seconds':generation,
            'baseline_truncated':metrics['truncated'],'forecast_seconds':forecasts,
            'formula':read(self.output/'design.json')['calibration_formula'],
            'pair_runtime_feasible':result['elapsed_seconds']<1550 and max(forecasts.values())<=1250,
            'limitations':'Planning forecast, not runtime guarantee. Longer adapted generations may fail guards; all partial artifacts remain.',
            'guards':{'training':1400,'evaluation':1600,'hard':1800}}
        write(self.output/'calibration.json',value,immutable=True);return value

    def advance(self):
        result=self.poll()
        if result.get('blocked') or result.get('running'):return result
        jobs=self.jobs()
        failed=[j['run_id'] for j in jobs if (j['folder_path']/'provider_terminal.json').exists()
            and read(j['folder_path']/'provider_terminal.json').get('kind')!='completed']
        if failed:return {'stage':'terminal_failure_requires_review','failed':failed,'paid_work_launched':False}
        pending=[j for j in jobs if not (j['folder_path']/'provider_terminal.json').exists()]
        if not pending:return {'stage':'all_three_complete','paid_work_launched':False}
        job=pending[0];phase='baseline' if job['role']=='baseline' else 'pair';r=review(self.output,phase)
        if r.get('study_manifest_sha256')!=sha(self.output/'study_manifest.json'):raise ValueError('Phase review lacks exact three-job input manifest')
        if phase=='pair':
            calibration=self.calibrate()
            if not calibration['pair_runtime_feasible'] or r.get('calibration_sha256')!=sha(self.output/'calibration.json'):
                raise ValueError('Both native arms need actual baseline runtime review')
        folder=job['folder_path']
        with exclusive(STATE/'native_reasoning_tick.lock'),exclusive(STATE/'gpu_launch.lock'):
            if (folder/'dispatch.json').exists() or (folder/'cli_spawn_started.json').exists():
                raise ValueError('Existing native intent must reconcile, never relaunch')
            apps=self.backend.apps()
            if any(type(a.get('tasks')) not in (int,str) or not str(a['tasks']).isdigit() for a in apps):
                raise ValueError('Unknown Modal task inventory blocks dispatch')
            if any(int(a['tasks'])>0 for a in apps):return {'stage':'external_modal_tasks_active','paid_work_launched':False}
            dispatch=make_dispatch(job['plan'],job['data'],source_inventory(),sha(self.output/('review_'+phase+'.json')))
            from cloud import modal_native_reasoning_batch_v4 as worker
            worker.validate_dispatch(job['data'],job['plan'],dispatch)
            with exclusive(STATE/'budget_reconcile.lock'):
                ledger=read(STATE/'budget.json')
                # Complete funding/migration/ownership checks BEFORE writing
                # any irreversible local dispatch claim. No transmission can
                # occur until the exact child allowance is durably committed.
                _bind_child(ledger,job,self.output,dispatch)
                write(folder/'controller_owner.json',{'pid':os.getpid(),'created_at_utc':now(),'claim_id':dispatch['claim_id']},immutable=True)
                write(folder/'dispatch.json',dispatch,immutable=True)
                write(STATE/'budget.json',ledger)
            receipt=self.backend.launch(folder);write(folder/'launch_receipt.private.json',receipt,immutable=True)
            if not (folder/'launch.json').exists():return {'stage':'ambiguous_dispatch_requires_reconciliation','run_id':job['run_id'],'paid_work_launched':None}
            launch=validate_launch(folder,job,dispatch,read(folder/'launch.json'))
            with exclusive(STATE/'budget_reconcile.lock'):
                ledger=read(STATE/'budget.json');entry=self._entry(ledger,job['run_id'])
                entry.update(status='spawned',call_id=launch['call_id'],app_id=receipt.get('app_id'));write(STATE/'budget.json',ledger)
            return {'stage':'native_call_spawned','run_id':job['run_id'],'call_id':launch['call_id'],'paid_work_launched':True}

def inspect(output=DEFAULT):
    output=safe(output)
    if not (output/'design.json').exists():return {'stage':'unprepared','paid_work_launched':False}
    d=verify_design(output)
    return {'stage':'plans_prepared' if (output/'study_manifest.json').exists() else 'awaiting_completed_teacher_pool',
        'run_id':d['run_id'],'official_test_used':False,'paid_work_launched':False,
        'launches':[read(p) for p in sorted(output.glob('arms/*/launch.json'))]}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['inspect','prepare-design','fund','prepare-arms','poll','advance','calibrate']);p.add_argument('--run',type=Path,default=DEFAULT);p.add_argument('--collection',type=Path);p.add_argument('--original',type=Path,default=ORIGINAL)
    a=p.parse_args()
    if a.action=='prepare-design':
        if a.collection is None:p.error('--collection required')
        result=prepare_design(a.collection,a.run,original=a.original)
    elif a.action=='fund':result=fund_stage_envelope(a.run)
    elif a.action=='prepare-arms':result=prepare_arms(a.run)
    elif a.action in ('poll','advance','calibrate'):result=getattr(Controller(a.run),a.action)()
    else:result=inspect(a.run)
    print(json.dumps(result,default=str))

if __name__=='__main__':main()
