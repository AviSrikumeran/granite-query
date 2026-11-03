"""Unlaunched sealed256 DeepSeek evaluator; never a training-data collector.

Only consumes the future reviewed loader's persisted final_eval_only sample.
No module import reads official data, contacts providers, or changes budgets.
All attempted outcomes are retained, including wrong/truncated/failed answers.
Per-request markers precede transmission; raw receipts precede interpretation.
Ambiguous attempts are never retransmitted automatically.
"""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
from decimal import Decimal
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud import final_eval_control as seal
from cloud import final_test_loader as loader
from cloud.comparison_metrics import summarize,score
from cloud.deepseek_reconcile import require_fresh_deepseek_budget

CAPABILITIES=dict(seal.CAPABILITIES['deepseek_evaluator'])
API_URL='https://api.deepseek.com/chat/completions'
PROMPT_VERSION='sealed256-matched-nonthinking512-v1'
MAX_BODY=1024*1024


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def paths(output,key):
    name=hashlib.sha256(key.encode()).hexdigest()
    return tuple(output/'attempts'/(name+suffix) for suffix in ('.json','.result.json','.raw.json'))


def credential():
    value=os.environ.get('DEEPSEEK_API_KEY')
    if not value and os.name=='nt':
        from cloud.run_api_pilot import credential as existing
        value=existing('DEEPSEEK_API_KEY')
    return value


def require_budget(reservation_id,teacher,*,ledger_path=None):
    ledger=seal.load(ledger_path or ROOT/'runs/supervisor/budget.json')
    if not ledger.get('deepseek_budget_accounting') or not ledger.get('deepseek_wallet_observation'):
        raise RuntimeError('A fresh reconciled DeepSeek funding observation is required')
    require_fresh_deepseek_budget(ledger)
    if Decimal(str(ledger['limits']['deepseek']))!=Decimal('20'):
        raise RuntimeError('Final teacher must remain inside the existing$20 service ceiling')
    jobs=[j for j in ledger['jobs'] if j.get('run_id')==reservation_id and j.get('service')=='deepseek']
    if (len(jobs)!=1 or jobs[0].get('status') not in ('reserved','collecting') or
            Decimal(str(jobs[0].get('reserved_usd',0)))<Decimal(str(teacher['peak_request_cost_bound_usd']))):
        raise RuntimeError('An existing sufficient final-teacher reservation is required before collection')


def protocol(final_folder):
    manifest=seal.verify(final_folder)
    entry=loader.require_role(manifest,'deepseek_evaluator',Path(__file__),dependencies=[ROOT/'final_test_loader.py'])
    if Path(entry['path']).resolve()!=Path(__file__).resolve():
        raise ValueError('Final evaluator source path differs from the reviewed executor')
    value=manifest['protocol'];teacher=value['teacher']
    expected={'enabled':True,'model':'deepseek-v4-pro','thinking':{'type':'disabled'},'max_tokens':512,
              'temperature':0,'max_attempts':256,'automatic_retries':0,'max_concurrent_requests':4,
              'filter_on_answer_correctness':False}
    if any(teacher.get(k)!=v for k,v in expected.items()) or value['dataset'].get('sample_count')!=256:
        raise ValueError('Frozen final teacher settings differ from the reviewed256/nonthinking512 protocol')
    if value['inference'].get('user_prefix')!=seal.PREFIX or value['inference'].get('max_new_tokens')!=512:
        raise ValueError('Final teacher/Granite user prompt or output cap changed')
    return manifest


def payload(row,manifest):
    return dict(model='deepseek-v4-pro',max_tokens=512,temperature=0,stream=False,
        thinking={'type':'disabled'},messages=[{'role':'user','content':manifest['protocol']['inference']['user_prefix']+row['prompt']}])


def http(request_payload,key):
    request=urllib.request.Request(API_URL,data=canonical(request_payload).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=120) as response:
        raw=response.read(MAX_BODY+1)
    if len(raw)>MAX_BODY:
        raise RuntimeError('Provider response exceeded bounded receipt size')
    return raw


def base_result(row,request_hash,manifest):
    return dict(id=row['id'],gold_answer=row['gold_answer'],freeze_sha256=manifest['freeze_sha256'],
        request_sha256=request_hash,role='final_eval_only',source_split='test',training_eligible=False,
        teacher_model='deepseek-v4-pro',response='',raw=None,failed=False,truncated=False,
        finish_reason='error',generated_tokens=0,
        generation={'prompt_version':PROMPT_VERSION,'settings':{'model':'deepseek-v4-pro','max_tokens':512,
            'temperature':0,'thinking':{'type':'disabled'},'automatic_retries':0}})


