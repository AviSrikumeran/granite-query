"""Separate final-scale teacher executor. Default CLI inspects metadata only.

No import/default command reads official content or contacts a provider. Prepare
and collect require explicit authorization and the existing sealed loader permit.
The controller owns all provider refreshes, reservations and phase approvals.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud import final_scale_contract as contract
from cloud import final_scale_seal as seal
from cloud import final_scale_loader as loader
from cloud import final_scale_teacher_receipts as receipts
from cloud.deepseek_reconcile import require_fresh_deepseek_budget

API_URL = 'https://api.deepseek.com/chat/completions'
STATE = ROOT/'runs/supervisor'
REQUESTS_FILE = 'final_teacher_requests.jsonl'
SOURCE_ROLES = {'teacher_executor':('final_scale_teacher.py','deepseek_reconcile.py','budget_reconcile.py','run_api_pilot.py'),
                'receipts':('final_scale_teacher_receipts.py',),'scoring':('comparison_metrics.py',)}


class AmbiguousAttemptError(RuntimeError):
    """An original transmission cannot be resolved from local durable bytes."""


def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return contract.digest(value)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def read_rows(path): return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]
def rows_bytes(rows): return b''.join(loader.encoded(row) for row in rows)


def mutable_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.teacher.'+str(os.getpid())+'.tmp')
    with temporary.open('wb') as handle:
        handle.write(loader.encoded(value));handle.flush();os.fsync(handle.fileno())
    for attempt in range(4):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==3:raise
            time.sleep(.05*(2**attempt))


def _sources(sealed):
    p=sealed['contract']['protocol']
    for role,names in SOURCE_ROLES.items():
        for name in names:
            path=ROOT/name
            if name not in p['source_roles'][role] or p['source_hashes'].get(name)!=sha(path.read_bytes()):
                raise ValueError('Teacher funding/receipt/scoring helper is not in the sealed reviewed role')


def payload(row,value):
    return dict(receipts.SETTINGS,messages=[{'role':'user','content':value['protocol']['inference']['user_prefix']+row['prompt']}])


def _context(seal_folder,input_folder,*,authorized):
    if authorized is not True:raise ValueError('Explicit prepared final-content authorization is required')
    sealed=seal.verify(seal_folder);_sources(sealed)
    loaded=loader.load_prepared(seal_folder,input_folder,authorized=True)
    if loaded['sealed']['seal_sha256']!=sealed['seal_sha256']:raise ValueError('Prepared source seal changed')
    value,binding,rows=sealed['contract'],loaded['binding'],loaded['rows']
    receipts.validate_binding(value,binding);receipts.settings(value)
    requested=[]
    for position,(row,question) in enumerate(zip(rows,binding['questions'])):
        if row['id']!=question['id'] or loader.question_input_hash(row,value)!=question['input_sha256']:
            raise ValueError('Prepared question/input binding differs')
        body=payload(row,value)
        requested.append({'id':row['id'],'global_position':position,'input_sha256':question['input_sha256'],
            'request_sha256':digest(body),'payload':body})
    if len(rows)!=value['protocol']['dataset']['sample_count'] or len(requested)!=len(binding['questions']):
        raise ValueError('Prepared sample does not retain the complete frozen denominator')
    return sealed,binding,rows,requested


def prepare(seal_folder,input_folder,output,*,bundle_id,authorized=False):
    output=seal._safe(output,private=True,exists=False)
    sealed,binding,rows,requested=_context(seal_folder,input_folder,authorized=authorized)
    manifest=receipts.build_manifest(sealed['contract'],binding,seal_sha256=sealed['seal_sha256'],
        bundle_id=bundle_id,request_manifest_sha256=digest(requested))
    output.mkdir(parents=True,exist_ok=True)
    if (output/'collector.lock').exists():raise ValueError('An existing collector owns this output')
    loader.ensure_bytes(output/REQUESTS_FILE,rows_bytes(requested))
    loader.ensure_json(output/'manifest.json',manifest)
    if not (output/'summary.json').exists():
        summary=receipts.aggregate(manifest,binding,[])
        mutable_json(output/'summary.json',dict(summary,stage='prepared_no_api_calls',updated_at_utc=now()))
    return inspect_metadata(output)


def require_budget(manifest,reservation_id,*,ledger_path=None):
    """Read-only. No provider refresh, reservation, or nested accounting lock."""
    ledger=seal.read(ledger_path or STATE/'budget.json')
    account=ledger.get('deepseek_budget_accounting',{})
    observation=ledger.get('deepseek_wallet_observation',{})
    if (account.get('status')!='conditional_wallet_inference' or account.get('issues')
            or account.get('funding_history_ambiguous') or not observation
            or observation.get('source')!='Official GET /user/balance'
            or account.get('max_snapshot_age_minutes',15)>15):
        raise RuntimeError('Fresh supported unambiguous DeepSeek funding accounting is required')
    require_fresh_deepseek_budget(ledger)
    if not isinstance(reservation_id,str) or not contract.NAME.fullmatch(reservation_id):
        raise ValueError('Explicit safe reservation identity is required')
    if contract.money(ledger['limits']['deepseek'])!=Decimal('20'):
        raise RuntimeError('Existing DeepSeek20USD ceiling must be retained')
    jobs=[job for job in ledger['jobs'] if job.get('run_id')==reservation_id and job.get('service')=='deepseek']
    expected={'final_scale_freeze_sha256':manifest['freeze_sha256'],
        'final_scale_seal_sha256':manifest['seal_sha256'],'final_scale_bundle_id':manifest['bundle_id']}
    if (len(jobs)!=1 or jobs[0].get('status') not in ('reserved','collecting','in_progress')
            or any(jobs[0].get(k)!=v for k,v in expected.items())
            or contract.money(jobs[0].get('reserved_usd',0))<Decimal(manifest['reserved_usd_required'])):
        raise RuntimeError('Unique active teacher reservation must bind the exact bundle/seal/freeze and full cap')


def paths(output,identifier):
    stem=Path(output)/'attempts'/sha(identifier.encode('utf-8'))
    return tuple(stem.with_suffix(suffix) for suffix in ('.intent.json','.wire','.transport.json','.result.json'))


def http(body,key):
    """One POST. Success/error bodies are returned raw; never log headers/key."""
    request=urllib.request.Request(API_URL,data=loader.encoded(body).rstrip(b'\n'),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:response=urllib.request.urlopen(request,timeout=120)
    except urllib.error.HTTPError as error:response=error
    with response:
        status=response.getcode()
        # Bound header metadata but never serialize request/response headers.
        header_bytes=sum(len(str(k).encode('utf-8'))+len(str(v).encode('utf-8'))+4 for k,v in response.headers.items())
        try:
            wire=response.read(receipts.MAX_BODY+1);failed=False
        except Exception as error:
            partial=getattr(error,'partial',b'')
            wire=partial[:receipts.MAX_BODY+1] if isinstance(partial,bytes) else b''
            failed=True
    return {'http_status':status,'response_header_bytes':header_bytes,'wire':wire,'body_read_failed':failed}


def attempt(manifest,question,request,output,key,*,phase_sha256,transport=http,budget_guard,on_halt=None):
    budget_guard()
    intent=receipts.make_intent(manifest,question,request['global_position'],
        request_sha256=request['request_sha256'],phase_approval_sha256=phase_sha256)
    intent_path,wire_path,transport_path,result_path=paths(output,request['id'])
    # Exclusive original intent. Never use an idempotent overwrite for dispatch.
    with intent_path.open('xb') as handle:
        handle.write(loader.encoded(intent));handle.flush();os.fsync(handle.fileno())
    started=time.monotonic()
    if len(loader.encoded(request['payload']['messages']).rstrip(b'\n'))>receipts.MAX_MESSAGES_BYTES:
        result=receipts.failure(manifest,question,request['global_position'],intent,kind='input_limit')
        loader.ensure_json(result_path,result);return result
    try:
        received=transport(request['payload'],key)
        if received.get('http_status') in (401,402,403,429) and on_halt:
            # Status is known before body interpretation. Stop new submissions
            # immediately while this already dispatched response is persisted.
            on_halt('http_'+str(received['http_status']))
        wire=received['wire']
        if not isinstance(wire,bytes) or len(wire)>receipts.MAX_BODY+1:raise ValueError('Invalid bounded wire transport')
        # Transport metadata precedes the raw file so a crash after raw fsync has
        # durable HTTP status. Neither operation parses/interprets the body.
        metadata={'intent_sha256':intent['intent_sha256'],'raw_response_sha256':sha(wire),
            'raw_response_bytes':len(wire),'http_status':received['http_status'],
            'response_header_bytes':received['response_header_bytes'],'body_read_failed':received.get('body_read_failed',False),
            'elapsed_seconds':time.monotonic()-started}
        loader.ensure_json(transport_path,metadata)
        loader.ensure_bytes(wire_path,wire)
        result=receipts.from_wire(manifest,question,request['global_position'],intent,wire,
            elapsed_seconds=metadata['elapsed_seconds'],http_status=metadata['http_status'],
            response_header_bytes=metadata['response_header_bytes'],body_read_failed=metadata['body_read_failed'])
    except Exception:
        # If any response evidence exists, preserve it for local reconciliation
        # instead of replacing it with a fabricated transport-failure receipt.
        if transport_path.exists() or wire_path.exists() or wire_path.with_name(wire_path.name+'.pending').exists():raise
        result=receipts.failure(manifest,question,request['global_position'],intent,
            kind='transport_ambiguous',elapsed_seconds=time.monotonic()-started)
    reason=receipts.halt_reason(result)
    if reason and on_halt:on_halt(reason)
    loader.ensure_json(result_path,result)
    return result


def recover(manifest,question,request,output):
    intent_path,wire_path,transport_path,result_path=paths(output,request['id'])
    wire_pending=wire_path.with_name(wire_path.name+'.pending')
    if not intent_path.exists():
        if any(p.exists() for p in (wire_path,wire_pending,transport_path,result_path)):
            raise ValueError('Receipt without its original pre-transmission intent')
        return None
    intent=seal.read(intent_path)
    receipts.validate_intent(manifest,question,request['global_position'],intent,request['request_sha256'])
    phase=seal.read(Path(output)/'phases'/(intent['phase_approval_sha256']+'.json'))
    if (digest(phase['approval'])!=intent['phase_approval_sha256'] or request['id'] not in phase['request_ids']
            or digest(phase['request_ids'])!=phase['approval']['never_attempted_ids_sha256']
            or phase['approval'].get('manifest_sha256')!=manifest['manifest_sha256'] or phase['approval'].get('approved') is not True):
        raise ValueError('Original intent lacks its exact approved phase identity')
    wire=None
    if transport_path.exists():
        metadata=seal.read(transport_path)
        if metadata.get('intent_sha256')!=intent['intent_sha256']:raise ValueError('Transport intent differs')
        if not wire_path.exists() and wire_pending.exists():
            loader.ensure_bytes(wire_path,wire_pending.read_bytes())
        if not wire_path.exists():raise AmbiguousAttemptError('Ambiguous response: metadata without durable bytes; never resend')
        wire=loader._raw(wire_path,receipts.MAX_BODY+1)
        if sha(wire)!=metadata.get('raw_response_sha256') or len(wire)!=metadata.get('raw_response_bytes'):
            raise ValueError('Original response bytes differ')
        expected=receipts.from_wire(manifest,question,request['global_position'],intent,wire,
            elapsed_seconds=metadata['elapsed_seconds'],http_status=metadata['http_status'],
            response_header_bytes=metadata['response_header_bytes'],body_read_failed=metadata['body_read_failed'])
        loader.ensure_json(result_path,expected)
    elif wire_path.exists() or wire_pending.exists():raise AmbiguousAttemptError('Ambiguous raw bytes without original transport status; never resend')
    elif not result_path.exists():raise AmbiguousAttemptError('Ambiguous prior request intent; no automatic retransmission')
    result=seal.read(result_path)
    receipts.validate_attempt(manifest,question,request['global_position'],intent,result,
        request_sha256=request['request_sha256'],wire=wire)
    return result


def _halt(output,manifest,*,phase_sha256,reservation_id,reason,attempted_ids):
    value=receipts.sealed({'schema_version':1,**{k:manifest[k] for k in receipts.IDENTITY},
        'phase_approval_sha256':phase_sha256,'reservation_id':reservation_id,'reason':reason,
        'attempted_ids_sha256':digest(attempted_ids),'attempted_count':len(attempted_ids),'at_utc':now()},'halt_sha256')
    folder=Path(output)/'halts';folder.mkdir(exist_ok=True)
    loader.ensure_json(folder/(value['halt_sha256']+'.json'),value)
    mutable_json(Path(output)/'halt.json',value)
    return value


def _summary(output,manifest,binding,results,stage):
    value=dict(receipts.aggregate(manifest,binding,results),stage=stage,updated_at_utc=now())
    mutable_json(Path(output)/'summary.json',value)
    return value


def preferred_halt(current,new):
    if new and new.startswith('http_') and (not current or not current.startswith('http_')):return new
    return current or new


def collect(seal_folder,input_folder,output,*,authorized=False,workers=4,reservation_id,
            phase_approval_path,transport=http,budget_guard=None,key_provider=None):
    if authorized is not True:raise ValueError('Explicit final collection authorization is required')
    if type(workers) is not int or not 1<=workers<=4:raise ValueError('At most4 concurrent original requests')
    output=seal._safe(output,private=True)
    manifest=seal.read(output/'manifest.json')
    sealed,binding,rows,requested=_context(seal_folder,input_folder,authorized=True)
    receipts.validate_manifest(sealed['contract'],binding,manifest)
    if manifest['seal_sha256']!=sealed['seal_sha256'] or digest(requested)!=manifest['request_manifest_sha256']:
        raise ValueError('Teacher manifest no longer matches the sealed sample')
    if loader._raw(output/REQUESTS_FILE,8*1024*1024)!=rows_bytes(requested):raise ValueError('Frozen teacher requests changed')
    guard=budget_guard or (lambda:require_budget(manifest,reservation_id))
    lock=output/'collector.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    results=[];phase_sha=None;halt_reason=None;stop=threading.Event();halt_lock=threading.Lock()
    try:
        os.write(fd,str(os.getpid()).encode('ascii'));os.fsync(fd)
        (output/'attempts').mkdir(exist_ok=True);(output/'phases').mkdir(exist_ok=True)
        history=output/'results.jsonl';old=read_rows(history) if history.exists() else []
        existing={r['id']:r for r in old}
        if len(existing)!=len(old) or not set(existing)<={r['id'] for r in requested}:raise ValueError('Foreign/duplicate result history')
        pending=[]
        def append(result):
            previous=existing.get(result['id'])
            if previous is not None:
                if previous!=result:raise ValueError('Appended result differs from original receipt')
            else:
                with history.open('ab') as handle:
                    handle.write(loader.encoded(result));handle.flush();os.fsync(handle.fileno())
                existing[result['id']]=result
            results.append(result)
        for question,request in zip(binding['questions'],requested):
            result=recover(manifest,question,request,output)
            if result is None:
                if request['id'] in existing:raise ValueError('History lost its original receipt')
                pending.append((question,request))
            else:append(result)
        if not pending:return _summary(output,manifest,binding,results,'completed')
        halt=seal.read(output/'halt.json') if (output/'halt.json').exists() else None
        if halt is not None:
            receipts.check_hash(halt,'halt_sha256')
            if any(halt.get(k)!=manifest[k] for k in receipts.IDENTITY):raise ValueError('Foreign halt record')
        # A crash after a stop-worthy receipt but before halt persistence must
        # also stop. It cannot be resumed through the initial approval again.
        prior_stop=next((receipts.halt_reason(r) for r in results if receipts.halt_reason(r)),None)
        if prior_stop and halt is None:
            old_phase=next(r['phase_approval_sha256'] for r in results if receipts.halt_reason(r))
            _halt(output,manifest,phase_sha256=old_phase,reservation_id=reservation_id,reason=prior_stop,
                attempted_ids=[r['id'] for r in results])
            return _summary(output,manifest,binding,results,'halted_new_phase_approval_required')
        approval=seal.read(seal._safe(phase_approval_path,private=True))
        pending_ids=[request['id'] for _,request in pending]
        phase_sha=receipts.validate_phase(manifest,approval,pending_ids,reservation_id=reservation_id,
            halt_sha256=halt['halt_sha256'] if halt else None,
            prior_approval_sha256=halt['phase_approval_sha256'] if halt else None)
        guard()
        loader.ensure_json(output/'phases'/(phase_sha+'.json'),{'approval':approval,'request_ids':pending_ids})
        if key_provider is None:
            def key_provider():
                value=os.environ.get('DEEPSEEK_API_KEY')
                if not value and os.name=='nt':
                    from cloud.run_api_pilot import credential
                    value=credential('DEEPSEEK_API_KEY')
                return value
        key=key_provider()
        if not key:raise RuntimeError('DeepSeek credential missing')
        _summary(output,manifest,binding,results,'collecting')
        queue=iter(pending)
        def signal(reason):
            nonlocal halt_reason
            with halt_lock:halt_reason=preferred_halt(halt_reason,reason)
            stop.set()
        def execute(question,request):
            try:
                return attempt(manifest,question,request,output,key,phase_sha256=phase_sha,
                    transport=transport,budget_guard=guard,on_halt=signal)
            except Exception:
                signal('execution_or_receipt_reconciliation_required');raise
        with ThreadPoolExecutor(max_workers=workers) as executor:
            active={}
            def submit():
                if stop.is_set():return
                item=next(queue,None)
                if item is None:return
                question,request=item
                # Guard before submission and immediately before transmission.
                guard()
                if stop.is_set():return
                active[executor.submit(execute,question,request)]=item
            try:
                for _ in range(min(workers,len(pending))):submit()
                while active:
                    done,_=wait(active,return_when=FIRST_COMPLETED)
                    for future in done:
                        question,request=active.pop(future)
                        try:
                            result=future.result()
                            # Validate even immediately returned derived results.
                            original=recover(manifest,question,request,output)
                            if result!=original:raise ValueError('Live result differs from durable receipt')
                            append(result)
                            halt_reason=preferred_halt(halt_reason,receipts.halt_reason(result))
                        except Exception:
                            halt_reason=halt_reason or 'execution_or_receipt_reconciliation_required'
                    _summary(output,manifest,binding,results,'halting' if halt_reason else 'collecting')
                    if not stop.is_set() and not halt_reason:
                        while len(active)<workers and len(existing)<manifest['max_original_attempts']:
                            before=len(active);submit()
                            if len(active)==before:break
            except Exception:
                halt_reason=halt_reason or 'fresh_funding_or_dispatch_guard_stopped'
                # Drain only the already submitted finite window; do not submit.
                for future,(question,request) in list(active.items()):
                    try:
                        future.result();original=recover(manifest,question,request,output)
                        if original is not None:
                            append(original);halt_reason=preferred_halt(halt_reason,receipts.halt_reason(original))
                    except Exception:pass
        if halt_reason:
            attempted=[]
            for request in requested:
                if paths(output,request['id'])[0].exists():attempted.append(request['id'])
            _halt(output,manifest,phase_sha256=phase_sha,reservation_id=reservation_id,reason=halt_reason,attempted_ids=attempted)
        return _summary(output,manifest,binding,results,'completed' if len(results)==manifest['sample_count'] else 'halted_new_phase_approval_required')
    except AmbiguousAttemptError:
        # A recovered intent is already allocated to the denominator. Preserve
        # a durable stop; no phase approval can turn it into a fresh request.
        attempted=[];owner_phase=phase_sha
        for request in requested:
            original=paths(output,request['id'])[0]
            if original.exists():
                attempted.append(request['id'])
                if owner_phase is None:owner_phase=seal.read(original).get('phase_approval_sha256')
        if owner_phase is not None:
            _halt(output,manifest,phase_sha256=owner_phase,reservation_id=reservation_id,
                reason='ambiguous_intent_requires_reconciliation',attempted_ids=attempted)
        _summary(output,manifest,binding,results,'action_required_ambiguous_intent')
        raise
    finally:
        os.close(fd)
        if lock.exists() and lock.read_text(encoding='ascii').strip()==str(os.getpid()):lock.unlink()


def inspect_metadata(output):
    """Allowlisted local manifest/summary only; no sample, prompts or receipts."""
    output=seal._safe(output,private=True,exists=False)
    if not (output/'manifest.json').exists():return {'stage':'not_prepared','official_content_read':False,'provider_called':False}
    manifest=seal.read(output/'manifest.json');receipts.check_hash(manifest,'manifest_sha256')
    summary=seal.read(output/'summary.json') if (output/'summary.json').exists() else {}
    if summary:
        count=manifest['sample_count']
        if (any(summary.get(k)!=manifest[k] for k in receipts.IDENTITY)
                or summary.get('expected_count')!=count or not receipts.integer(summary.get('retained_count'))
                or summary['retained_count']>count or summary.get('status') not in ('incomplete','completed')):
            raise ValueError('Aggregate metadata differs from this manifest')
        metrics=summary.get('metrics')
        if metrics is not None and (summary['status']!='completed' or summary['retained_count']!=count
                or metrics.get('count')!=count or not receipts.integer(metrics.get('numeric_correct'))
                or metrics['numeric_correct']>count):
            raise ValueError('Aggregate cannot claim a reduced-denominator score')
    allowed=('stage','status','expected_count','retained_count','outcomes','metrics','known_usage','unknown_usage_attempts','provider_calls_attempted',
        'recorded_peak_token_estimate_usd','actual_returned_models','updated_at_utc')
    return {'manifest_sha256':manifest['manifest_sha256'],'bundle_id':manifest['bundle_id'],
        'sample_count':manifest['sample_count'],'reserved_usd_required':manifest['reserved_usd_required'],
        'official_content_read':False,'provider_called':False,**{k:summary[k] for k in allowed if k in summary}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='inspect',choices=('inspect','prepare','collect'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal-folder',type=Path);parser.add_argument('--input-folder',type=Path)
    parser.add_argument('--bundle-id');parser.add_argument('--reservation-id');parser.add_argument('--phase-approval',type=Path)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--authorize-final-content',action='store_true')
    args=parser.parse_args()
    if args.action=='inspect':result=inspect_metadata(args.output)
    elif args.action=='prepare':
        result=prepare(args.seal_folder,args.input_folder,args.output,bundle_id=args.bundle_id,authorized=args.authorize_final_content)
    else:
        result=collect(args.seal_folder,args.input_folder,args.output,authorized=args.authorize_final_content,
            workers=args.workers,reservation_id=args.reservation_id,phase_approval_path=args.phase_approval)
    print(json.dumps(result))


if __name__=='__main__':main()
