"""Matched DeepSeek measurement on the existing200 TRAIN development items.

Default inspection is metadata-only. Explicit prepare is unpaid; collection
requires root review, a fresh bound reservation and protected final credit.
No responses become training data and no official-test source is ever opened.
"""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from decimal import Decimal
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud import final_scale_teacher as shared
from cloud import final_scale_teacher_receipts as parser
from cloud import final_scale_loader as files
from cloud import final_scale_contract as contract
from cloud.deepseek_reconcile import require_fresh_deepseek_budget
from cloud.comparison_metrics import score

VERSION='development-teacher200-nonthinking512-v2'
ROLE='development_teacher_measurement'
SOURCE=ROOT/'runs/human_math_cohort2048_dev200_v1/development.jsonl'
SOURCE_SHA='cccdce864d728e6b43d9d4de866e719bfd9c706cc735a3a3d429095835c767c7'
RUN=ROOT/'runs/development_teacher200_nonthinking512_v2'
REQUESTS_FILE='development_teacher_requests.jsonl'
COST=Decimal(200)*(2000*Decimal('1.32')+512*Decimal('3.96'))/1000000
DEPS=('development_teacher200.py','final_scale_teacher.py','final_scale_teacher_receipts.py',
      'final_scale_loader.py','final_scale_contract.py','final_scale_seal.py','valuation_contract.py',
      'run_api_pilot.py','deepseek_reconcile.py','budget_reconcile.py','comparison_metrics.py')


def digest(value):return contract.digest(value)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def rows(path):return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]
def bytes_rows(values):return b''.join(files.encoded(v) for v in values)
def settings():return dict(parser.SETTINGS,user_prefix=contract.PREFIX)
def sources():return {name:sha((ROOT/name).read_bytes()) for name in DEPS}
def payload(row):return dict(parser.SETTINGS,messages=[{'role':'user','content':contract.PREFIX+row['prompt']}])


def prepare(output=RUN,*,authorized=False):
    if authorized is not True:raise ValueError('Explicit TRAIN development preparation authorization is required')
    output=files.private(output);raw=SOURCE.read_bytes()
    if sha(raw)!=SOURCE_SHA:raise ValueError('The exact existing human200 development source changed')
    data=[json.loads(line) for line in raw.decode('utf-8').split('\n') if line.strip()]
    if (len(data)!=200 or len({r['id'] for r in data})!=200
            or any(r.get('source_split')!='train' or not r['id'].startswith('gsm8k:train:') for r in data)):
        raise ValueError('Only the frozen200 unique TRAIN development questions are allowed')
    reference=[dict({k:r[k] for k in ('id','prompt','gold_answer','source_split')},training_eligible=False) for r in data]
    requested=[{'id':r['id'],'position':i,'payload':payload(r),'request_sha256':digest(payload(r))} for i,r in enumerate(reference)]
    manifest=parser.sealed({'version':VERSION,'role':ROLE,'run_id':output.name,'source_sha256':SOURCE_SHA,
        'source_split':'train','training_eligible':False,'official_test_used':False,'requested':200,'max_original_attempts':200,
        'reference_sha256':sha(bytes_rows(reference)),'requests_sha256':sha(bytes_rows(requested)),
        'settings':settings(),'settings_sha256':digest(settings()),'source_hashes':sources(),
        'max_messages_utf8_bytes':1900,'input_framing_allowance_tokens':100,'input_token_cap':2000,
        'max_output_tokens':512,'max_concurrent':4,'automatic_retries':0,
        'conservative_max_cost_usd':str(COST),'reserved_usd_required':'1','protected_final_deepseek_usd':'5'},'manifest_sha256')
    output.mkdir(parents=True,exist_ok=True)
    files.ensure_bytes(output/'development_source.jsonl',bytes_rows(reference))
    files.ensure_bytes(output/REQUESTS_FILE,bytes_rows(requested));files.ensure_json(output/'manifest.json',manifest)
    if not (output/'summary.json').exists():shared.mutable_json(output/'summary.json',summary(manifest,[],'prepared_unpaid'))
    return inspect_metadata(output)


