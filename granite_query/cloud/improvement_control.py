"""Durable next-phase plan: shared64 monitoring evaluation and full120 training."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent))
from cloud.comparison_control import read_jsonl,write
from cloud.progress import record
from cloud.comparison_metrics import summarize

EVAL=ROOT/'runs/matched_eval64_v1'
TRAIN=ROOT/'runs/granite_full120_v1'

def prepare():
    EVAL.mkdir(parents=True,exist_ok=True)
    TRAIN.mkdir(parents=True,exist_ok=True)
    if (EVAL/'plan.json').exists():
        print('Existing frozen64 plan retained')
        return
    old=ROOT/'runs/ranked_random_32_seed42_v1'
    oldplan=json.loads((old/'plan.json').read_text())
    excluded=set(oldplan['candidate_ids']+oldplan['development_ids'])
    excluded|={r['id'] for r in read_jsonl(ROOT/'runs/deepseek32b_pilot16_seed42/requests.jsonl')}
    source=ROOT.parent/'ranking/runs/gsm8k_preview_128_seed42/scores.jsonl'
    eligible=sorted([r for r in read_jsonl(source) if r['id'] not in excluded],key=lambda r:r['id'])
    random.Random(20261104).shuffle(eligible)
    dev=eligible[:64]
    assert len(dev)==64 and all(r['source_split']=='train' for r in dev)
    teacher=[r for r in read_jsonl(old/'teacher_results.jsonl') if r.get('eligible')]
    assert len(teacher)==120 and not ({r['id'] for r in dev}&{r['id'] for r in teacher})
    common={'model':oldplan['model'],'revision':oldplan['revision'],'seed':42,
        'development_ids':[r['id'] for r in dev],'max_new_tokens':512,
        'enable_thinking':False,'do_sample':False,'held_out_test_used':False,
        'monitoring_set':'64 official-training-split questions, never training targets',
        'limitations':'Development monitoring, not final test. Older BM25 adapter used corpus statistics that included these question texts, without labels.',
        'gpu':'A100-80GB','timeout_seconds':900,'reserved_usd':3}
    evalplan=dict(common,run_id=EVAL.name,mode='evaluate_saved',
        checkpoints=['baseline','ranked32','random32'],adapter_source=old.name)
    fullplan={**common,'run_id':TRAIN.name,'mode':'train_full120','learning_rate':1e-4,
        'lora_r':8,'lora_alpha':16,'context_limit':2048,'epochs':1,
        'train_ids':sorted(r['id'] for r in teacher),
        'teacher_pool_sha256':hashlib.sha256((old/'teacher_results.jsonl').read_bytes()).hexdigest()}
    write(EVAL/'plan.json',evalplan)
    write(TRAIN/'plan.json',fullplan)
    (EVAL/'development.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in dev),encoding='utf-8')
    minimaldev=[{k:r[k] for k in ('id','prompt','gold_answer')} for r in dev]
    write(EVAL/'input.json',{'development':minimaldev})
    write(TRAIN/'input.json',{'development':minimaldev,'training':[
        {k:r[k] for k in ('id','prompt','response','gold_answer')} for r in teacher]})
    record('planned','Shared64 benchmark and full120 training frozen',
        'A new64 development monitoring set is disjoint from the earlier pilot, teacher candidates and old development questions. Evaluate original Granite and saved32-example adapters, then train a fresh adapter on all120 verified teacher examples. Reuse the same64 questions for before/after comparisons. Official test remains untouched. Improvement is measured, not assumed.','improvement64-plan')
    write(WORKSPACE/'progress/current.json',{'stage':'Matched DeepSeek/Granite benchmark and larger training queued',
        'training_completed':True,'held_out_evaluation_completed':False})
    print(json.dumps({'evaluation':EVAL.name,'training':TRAIN.name,'monitoring_questions':64}))

def poll(run):
    import modal
    resume=ROOT/'runs/matched_eval64_resume1'
    folder=(resume if (resume/'launch.json').exists() else EVAL) if run=='eval' else TRAIN
    launch=json.loads((folder/'launch.json').read_text())
    if not launch.get('call_id'):
        raise RuntimeError('Ambiguous launch: reconcile before any retry')
    status=modal.Dict.from_name('granite-query-training-progress').get(folder.name,{'stage':'queued'})
    write(folder/'remote_status.json',status)
    if run=='eval' and folder!=EVAL:
        write(EVAL/'remote_status.json',status)
    try:
        result=modal.FunctionCall.from_id(launch['call_id']).get(timeout=0)
    except TimeoutError:
        result=None
    except Exception as exc:
        if status.get('stage')!='failed' and not isinstance(exc,modal.exception.FunctionTimeoutError):
            print(json.dumps(dict(status,monitoring_error_type=type(exc).__name__,note='Reconcile call state; no retry authorized by this monitoring error')))
            return
        status=dict(status,stage='failed',call_error_type=type(exc).__name__)
        write(folder/'remote_status.json',status)
        if run=='eval':
            write(EVAL/'remote_status.json',status)
        record('failed','Shared64 phase worker failed','Inspect saved stage artifacts before a separately reserved retry.',folder.name+'-failed')
        print(json.dumps(status))
        return
    if result is not None:
        write(folder/'result.json',result)
        metrics={name:summarize(rows) for name,rows in result['evaluations'].items()}
        write(folder/'metrics.json',metrics)
        if run=='eval' and folder!=EVAL:
            write(EVAL/'result.json',result)
            write(EVAL/'metrics.json',metrics)
        record('completed','Shared64 phase completed: '+run,
            'All evaluation outputs saved for the frozen64 monitoring questions. Counts: '+
            ', '.join(name+' '+str(m['numeric_correct'])+'/64' for name,m in metrics.items())+
            '. This is development monitoring, not final-test accuracy.',folder.name+'-completed')
    else:
        record('in_progress','Shared64 worker: '+status['stage'].replace('_',' '),
            'Polling the existing detached call; no duplicate job launched.',folder.name+'-'+status['stage'])
    write(WORKSPACE/'progress/current.json',{'stage':folder.name+': '+status['stage'],
        'training_completed':True,'held_out_evaluation_completed':False})
    print(json.dumps(status))

def prepare_resume():
    from cloud.comparison_control import reserve
    status=json.loads((EVAL/'remote_status.json').read_text())
    if status.get('stage')!='failed':
        raise RuntimeError('Only a confirmed failed evaluation may be resumed')
    target=ROOT/'runs/matched_eval64_resume1'
    if (target/'plan.json').exists():
        print('Existing resume plan retained')
        return
    plan=json.loads((EVAL/'plan.json').read_text())
    reserve('modal',3,target.name)
    target.mkdir(parents=True,exist_ok=True)
    write(target/'plan.json',dict(plan,run_id=target.name,resume_from=EVAL.name))
    (target/'input.json').write_bytes((EVAL/'input.json').read_bytes())
    record('planned','Resume only unfinished64-question evaluations',
        'The first evaluation attempt ended before all checkpoints finished. A single separately reserved resume preserves completed outputs and evaluates only missing questions under identical frozen conditions. Do not rerun completed phases.','matched64-resume-plan')
    print(json.dumps({'resume':target.name,'reserved_usd':3}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','poll','prepare_resume'])
    parser.add_argument('--run',choices=['eval','train'],default='eval')
    args=parser.parse_args()
    if args.action=='prepare':
        prepare()
    elif args.action=='prepare_resume':
        prepare_resume()
    else:
        poll(args.run)
