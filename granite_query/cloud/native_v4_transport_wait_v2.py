"""Bounded local wait and correctly ordered fresh transport gates.

The prior transport and all21 model/protocol sources remain immutable. A
driver's evidence is historical after CPU checks; only a new final supported
observation immediately before transmission can satisfy the fresh gate.
"""
from datetime import datetime
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import json
from cloud import native_v4_transport as base

control=base.control
VERSION='native-v4-local-wait-fresh-gate-v2'
NORMAL_CLI=base.NORMAL_CLI
REPAIR_CLI='cloud.modal_native_v4_transport_wait_v2::repair_launch_v2'
LOCAL_WAIT_SECONDS=900
SOURCES=('native_v4_transport_wait_v2.py','modal_native_v4_transport_wait_v2.py')


def source_hashes():return {name:control.sha(control.ROOT/name) for name in SOURCES}


def policy_template(output=control.DEFAULT,*,base_review=None):
    output=control.safe(output);r=base_review if base_review is not None else base.validate_transport_review(output)
    return {'version':VERSION,'reviewed':False,'phase':'bounded_local_wait_and_final_fresh_gate',
        'base_review_sha256':control.sha(output/'transport_review.json'),'base_transport_source_sha256':base.source_hashes(),
        'wait_source_sha256':source_hashes(),'frozen_source_sha256':r['frozen_source_sha256'],
        'design_sha256':r['design_sha256'],'manifest_sha256':r['manifest_sha256'],'funding_sha256':r['funding_sha256'],
        'dispatch_sha256':r['dispatch_sha256'],'claim_id':r['claim_id'],'normal_cli':NORMAL_CLI,'repair_cli':REPAIR_CLI,
        'local_cli_wait_seconds':900,'model_hard_timeout_seconds':1800,'training_guard_seconds':1400,'evaluation_guard_seconds':1600,
        'final_fresh_evidence_max_age_seconds':120,'historical_driver_proof_bound_to_original_intent':True,
        'same_dispatch_and_allowance':True,'allowance_usd':1.75,'new_reservation_created':False,'automatic_retries':0}


def validate_wait_review(output=control.DEFAULT):
    output=control.safe(output);r=base.validate_transport_review(output)
    actual=control.read(output/'transport_wait_review_v2.json');expected=dict(policy_template(output,base_review=r),reviewed=True)
    if (actual!=expected or actual.get('reviewed') is not True or actual.get('same_dispatch_and_allowance') is not True
            or actual.get('new_reservation_created') is not False or actual.get('historical_driver_proof_bound_to_original_intent') is not True
            or type(actual.get('local_cli_wait_seconds')) is not int):
        raise ValueError('Exact separate local-wait/freshness policy review required')
    return {'policy':actual,'base_review':r}


def launch_args(folder,*,repair=False):
    return [sys.executable,'-m','modal','run','--detach','-m',REPAIR_CLI if repair else NORMAL_CLI,'--folder',str(control.safe(folder))]