def validate(output):
    output=files.private(output);m=read(output/'manifest.json');parser.check_hash(m,'manifest_sha256')
    reference,requested=rows(output/'development_source.jsonl'),rows(output/REQUESTS_FILE)
    if (m['version']!=VERSION or m['role']!=ROLE or m['run_id']!=output.name or m['source_sha256']!=SOURCE_SHA
            or sha(SOURCE.read_bytes())!=SOURCE_SHA or m['source_hashes']!=sources()
            or m['settings']!=settings() or m['settings_sha256']!=digest(settings()) or m['requested']!=200
            or m['max_original_attempts']!=200 or m['training_eligible'] is not False or m['official_test_used'] is not False
            or m['conservative_max_cost_usd']!=str(COST) or m['reserved_usd_required']!='1'
            or len(reference)!=200 or len({r['id'] for r in reference})!=200
            or sha(bytes_rows(reference))!=m['reference_sha256'] or sha(bytes_rows(requested))!=m['requests_sha256']):
        raise ValueError('Frozen development/source/settings contract differs')
    originals=rows(SOURCE)
    if reference!=[dict({k:r[k] for k in ('id','prompt','gold_answer','source_split')},training_eligible=False) for r in originals]:
        raise ValueError('Reference records differ from original human TRAIN source')
    if requested!=[{'id':r['id'],'position':i,'payload':payload(r),'request_sha256':digest(payload(r))} for i,r in enumerate(reference)]:
        raise ValueError('Frozen requests differ; gold/reference solutions must never be transmitted')
    return m,reference,requested


def require_budget(manifest,reservation_id):
    ledger=read(ROOT/'runs/supervisor/budget.json');account=ledger.get('deepseek_budget_accounting',{})
    if (account.get('status')!='conditional_wallet_inference' or account.get('issues') or account.get('funding_history_ambiguous')
            or ledger.get('deepseek_wallet_observation',{}).get('source')!='Official GET /user/balance'):
        raise RuntimeError('Fresh supported DeepSeek accounting is required')
    require_fresh_deepseek_budget(ledger)
    if contract.money(ledger['limits']['deepseek'])!=20:raise RuntimeError('Keep the existing20USD ceiling')
    jobs=[j for j in ledger['jobs'] if j.get('run_id')==reservation_id and j.get('service')=='deepseek']
    expected={'development_teacher200_manifest_sha256':manifest['manifest_sha256'],
        'development_teacher200_source_sha256':SOURCE_SHA,'development_teacher200_settings_sha256':manifest['settings_sha256']}
    if (len(jobs)!=1 or jobs[0].get('status') not in ('reserved','collecting','in_progress')
            or contract.money(jobs[0].get('reserved_usd',0))<1 or any(jobs[0].get(k)!=v for k,v in expected.items())):
        raise RuntimeError('Unique active1USD reservation must bind this development manifest/source/settings')
    protected=sum((contract.money(j.get('reserved_usd',0)) for j in ledger['jobs'] if j.get('service')=='deepseek'
        and j.get('status') in ('reserved','collecting','in_progress') and j.get('final_scale_bundle_id')),Decimal(0))
    free=Decimal(20)-contract.money(ledger['estimated_spend']['deepseek'])-contract.money(ledger['reserved']['deepseek'])
    if free+protected<5:raise RuntimeError('Retain5USD DeepSeek credit for final measurement')


