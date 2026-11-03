"""Prepare or collect one separately funded512-request human-math chunk.

Preparation is unpaid. Collection never reserves funds or starts another chunk;
the caller must refresh accounting and reserve the chosen chunk beforehand.
The200 frozen development questions never enter teaching requests or selection.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from cloud import human_math_cohort as source
from cloud import student_pool as transport
from cloud.math_teacher import assert_reserved, other_collector_locks
from cloud.matched_teacher import _attempt_paths, _digest, _write, _canonical
from cloud.student_valuation import load_tokenizer, REVISION as STUDENT_REVISION
from cloud.progress import record

COHORT = source.RUN
RUN = ROOT / 'runs/human_math_teacher2048_v1'
PUBLIC = ROOT.parents[1] / 'progress/HUMAN_MATH_TEACHER.json'


def now(): return datetime.now(timezone.utc).isoformat()
def read_rows(path): return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').split('\n') if line.strip()]
def raw_rows(rows): return ''.join(_canonical(row)+'\n' for row in rows).encode('utf-8')


def prepare(cohort=COHORT, output=RUN):
    cohort, output = Path(cohort).resolve(), Path(output).resolve()
    if not all(path.is_relative_to((ROOT/'runs').resolve()) for path in (cohort,output)):
        raise ValueError('Use local ignored source and teacher artifacts')
    report = source.validate_frozen(cohort)
    source_plan = json.loads((cohort/'plan.json').read_text(encoding='utf-8'))
    if report['stage']!='prepared_unpaid' or source_plan['official_test_accessed'] is not False:
        raise ValueError('Require the frozen training-only human cohort')
    if source.sha(source.SOURCE.read_bytes())!=source.SOURCE_SHA:
        raise ValueError('Pinned original GSM training cache changed')
    rows, development, requests = [read_rows(cohort/name) for name in ('candidates.jsonl','development.jsonl','requests.jsonl')]
    if len(rows)!=2048 or len(development)!=200 or {r['id'] for r in rows}&{r['id'] for r in development}:
        raise ValueError('Require2048 teaching questions and200 disjoint development questions')
    for row in rows+development:
        if (row.get('source_split')!='train' or row.get('source_revision')!=source.REVISION
                or row.get('reference_type')!='human_dataset_answer_with_exact_annotation_checks'):
            raise ValueError('Unexpected source origin')
        proof, reason, _ = source.annotation_check(row['reference_solution'],row['gold_answer'])
        if reason!='exact_annotations_and_final' or proof!=row['annotation_verification']:
            raise ValueError('Human arithmetic-annotation proof differs')
        if source.sha(row['reference_solution'].encode())!=row['reference_solution_sha256']:
            raise ValueError('Original human reference changed')
    expected=[{'id':row['id'],'payload':transport.build_payload(row)} for row in rows]
    if requests!=expected or max(transport.input_bound(row) for row in rows)>transport.MAX_MESSAGES_UTF8_BYTES:
        raise ValueError('Source teaching requests differ or exceed the conservative byte allowance')
    chunks=[]
    for index,start in enumerate(range(0,2048,512)):
        chosen, requested = rows[start:start+512],requests[start:start+512]
        chunks.append({'index':index,'run_id':f'{output.name}-chunk{index:03d}',
            'budget_job_id':f'{output.name}-chunk{index:03d}-teacher','ids':[row['id'] for row in chosen],
            'candidate_count':512,'candidates_sha256':source.sha(raw_rows(chosen)),
            'requests_sha256':source.sha(raw_rows(requested)),
            'conservative_max_cost_usd':512*(2000*1.32+1024*3.96)/1e6,
            'reserved_usd_required':4,'max_serialized_messages_utf8_bytes':max(transport.input_bound(row) for row in chosen)})
    plan={'schema_version':1,'run_id':output.name,'source_cohort_run':cohort.name,
        'source_plan_sha256':source.sha((cohort/'plan.json').read_bytes()),
        'candidate_count':2048,'excluded_development_count':200,
        'excluded_development_ids_sha256':_digest([row['id'] for row in development]),
        'candidates_sha256':source.sha(raw_rows(rows)),'requests_sha256':source.sha(raw_rows(requests)),
        'chunks':chunks,'model':transport.MODEL,'max_output_tokens':1024,'thinking_enabled':False,
        'max_concurrent':4,'automatic_retries':0,'conservative_input_token_bound':2000,
        'max_response_tokens':768,'context_limit':2048,'student_model':'ibm-granite/granite-4.2-3b',
        'student_revision':STUDENT_REVISION,
        'chunk_policy':'One explicit separately reserved chunk per invocation; no automatic later chunk launches',
        'budget_policy':'Fresh provider accounting and own active$4reservation required before each512-call chunk; preparation reserves nothing',
        'reference_policy':'Human references passed exact arithmetic annotation/final checks; semantic sufficiency remains unproven',
        'official_test_accessed':False,'paid_launches_by_preparation':0,'excluded_development_sent_to_teacher':False}
    output.mkdir(parents=True,exist_ok=True)
    if (output/'plan.json').exists():
        if json.loads((output/'plan.json').read_text(encoding='utf-8'))!=plan:
            raise RuntimeError('Immutable human teacher plan differs')
        for name,key in [('candidates.jsonl','candidates_sha256'),('requests.jsonl','requests_sha256')]:
            if source.sha((output/name).read_bytes())!=plan[key]:
                raise RuntimeError('Immutable master teacher artifact changed')
        return plan
    (output/'candidates.jsonl').write_bytes(raw_rows(rows))
    (output/'requests.jsonl').write_bytes(raw_rows(requests))
    (output/'chunks').mkdir()
    for chunk in chunks:
        folder=output/'chunks'/f'{chunk["index"]:03d}'
        folder.mkdir()
        start=chunk['index']*512
        (folder/'candidates.jsonl').write_bytes(raw_rows(rows[start:start+512]))
        (folder/'requests.jsonl').write_bytes(raw_rows(requests[start:start+512]))
        _write(folder/'plan.json',chunk)
    _write(output/'plan.json',plan)
    aggregate(output,plan,[],'prepared_unpaid')
    return plan


def aggregate(output,plan,results,stage,halt=None):
    by_id={row['id']:row for row in results}
    if len(by_id)!=len(results):raise ValueError('Duplicate aggregate result IDs')
    eligible=[row for row in results if row.get('eligible')]
    usage={key:sum((row.get('raw') or {}).get('usage',{}).get(key,0) for row in results)
           for key in ('prompt_tokens','completion_tokens')}
    chunks=[{'index':c['index'],'requested':512,'completed':sum(key in by_id for key in c['ids']),
             'budget_job_id':c['budget_job_id'],'requests_sha256':c['requests_sha256']} for c in plan['chunks']]
    summary={'schema_version':1,'run_id':plan['run_id'],'stage':stage,'requested':2048,'completed':len(results),
        'eligible':len(eligible),'failed':sum(bool(row.get('failed')) for row in results),
        'truncated':sum(bool(row.get('truncated')) for row in results),'chunks':chunks,
        'supervised_tokens_available':sum(row.get('supervised_tokens',0) for row in eligible),
        'eligibility_counts':dict(Counter(row['verification'] for row in results)),
        'estimated_peak_cost_usd':(usage['prompt_tokens']*1.32+usage['completion_tokens']*3.96)/1e6,
        'cost_note':'Recorded peak-rate token estimate, not provider wallet consumption or invoice',
        'usage':usage,'halt_reason':halt,'excluded_development_count':200,
        'artifact_fingerprints':{key:plan[key] for key in ('source_plan_sha256','candidates_sha256','requests_sha256','excluded_development_ids_sha256') if key in plan},
        'official_test_accessed':False,'automatic_retries':0,'thinking_enabled':False,'updated_at_utc':now(),
        'interpretation':'Reference-match eligibility does not prove natural-language semantic sufficiency. The200 separately frozen development questions are never teaching requests.'}
    transport.write_jsonl(output/'eligible.jsonl',eligible)
    _write(output/'teacher_summary.json',summary)
    _write(PUBLIC,{key:value for key,value in summary.items() if key!='usage'})
    return summary


def collect(output=RUN,chunk_index=None,workers=4):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'runs').resolve()) or chunk_index not in range(4) or not 1<=workers<=4:
        raise ValueError('Choose one explicit chunk0..3 and one to four workers')
    plan=json.loads((output/'plan.json').read_text(encoding='utf-8'))
    chunk=plan['chunks'][chunk_index]
    folder=output/'chunks'/f'{chunk_index:03d}'
    rows,requests=read_rows(folder/'candidates.jsonl'),read_rows(folder/'requests.jsonl')
    if (source.sha((folder/'candidates.jsonl').read_bytes())!=chunk['candidates_sha256']
            or source.sha((folder/'requests.jsonl').read_bytes())!=chunk['requests_sha256']
            or requests!=[{'id':row['id'],'payload':transport.build_payload(row)} for row in rows]
            or [row['id'] for row in rows]!=chunk['ids'] or len(rows)!=512):
        raise ValueError('Frozen chunk files or generation settings differ')
    if other_collector_locks(output):
        raise RuntimeError('Another teacher collector lock exists; inspect its process before launching')
    assert_reserved(chunk)
    tokenizer=load_tokenizer(local_files_only=True)
    fd=os.open(output/'collector.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    results=[];halt=None
    try:
        os.write(fd,str(os.getpid()).encode());os.fsync(fd)
        results_path=output/'teacher_results.jsonl'
        results=read_rows(results_path) if results_path.exists() else []
        by_id={row['id']:row for row in results}
        if len(by_id)!=len(results) or not set(by_id)<={key for c in plan['chunks'] for key in c['ids']}:
            raise RuntimeError('Existing result identities differ')
        if any(not set(c['ids'])<=set(by_id) for c in plan['chunks'][:chunk_index]):
            raise RuntimeError('Earlier chunk is incomplete; do not skip or overlap chunk invocations')
        (folder/'attempts').mkdir(exist_ok=True)
        def append(raw):
            row=transport.verify(raw,tokenizer)
            row.update(chunk_index=chunk_index,reference_match_is_independent_gold=True,
                       reference_semantics_verified=False)
            with results_path.open('a',encoding='utf-8') as handle:
                handle.write(_canonical(row)+'\n');handle.flush();os.fsync(handle.fileno())
            results.append(row);by_id[row['id']]=row
            return row
        pending=[]
        for row in rows:
            expected=_digest(transport.build_payload(row))
            if row['id'] in by_id:
                if by_id[row['id']].get('request_sha256')!=expected:raise RuntimeError('Saved request hash differs')
                continue
            marker,saved=_attempt_paths(folder,row['id'])
            if saved.exists():
                raw=json.loads(saved.read_text(encoding='utf-8'))
                if raw.get('id')!=row['id'] or raw.get('request_sha256')!=expected:raise RuntimeError('Recovered receipt differs')
                append(raw)
            elif marker.exists():
                raise RuntimeError('Ambiguous prior attempt requires process/provider reconciliation; no automatic replay')
            else:pending.append(row)
        aggregate(output,plan,results,'collecting')
        key=transport.credential('DEEPSEEK_API_KEY') if pending else None
        if pending and not key:raise RuntimeError('DeepSeek credential missing')
        record('in_progress','Human-reference teacher chunk started',
            f'Chunk{chunk_index+1}/4: at most512 immutable requests, four workers, nonthinking V4/1024tokens, no retries. Separate200-question development holdout withheld. Fresh funding and own reservation checked.',f'{plan["run_id"]}-chunk{chunk_index}-started')
        failures=0
        if pending:
            queue=iter(pending)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                active={executor.submit(transport._call,next(queue),folder,key) for _ in range(min(workers,len(pending)))}
                while active:
                    done,active=wait(active,return_when=FIRST_COMPLETED)
                    for future in done:
                        row=append(future.result())
                        failures=failures+1 if row.get('failed') else 0
                        if row.get('http_status') in (401,402,403,429):halt='provider_http_'+str(row['http_status'])
                        elif failures>=3:halt='three_consecutive_request_failures'
                        summary=aggregate(output,plan,results,'halted' if halt else 'collecting',halt)
                        print(json.dumps({key:summary[key] for key in ('stage','completed','requested','eligible','failed')}),flush=True)
                    if not halt:
                        while len(active)<workers:
                            row=next(queue,None)
                            if row is None:break
                            active.add(executor.submit(transport._call,row,folder,key))
        stage='completed' if len(results)==2048 else ('halted' if halt else 'awaiting_next_chunk')
        summary=aggregate(output,plan,results,stage,halt)
        record('failed' if halt else 'completed','Human-reference teacher chunk stopped' if halt else 'Human-reference teacher chunk completed',
            f'Chunk{chunk_index+1}/4 ended with {len(results)}/2048 total receipts and {summary["eligible"]} eligible responses. No next chunk launched; a new chunk requires its own fresh funding check and reservation.',f'{plan["run_id"]}-chunk{chunk_index}-'+stage)
        return summary
    except Exception as error:
        _write(output/'collector_failure.json',{'error_type':type(error).__name__,'chunk_index':chunk_index,
            'at_utc':now(),'completed':len(results),'note':'Reconcile lock/PID, receipts and funding before any resume; never replay ambiguous attempts'})
        raise
    finally:
        os.close(fd);(output/'collector.lock').unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','collect'))
    parser.add_argument('--cohort',type=Path,default=COHORT)
    parser.add_argument('--output',type=Path,default=RUN)
    parser.add_argument('--chunk',type=int)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    result=prepare(args.cohort,args.output) if args.action=='prepare' else collect(args.output,args.chunk,args.workers)
    print(json.dumps({key:result[key] for key in ('run_id','candidate_count','stage','completed','eligible') if key in result}),flush=True)


if __name__=='__main__':main()