class WaitBackend(base.TransportBackend):
    def launch(self,folder):return self.run_cli(folder,repair=False)
    def run_cli(self,folder,*,repair):
        folder=control.safe(folder);output=folder.parents[1];review=validate_wait_review(output)
        if repair:
            control.write(folder/'transport_wait_policy_claim_v2.json',{'version':VERSION,
                'wait_review_sha256':control.sha(output/'transport_wait_review_v2.json'),
                'base_intent_sha256':control.sha(folder/'transport_repair_intent.json'),
                'dispatch_sha256':control.sha(folder/'dispatch.json'),'wait_source_sha256':source_hashes(),
                'module':REPAIR_CLI,'local_cli_wait_seconds':900,'new_reservation_created':False},immutable=True)
        prefix='transport.wait2.repair' if repair else 'transport.wait2.launch'
        try:
            result=subprocess.run(launch_args(folder,repair=repair),cwd=control.ROOT.parent,capture_output=True,
                timeout=LOCAL_WAIT_SECONDS,env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',MODAL_IMAGE_BUILDER_VERSION='2025.06'))
            out,err,code=result.stdout,result.stderr,result.returncode
        except subprocess.TimeoutExpired as exc:out,err,code=exc.stdout or b'',exc.stderr or b'',None
        base._immutable_bytes(folder/(prefix+'.stdout.private.log'),out or b'\n')
        base._immutable_bytes(folder/(prefix+'.stderr.private.log'),err or b'\n')
        app=re.search(rb'ap-[A-Za-z0-9]+',out+b'\n'+err)
        return {'return_code':code,'app_id':app.group().decode() if app else None,'transport_version':VERSION,
            'module':REPAIR_CLI if repair else NORMAL_CLI,'wait_source_sha256':source_hashes(),
            'wait_review_sha256':control.sha(output/'transport_wait_review_v2.json'),'local_cli_wait_seconds':900}


def validate_historical_absence(evidence,job,intent):
    """Validate pre-intent facts and their original timing, never call them fresh now."""
    observed=datetime.fromisoformat(evidence['observed_at_utc'].replace('Z','+00:00'))
    created=datetime.fromisoformat(intent['created_at_utc'].replace('Z','+00:00'))
    if (observed.tzinfo is None or created.tzinfo is None or not 0<=(created-observed).total_seconds()<=120
            or not {'actual_remote_owner','actual_remote_progress'}<=evidence.keys()
            or evidence.get('run_id')!=job['run_id'] or evidence.get('actual_remote_owner') is not None
            or evidence.get('actual_remote_progress') is not None or evidence.get('old_processes')!=[None,None]
            or evidence.get('volume')!={'exists':False,'provider_exception':'NotFoundError'}):
        raise ValueError('Historical driver evidence must have been valid before its exact original intent')
    base._zero_apps(evidence.get('apps'))


def delegated_preflight_v2(folder):
    """All expensive audits finish before the final live provider observation."""
    folder=control.safe(folder);output=folder.parents[1];reviews=validate_wait_review(output);r=reviews['base_review']
    jobs=control.load_jobs(output);job=next(j for j in jobs if j['folder_path']==folder)
    dispatch=control.Controller(output)._dispatch(job);original=control.read(folder/'controller_owner.json')
    delegation=control.read(folder/'transport_delegation.json');intent=control.read(folder/'transport_repair_intent.json')
    claim=control.read(folder/'transport_wait_policy_claim_v2.json')
    live=base.process_identity(delegation['new_driver']['pid']);lease=control.safe(control.STATE/'gpu_launch.lock')
    if (delegation.get('version')!=base.VERSION or delegation.get('original_owner_sha256')!=control.sha(folder/'controller_owner.json')
            or original.get('claim_id')!=dispatch['claim_id'] or delegation.get('claim_id')!=dispatch['claim_id']
            or delegation.get('transport_review_sha256')!=control.sha(output/'transport_review.json')
            or not isinstance(live,dict) or live!=delegation.get('new_driver') or not lease.is_file() or lease.read_text()!=str(live['pid'])
            or intent.get('version')!=base.VERSION or intent.get('delegation_sha256')!=control.sha(folder/'transport_delegation.json')
            or intent.get('dispatch_sha256')!=control.sha(folder/'dispatch.json') or intent.get('transport_source_sha256')!=base.source_hashes()
            or intent.get('fresh_reconciliation_sha256')!=control.sha(folder/'transport_never_transmitted.json')
            or intent.get('original_failed_receipt_sha256')!=r['wrong_cli_receipt_sha256']
            or claim!={'version':VERSION,'wait_review_sha256':control.sha(output/'transport_wait_review_v2.json'),
                'base_intent_sha256':control.sha(folder/'transport_repair_intent.json'),'dispatch_sha256':control.sha(folder/'dispatch.json'),
                'wait_source_sha256':source_hashes(),'module':REPAIR_CLI,'local_cli_wait_seconds':900,'new_reservation_created':False}):
        raise ValueError('Exact actual owner delegation, historical intent and separate wait-policy claim required')
    base.observe_cli_ancestry(delegation)
    validate_historical_absence(control.read(folder/'transport_never_transmitted.json'),job,intent)
    if any((folder/name).exists() for name in ('launch.json','cli_spawn_started.json','transport_cli_spawn_started.json','transport_cli_spawn_started_v2.json')):
        raise ValueError('Known or unknown prior transmission; never retry')
    ledger=control.fresh_funding(control.read(control.STATE/'budget.json'));control.validate_stage_funding(output,ledger)
    _funding_gate(ledger,job,dispatch,output)
    phase=control.review(output,'baseline')
    if job['role']!='baseline' or phase.get('study_manifest_sha256')!=control.sha(output/'study_manifest.json'):
        raise ValueError('Only the reviewed never-transmitted baseline may delegate')
    base.frozen_cli.worker.validate_dispatch(job['data'],job['plan'],dispatch)
    base.frozen_cli.worker.verify_sources(dispatch['source_sha256'])
    names=('design.json','study_manifest.json','funding.json','transport_review.json','transport_wait_review_v2.json')
    return {'job':job,'dispatch':dispatch,'delegation':delegation,'reviews':reviews,
        'file_hashes':{str(output/name):control.sha(output/name) for name in names},
        'arm_hashes':{str(folder/name):control.sha(folder/name) for name in ('controller_owner.json','plan.json','input.json',
            'dispatch.json','transport_delegation.json','transport_repair_intent.json','transport_never_transmitted.json','transport_wait_policy_claim_v2.json')},
        'frozen_source_sha256':control.source_inventory(),'base_source_sha256':base.source_hashes(),'wait_source_sha256':source_hashes()}


def _funding_gate(ledger,job,dispatch,output):
    entry=control._one(ledger,job['run_id'])
    if (entry.get('status')!='spawning' or entry.get('reserved_usd')!=1.75 or entry.get('native_claim_id')!=dispatch['claim_id']
            or entry.get('native_intent_sha256')!=dispatch['intent_sha256'] or entry.get('native_design_sha256')!=control.sha(output/'design.json')
            or any(j['run_id']!=job['run_id'] for j in control.active_jobs(ledger))
            or ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']<5):
        raise ValueError('Current exact same1.75 claim and protected funds required')


def final_guard(context,evidence,*,own_app_id):
    """Cheap actual rechecks only; no repeated expensive review after fresh query."""
    job,dispatch=context['job'],context['dispatch'];folder=job['folder_path'];output=folder.parents[1]
    live=base.process_identity(context['delegation']['new_driver']['pid']);lease=control.safe(control.STATE/'gpu_launch.lock')
    if (not isinstance(live,dict) or live!=context['delegation']['new_driver'] or not lease.is_file() or lease.read_text()!=str(live['pid'])
            or any(control.sha(path)!=expected for path,expected in {**context['file_hashes'],**context['arm_hashes']}.items())
            or control.source_inventory()!=context['frozen_source_sha256'] or base.source_hashes()!=context['base_source_sha256']
            or source_hashes()!=context['wait_source_sha256']):raise ValueError('Actual owner/lease/source/intent changed after physical audit')
    ancestry=base.observe_cli_ancestry(context['delegation'])
    ledger=control.fresh_funding(control.read(control.STATE/'budget.json'));_funding_gate(ledger,job,dispatch,output)
    base._fresh_absence(evidence,job,own_app_id=own_app_id)
    if any((folder/name).exists() for name in ('launch.json','cli_spawn_started.json','transport_cli_spawn_started.json','transport_cli_spawn_started_v2.json')):
        raise ValueError('A transmission marker appeared; never retry')
    return ancestry


def repair_existing(output=control.DEFAULT,*,backend=None):
    validate_wait_review(output)
    return base.repair_existing(output,backend=backend or WaitBackend())


def safe_advance(output=control.DEFAULT,*,backend=None):
    validate_wait_review(output)
    return control.Controller(output,backend or WaitBackend()).advance()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',nargs='?',default='inspect',choices=('inspect','review-template','repair','advance','poll','calibrate'))
    p.add_argument('--run',type=Path,default=control.DEFAULT);a=p.parse_args()
    if a.action=='inspect':result=control.inspect(a.run)
    elif a.action=='review-template':result=policy_template(a.run)
    elif a.action=='repair':result=repair_existing(a.run)
    elif a.action=='advance':result=safe_advance(a.run)
    else:validate_wait_review(a.run);result=getattr(control.Controller(a.run,WaitBackend()),a.action)()
    print(json.dumps(result,default=str))


if __name__=='__main__':main()