def parse_result(m,row,request,intent,wire=None,transport_meta=None,*,failure=None,elapsed=0):
    # Reuse only the pure response parser, not final-sample access or final roles.
    shim={key:m['manifest_sha256'] for key in parser.IDENTITY};shim['bundle_id']=m['run_id'];shim['settings_sha256']=m['settings_sha256']
    q={'id':row['id'],'source_index':int(row['id'].rsplit(':',1)[1]),'gold_answer':row['gold_answer'],
       'input_sha256':digest(request['payload']['messages'])}
    shim_intent={'request_sha256':request['request_sha256'],'intent_sha256':intent['intent_sha256'],'phase_approval_sha256':m['manifest_sha256']}
    if wire is not None:
        t=transport_meta
        parsed=parser.from_wire(shim,q,request['position'],shim_intent,wire,elapsed_seconds=t['elapsed_seconds'],
            http_status=t['http_status'],response_header_bytes=t['response_header_bytes'],body_read_failed=t['body_read_failed'])
    else:parsed=parser.failure(shim,q,request['position'],shim_intent,kind=failure,elapsed_seconds=elapsed)
    keys=('outcome','response','reasoning_content','finish_reason','actual_returned_model','system_fingerprint','generated_tokens',
          'truncated','usage','provider_call_attempted','raw_response_sha256','raw_response_bytes','raw_complete','body_read_failed',
          'http_status','response_header_bytes','failure_type','elapsed_seconds')
    return parser.sealed({'role':ROLE,'source_split':'train','training_eligible':False,'official_test_used':False,
        'id':row['id'],'gold_answer':row['gold_answer'],'position':request['position'],'manifest_sha256':m['manifest_sha256'],
        'request_sha256':request['request_sha256'],'intent_sha256':intent['intent_sha256'],**{k:parsed[k] for k in keys}},'receipt_sha256')


def attempt(m,row,request,output,key,guard,stop,*,transport=shared.http):
    guard();intent_path,wire_path,meta_path,result_path=shared.paths(output,row['id'])
    intent=parser.sealed({'id':row['id'],'manifest_sha256':m['manifest_sha256'],'request_sha256':request['request_sha256']},'intent_sha256')
    with intent_path.open('xb') as h:h.write(files.encoded(intent));h.flush();os.fsync(h.fileno())
    started=time.monotonic()
    if len(files.encoded(request['payload']['messages']).rstrip(b'\n'))>1900:
        result=parse_result(m,row,request,intent,failure='input_limit')
    else:
        try:
            got=transport(request['payload'],key)
            if got['http_status'] in (401,402,403,429):stop.set()
            wire=got['wire']
            meta={k:got.get(k,False) for k in ('http_status','response_header_bytes','body_read_failed')}
            meta.update(elapsed_seconds=time.monotonic()-started,intent_sha256=intent['intent_sha256'],raw_sha256=sha(wire))
            files.ensure_json(meta_path,meta);files.ensure_bytes(wire_path,wire)
            result=parse_result(m,row,request,intent,wire,meta)
        except Exception:
            if meta_path.exists() or wire_path.exists():stop.set();raise
            result=parse_result(m,row,request,intent,failure='transport_ambiguous',elapsed=time.monotonic()-started)
    if parser.halt_reason(result):stop.set()
    files.ensure_json(result_path,result);return result


def recover(m,row,request,output):
    intent_path,wire_path,meta_path,result_path=shared.paths(output,row['id'])
    if not intent_path.exists():
        if any(p.exists() for p in (wire_path,meta_path,result_path)):raise ValueError('Orphaned development receipt')
        return None
    intent=read(intent_path);parser.check_hash(intent,'intent_sha256')
    if any(intent.get(k)!=v for k,v in {'id':row['id'],'manifest_sha256':m['manifest_sha256'],'request_sha256':request['request_sha256']}.items()):raise ValueError('Intent changed')
    if meta_path.exists():
        meta=read(meta_path)
        pending=wire_path.with_name(wire_path.name+'.pending')
        if not wire_path.exists() and pending.exists():files.ensure_bytes(wire_path,pending.read_bytes())
        if not wire_path.exists():raise RuntimeError('Ambiguous original transmission; never resend')
        wire=files._raw(wire_path,parser.MAX_BODY+1)
        if sha(wire)!=meta['raw_sha256'] or meta['intent_sha256']!=intent['intent_sha256']:raise ValueError('Raw development receipt changed')
        result=parse_result(m,row,request,intent,wire,meta);files.ensure_json(result_path,result)
    elif not result_path.exists():raise RuntimeError('Ambiguous original intent; never resend')
    result=read(result_path);parser.check_hash(result,'receipt_sha256')
    if not meta_path.exists():
        expected=parse_result(m,row,request,intent,failure=result['failure_type'],elapsed=result['elapsed_seconds'])
        if expected!=result:raise ValueError('Derived failure receipt changed')
    return result


