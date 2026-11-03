"""Offline preparation/validation of separate bounded base/chosen final calls."""
import argparse
import json
from pathlib import Path
import shutil
from cloud import final_eval_control as seal
from cloud import final_test_loader as loader

ROOT=Path(__file__).resolve().parent
DEPS=('final_eval_jobs.py','final_test_loader.py','modal_train.py','valuation_contract.py')
FIXED={'mode':'evaluate_saved','evaluation_kind':'final_test','evaluation_batch_size':8,
    'max_new_tokens':512,'enable_thinking':False,'do_sample':False,'timeout_seconds':1800,
    'application_guard_seconds':1600,'hard_cpu_cores':4,'hard_memory_gib':32,'reserved_usd_required':3}


def validate_payload(payload,plan,manifest):
    if seal.digest(manifest['protocol'])!=manifest['freeze_sha256'] or plan['freeze_sha256']!=manifest['freeze_sha256']:
        raise ValueError('Final job no longer matches the sealed protocol')
    if any(plan.get(k)!=v for k,v in FIXED.items()):raise ValueError('Bounded final inference protocol changed')
    if plan['checkpoint'] not in ('base','chosen') or plan['model']!=seal.MODEL or plan['revision']!=seal.REVISION:
        raise ValueError('Unknown final checkpoint identity')
    if plan['input_sha256']!=loader.sha_bytes(loader.encoded(payload)):
        raise ValueError('Final job payload changed')
    raw=payload['sample_jsonl'].encode('utf-8')
    rows=loader.validate_sample(raw,payload['sample_manifest'],manifest)
    protocol={k:v for k,v in plan.items() if k not in ('run_id','protocol_hash','resume_from')}
    if seal.digest(protocol)!=plan['protocol_hash']:raise ValueError('Final job plan changed')
    return rows


def prepare(final_folder,input_folder,output,*,checkpoint):
    if checkpoint not in ('base','chosen'):raise ValueError('Use base or the sealed chosen adapter')
    output=seal.private(output)
    if not seal.safe_name(output.name):raise ValueError('Final job run ID is unsafe')
    if output.exists():raise FileExistsError('Final job preparation is immutable')
    manifest,sample,raw,_=loader.load_prepared(final_folder,input_folder)
    loader.require_role(manifest,'granite_evaluator',ROOT/'modal_final_eval.py',dependencies=[ROOT/name for name in DEPS])
    payload={'sample_jsonl':raw.decode('utf-8'),'sample_manifest':sample}
    protocol=dict(FIXED,checkpoint=checkpoint,model=seal.MODEL,revision=seal.REVISION,
        seed=seal.SEED,freeze_sha256=manifest['freeze_sha256'],final_folder_path=str(Path(final_folder).resolve()),
        input_folder_path=str(Path(input_folder).resolve()),
        input_sha256=loader.sha_bytes(loader.encoded(payload)))
    plan=dict(protocol,run_id=output.name,protocol_hash=seal.digest(protocol),resume_from=None)
    validate_payload(payload,plan,manifest)
    output.mkdir(parents=True)
    seal.write_once(output/'plan.json',plan);seal.write_once(output/'input.json',payload)
    seal.write_once(output/'seal.json',manifest)
    return {'stage':'prepared','checkpoint':checkpoint,'questions':256,'paid_work_launched':False}


def prepare_resume(previous,output):
    previous,output=seal.private(previous),seal.private(output)
    if not seal.safe_name(output.name):raise ValueError('Recovery job run ID is unsafe')
    if output.exists():raise FileExistsError('Resume needs a new immutable run ID')
    launch=seal.load(previous/'launch.json');terminal=seal.load(previous/'terminal.json')
    if (terminal.get('confirmed_terminal') is not True or terminal.get('call_id')!=launch.get('call_id')
            or terminal.get('stage')=='completed'):
        raise ValueError('Confirm the old final call is terminal and incomplete before recovery')
    plan=seal.load(previous/'plan.json');manifest=seal.load(previous/'seal.json');payload=seal.load(previous/'input.json')
    validate_payload(payload,plan,manifest)
    updated=dict(plan,run_id=output.name,resume_from=previous.name)
    output.mkdir(parents=True)
    for name in ('input.json','seal.json'):shutil.copyfile(previous/name,output/name)
    seal.write_once(output/'plan.json',updated)
    return {'stage':'prepared_resume','checkpoint':plan['checkpoint'],'paid_work_launched':False}


