"""Prepare/poll immutable per-arm equal-token jobs. Preparation spends nothing."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud.comparison_control import write,read_jsonl
from cloud.valuation_contract import validate_arm
from cloud.progress import record
from cloud.comparison_metrics import summarize


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(selection,arm_name,development,output,*,learning_rate=2e-5,evaluation_batch_size=8,probe_pool=None):
    selection,development,output=Path(selection),Path(development),Path(output)
    if output.exists():
        raise FileExistsError('Use a new immutable per-arm output folder')
    manifest_raw=(selection/'manifest.json').read_bytes()
    manifest=json.loads(manifest_raw)
    arm_path=selection/(arm_name+'_input.json')
    arm_raw=arm_path.read_bytes()
    if digest(arm_raw)!=manifest['artifacts_sha256'][arm_path.name]:
        raise ValueError('Selection input changed after freezing')
    arm=json.loads(arm_raw)
    rows=validate_arm(arm)
    if manifest['token_budget']!=arm['token_budget'] or arm['arm']!=arm_name:
        raise ValueError('Selector manifest and arm differ')
    if arm['token_budget']!=32768 or arm['tokens_per_update']!=1024:
        raise ValueError('Current reviewed protocol requires32768 supervised tokens and1024 tokens/update')
    dev=read_jsonl(development)
    ids=[row['id'] for row in dev]
    if len(ids)!=64 or len(set(ids))!=64 or set(ids)&set(rows):
        raise ValueError('Require64 distinct disjoint development questions')
    if any(row.get('source_split','train')!='train' for row in dev):
        raise ValueError('This controller prepares development monitoring only')
    if learning_rate!=2e-5 or not 1<=evaluation_batch_size<=16:
        raise ValueError('Unexpected learning rate or evaluation batch size')
    payload={'arm':arm,'development':[{k:row[k] for k in ('id','prompt','gold_answer')} for row in dev]}
    probe_hash=None
    if probe_pool:
        probe_path=Path(probe_pool)
        prepared=read_jsonl(probe_path)
        if len(prepared)>512 or len({r['id'] for r in prepared})!=len(prepared):
            raise ValueError('At most512 unique probe candidates')
        if any(r.get('source_split')!='train' or r['id'] in ids for r in prepared):
            raise ValueError('Probe candidates must be training records disjoint from development')
        payload['probe_candidates']=[{'id':r['id'],'input_ids':r['prefix_ids']+r['answer_ids'],
            'prefix_tokens':len(r['prefix_ids']),'raw_response_sha256':r['raw_response_sha256']} for r in prepared]
        probe_hash=digest(probe_path.read_bytes())
    input_raw=(json.dumps(payload,indent=2)+'\n').encode('utf-8')
    protocol={'mode':'train_evaluate','model':arm['tokenizer']['model'],'revision':arm['tokenizer']['revision'],
        'seed':manifest['seed'],'arm':arm_name,'token_budget':arm['token_budget'],
        'tokens_per_update':arm['tokens_per_update'],'learning_rate':learning_rate,'lora_r':8,'lora_alpha':16,
        'context_limit':2048,'max_new_tokens':512,'enable_thinking':False,'do_sample':False,
        'evaluation_batch_size':evaluation_batch_size,'evaluation_kind':'development',
        'development_ids':ids,'development_source_sha256':digest(development.read_bytes()),
        'selection_manifest_sha256':digest(manifest_raw),'arm_source_sha256':digest(arm_raw),
        'probe_pool_sha256':probe_hash,'input_sha256':digest(input_raw),
        'gpu':'A100-80GB','timeout_seconds':1800,'application_evaluation_guard_seconds':1600,
        'reserved_usd':3,'latency_measurement':'amortized batched GPU wall time; not single-request latency'}
    plan=dict(protocol,run_id=output.name,
        protocol_hash=digest(json.dumps(protocol,sort_keys=True,separators=(',',':')).encode()))
    output.mkdir(parents=True)
    (output/'input.json').write_bytes(input_raw)
    write(output/'plan.json',plan)
    record('planned','Exact-token '+arm_name+' arm prepared',
        'Prepared32768 supervised answer tokens,32 optimizer updates, learning rate0.00002, and batched64-question development evaluation. Each arm starts from the pinned base. Preparation launched no GPU job.',output.name+'-prepared')
    print(json.dumps({'prepared':str(output),'run_id':output.name,'arm':arm_name,'token_budget':arm['token_budget'],
        'optimizer_updates':arm['optimizer_updates'],'probe_candidates':len(payload.get('probe_candidates',[])),
        'paid_work_launched':False}))
    return plan


def poll(folder):
    import modal
    folder=Path(folder)
    launch=json.loads((folder/'launch.json').read_text())
    if not launch.get('call_id'):
        raise RuntimeError('Ambiguous launch: reconcile before retry')
    status=modal.Dict.from_name('granite-query-training-progress').get(folder.name,{'stage':'queued'})
    write(folder/'remote_status.json',status)
    try:
        result=modal.FunctionCall.from_id(launch['call_id']).get(timeout=0)
    except TimeoutError as exc:
        if status.get('stage')=='failed':
            record('failed','Equal-token arm stopped','Adapter/checkpoint and completed evaluation batches remain preserved; reconcile before a separately reserved recovery.',folder.name+'-failed')
        result=None
    except Exception as exc:
        if status.get('stage')!='failed':
            print(json.dumps(dict(status,monitoring_error_type=type(exc).__name__)))
            return
        result=None
        record('failed','Equal-token arm failed','Inspect the saved error, latest adapter and optimizer checkpoint; do not silently relaunch.',folder.name+'-failed')
    if result is not None:
        write(folder/'result.json',result)
        metrics={key:summarize(value) for key,value in result['evaluations'].items()}
        write(folder/'metrics.json',metrics)
        if result.get('student_probe'):
            write(folder/'student_scores.json',result['student_probe'])
        record('completed','Equal-token '+result['arm']+' arm completed',
            f"Completed {result['supervised_tokens']} supervised tokens and {result['optimizer_updates']} optimizer updates. Batched development results are saved; compare only the frozen matched arms and disclose adaptive development use.",folder.name+'-completed')
    print(json.dumps(status))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest='action',required=True)
    prep=commands.add_parser('prepare')
    prep.add_argument('--selection',type=Path,required=True)
    prep.add_argument('--arm',choices=['valued','random'],required=True)
    prep.add_argument('--development',type=Path,required=True)
    prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--probe-pool',type=Path)
    prep.add_argument('--evaluation-batch-size',type=int,default=8)
    monitor=commands.add_parser('poll')
    monitor.add_argument('--folder',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='prepare':
        prepare(args.selection,args.arm,args.development,args.output,
            evaluation_batch_size=args.evaluation_batch_size,probe_pool=args.probe_pool)
    else:
        poll(args.folder)
