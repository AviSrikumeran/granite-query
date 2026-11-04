"""Pure teacher-only final-scale receipts; no files, providers or permissions.

The existing final_scale_receipts remains the base/chosen GPU contract. These
helpers validate supplied teacher metadata and retain the complete denominator.
"""
from decimal import Decimal
import json
import math
import re

from cloud import final_scale_contract as contract
from cloud.final_scale_receipts import validate_binding
from cloud.comparison_metrics import score

VERSION = 'final-scale-teacher-v1'
ROLE = 'final_eval_only'
MAX_BODY = 1024*1024
MAX_HEADER_BYTES = 16*1024
MAX_MESSAGES_BYTES = 1900
OUTCOMES = {'generated', 'truncated', 'input_limit', 'api_failure', 'execution_failure'}
IDENTITY = ('freeze_sha256','source_bundle_sha256','full_source_sha256','sample_sha256',
            'binding_sha256','seal_sha256','bundle_id','manifest_sha256')
SETTINGS = {'model':'deepseek-v4-pro','max_tokens':512,'temperature':0,'stream':False,
            'thinking':{'type':'disabled'}}


def digest(value): return contract.digest(value)
def integer(value): return type(value) is int and value >= 0
def finite(value): return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0
def sealed(value, field): return dict(value, **{field:digest(value)})


def check_hash(value, field):
    contract.require_hash(value.get(field))
    if digest({k:v for k,v in value.items() if k != field}) != value[field]:
        raise ValueError('Receipt hash differs: '+field)


def settings(value):
    contract.validate(value)
    p = value['protocol']; n = p['dataset']['sample_count']; teacher = p['model_roles']['teacher']
    expected = {'questions':n,'model':'deepseek-v4-pro','max_attempts':n,'max_tokens':512,
                'thinking_enabled':False,'max_concurrent_requests':4,'automatic_retries':0,'input_token_cap':2000}
    if any(teacher.get(k) != v for k,v in expected.items()) or p['inference']['max_new_tokens'] != 512:
        raise ValueError('Teacher differs from the bounded final-scale contract')
    return dict(SETTINGS, user_prefix_sha256=digest(p['inference']['user_prefix']))


def build_manifest(value, binding, *, seal_sha256, bundle_id, request_manifest_sha256):
    validate_binding(value,binding)
    contract.require_hash(seal_sha256); contract.require_hash(request_manifest_sha256)
    if not isinstance(bundle_id,str) or not contract.NAME.fullmatch(bundle_id): raise ValueError('Unsafe bundle identity')
    p = value['protocol']; n = p['dataset']['sample_count']; config = settings(value)
    result = {'schema_version':1,'version':VERSION,'role':ROLE,'source_split':'test','model_role':'teacher',
        **{k:binding[k] for k in ('freeze_sha256','source_bundle_sha256','full_source_sha256','sample_sha256','binding_sha256')},
        'seal_sha256':seal_sha256,'bundle_id':bundle_id,'sample_count':n,'max_original_attempts':n,
        'question_ids_sha256':digest(contract.expected_ids(value)), 'request_manifest_sha256':request_manifest_sha256,
        'settings':config,'settings_sha256':digest(config),'max_concurrent':4,'automatic_retries':0,
        'input_token_cap':2000,'max_messages_utf8_bytes':MAX_MESSAGES_BYTES,'max_response_bytes':MAX_BODY,
        'input_bound_basis':'UTF8 serialized messages<=1900 bytes plus conservative100-token single-user framing allowance; no tools/history/system or Granite-tokenizer substitution. Validate provider usage and halt on any breach.',
        'max_response_header_bytes':MAX_HEADER_BYTES,
        'conservative_max_cost_usd':p['bounds']['teacher_peak_token_bound_usd'],
        'reserved_usd_required':p['bounds']['teacher_reservation_usd'],'training_eligible':False}
    return sealed(result,'manifest_sha256')


def validate_manifest(value,binding,manifest):
    check_hash(manifest,'manifest_sha256')
    expected = build_manifest(value,binding,seal_sha256=manifest['seal_sha256'],bundle_id=manifest['bundle_id'],
                              request_manifest_sha256=manifest['request_manifest_sha256'])
    if manifest != expected: raise ValueError('Teacher manifest differs from its full sealed sample/settings')
    return manifest


