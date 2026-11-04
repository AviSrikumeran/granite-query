"""Pure accounting for one reviewed completed-parent batch32 transfer.

No provider, source-data or filesystem access occurs here. Physical proof is
checked by the new controller. The old transfer graph is validated in a
separate proof view; billing always sees the actual zero source reservation.
"""
from copy import deepcopy
from decimal import Decimal
import math
from pathlib import Path
from cloud import native_budget_reconcile as prior

VERSION='native-completed-parent-batch32-accounting-v4'
FUNDING_VERSION='native-reasoning-completed-parent-batch-funding-v4'
KEYS=set(('version parent_envelope_id new_envelope_id transferred_unused_usd additional_new_reservation_usd '
    'funded_envelope_usd new_reservation_created total_commitment_increase_usd parent_completed_child_run_id '
    'historical_allowance_each_usd parent_completed parent_funding_receipt_sha256 new_design_sha256 '
    'new_manifest_sha256 batch_runtime_review_sha256 new_source_sha256 parent_validated_outputs '
    'parent_runtime_infeasible new_batch_size new_max_new_tokens accuracy_used_as_gate created_at_utc funding_sha256').split())


def _finite(value):
    return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value)


def verify_transfers(ledger):
    jobs=ledger.get('jobs')
    if not isinstance(jobs,list) or any(not isinstance(j,dict) or not isinstance(j.get('run_id'),str) for j in jobs):
        raise ValueError('Explicit unique job identities required')
    if len({j['run_id'] for j in jobs})!=len(jobs):raise ValueError('Duplicate job identity')
    by_id={j['run_id']:j for j in jobs}
    attached=[j for j in jobs if 'native_batch_funding' in j]
    if not attached:
        old=prior.verify_transfers(ledger)
        return dict(old,version=VERSION,batch_transfer=None)
    if len(attached)!=2:raise ValueError('Exactly two attachments for one batch32 transfer required')
    record=attached[0]['native_batch_funding']
    if (not isinstance(record,dict) or set(record)!=KEYS or record.get('version')!=FUNDING_VERSION
            or attached[1]['native_batch_funding']!=record
            or record.get('funding_sha256')!=prior.digest({k:v for k,v in record.items() if k!='funding_sha256'})):
        raise ValueError('Exact shared completed-parent funding audit required')
    source_id,target_id=prior._id(record['parent_envelope_id']),prior._id(record['new_envelope_id'])
    if source_id==target_id or {j['run_id'] for j in attached}!={source_id,target_id}:
        raise ValueError('Batch transfer cannot fork, merge or self-reference')
    source,target=by_id[source_id],by_id[target_id];parent=record['parent_completed']
    if not isinstance(parent,dict):raise ValueError('Completed-parent proof required')
    if (record.get('new_reservation_created') is not True or record.get('parent_runtime_infeasible') is not True
            or record.get('accuracy_used_as_gate') is not False or type(record.get('parent_validated_outputs')) is not int
            or record['parent_validated_outputs']!=200 or type(record.get('new_batch_size')) is not int or record['new_batch_size']!=32
            or type(record.get('new_max_new_tokens')) is not int or record['new_max_new_tokens']!=2048
            or any(prior._money(record[k])!=Decimal(v) for k,v in (
                ('transferred_unused_usd','3.50'),('additional_new_reservation_usd','1.75'),
                ('total_commitment_increase_usd','1.75'),('funded_envelope_usd','5.25'),('historical_allowance_each_usd','1.75')))):
        raise ValueError('Only explicit3.50 transfer plus NEW1.75 batch32 funding is supported')
    for job in (source,target):
        if (job.get('service','modal')!='modal' or job.get('native_envelope') is not True
                or not prior._hash(job.get('native_design_sha256'))):raise ValueError('Explicit native Modal envelopes required')
    if (source.get('status')!='superseded' or prior._money(source.get('reserved_usd',-1))!=0
            or source.get('superseded_by')!=target_id or prior._money(source.get('initial_reserved_usd',0))!=Decimal('5.25')
            or target.get('status')!='reserved' or prior._money(target.get('initial_reserved_usd',0))!=Decimal('5.25')
            or target.get('native_design_sha256')!=record['new_design_sha256']):
        raise ValueError('Actual source must be zero superseded and target a reserved5.25 envelope')
    for key in ('new_design_sha256','new_manifest_sha256','batch_runtime_review_sha256','parent_funding_receipt_sha256'):
        if not prior._hash(record.get(key)):raise ValueError('Funding review/source/manifest proof hash required')
    prior._inventory(record['new_source_sha256']);prior._stamp(record['created_at_utc'])
    if (parent.get('parent_completed') is not True or parent.get('runtime_infeasible') is not True
            or type(parent.get('validated_outputs')) is not int or parent['validated_outputs']!=200
            or Path(parent.get('original_output','')).name+'-envelope'!=source_id
            or parent.get('original_design_sha256')!=source['native_design_sha256']):
        raise ValueError('A successful complete200 parent is required; never relabel it failed')
    child_id=record['parent_completed_child_run_id'];child=by_id.get(child_id,{})
    if (child_id!=parent.get('original_baseline_run_id') or source.get('dispatches')!=[child_id]
            or child.get('status')!='completed' or child.get('service','modal')!='modal'
            or child.get('native_envelope_parent')!=source_id or prior._money(child.get('reserved_usd',0))!=Decimal('1.75')
            or any(child.get(k)!=parent.get(v) for k,v in (
                ('native_design_sha256','original_design_sha256'),('native_claim_id','original_claim_id'),
                ('native_intent_sha256','original_intent_sha256'),('native_terminal_sha256','original_provider_terminal_sha256'),
                ('call_id','original_call_id')))):
        raise ValueError('Original completed child allowance/claim/call/terminal must stay intact')
    for key in ('original_design_sha256','original_manifest_sha256','original_launch_sha256',
            'original_provider_terminal_sha256','original_provider_result_sha256','original_result_sha256',
            'original_raw_validation_sha256','original_raw_inventory_sha256','original_calibration_sha256'):
        if not prior._hash(parent.get(key)):raise ValueError('Completed physical receipt hash missing')
    prior._inventory(parent.get('original_source_sha256'))
    launch={k:child[v] for k,v in (('run_id','run_id'),('call_id','call_id'),('claim_id','native_claim_id'),('intent_sha256','native_intent_sha256'))}
    if prior._file_digest(launch)!=parent['original_launch_sha256']:raise ValueError('Completed launch hash changed')
    calibration=parent.get('original_calibration');forwarded=parent.get('original_forwarded_input_tokens')
    if not isinstance(calibration,dict) or not isinstance(forwarded,dict) or set(forwarded)!={'concise','thinking'}:
        raise ValueError('Actual frozen calibration and both exposure forecasts required')
    generation=calibration.get('baseline_generation_seconds');elapsed=calibration.get('baseline_elapsed_seconds')
    if (not _finite(generation) or generation<0 or not _finite(elapsed) or not 0<elapsed<=1805
            or generation>elapsed or any(type(v) is not int or v<=0 for v in forwarded.values())):
        raise ValueError('Finite actual completed calibration timing required')
    forecasts={role:round(80+1.25*generation+.0032*value,3) for role,value in forwarded.items()}
    if (calibration.get('baseline_call_id')!=child['call_id']
            or calibration.get('design_sha256')!=parent['original_design_sha256']
            or calibration.get('baseline_result_sha256')!=parent['original_result_sha256']
            or calibration.get('raw_validation_sha256')!=parent['original_raw_validation_sha256']
            or calibration.get('forecast_seconds')!=forecasts
            or calibration.get('formula')!='80+1.25*baseline_generation_seconds+0.0032*forwarded_input_tokens'
            or calibration.get('guards')!={'training':1400,'evaluation':1600,'hard':1800}
            or calibration.get('pair_runtime_feasible') is not False or (elapsed<1550 and max(forecasts.values())<=1250)):
        raise ValueError('Frozen parent runtime gate must recompute infeasible without accuracy')
    if prior._file_digest(calibration)!=parent['original_calibration_sha256']:raise ValueError('Exact calibration bytes are not bound')
    old_receipt=parent.get('parent_funding_receipt')
    if (not isinstance(old_receipt,dict) or source.get('native_config_funding')!=old_receipt
            or prior._file_digest(old_receipt)!=parent.get('parent_funding_receipt_sha256')
            or record['parent_funding_receipt_sha256']!=parent['parent_funding_receipt_sha256']):
        raise ValueError('Preserve full V1/V2/V3 incoming funding history')
    if prior._stamp(record['created_at_utc'])<prior._stamp(old_receipt['created_at_utc']):raise ValueError('Transfer predates incoming funds')
    children=[j for j in jobs if j.get('native_envelope_parent')==target_id]
    if (len(children)>3 or target.get('dispatches')!=[j['run_id'] for j in children]
            or prior._money(target['reserved_usd'])+sum((prior._money(j.get('reserved_usd',0)) for j in children),Decimal(0))!=Decimal('5.25')
            or any(j.get('service','modal')!='modal' or prior._money(j.get('reserved_usd',0))!=Decimal('1.75')
                or j.get('native_design_sha256')!=target['native_design_sha256'] for j in children)):
        raise ValueError('New original three-call allowances do not conserve')
    # A proof-only restored parent validates its OLD incoming graph. Never
    # pass this synthetic3.50 to liability reconciliation beside the new5.25.
    proof_view=deepcopy(ledger)
    for job in proof_view['jobs']:
        job.pop('native_batch_funding',None)
        if job['run_id']==source_id:
            job.update(status='reserved',reserved_usd=3.5);job.pop('superseded_by',None)
    old_proof=prior.verify_transfers(proof_view)
    return {'version':VERSION,'conservation_verified':True,
        'verified_superseded_ids':sorted(old_proof['verified_superseded_ids']+[source_id]),
        'edges':old_proof['edges']+[{'source':source_id,'target':target_id,'transferred_usd':3.5,
            'new_reservation_usd':1.75,'receipt_sha256':prior.digest(record)}],
        'batch_transfer':{'parent_completed':True,'validated_outputs':200,'accuracy_used_as_gate':False}}


def reconcile(ledger,snapshot,*,apps=(),now=None,lag_minutes=15,lag_buffer_usd=3):
    proof=verify_transfers(ledger);planning=deepcopy(ledger)
    for job in planning['jobs']:
        if job['run_id'] in proof['verified_superseded_ids']:job['status']='reserved'
    result=prior.legacy.reconcile(planning,snapshot,apps=apps,now=now,
        lag_minutes=lag_minutes,lag_buffer_usd=lag_buffer_usd)
    for job in result['jobs']:
        if job['run_id'] in proof['verified_superseded_ids']:
            job['status']='superseded'
            job['budget_liability']={'kind':'verified_transferred_native_envelope_zero','amount_usd':0.0,
                'note':'Actual zero transfer source; historical completed/failed children remain unchanged.'}
    result['native_transfer_accounting']=proof
    return result