def from_receipt(row,request_hash,manifest,raw_bytes,elapsed):
    result=base_result(row,request_hash,manifest)
    result['raw_receipt_sha256']=hashlib.sha256(raw_bytes).hexdigest()
    try:
        raw=json.loads(raw_bytes);result['raw']=raw
        choice=raw['choices'][0];content=choice['message'].get('content') or ''
        tokens=raw.get('usage',{}).get('completion_tokens',0)
        if not isinstance(content,str) or type(tokens) is not int or not 0<=tokens<=512:
            raise ValueError('Provider completion violates bounded response contract')
        result.update(response=content,teacher_revision=raw.get('model','deepseek-v4-pro'),
            finish_reason=choice.get('finish_reason'),truncated=choice.get('finish_reason')!='stop',generated_tokens=tokens)
    except (KeyError,ValueError,TypeError,IndexError):
        result.update(failed=True,error_type='InvalidProviderReceipt',response='')
    result['elapsed_seconds']=elapsed;result['scoring']=score(result)
    return result


def attempt(row,output,key,manifest,*,transport=http,budget_guard=None):
    request_payload=payload(row,manifest);request_hash=digest(request_payload)
    marker,saved,raw_path=paths(output,row['id'])
    if budget_guard:
        budget_guard()
    seal.write_once(marker,{'id':row['id'],'request_sha256':request_hash,'freeze_sha256':manifest['freeze_sha256'],
                            'started_at_utc':now(),'automatic_retries':0})
    started=time.monotonic()
    if len(canonical(request_payload['messages']).encode())>1900:
        result=base_result(row,request_hash,manifest)
        result.update(failed=True,error_type='InputByteLimit',elapsed_seconds=0,transmitted=False)
        result['scoring']=score(result);loader.atomic(saved,result)
        return result
    try:
        raw=transport(request_payload,key)
        if not isinstance(raw,bytes) or len(raw)>MAX_BODY:
            raise ValueError('Invalid bounded raw receipt')
        # Byte-exact durable receipt before parsing/scoring; recovery never calls
        # the provider again if the process stops after this write.
        with raw_path.open('xb') as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
        result=from_receipt(row,request_hash,manifest,raw,time.monotonic()-started)
    except Exception as error:
        result=base_result(row,request_hash,manifest)
        result.update(failed=True,error_type=type(error).__name__,elapsed_seconds=time.monotonic()-started)
        if isinstance(error,urllib.error.HTTPError):
            result['http_status']=error.code
        result['scoring']=score(result)
    loader.atomic(saved,result)
    return result