def phase_template(manifest, pending_ids, reservation_id, *, phase_id, halt_sha256=None):
    if (not isinstance(pending_ids,list) or len(set(pending_ids)) != len(pending_ids)
            or not all(isinstance(x,str) for x in pending_ids) or not 0 < len(pending_ids) <= manifest['sample_count']):
        raise ValueError('Require the exact nonempty ordered never-attempted identities')
    for name in (reservation_id,phase_id):
        if not isinstance(name,str) or not contract.NAME.fullmatch(name): raise ValueError('Unsafe phase/reservation identity')
    if halt_sha256 is not None: contract.require_hash(halt_sha256)
    return {'schema_version':1,'role':'final_teacher_phase_approval','approved':False,
        **{k:manifest[k] for k in IDENTITY},'phase_id':phase_id,'reservation_id':reservation_id,
        'never_attempted_ids_sha256':digest(pending_ids),'never_attempted_count':len(pending_ids),
        'halt_sha256':halt_sha256,'resume_unattempted_after_halt':halt_sha256 is not None,
        'zero_retries_acknowledged':True}


def validate_phase(manifest,approval,pending_ids,*,reservation_id,halt_sha256=None,prior_approval_sha256=None):
    if not isinstance(approval,dict): raise ValueError('Explicit phase approval is required')
    expected = phase_template(manifest,pending_ids,reservation_id,phase_id=approval.get('phase_id'),halt_sha256=halt_sha256)
    expected['approved'] = True
    if approval != expected: raise ValueError('Approval does not bind exact never-attempted IDs, halt, manifest and reservation')
    if prior_approval_sha256 is not None and digest(approval) == prior_approval_sha256:
        raise ValueError('A stopped phase cannot authorize new scheduling again')
    return digest(approval)


def make_intent(manifest,question,position,*,request_sha256,phase_approval_sha256):
    for value in (request_sha256,phase_approval_sha256): contract.require_hash(value)
    return sealed({'schema_version':1,'role':ROLE, **{k:manifest[k] for k in IDENTITY},
        'id':question['id'],'source_index':question['source_index'],'global_position':position,
        'input_sha256':question['input_sha256'],'request_sha256':request_sha256,
        'settings_sha256':manifest['settings_sha256'],'phase_approval_sha256':phase_approval_sha256,
        'automatic_retries':0},'intent_sha256')


def validate_intent(manifest,question,position,intent,request_sha256):
    check_hash(intent,'intent_sha256')
    expected = make_intent(manifest,question,position,request_sha256=request_sha256,
                           phase_approval_sha256=intent['phase_approval_sha256'])
    if intent != expected: raise ValueError('Original teacher intent no longer matches this exact request')
    return intent


def _usage(raw):
    usage = raw.get('usage') if isinstance(raw,dict) else None
    if not isinstance(usage,dict) or not all(integer(usage.get(k)) for k in ('prompt_tokens','completion_tokens')): return None
    details = usage.get('completion_tokens_details')
    reasoning = details.get('reasoning_tokens') if isinstance(details,dict) else None
    if reasoning is not None and (not integer(reasoning) or reasoning > usage['completion_tokens']): return None
    return {'prompt_tokens':usage['prompt_tokens'],'completion_tokens':usage['completion_tokens'],'reasoning_tokens':reasoning}


def base_receipt(manifest,question,position,intent,*,elapsed_seconds,latency_recovered=False):
    if elapsed_seconds is not None and not finite(elapsed_seconds): raise ValueError('Invalid elapsed time')
    if type(latency_recovered) is not bool or elapsed_seconds is None and not latency_recovered:
        raise ValueError('Unknown latency must be explicitly marked recovered without timing')
    return {'schema_version':1,'role':ROLE,'model_role':'teacher', **{k:manifest[k] for k in IDENTITY},
        'id':question['id'],'source_index':question['source_index'],'global_position':position,
        'input_sha256':question['input_sha256'],'gold_answer':question['gold_answer'],
        'request_sha256':intent['request_sha256'],'intent_sha256':intent['intent_sha256'],
        'phase_approval_sha256':intent['phase_approval_sha256'],'settings_sha256':manifest['settings_sha256'],
        'requested_model':'deepseek-v4-pro','actual_returned_model':None,'system_fingerprint':None,
        'outcome':'execution_failure','response':'','reasoning_content':'','finish_reason':None,
        'generated_tokens':0,'truncated':False,'usage':None,'provider_call_attempted':True,
        'raw_response_sha256':None,'raw_response_bytes':0,'raw_complete':False,'body_read_failed':False,
        'http_status':None,'response_header_bytes':None,'failure_type':None,'elapsed_seconds':elapsed_seconds,
        'latency_recovered_without_timing':latency_recovered,'training_eligible':False}


