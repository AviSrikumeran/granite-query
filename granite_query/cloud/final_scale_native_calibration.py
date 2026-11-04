"""Read-only bridge prototype for ONE native paired400 compatibility result.

This does not consume NativeStudy receipts, choose a checkpoint, authorize a
provider call, grant final-data access, or make the old physical seal accept a
new format. Supply actual native proof objects; never fabricate per-role
provider-returned results. Pure validation and explicit physical inspection are
separate. No tokenizer/model download is performed by either entrypoint.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from cloud import final_scale_compat as compat
from cloud import final_scale_contract as contract_api
from cloud import final_scale_seal as physical

VERSION = 'native-paired400-calibration-bridge-v1'
ROLES = ('base', 'chosen')
MAX_JSON_BYTES = 64*1024*1024
MAX_RAW_BYTES = 1024*1024
TOKENIZER_BITS = {'chat_template_sha256': 'f0ba43f79b3cabca5e5a7584c77aec92f49feae45cdf7779c87d9fc54cd90258',
    'backend_sha256': 'ea0abe115d2928a025701b521d950e11b578be3fc4f32bd0c1aaa9060e48a9a5',
    'eos_token': '<|im_end|>', 'eos_token_id': 100257}
RAW_FIELDS = {'role','checkpoint','plan_sha256','call_id','start','count','question_ids','input_tokens',
    'generated_ids','generation_failed','generation_elapsed_seconds','eos_token_ids'}


def digest(value): return contract_api.digest(value)
def sha(raw): return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value: raise ValueError('Duplicate JSON key')
        value[key] = item
    return value


def parse(raw, *, limit=MAX_JSON_BYTES):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= limit: raise ValueError('Bounded exact original bytes required')
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        pending = [(value,0)]; nodes = 0
        while pending:
            item,depth = pending.pop();nodes += 1
            if depth > 64 or nodes > 1000000: raise ValueError('Receipt JSON tree exceeds fixed bounds')
            if isinstance(item,dict): pending.extend((child,depth+1) for child in item.values())
            elif isinstance(item,list): pending.extend((child,depth+1) for child in item)
        # The entire tree, including unused fields, must remain safely durable.
        compat.encoded(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ValueError('Invalid finite UTF8 receipt JSON') from error


def _object(value, label):
    if not isinstance(value, dict): raise ValueError(label+' must be an object')
    return value


def _tokenizer_bits(tokenizer):
    try:
        actual = {'chat_template_sha256': sha(tokenizer.chat_template.encode('utf-8')),
            'backend_sha256': sha(tokenizer.backend_tokenizer.to_str().encode('utf-8')),
            'eos_token': tokenizer.eos_token, 'eos_token_id': tokenizer.eos_token_id}
    except (AttributeError, TypeError, UnicodeError) as error:
        raise ValueError('Already loaded pinned tokenizer required') from error
    if actual != TOKENIZER_BITS: raise ValueError('Actual tokenizer/template/backend/EOS bits differ')
    return actual


def _identity(plan, dispatch, launch, terminal, result_sha256):
    _object(launch, 'Launch'); _object(terminal, 'Provider terminal')
    call_id = launch.get('call_id')
    if not isinstance(call_id, str) or re.fullmatch(r'fc-[A-Za-z0-9-]+', call_id) is None:
        raise ValueError('Actual provider call ID required')
    bindings = {'run_id': plan['run_id'], 'call_id': call_id, 'plan_sha256': plan['plan_sha256'],
        'dispatch_sha256': dispatch['dispatch_sha256'], 'claim_id': dispatch['claim_id']}
    if any(launch.get(key) != expected or terminal.get(key) != expected for key, expected in bindings.items()):
        raise ValueError('Native launch/terminal must bind one exact plan, claim and call')
    if (terminal.get('kind') != 'completed' or terminal.get('confirmed_terminal') is not True
            or terminal.get('result_sha256') != result_sha256):
        raise ValueError('Matching confirmed complete native provider result required')
    try:
        stamp = datetime.fromisoformat(terminal['observed_at_utc'].replace('Z','+00:00'))
        if stamp.tzinfo is None: raise ValueError('Unzoned observation')
    except (KeyError, AttributeError, TypeError, ValueError) as error:
        raise ValueError('Zoned provider observation time required') from error
    return call_id


def _validate_bundle(value, *, plan, payload, input_descriptor, authorization, dispatch, launch,
                    provider_terminal, provider_result_bytes, raw_batches, tokenizer):
    """Pure original-input/native-result validator; see module boundaries."""
    for item, label in ((value,'Contract'), (plan,'Plan'), (payload,'Input'),
            (authorization,'Authorization'), (dispatch,'Dispatch'), (raw_batches,'Raw inventory')): _object(item,label)
    compat.validate_sources(value)
    if Path(__file__).name not in value['protocol']['source_roles']['checkpoint_validator']:
        raise ValueError('The separate native calibration bridge must be source-bound')
    if authorization.get('sealed',{}).get('contract') != value: raise ValueError('Authorization contract differs')
    compat.validate_metadata(plan,input_descriptor,authorization)
    compat.validate_dispatch(plan,authorization,dispatch)
    rows = compat.validate_payload(payload,plan,authorization)
    result = parse(provider_result_bytes); _object(result,'Native provider result')
    result_sha = sha(provider_result_bytes)
    call_id = _identity(plan,dispatch,launch,provider_terminal,result_sha)
    if (result.get('call_id') != call_id or result.get('raw_pending') is not False
            or set(result.get('evaluations',{})) != set(ROLES)
            or set(result.get('batches',{})) != set(ROLES)
            or set(raw_batches) != set(ROLES)):
        raise ValueError('One complete paired400 native result with no pending raw is required')
    evidence = compat.validate_result(value,plan,payload,result)
    if (not compat.finite(result['elapsed_seconds']) or not 0 < result['elapsed_seconds'] <= 1805
            or evidence.get('calibration',{}).get('runtime_feasible') is not True):
        raise ValueError('Observed complete compatibility timing must fit its bounds')
    bits = _tokenizer_bits(tokenizer)
    counts = []
    for row in rows:
        prompt = tokenizer.apply_chat_template([{'role':'user','content':value['protocol']['inference']['user_prefix']+row['prompt']}],
            tokenize=False,add_generation_prompt=True,enable_thinking=False)
        if not isinstance(prompt,str): raise ValueError('Pinned rendered prompt must be text')
        ids = tokenizer.encode(prompt,add_special_tokens=False)
        if not isinstance(ids,list) or not ids or any(type(token) is not int or not 0 <= token < 100352 for token in ids):
            raise ValueError('Pinned prompt encoding differs')
        counts.append(len(ids))
    roles = {}
    for role in ROLES:
        supplied = raw_batches[role]
        if not isinstance(supplied,dict) or set(supplied) != set(range(0,200,8)):
            raise ValueError('Exact25 physical raw batches per native role required')
        replay, raw_hashes = [], []
        for start, saved in zip(range(0,200,8),result['batches'][role]):
            original = supplied[start]; raw = parse(original,limit=MAX_RAW_BYTES); _object(raw,'Raw batch')
            if (set(raw) != RAW_FIELDS or raw.get('checkpoint') != role or raw.get('call_id') != call_id
                    or raw.get('plan_sha256') != plan['plan_sha256'] or raw.get('start') != start
                    or raw.get('input_tokens') != counts[start:start+8] or raw.get('eos_token_ids') != [100257]
                    or original != compat.encoded(raw)):
                raise ValueError('Native raw identity, pinned input counts or original serialization differ')
            derived = compat.derive_batch(rows,raw,lambda ids: tokenizer.decode(ids,
                skip_special_tokens=True,clean_up_tokenization_spaces=False))
            if derived != saved or any(not isinstance(row.get('response'),str) for row in derived['rows']):
                raise ValueError('Native derived responses differ from exact original tokens')
            if any(row['outcome'] != 'generated' for row in derived['rows']):
                raise ValueError('Full-input execution is required for a physical runtime calibration')
            replay.extend(derived['rows']); raw_hashes.append({'start':start,'sha256':sha(original)})
        if replay != result['evaluations'][role]: raise ValueError('Native ordered200 outcomes differ')
        timing = result['runtime_timings'][role]
        if sum(row['elapsed_seconds'] for row in replay) > timing['role_wall_seconds']+.001:
            raise ValueError('Generation duration exceeds its enclosing role wall time')
        roles[role] = {'count':200,'provider_result_sha256':result_sha,'provider_call_id':call_id,
            'outcomes_sha256':digest(replay),'raw_inventory_sha256':digest(raw_hashes),
            'generation_seconds':timing['generation_seconds'],'role_wall_seconds':timing['role_wall_seconds'],
            'truncated':sum(row['truncated'] for row in replay)}
    calibration = compat.calibration_record(value,result['evaluations'],result['runtime_timings'],result['elapsed_seconds'])
    rebuilt = compat.make_evidence(value,plan,authorization,call_id=call_id,
        proofs=evidence['proofs_by_role'],calibration=calibration,evaluations=result['evaluations'])
    if rebuilt != evidence or evidence['proofs_by_role']['chosen'].get('baseline_adapter_unloaded') is not False:
        raise ValueError('Actual paired role/model/PEFT/value proof differs')
    candidate = contract_api.calibration(value,base_generation_seconds=roles['base']['generation_seconds'],
        chosen_generation_seconds=roles['chosen']['generation_seconds'],
        evidence_hashes={role:result_sha for role in ROLES},load_allowance_seconds=calibration['load_allowance_seconds'])
    body = {'schema_version':1,'version':VERSION,'role':'native_paired400_development_calibration',
        'run_id':plan['run_id'],'call_id':call_id,'freeze_sha256':value['freeze_sha256'],
        'source_bundle_sha256':digest(value['protocol']['source_hashes']),
        'selected_sha256':digest(value['protocol']['selected']),'adapter_inventory_sha256':plan['adapter_inventory_sha256'],
        'adapter_model_sha256':plan['adapter_model_sha256'],'inference_sha256':plan['inference_sha256'],
        'plan_sha256':plan['plan_sha256'],'input_sha256':plan['input_sha256'],
        'authorization_sha256':authorization['authorization_sha256'],'dispatch_sha256':dispatch['dispatch_sha256'],
        'launch_sha256':digest(launch),'provider_terminal_sha256':digest(provider_terminal),
        'native_provider_result_sha256':result_sha,'runtime_evidence_sha256':evidence['evidence_sha256'],
        'tokenizer_bits':bits,'per_role':roles,'calibration_candidate':candidate,
        'native_timing_evidence':calibration,'same_native_provider_result_for_both_roles':True,
        'old_per_role_physical_seal_format_compatible':False,'funded_entrypoint_verified':False,
        'official_test_used':False,'training_performed':False,'final_access_authorized':False,
        'limitations':['One native paired400 result, not two independent provider calls.',
            'This prototype does not consume NativeStudy separate-call receipts.',
            'Physical inspection verifies source/receipt files; adapter bytes are not re-downloaded or re-read by this bridge.',
            'The existing physical seal needs explicit versioned integration; no per-role provider wrapper is created.',
            'Runtime forecasts are planning estimates; no paid work, funding or access is authorized.']}
    return dict(body,bridge_sha256=digest(body))


def validate_bundle(value, **inputs):
    """Pure supplied-object/byte replay, retaining one original paired result.

    Keyword inputs: plan, payload, input_descriptor, authorization, dispatch,
    launch, provider_terminal, provider_result_bytes, raw_batches, tokenizer.
    No file/provider reads or writes occur here. An already loaded tokenizer is
    required; both roles cite the same original result and call. This does not
    grant funding/access or produce an old per-role provider wrapper.
    """
    try:
        return _validate_bundle(value, **inputs)
    except (KeyError, TypeError, AttributeError, UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError('Malformed native calibration input/proof') from error


def inspect_bundle(folder, *, tokenizer, source_paths):
    """Read actual explicit native files only, never datasets/providers/budgets."""
    folder = physical._safe(folder,private=True)
    if not folder.is_dir(): raise ValueError('Explicit private native receipt folder required')
    def raw(relative,limit=MAX_JSON_BYTES):
        path = physical._safe(folder/relative,private=True)
        if not path.is_relative_to(folder) or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ValueError('Physical native artifact path/type/size differs')
        return path.read_bytes()
    objects = {name:parse(raw(name+'.json')) for name in ('plan','input','input_descriptor','authorization','dispatch','launch','provider_terminal')}
    value = objects['authorization']['sealed']['contract']
    observed_paths,_ = physical._source_inventory(value,source_paths)
    loaded = {Path(__file__).name:Path(__file__).resolve(),
        **{Path(module.__file__).name:Path(module.__file__).resolve()
            for module in (compat,compat.execution,compat.layout)}}
    if any(Path(observed_paths.get(name,'')) != path for name,path in loaded.items()):
        raise ValueError('Physical review must bind exact loaded bridge and compatibility implementations')
    batches = {role:{start:raw(f'roles/{role}/raw/batch{start:04d}.json',MAX_RAW_BYTES)
        for start in range(0,200,8)} for role in ROLES}
    binding = validate_bundle(value,plan=objects['plan'],payload=objects['input'],
        input_descriptor=objects['input_descriptor'],authorization=objects['authorization'],dispatch=objects['dispatch'],
        launch=objects['launch'],provider_terminal=objects['provider_terminal'],
        provider_result_bytes=raw('provider_result.json'),raw_batches=batches,tokenizer=tokenizer)
    return {'binding':binding,'physical_source_files_verified':True,
        'physical_native_receipt_paths_verified':True,'provider_status_queried':False,
        'files_written':False,'old_seal_or_permit_created':False}


def native_study_adaptation_note():
    return {'stage':'prospective_design_only','implemented_by_this_module':False,
        'native_study_requires_another_paid400_call':False,
        'minimal_adapter':['Bind actual baseline/chosen run, plan/input, unique dispatch/claim/call, provider result and confirmed terminal hashes.',
            'Verify original raw batches and their existing raw_validation receipts for all200 ordered development questions per call.',
            'Bind the selected adapter saved-before-evaluation hashes and observed PEFT/layout/value proof; preserve actual capture timing.',
            'Derive per-role generation timing from retained raw batches and an enclosing worker duration, with no fabricated provider-returned exports.',
            'Version the final physical calibration schema/source review explicitly before sealing.'],
        'inference_warning':'Current NativeStudy open-thinking/1024 and prepared final nonthinking/512 differ. Weight/runtime proof may be reusable; timing is reusable only when the final frozen inference protocol actually matches, or after an explicitly reviewed development-only inference check.',
        'official_test_used':False,'actual_results_asserted':False,'model_or_protocol_chosen':False}


if __name__ == '__main__':
    print(json.dumps({'stage':'prototype_only_no_files_opened','version':VERSION,
        'funded_entrypoint':False,'official_test_used':False}))