def summary(m,results,stage):
    if len({r['id'] for r in results})!=len(results) or len(results)>200:raise ValueError('Duplicate/excess development outcomes')
    count=len(results);complete=count==200
    scored=[score(dict(r,truncated=r['truncated'] or r['outcome']!='generated')) for r in results] if complete else []
    known={k:sum(r['usage'][k] for r in results if r['usage'] is not None) for k in ('prompt_tokens','completion_tokens')}
    return {'version':VERSION,'role':ROLE,'stage':stage,'source_split':'train','official_test_used':False,'training_eligible':False,
        'manifest_sha256':m['manifest_sha256'],'development_source_sha256':SOURCE_SHA,'requested':200,'retained':count,
        'metrics':{'count':200,'numeric_correct':sum(r['correct'] for r in scored),'strict_format_correct':sum(r['strict_format_correct'] for r in scored),
            'truncated':sum(r['truncated'] for r in results),'failed':sum(r['outcome'] in ('api_failure','execution_failure') for r in results),
            'input_limit':sum(r['outcome']=='input_limit' for r in results)} if complete else None,
        'known_usage':known,'unknown_usage_attempts':sum(r['provider_call_attempted'] and r['usage'] is None for r in results),
        'recorded_peak_token_estimate_usd':(known['prompt_tokens']*1.32+known['completion_tokens']*3.96)/1e6,
        'cost_note':'Known peak-token estimate excludes unknown charges; not a provider invoice.',
        'interpretation':'Matched nonthinking512 teacher measurement on200 TRAIN development questions, separate from old64 thinking4096 and from official final evaluation. No teacher grading or training-data qualification.'}