def collect(final_folder,input_folder,output,*,workers=4,reservation_id=None,transport=http,
            budget_guard=None,key_provider=credential):
    if not 1<=workers<=4:
        raise ValueError('Final teacher concurrency must be between1 and4')
    final_folder,input_folder,output=map(seal.private,(final_folder,input_folder,output))
    manifest=protocol(final_folder)
    reservation_id=reservation_id or output.name+'-teacher'
    guard=budget_guard or (lambda:require_budget(reservation_id,manifest['protocol']['teacher']))
    guard() # Before prepared final-sample access and before each paid dispatch.
    loaded,sample,raw,rows=loader.load_prepared(final_folder,input_folder)
    if loaded['freeze_sha256']!=manifest['freeze_sha256']:
        raise ValueError('Prepared sample belongs to another final freeze')
    rows=loader.validate_sample(raw,sample,manifest)
    if len(rows)!=256 or sample['sample_rows_sha256']!=hashlib.sha256(raw).hexdigest():
        raise ValueError('Final teacher requires the exact256 persisted final-evaluation records')
    requests=[{'id':row['id'],'payload':payload(row,manifest)} for row in rows]
    frozen=dict(schema_version=1,freeze_sha256=manifest['freeze_sha256'],sample_rows_sha256=sample['sample_rows_sha256'],
        dataset_sha256=sample['dataset_sha256'],request_manifest_sha256=digest(requests),ids=[r['id'] for r in rows],
        role='final_eval_only',training_eligible=False,official_test_used=True,max_attempts=256,
        model='deepseek-v4-pro',max_tokens=512,thinking_enabled=False,temperature=0,automatic_retries=0,
        prompt_version=PROMPT_VERSION,filter_on_answer_correctness=False,reservation_id=reservation_id,
        source_sha256=seal.sha(Path(__file__)))
    output.mkdir(parents=True,exist_ok=True);lock=output/'collector.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode());(output/'attempts').mkdir(exist_ok=True)
        if (output/'manifest.json').exists():
            if seal.load(output/'manifest.json')!=frozen:
                raise ValueError('Final teacher output belongs to a different immutable sample/protocol')
        else:
            seal.write_once(output/'manifest.json',frozen)
        expected_requests=b''.join((canonical(row)+'\n').encode() for row in requests)
        if (output/'requests.jsonl').exists():
            if (output/'requests.jsonl').read_bytes()!=expected_requests:
                raise ValueError('Immutable final request artifact changed')
        else:
            with (output/'requests.jsonl').open('xb') as handle:
                handle.write(expected_requests);handle.flush();os.fsync(handle.fileno())
        results_path=output/'results.jsonl'
        existing=[json.loads(line) for line in results_path.read_text(encoding='utf-8').split('\n') if line.strip()] if results_path.exists() else []
        by_id={row['id']:row for row in existing}
        if len(by_id)!=len(existing) or not set(by_id).issubset(frozen['ids']):
            raise ValueError('Stored final results contain duplicate or foreign IDs')
        def validate(result,row):
            if (result.get('id')!=row['id'] or result.get('request_sha256')!=digest(payload(row,manifest))
                    or result.get('freeze_sha256')!=manifest['freeze_sha256'] or result.get('training_eligible') is not False
                    or result.get('role')!='final_eval_only' or str(result.get('gold_answer'))!=str(row['gold_answer'])):
                raise ValueError('Saved final attempt does not match its sealed request')
            marker,_,receipt=paths(output,row['id'])
            if not marker.exists():
                raise ValueError('Final attempt lacks its durable pre-transmission marker')
            marked=seal.load(marker)
            if marked.get('request_sha256')!=result['request_sha256'] or marked.get('freeze_sha256')!=manifest['freeze_sha256']:
                raise ValueError('Final attempt marker identity changed')
            if result.get('raw_receipt_sha256'):
                if not receipt.exists() or hashlib.sha256(receipt.read_bytes()).hexdigest()!=result['raw_receipt_sha256']:
                    raise ValueError('Original provider receipt is missing or changed')
                replay=from_receipt(row,result['request_sha256'],manifest,receipt.read_bytes(),0)
                for key in ('response','failed','truncated','finish_reason','generated_tokens','raw'):
                    if result.get(key)!=replay.get(key):
                        raise ValueError('Final result differs from the original raw provider receipt')
        def append(result,row):
            validate(result,row)
            with results_path.open('a',encoding='utf-8') as handle:
                handle.write(canonical(result)+'\n');handle.flush();os.fsync(handle.fileno())
            by_id[row['id']]=result
        pending=[]
        for row in rows:
            marker,saved,receipt=paths(output,row['id'])
            if row['id'] in by_id:
                validate(by_id[row['id']],row);continue
            if marker.exists():
                mark=seal.load(marker)
                if mark.get('request_sha256')!=digest(payload(row,manifest)) or mark.get('freeze_sha256')!=manifest['freeze_sha256']:
                    raise ValueError('Attempt marker belongs to a different final request')
            if saved.exists():
                if not marker.exists():raise ValueError('Saved final result lacks its pre-transmission marker')
                append(seal.load(saved),row)
            elif receipt.exists():
                if not marker.exists():raise ValueError('Raw receipt lacks its pre-transmission marker')
                result=from_receipt(row,digest(payload(row,manifest)),manifest,receipt.read_bytes(),0)
                result['latency_recovered_without_timing']=True;loader.atomic(saved,result);append(result,row)
            elif marker.exists():
                raise RuntimeError('Ambiguous earlier final request: reconcile it; automatic retransmission is refused')
            else:
                pending.append(row)
        if pending:
            key=key_provider()
            if not key:raise RuntimeError('DeepSeek credential is not configured')
            waiting=iter(pending)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                active={}
                def submit():
                    row=next(waiting,None)
                    if row is not None:
                        active[executor.submit(attempt,row,output,key,manifest,transport=transport,budget_guard=guard)]=row
                for _ in range(workers):submit()
                while active:
                    done,_=wait(active,return_when=FIRST_COMPLETED)
                    for future in done:
                        row=active.pop(future);append(future.result(),row);submit()
        ordered=[by_id[row['id']] for row in rows]
        summary=summarize(ordered)
        summary.update(stage='completed',requested_count=256,completed_count=len(ordered),failed_count=sum(r['failed'] for r in ordered),
            freeze_sha256=manifest['freeze_sha256'],sample_rows_sha256=sample['sample_rows_sha256'],
            model='deepseek-v4-pro',max_tokens=512,thinking_enabled=False,automatic_retries=0,
            official_test_used=True,training_eligible=False,filter_on_answer_correctness=False,
            latency_scope='API round-trip timings; recovered raw receipts may lack original timing. Not comparable to amortized Granite GPU-batch latency.')
        loader.atomic(output/'summary.json',summary)
        return summary
    finally:
        os.close(fd);lock.unlink()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final-folder',required=True,type=Path);parser.add_argument('--input-folder',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--reservation-id')
    args=parser.parse_args()
    print(json.dumps(collect(args.final_folder,args.input_folder,args.output,workers=args.workers,reservation_id=args.reservation_id)))