def from_wire(manifest,question,position,intent,wire,*,elapsed_seconds,latency_recovered=False,
              http_status=200,response_header_bytes=0,body_read_failed=False):
    if not isinstance(wire,bytes) or len(wire) > MAX_BODY+1: raise ValueError('Wire exceeds bounded saved bytes')
    import hashlib
    r = base_receipt(manifest,question,position,intent,elapsed_seconds=elapsed_seconds,latency_recovered=latency_recovered)
    if (type(http_status) is not int or not 100<=http_status<=599 or not integer(response_header_bytes)
            or type(body_read_failed) is not bool):
        raise ValueError('Invalid bounded transport metadata')
    r.update(http_status=http_status,response_header_bytes=response_header_bytes)
    r.update(raw_response_sha256=hashlib.sha256(wire).hexdigest(),raw_response_bytes=len(wire),raw_complete=len(wire)<=MAX_BODY)
    if body_read_failed:
        r.update(body_read_failed=True,raw_complete=False,failure_type='transport_ambiguous')
        return sealed(r,'receipt_sha256')
    if len(wire)>MAX_BODY:
        r['failure_type']='response_byte_limit';return sealed(r,'receipt_sha256')
    if response_header_bytes>MAX_HEADER_BYTES:
        r['failure_type']='response_header_limit';return sealed(r,'receipt_sha256')
    r.update(outcome='api_failure',failure_type='invalid_provider_receipt')
    if http_status>=400: r['failure_type']='http_error'
    try:
        raw = json.loads(wire); choice = raw['choices'][0]; msg = choice['message']
        content, reasoning = msg.get('content'), msg.get('reasoning_content')
        if not isinstance(content,(str,type(None))) or not isinstance(reasoning,(str,type(None))):
            raise ValueError('Invalid channels')
        content,reasoning=content or '',reasoning or ''
        # Validate encodability without changing the originals.
        content.encode('utf-8');reasoning.encode('utf-8')
        model = raw.get('model'); fingerprint = raw.get('system_fingerprint')
        finish = choice.get('finish_reason')
        if model is not None and (not isinstance(model,str) or len(model)>256): raise ValueError('Invalid returned model')
        if fingerprint is not None and (not isinstance(fingerprint,str) or len(fingerprint)>256): raise ValueError('Invalid fingerprint')
        if finish is not None and (not isinstance(finish,str) or len(finish)>64):raise ValueError('Invalid finish identity')
        if model is not None:model.encode('utf-8')
        if fingerprint is not None:fingerprint.encode('utf-8')
        usage = _usage(raw)
        r.update(response=content,reasoning_content=reasoning,actual_returned_model=model,
            system_fingerprint=fingerprint,finish_reason=finish,usage=usage,
            generated_tokens=usage['completion_tokens'] if usage else 0,truncated=finish=='length')
        if http_status>=400: r['failure_type']='http_error'
        elif usage is None: r['failure_type']='unknown_provider_usage'
        elif usage['prompt_tokens']>2000 or usage['completion_tokens']>512: r['failure_type']='provider_token_bound'
        elif not model or not model.casefold().startswith('deepseek-v4-pro'): r['failure_type']='unexpected_teacher_model'
        elif reasoning or (usage.get('reasoning_tokens') or 0)>0: r['failure_type']='unexpected_reasoning_channel'
        elif choice.get('finish_reason')=='length': r.update(outcome='truncated',failure_type=None)
        elif choice.get('finish_reason')=='stop': r.update(outcome='generated',failure_type=None)
        else: r['failure_type']='provider_nonstop_completion'
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,UnicodeError): pass
    return sealed(r,'receipt_sha256')


def failure(manifest,question,position,intent,*,kind,elapsed_seconds=0,http_status=None):
    r = base_receipt(manifest,question,position,intent,elapsed_seconds=elapsed_seconds)
    allowed = {'input_limit','http_error','transport_ambiguous','execution_failure'}
    if kind not in allowed: raise ValueError('Unknown bounded failure kind')
    if kind=='input_limit': r.update(outcome='input_limit',provider_call_attempted=False,elapsed_seconds=0)
    elif kind=='http_error':
        if type(http_status) is not int or not 100<=http_status<=599: raise ValueError('Invalid HTTP status')
        r.update(outcome='api_failure',http_status=http_status)
    r['failure_type']=kind
    return sealed(r,'receipt_sha256')


def halt_reason(receipt):
    if receipt.get('http_status') in (401,402,403,429): return 'http_'+str(receipt['http_status'])
    if receipt['provider_call_attempted'] and receipt['usage'] is None: return 'unknown_provider_usage_or_transport'
    if receipt['failure_type'] in ('provider_token_bound','unexpected_teacher_model','unexpected_reasoning_channel'):
        return receipt['failure_type']
    return None