def collect(output=RUN,*,authorized=False,reservation_id,workers=4,transport=shared.http,budget_guard=None,key_provider=None,resume_approval=None):
    if authorized is not True:raise ValueError('Explicit development collection authorization is required')
    if type(workers) is not int or not 1<=workers<=4:raise ValueError('At most4 workers')
    output=files.private(output);m,reference,requested=validate(output)
    if any(p.parent!=output for p in (ROOT/'runs').rglob('collector.lock')):
        raise RuntimeError('Another teacher collector lock needs owner reconciliation')
    guard=budget_guard or (lambda:require_budget(m,reservation_id))
    fd=os.open(output/'collector.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);results=[];stop=threading.Event();reason=None
    try:
        os.write(fd,str(os.getpid()).encode());os.fsync(fd);(output/'attempts').mkdir(exist_ok=True)
        history=output/'results.jsonl';old=rows(history) if history.exists() else [];byid={r['id']:r for r in old}
        if len(byid)!=len(old) or not set(byid)<={r['id'] for r in reference}:raise ValueError('Duplicate/foreign history')
        def append(r):
            if r['id'] in byid:
                if byid[r['id']]!=r:raise ValueError('History differs from original receipt')
            else:
                with history.open('ab') as h:h.write(files.encoded(r));h.flush();os.fsync(h.fileno())
                byid[r['id']]=r
            results.append(r)
        pending=[]
        for row,request in zip(reference,requested):
            r=recover(m,row,request,output)
            if r is None:
                if row['id'] in byid:raise ValueError('History lost its original intent')
                pending.append((row,request))
            else:append(r)
        if not pending:
            value=summary(m,results,'completed');shared.mutable_json(output/'summary.json',value);return value
        halt=read(output/'halt.json') if (output/'halt.json').exists() else None
        prior=next((parser.halt_reason(r) for r in results if parser.halt_reason(r)),None)
        if prior and halt is None:
            halt={'manifest_sha256':m['manifest_sha256'],'reason':prior};halt=parser.sealed(halt,'halt_sha256');files.ensure_json(output/'halt.json',halt)
        if halt:
            expected={'approved':True,'manifest_sha256':m['manifest_sha256'],'halt_sha256':halt['halt_sha256'],
                'never_attempted_ids_sha256':digest([r['id'] for r,_ in pending]),'reservation_id':reservation_id}
            if resume_approval is None or read(resume_approval)!=expected:raise RuntimeError('Halted collector needs explicit new review of never-attempted IDs')
        guard()
        if key_provider is None:
            def key_provider():
                value=os.environ.get('DEEPSEEK_API_KEY')
                if not value:
                    from cloud.run_api_pilot import credential
                    value=credential('DEEPSEEK_API_KEY')
                return value
        key=key_provider()
        if not key:raise RuntimeError('DeepSeek credential missing')
        queue=iter(pending)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            active={}
            def submit():
                if stop.is_set():return
                pair=next(queue,None)
                if pair is None:return
                row,request=pair;guard()
                active[executor.submit(attempt,m,row,request,output,key,guard,stop,transport=transport)]=pair
            try:
                for _ in range(min(workers,len(pending))):submit()
                while active:
                    done,_=wait(active,return_when=FIRST_COMPLETED)
                    for future in done:
                        row,request=active.pop(future)
                        try:
                            r=future.result();verified=recover(m,row,request,output)
                            if r!=verified:raise ValueError('Live result differs from raw receipt')
                            append(r);reason=shared.preferred_halt(reason,parser.halt_reason(r))
                        except Exception:stop.set();reason=reason or 'receipt_or_funding_reconciliation_required'
                    shared.mutable_json(output/'summary.json',summary(m,results,'halting' if stop.is_set() else 'collecting'))
                    if not stop.is_set():
                        while len(active)<workers:
                            before=len(active);submit()
                            if len(active)==before:break
            except Exception:
                stop.set();reason=reason or 'funding_guard_stopped'
                for future,(row,request) in active.items():
                    try:future.result();r=recover(m,row,request,output);append(r)
                    except Exception:pass
        if reason:
            h=parser.sealed({'manifest_sha256':m['manifest_sha256'],'reason':reason,'retained':len(results)},'halt_sha256')
            shared.mutable_json(output/'halt.json',h)
        value=summary(m,results,'completed' if len(results)==200 else 'halted_review_required');shared.mutable_json(output/'summary.json',value);return value
    finally:
        os.close(fd)
        lock=output/'collector.lock'
        if lock.exists() and lock.read_text(encoding='ascii').strip()==str(os.getpid()):lock.unlink()


def inspect_metadata(output=RUN):
    output=files.private(output)
    if not (output/'manifest.json').exists():return {'stage':'not_prepared','provider_called':False,'official_test_used':False}
    m=read(output/'manifest.json');parser.check_hash(m,'manifest_sha256')
    s=read(output/'summary.json') if (output/'summary.json').exists() else {}
    return {'run_id':m['run_id'],'manifest_sha256':m['manifest_sha256'],'stage':s.get('stage','prepared_unpaid'),
        'requested':200,'retained':s.get('retained',0),'metrics':s.get('metrics'),'source_split':'train',
        'source_sha256':m['source_sha256'],'settings_sha256':m['settings_sha256'],
        'conservative_max_cost_usd':str(COST),'reservation_required_usd':1,'protected_final_deepseek_usd':5,
        'provider_called':False,'official_test_used':False,'training_eligible':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',nargs='?',default='inspect',choices=('inspect','prepare','collect'))
    p.add_argument('--output',type=Path,default=RUN);p.add_argument('--authorize-development',action='store_true')
    p.add_argument('--reservation-id');p.add_argument('--workers',type=int,default=4);p.add_argument('--resume-approval',type=Path)
    a=p.parse_args()
    result=prepare(a.output,authorized=a.authorize_development) if a.action=='prepare' else collect(a.output,authorized=a.authorize_development,
        reservation_id=a.reservation_id,workers=a.workers,resume_approval=a.resume_approval) if a.action=='collect' else inspect_metadata(a.output)
    print(json.dumps(result))
