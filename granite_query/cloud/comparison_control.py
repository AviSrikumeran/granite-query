"""Frozen, budget-reserved ranked/random pilot and resumable teacher collection."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'runs/ranked_random_32_seed42_v1'
sys.path.insert(0, str(ROOT.parent))
from cloud.run_api_pilot import credential
from cloud.progress import record
from ranking.verification import teacher_eligible

def write(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(path)

def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').split('\n') if line.strip()]

def reserve(service, amount, job_id):
    path = ROOT / 'runs/supervisor/budget.json'
    ledger = json.loads(path.read_text())
    if any(j['run_id'] == job_id for j in ledger['jobs']):
        return
    if ledger['estimated_spend'][service] + ledger['reserved'][service] + amount > ledger['limits'][service]:
        raise RuntimeError('Service budget would be exceeded')
    ledger['reserved'][service] += amount
    ledger['jobs'].append({'run_id': job_id, 'service': service, 'reserved_usd': amount,
        'status': 'reserved', 'created_at_utc': datetime.now(timezone.utc).isoformat()})
    write(path, ledger)

def prepare():
    RUN.mkdir(parents=True, exist_ok=True)
    if (RUN / 'plan.json').exists():
        print('Frozen comparison plan already exists')
        return
    score_file = ROOT.parent / 'ranking/runs/gsm8k_preview_128_seed42/scores.jsonl'
    rows = read_jsonl(score_file)
    pilot_ids = {r['id'] for r in read_jsonl(ROOT / 'runs/deepseek32b_pilot16_seed42/requests.jsonl')}
    rows = sorted([r for r in rows if r['id'] not in pilot_ids], key=lambda r:r['id'])
    random.Random(20261103).shuffle(rows)
    development, candidates = rows[:16], rows[16:144]
    assert len({r['id'] for r in development+candidates}) == 144
    assert all(r['source_split'] == 'train' for r in development+candidates)
    plan = {'run_id': RUN.name, 'model': 'ibm-granite/granite-4.2-3b',
        'revision': '4e9c275e232f10211ec88644d106a1f6a1b60e06',
        'seed': 42, 'sampling_seed': 20261103, 'candidate_count': 128,
        'examples_per_arm': 32, 'epochs': 1, 'learning_rate': 1e-4,
        'lora_r': 8, 'lora_alpha': 16, 'context_limit': 2048,
        'max_new_tokens': 512, 'do_sample': False, 'enable_thinking': False,
        'development_ids': [r['id'] for r in development],
        'candidate_ids': [r['id'] for r in candidates], 'held_out_test_used': False,
        'selection': 'mean BM25 against 128 frozen training probes using fixed 7344-question reference index',
        'score_source_sha256': hashlib.sha256(score_file.read_bytes()).hexdigest(),
        'teacher_model': 'deepseek-v4-pro', 'teacher_max_tokens': 4096,
        'teacher_calls_max': 128, 'teacher_retries': 0,
        'matching': 'equal examples and epochs; actual supervised tokens measured, not assumed equal',
        'limitations': 'single seed, 16 training-split development questions, not final test or publication-grade conclusion',
        'modal_timeout_seconds': 900, 'modal_reservation_usd': 3,
        'deepseek_reservation_usd': 3}
    reserve('deepseek', 3, RUN.name+'-teacher')
    reserve('modal', 3, RUN.name)
    for filename, data in [('candidates.jsonl', candidates), ('development.jsonl', development)]:
        (RUN / filename).write_text(''.join(json.dumps(r)+'\n' for r in data), encoding='utf-8')
    write(RUN / 'plan.json', plan)
    record('in_progress', 'Ranked versus random comparison frozen',
        '128 new candidate questions, 32 examples per arm, and 16 separate training-split development questions. Both arms start from pinned Granite 4.2 3B with identical LoRA settings. One seed; equal example counts, with actual token counts reported. Reserved 3 dollars DeepSeek and 3 dollars Modal. No official test data.')
    write(ROOT.parents[1] / 'progress/current.json', {'stage':'Generating the shared verified teacher pool',
        'training_completed': True, 'held_out_evaluation_completed': False})
    print(json.dumps({'prepared':RUN.name,'candidates':128,'examples_per_arm':32,'development':16}))

def _generate():
    plan = json.loads((RUN / 'plan.json').read_text())
    key = credential('DEEPSEEK_API_KEY')
    if not key:
        raise RuntimeError('Teacher credential missing')
    output = RUN / 'teacher_results.jsonl'
    done = {r['id'] for r in read_jsonl(output)} if output.exists() else set()
    def call(row):
        body = {'model':plan['teacher_model'],'max_tokens':4096,'stream':False,
            'thinking':{'type':'enabled'},'messages':[
            {'role':'system','content':'Solve the math problem. Explain the necessary calculation steps clearly. End with exactly #### followed by a plain numeric final answer, without currency symbols or units. No text after the final answer.'},
            {'role':'user','content':row['prompt']}]}
        req = urllib.request.Request('https://api.deepseek.com/chat/completions',
            data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req,timeout=120) as response:
                raw = json.load(response)
            choice = raw['choices'][0]
            result = dict(row,response=choice['message'].get('content') or '',raw=raw,
                teacher_model=plan['teacher_model'],teacher_revision=raw.get('model',plan['teacher_model']),
                finish_reason=choice.get('finish_reason'),elapsed_seconds=time.monotonic()-started,
                generation={'prompt_version':'gsm8k-comparison-v1','settings':{k:v for k,v in body.items() if k!='messages'}})
            result['eligible'], result['verification'] = teacher_eligible(result)
            return result
        except Exception as exc:
            return dict(row,eligible=False,verification='api_failure',error_type=type(exc).__name__)
    pending = [r for r in read_jsonl(RUN / 'candidates.jsonl') if r['id'] not in done]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(call,row) for row in pending]
        for future in as_completed(futures):
            row = future.result()
            with output.open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(row,ensure_ascii=False)+'\n')
            done.add(row['id'])
            print(json.dumps({'teacher_completed':len(done),'eligible':row['eligible']}),flush=True)
    rows = read_jsonl(output)
    summary = {'completed':len(rows),'eligible':sum(r['eligible'] for r in rows),
        'prompt_tokens':sum(r.get('raw',{}).get('usage',{}).get('prompt_tokens',0) for r in rows),
        'completion_tokens':sum(r.get('raw',{}).get('usage',{}).get('completion_tokens',0) for r in rows)}
    summary['estimated_upper_cost_usd'] = (summary['prompt_tokens']*1.32+summary['completion_tokens']*3.96)/1e6
    write(RUN / 'teacher_summary.json',summary)
    record('completed','Shared teacher pool generated',
        f"Received {summary['completed']} candidate attempts; {summary['eligible']} passed strict final-answer checks. Raw outputs and rejected records retained. The same eligible pool feeds both selectors.")
    print(json.dumps(summary),flush=True)

def generate():
    lock=RUN/'teacher.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode())
        _generate()
    finally:
        os.close(fd)
        lock.unlink()

def select():
    plan = json.loads((RUN / 'plan.json').read_text())
    rows = [r for r in read_jsonl(RUN / 'teacher_results.jsonl') if r.get('eligible') and teacher_eligible(r)[0]]
    if len(rows)<64:
        raise RuntimeError('Fewer than 64 verified examples; do not silently weaken the experiment')
    ranked = sorted(rows,key=lambda r:(-r['selection_score'],r['id']))[:32]
    shuffled = sorted(rows,key=lambda r:r['id'])
    random.Random(42).shuffle(shuffled)
    random_rows = shuffled[:32]
    plan['arms'] = {name:[r['id'] for r in arm] for name,arm in [('ranked',ranked),('random',random_rows)]}
    plan['eligible_count'] = len(rows)
    plan['arm_overlap'] = len(set(plan['arms']['ranked'])&set(plan['arms']['random']))
    plan['teacher_results_sha256'] = hashlib.sha256((RUN/'teacher_results.jsonl').read_bytes()).hexdigest()
    if (RUN / 'launch.json').exists():
        raise RuntimeError('Cannot modify a launched plan')
    write(RUN / 'plan.json',plan)
    fields=('id','prompt','response','gold_answer')
    unique={r['id']:r for r in ranked+random_rows}
    data={'training':[ {k:r[k] for k in fields} for r in unique.values()],
          'development':[ {k:r[k] for k in ('id','prompt','gold_answer')} for r in read_jsonl(RUN/'development.jsonl')]}
    write(RUN / 'input.json',data)
    record('completed','Ranked and random subsets selected',
        f"Selected 32 examples per arm from {len(rows)} identical eligible candidates. Overlap: {plan['arm_overlap']} examples. BM25 uses frozen prompt-only relevance scores; random selection uses seed 42. Training and development IDs are disjoint.")
    print(json.dumps({'eligible':len(rows),'overlap':plan['arm_overlap'],'ready':True}))

def poll():
    import modal
    launch=json.loads((RUN/'launch.json').read_text())
    if not launch.get('call_id'):
        raise RuntimeError('Ambiguous launch; reconcile instead of retrying')
    remote=modal.Dict.from_name('granite-query-training-progress')
    status=remote.get(RUN.name,{'stage':'queued'})
    write(RUN/'remote_status.json',status)
    try:
        result=modal.FunctionCall.from_id(launch['call_id']).get(timeout=0)
    except TimeoutError:
        result=None
    except Exception as exc:
        status=dict(status,stage='failed',error_type=type(exc).__name__)
        write(RUN/'remote_status.json',status)
        record('failed','Ranked versus random worker failed','Inspect preserved checkpoints and logs before creating a new attempt.',RUN.name+'-failed')
        result=None
    if result is not None:
        write(RUN/'result.json',result)
        from cloud.comparison_metrics import summarize, score
        metrics={'baseline':summarize(result['baseline']),
            'arms':{name:dict(summarize(arm['evaluation']),supervised_tokens=arm['supervised_tokens'],steps=arm['steps']) for name,arm in result['arms'].items()},
            'held_out_test_used':False,'single_seed':True,
            'limitation':'16 development questions; equal example counts, not equal training tokens. No final-test or generalization claim.'}
        metrics['ranked_minus_random_correct']=metrics['arms']['ranked']['numeric_correct']-metrics['arms']['random']['numeric_correct']
        write(RUN/'metrics.json',metrics)
        record('completed','First ranked versus random run completed',
            f"Numeric development matches out of 16: baseline {metrics['baseline']['numeric_correct']}, ranked {metrics['arms']['ranked']['numeric_correct']}, random {metrics['arms']['random']['numeric_correct']}. Supervised training tokens: ranked {metrics['arms']['ranked']['supervised_tokens']}, random {metrics['arms']['random']['supervised_tokens']}. Both adapters and raw evaluations saved. One seed and development data only; no final-test or robust generalization claim.",RUN.name+'-completed')
    else:
        record('in_progress','Comparison worker: '+status['stage'].replace('_',' '),
            'Polling the existing detached call; no duplicate job launched.',RUN.name+'-'+status['stage'])
    write(ROOT.parents[1]/'progress/current.json',{'stage':'Ranked versus random: '+status['stage'],
        'training_completed':True,'held_out_evaluation_completed':False})
    print(json.dumps(status))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','generate','select','poll'])
    args=parser.parse_args()
    globals()[args.action]()