def validate_saved(rows,source,manifest_hash):
    if len(rows)%8 or len(rows)>256 or len({r['id'] for r in rows})!=len(rows):
        raise ValueError('Saved final batches are incomplete or duplicated')
    if [r['id'] for r in rows]!=[r['id'] for r in source[:len(rows)]]:
        raise ValueError('Saved final batch question order changed')
    for result,gold in zip(rows,source):
        if str(result.get('gold_answer'))!=str(gold['gold_answer']) or result.get('freeze_sha256')!=manifest_hash:
            raise ValueError('Saved final result reference/protocol changed')
    return rows


def validate_batch(value,source,plan,manifest):
    start=value.get('start')
    if (type(start) is not int or start%8 or not 0<=start<256
            or value.get('freeze_sha256')!=manifest['freeze_sha256']
            or value.get('protocol_hash')!=plan['protocol_hash']
            or value.get('rows_sha256')!=loader.sha_bytes(loader.encoded(value.get('rows')))):
        raise ValueError('Durable final batch identity/hash changed')
    batch=value['rows']
    validate_saved(batch,source[start:start+8],manifest['freeze_sha256'])
    if len(batch)!=8:raise ValueError('Final batch must contain all eight saved outcomes')
    return batch


def validated_adapter(artifact_root,manifest):
    selected=manifest['protocol']['selected']
    if not seal.safe_name(selected['run_id']) or selected['adapter_subpath']!='adapter':
        raise ValueError('Invalid sealed chosen artifact identity')
    adapter=Path(artifact_root)/selected['run_id']/'adapter'
    hashes=selected.get('files_sha256',{})
    if not all(name in hashes for name in ('adapter_config.json','adapter_model.safetensors')):
        raise ValueError('Selected adapter inventory is incomplete')
    for name,expected in hashes.items():
        target=(adapter/name).resolve()
        if not target.is_relative_to(adapter.resolve()) or not target.is_file() or seal.sha(target)!=expected:
            raise ValueError('Chosen immutable adapter changed before final model loading')
    return adapter


def poll(folder):
    import modal
    folder=seal.private(folder);launch=seal.load(folder/'launch.json')
    if not launch.get('call_id'):raise ValueError('Ambiguous final launch requires reconciliation')
    try:result=modal.FunctionCall.from_id(launch['call_id']).get(timeout=0)
    except TimeoutError:return {'stage':'running_or_queued','confirmed_terminal':False}
    except Exception as error:
        terminal=isinstance(error,(modal.exception.FunctionTimeoutError,modal.exception.UserCodeException))
        value={'stage':'failed' if terminal else 'monitoring_error','error_type':type(error).__name__,
            'confirmed_terminal':terminal,'call_id':launch['call_id']}
        if terminal:loader.atomic(folder/'terminal.json',value)
        return value
    loader.atomic(folder/'result.json',result)
    loader.atomic(folder/'terminal.json',{'stage':result['stage'],'confirmed_terminal':True,'call_id':launch['call_id']})
    return {'stage':result['stage'],'confirmed_terminal':True,'call_id':launch['call_id']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare')
    for name in ('final-folder','input-folder','output'):prep.add_argument('--'+name,type=Path,required=True)
    prep.add_argument('--checkpoint',choices=['base','chosen'],required=True)
    resume=sub.add_parser('prepare-resume');resume.add_argument('--previous',type=Path,required=True);resume.add_argument('--output',type=Path,required=True)
    monitor=sub.add_parser('poll');monitor.add_argument('--folder',type=Path,required=True)
    args=parser.parse_args()
    result=(prepare(args.final_folder,args.input_folder,args.output,checkpoint=args.checkpoint) if args.action=='prepare'
        else prepare_resume(args.previous,args.output) if args.action=='prepare-resume' else poll(args.folder))
    print(json.dumps(result))