def validate_attempt(manifest,question,position,intent,receipt,*,request_sha256,wire=None):
    validate_intent(manifest,question,position,intent,request_sha256)
    check_hash(receipt,'receipt_sha256')
    if receipt.get('outcome') not in OUTCOMES: raise ValueError('Unknown teacher outcome')
    if wire is not None:
        expected = from_wire(manifest,question,position,intent,wire,elapsed_seconds=receipt.get('elapsed_seconds'),
            latency_recovered=receipt.get('latency_recovered_without_timing'),http_status=receipt.get('http_status'),
            response_header_bytes=receipt.get('response_header_bytes'),body_read_failed=receipt.get('body_read_failed'))
    else:
        expected = failure(manifest,question,position,intent,kind=receipt.get('failure_type'),
            elapsed_seconds=receipt.get('elapsed_seconds'),http_status=receipt.get('http_status'))
    if receipt != expected: raise ValueError('Teacher result differs from original wire/failure receipt')
    return receipt


def scoring_rows(receipts):
    """Whole-denominator rows for later paired statistics; never drop failures."""
    return [{'id':r['id'],'response':r['response'],'gold_answer':r['gold_answer'],
             'truncated':r['truncated'] or r['outcome']!='generated'} for r in receipts]


def aggregate(manifest,binding,receipts):
    """Caller first validates each receipt against its original intent/wire."""
    check_hash(manifest,'manifest_sha256');check_hash(binding,'binding_sha256')
    if (manifest.get('sample_count') not in (1000,1319)
            or any(binding.get(k)!=manifest[k] for k in ('freeze_sha256','source_bundle_sha256',
                'full_source_sha256','sample_sha256','binding_sha256'))):
        raise ValueError('Teacher aggregate differs from its full final-scale binding')
    ids = [q['id'] for q in binding['questions']]
    if len(ids)!=manifest['sample_count'] or len(set(ids))!=len(ids) or digest(ids)!=manifest['question_ids_sha256']:
        raise ValueError('Teacher aggregate must retain the one fixed denominator/order')
    indexed = {r['id']:r for r in receipts}
    if len(indexed)!=len(receipts) or not set(indexed)<=set(ids): raise ValueError('Duplicated or foreign teacher outcomes')
    for r in receipts:
        check_hash(r,'receipt_sha256')
        if not integer(r.get('global_position')) or not r['global_position']<len(binding['questions']):
            raise ValueError('Teacher outcome has invalid global position')
        q = binding['questions'][r['global_position']]
        if (any(r.get(k)!=manifest[k] for k in IDENTITY) or r['id']!=q['id'] or r['input_sha256']!=q['input_sha256']
                or r['source_index']!=q['source_index'] or r['gold_answer']!=q['gold_answer']):
            raise ValueError('Teacher outcome input/reference/manifest differs')
    ordered = [indexed[i] for i in ids if i in indexed]
    complete = len(ordered)==manifest['sample_count']
    counts = {key:sum(r['outcome']==key for r in ordered) for key in sorted(OUTCOMES)}
    correct = strict = 0
    if complete:
        for r in scoring_rows(ordered):
            result = score(r)
            correct += result['correct']; strict += result['strict_format_correct']
    usage = {key:sum(r['usage'][key] for r in ordered if r['usage'] is not None) for key in ('prompt_tokens','completion_tokens')}
    known_times = [r['elapsed_seconds'] for r in ordered if r['provider_call_attempted'] and r['elapsed_seconds'] is not None]
    return {'schema_version':1,'role':ROLE,'model_role':'teacher',**{k:manifest[k] for k in IDENTITY},
        'expected_count':manifest['sample_count'],'retained_count':len(ordered),'status':'completed' if complete else 'incomplete',
        'outcomes':counts,'metrics':{'count':len(ids),'numeric_correct':correct,'strict_format_correct':strict,
            'accuracy_percent':100*correct/len(ids)} if complete else None,
        'known_usage':usage,'unknown_usage_attempts':sum(r['provider_call_attempted'] and r['usage'] is None for r in ordered),
        'provider_calls_attempted':sum(r['provider_call_attempted'] for r in ordered),
        'recorded_peak_token_estimate_usd':float((Decimal(usage['prompt_tokens'])*Decimal('1.32')+Decimal(usage['completion_tokens'])*Decimal('3.96'))/1000000),
        'measured_round_trip_seconds_total':sum(known_times),'timing_observed_attempts':len(known_times),
        'actual_returned_models':sorted({r['actual_returned_model'] for r in ordered if isinstance(r['actual_returned_model'],str)
            and re.fullmatch(r'[A-Za-z0-9_.-]{1,256}',r['actual_returned_model'])}),
        'training_eligible':False,'official_test_used':True,
        'limitations':['Whole frozen denominator; failures are never filtered or resampled.',
            'Known token estimates exclude unknown attempted-request charges and are not invoices.',
            'Teacher API round trips are separate from amortized batched Granite GPU time.',
            'Numeric final-answer scoring does not verify intermediate reasoning.']}
