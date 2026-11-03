"""One bounded grid tick. Default inspection never calls providers or mutates funds.

`tick --grid PATH --advance` reconciles owned calls, then may reserve a reviewed
phase and launch ONE unchanged modal_valuation call. No retry/retraining engine,
official-test work, teacher generation, or endpoint deployment is included.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud import data_efficiency_control as study
from cloud import budget_reconcile as accounting
from cloud.comparison_control import require_fresh_modal_budget
from cloud.comparison_metrics import summarize

ORDER=((42,'random'),(42,'skill'),(42,'gradient'),(43,'gradient'),(43,'skill'),(43,'random'))
ACTIVE={'reserved','spawning','spawned','running','queued'}


def now():return datetime.now(timezone.utc).isoformat()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.study.'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');temporary.replace(path)


@contextmanager
def exclusive(path):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:os.write(fd,str(os.getpid()).encode());os.fsync(fd);yield
    finally:os.close(fd);Path(path).unlink()


class Backend:
    """Provider/CLI boundary; tests substitute this entire boundary."""
    def refresh(self,state):
        if state.resolve()!=(ROOT/'runs/supervisor').resolve():raise ValueError('Production provider helper requires its normal durable state directory')
        result=subprocess.run([sys.executable,str(ROOT/'budget_reconcile.py'),'--refresh'],cwd=ROOT.parent,
            capture_output=True,env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'),timeout=60)
        write(state/'study_budget_refresh.private.json',{'at_utc':now(),'return_code':result.returncode,
            'stdout':result.stdout.decode('utf-8',errors='replace'),'stderr':result.stderr.decode('utf-8',errors='replace')})
        if result.returncode:raise RuntimeError('Supported provider budget refresh failed; inspect private state')

    def apps(self):
        result=subprocess.run([sys.executable,'-m','modal','app','list','--json'],capture_output=True,
            env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'),timeout=30,check=True)
        return json.loads(result.stdout.decode('utf-8'))

    def poll(self,folder,call_id):
        import modal
        try:result=modal.FunctionCall.from_id(call_id).get(timeout=0)
        except (modal.exception.FunctionTimeoutError,modal.exception.UserCodeException) as error:
            return {'kind':'failed','error_type':type(error).__name__}
        except TimeoutError:
            status=modal.Dict.from_name('granite-query-training-progress').get(folder.name,None)
            return {'kind':'running','remote_status':status or {'stage':'awaiting_worker_progress'}}
        except Exception as error:return {'kind':'monitoring_error','error_type':type(error).__name__}
        return {'kind':'completed','result':result}

    def launch(self,folder):
        args=[sys.executable,'-m','modal','run','--detach','-m','cloud.modal_valuation','--folder',str(folder)]
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',MODAL_IMAGE_BUILDER_VERSION='2025.06')
        try:
            result=subprocess.run(args,cwd=ROOT.parent,capture_output=True,env=env,timeout=180)
            out,err,code=result.stdout,result.stderr,result.returncode
        except subprocess.TimeoutExpired as error:
            out,err,code=error.stdout or b'',error.stderr or b'',None
        if isinstance(out,str):out=out.encode()
        if isinstance(err,str):err=err.encode()
        (folder/'study_launch.stdout.private.log').write_bytes(out)
        (folder/'study_launch.stderr.private.log').write_bytes(err)
        found=re.search(rb'ap-[A-Za-z0-9]+',out+b'\n'+err)
        value={'return_code':code,'app_id':found.group().decode() if found else None,
            'stdout_sha256':hashlib.sha256(out).hexdigest(),'stderr_sha256':hashlib.sha256(err).hexdigest()}
        write(folder/'study_launch.private.json',value)
        return value


class StudyRunner:
    def __init__(self,grid,*,review=None,state_dir=None,backend=None,verifier=study.verify,journal=None):
        self.grid=Path(grid).resolve();self.review_path=Path(review).resolve() if review else self.grid/'reviewed_for_launch.json'
        self.state=Path(state_dir or ROOT/'runs/supervisor').resolve()
        if not self.grid.is_relative_to((ROOT/'runs').resolve()) or not self.state.is_relative_to((ROOT/'runs').resolve()):
            raise ValueError('Grid and durable state must stay under ignored cloud/runs')
        self.backend=backend or Backend();self.verifier=verifier
        if journal is None:
            from cloud.progress import record
            self.journal=lambda kind,title,detail,key:record(kind,title,detail,key)
        else:self.journal=journal
        self.jobs=[]
        self.plan_issues=[]
        self.dispatch_attempted=False

    def load(self):
        top=read(self.grid/'grid_manifest.json')
        for child in top['studies']:
            folder=(self.grid/child['folder']).resolve()
            if not folder.is_relative_to(self.grid) or sha(folder/'manifest.json')!=child['manifest_sha256']:
                raise ValueError('Prospective grid manifest changed')
            manifest=read(folder/'manifest.json')
            if manifest['token_budget']!=child['token_budget']:raise ValueError('Budget level identity changed')
            for job in manifest['jobs']:
                path=(folder/job['folder']).resolve()
                if not path.is_relative_to(folder):raise ValueError('Unsafe grid job path')
                plan=read(path/'plan.json')
                if (plan.get('run_id')!=job['run_id'] or plan.get('protocol_hash')!=job['protocol_hash']
                        or plan.get('selector_name')!=job['selector'] or plan.get('seed')!=job['seed']):
                    self.plan_issues.append(job['run_id'])
                self.jobs.append(dict(job,folder_path=path,token_budget=child['token_budget'],plan=plan))
        if len({j['run_id'] for j in self.jobs})!=len(self.jobs):raise ValueError('Duplicate prospective run IDs')
        rank={pair:index for index,pair in enumerate(ORDER)}
        self.jobs.sort(key=lambda j:(j['token_budget'],rank[(j['seed'],j['selector'])]))
        return top

    def review(self):
        value=read(self.review_path)
        if (value.get('reviewed') is not True or value.get('grid_manifest_sha256')!=sha(self.grid/'grid_manifest.json')
                or value.get('runner_sha256')!=sha(Path(__file__)) or value.get('protected_modal_usd')!=5
                or sorted(value.get('approved_selectors',[]))!=sorted(study.SELECTORS)
                or sorted(value.get('approved_seeds',[]))!=[42,43]
                or not value.get('approved_token_budgets')
                or not set(value['approved_token_budgets'])<=set(j['token_budget'] for j in self.jobs)):
            raise ValueError('Root review must bind this runner/grid, approved levels/selectors/seeds and protected5 dollars')
        return value

    def edit_budget(self,change):
        path=self.state/'budget.json'
        with exclusive(self.state/'budget_reconcile.lock'):
            original=path.read_bytes();ledger=json.loads(original);change(ledger)
            snapshot=self.state/'modal_billing_snapshot.json';apps=self.state/'modal_app_status_snapshot.json'
            if snapshot.exists():
                ledger=accounting.reconcile(ledger,read(snapshot),apps=read(apps).get('apps',[]) if apps.exists() else [])
            if path.read_bytes()!=original:raise RuntimeError('Ledger changed concurrently; no overwrite performed')
            write(path,ledger)

    def terminal(self,job,kind,*,runtime=None,call_id=None,app_id=None):
        def change(ledger):
            target=next((j for j in ledger['jobs'] if j['run_id']==job['run_id'] and j.get('service','modal')=='modal'),None)
            if target is None:raise ValueError('Owned call has no saved budget reservation')
            if target.get('call_id') not in (None,call_id):raise ValueError('Ledger call identity changed')
            target.update(status=kind,call_id=call_id,terminal_observed_at_utc=now())
            if app_id:target['app_id']=app_id
            if runtime is not None:target['runtime_seconds']=runtime
            target['cost_basis']='Confirmed terminal call; provider observations and temporary liabilities determine cost, never the full reservation as an invented charge'
        self.edit_budget(change)

    def validate_result(self,job,result):
        plan=job['plan'];name=job['selector'];data=read(job['folder_path']/'input.json')
        if (not isinstance(result,dict) or result.get('stage')!='completed' or result.get('plan')!=plan
                or result.get('supervised_tokens')!=job['token_budget']
                or result.get('optimizer_updates')!=job['token_budget']//1024
                or set(result.get('evaluations',{}))!={name} or result.get('held_out_test_used') is not False):
            raise ValueError('Terminal result differs from the reviewed token/checkpoint protocol')
        outcomes=result['evaluations'][name];expected=data['development']
        if len(outcomes)!=64 or [r['id'] for r in outcomes]!=[r['id'] for r in expected]:
            raise ValueError('Terminal development question identities/order changed')
        if any(str(r['gold_answer'])!=str(e['gold_answer']) for r,e in zip(outcomes,expected)):
            raise ValueError('Terminal development reference answers changed')
        return {name:summarize(outcomes)}

    def reconcile_calls(self):
        running=[];blocked=[]
        for job in self.jobs:
            folder=job['folder_path'];launch_path=folder/'launch.json';terminal_path=folder/'study_terminal.json'
            ledger=read(self.state/'budget.json')
            entry=next((j for j in ledger['jobs'] if j['run_id']==job['run_id'] and j.get('service','modal')=='modal'),None)
            if not launch_path.exists():
                if entry and entry.get('call_id'):
                    write(launch_path,{'run_id':job['run_id'],'call_id':entry['call_id'],'app_id':entry.get('app_id'),'status':'recovered_from_ledger'})
                elif entry and entry.get('status') not in ('reserved',):
                    blocked.append({'run_id':job['run_id'],'reason':'ambiguous_ledger_dispatch'});continue
                elif (folder/'result.json').exists():
                    blocked.append({'run_id':job['run_id'],'reason':'orphaned_result_without_call_identity'});continue
                else:continue
            try:launch=read(launch_path)
            except (ValueError,UnicodeError):launch={}
            call_id=launch.get('call_id')
            if not call_id:
                blocked.append({'run_id':job['run_id'],'reason':'ambiguous_launch'})
                if entry and entry.get('status')=='reserved':
                    def uncertain(ledger):
                        owned=next(j for j in ledger['jobs'] if j['run_id']==job['run_id'])
                        owned.update(status='spawning',dispatch_ambiguity=True)
                    self.edit_budget(uncertain)
                continue
            receipt_path=folder/'study_launch.private.json'
            app_id=launch.get('app_id') or (read(receipt_path).get('app_id') if receipt_path.exists() else None)
            if entry and (not entry.get('call_id') or app_id and not entry.get('app_id') or entry.get('dispatch_ambiguity')):
                def bind(ledger):
                    owned=next(j for j in ledger['jobs'] if j['run_id']==job['run_id'])
                    if owned.get('call_id') not in (None,call_id):raise ValueError('Ledger and launch call identities differ')
                    owned['call_id']=call_id
                    if owned.get('status') in ('reserved','spawning'):owned['status']='spawned'
                    owned['dispatch_ambiguity']=False
                    if app_id:owned['app_id']=app_id
                self.edit_budget(bind)
            if terminal_path.exists():
                terminal=read(terminal_path)
                if terminal.get('call_id')!=call_id:raise ValueError('Terminal receipt call identity changed')
                if terminal.get('result_sha256') and sha(folder/'result.json')!=terminal['result_sha256']:
                    raise ValueError('Saved terminal result changed')
                if terminal['kind']!='completed':blocked.append({'run_id':job['run_id'],'reason':'failed_owned_call'})
                continue
            status=self.backend.poll(folder,call_id)
            if status['kind']=='running':
                write(folder/'remote_status.json',status['remote_status']);running.append(job['run_id']);continue
            if status['kind']=='monitoring_error':blocked.append({'run_id':job['run_id'],'reason':'monitoring_error'});continue
            terminal={'call_id':call_id,'kind':status['kind'],'at_utc':now()};runtime=None
            if status['kind']=='completed':
                result=status['result'];write(folder/'result.json',result);runtime=result.get('elapsed_seconds') if isinstance(result,dict) else None
                terminal['result_sha256']=sha(folder/'result.json')
                try:write(folder/'metrics.json',self.validate_result(job,result))
                except (ValueError,KeyError,TypeError):terminal['kind']='failed';terminal['reason']='invalid_terminal_result'
            else:terminal['error_type']=status.get('error_type')
            # Receipt precedes ledger transition; a later tick can reconcile it idempotently.
            write(terminal_path,terminal)
            self.terminal(job,terminal['kind'],runtime=runtime,call_id=call_id,app_id=app_id)
            self.journal('completed' if terminal['kind']=='completed' else 'failed',
                f"Study {job['selector']} seed {job['seed']} {terminal['kind']}",
                f"Saved immutable {job['token_budget']}-token development artifacts. Exact selector identity is {job['selector']}; final test remains sealed.",job['run_id']+'-study-terminal')
            if terminal['kind']!='completed':blocked.append({'run_id':job['run_id'],'reason':'failed_owned_call'})
        # Repair a receipt-written/ledger-write interruption without polling/retraining.
        ledger=read(self.state/'budget.json')
        for job in self.jobs:
            path=job['folder_path']/'study_terminal.json'
            if not path.exists():continue
            receipt=read(path);entry=next((j for j in ledger['jobs'] if j['run_id']==job['run_id']),None)
            if entry and entry.get('status')!=receipt['kind']:
                result=read(job['folder_path']/'result.json') if receipt.get('result_sha256') else {}
                self.terminal(job,receipt['kind'],runtime=result.get('elapsed_seconds'),call_id=receipt['call_id'])
                self.journal('completed' if receipt['kind']=='completed' else 'failed',
                    f"Study {job['selector']} seed {job['seed']} {receipt['kind']}",
                    'Reconciled a durable terminal receipt after an interrupted ledger write; no compute was repeated.',job['run_id']+'-study-terminal')
        return running,blocked

    def allocate(self,jobs,protect):
        def change(ledger):
            require_fresh_modal_budget(ledger,new_reservation=True)
            if not 0<ledger['limits']['modal']<=30:raise ValueError('Modal ceiling exceeds the existing authorization')
            existing={j['run_id']:j for j in ledger['jobs']}
            missing=[job for job in jobs if job['run_id'] not in existing]
            amount=3*len(missing)
            free=ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']
            if free<amount+protect:raise FundingWait('Whole phase plus protected funds is not available')
            for job in jobs:
                old=existing.get(job['run_id'])
                if old and (old.get('service','modal')!='modal' or old.get('reserved_usd',0)<3 or old.get('status') not in ACTIVE):
                    raise ValueError('Existing phase reservation is not an unused/funded job')
            for job in missing:
                ledger['jobs'].append({'run_id':job['run_id'],'service':'modal','reserved_usd':3,
                    'status':'reserved','created_at_utc':now(),'study_grid_sha256':sha(self.grid/'grid_manifest.json')})
            ledger['reserved']['modal']+=amount
        self.edit_budget(change)

    def tick(self,*,advance=False):
        if not (self.grid/'grid_manifest.json').exists():return {'stage':'awaiting_prepared_grid','paid_work_launched':False}
        self.jobs=[];self.plan_issues=[];self.dispatch_attempted=False;self.load()
        if not advance:
            return {'stage':'inspect','jobs':len(self.jobs),'saved_launches':sum((j['folder_path']/'launch.json').exists() for j in self.jobs),
                'root_review_present':self.review_path.exists(),'paid_work_launched':False}
        self.state.mkdir(parents=True,exist_ok=True)
        try:
            with exclusive(self.state/'study_tick.lock'):
                return self._advance()
        except FileExistsError:return {'stage':'waiting_for_tick_or_budget_lock','paid_work_launched':None if self.dispatch_attempted else False}

    def _advance(self):
        running,blocked=self.reconcile_calls()
        if self.state.joinpath('budget_reconcile.lock').exists():return {'stage':'waiting_for_budget_lock','paid_work_launched':False}
        try:self.backend.refresh(self.state)
        except Exception as error:return {'stage':'budget_refresh_blocked','error_type':type(error).__name__,'paid_work_launched':False}
        if blocked:return {'stage':'action_required','issues':blocked,'paid_work_launched':False}
        if running:return {'stage':'owned_call_running','run_ids':running,'paid_work_launched':False}
        if self.plan_issues:return {'stage':'action_required_changed_plan','run_ids':self.plan_issues,'paid_work_launched':False}
        try:
            self.verifier(self.grid);review=self.review()
        except (ValueError,FileNotFoundError,KeyError):return {'stage':'awaiting_valid_root_review_or_immutable_sources','paid_work_launched':False}
        approved=[j for j in self.jobs if j['token_budget'] in review['approved_token_budgets']]
        pending=[j for j in approved if not (j['folder_path']/'study_terminal.json').exists()]
        if not pending:return {'stage':'approved_grid_completed','paid_work_launched':False}
        next_job=pending[0];folder=next_job['folder_path']
        if (folder/'study_launch_blocked.json').exists():return {'stage':'action_required_launch_preflight','run_id':next_job['run_id'],'paid_work_launched':False}
        if (self.state/'gpu_launch.lock').exists():return {'stage':'waiting_for_gpu_launch_lock','paid_work_launched':False}
        try:apps=self.backend.apps()
        except Exception as error:return {'stage':'app_monitoring_blocked','error_type':type(error).__name__,'paid_work_launched':False}
        if any(int(app.get('tasks',0))>0 for app in apps):return {'stage':'waiting_for_outside_modal_task','paid_work_launched':False}
        phase=[next_job] if next_job['token_budget']==32768 else [j for j in pending
            if j['token_budget']==next_job['token_budget'] and j['seed']==next_job['seed']]
        try:self.allocate(phase,review['protected_modal_usd'])
        except FundingWait:return {'stage':'waiting_for_protected_phase_funding','paid_work_launched':False}
        except (RuntimeError,ValueError):return {'stage':'phase_allocation_blocked','paid_work_launched':False}
        if (folder/'launch.json').exists():return {'stage':'action_required_ambiguous_launch','paid_work_launched':False}
        try:
            self.verifier(self.grid);latest_review=self.review()
            if next_job['token_budget'] not in latest_review['approved_token_budgets'] or read(folder/'plan.json')!=next_job['plan']:
                raise ValueError('Source, review or frozen plan changed before dispatch')
        except (ValueError,FileNotFoundError,KeyError):
            return {'stage':'action_required_changed_before_dispatch','paid_work_launched':False}
        # Never acquire gpu_launch.lock here: the unchanged launch entrypoint owns it.
        self.dispatch_attempted=True
        try:receipt=self.backend.launch(folder)
        except Exception as error:
            receipt={'return_code':None,'app_id':None,'error_type':type(error).__name__}
        try:launch=read(folder/'launch.json') if (folder/'launch.json').exists() else {}
        except (ValueError,UnicodeError):launch={}
        if not (folder/'study_launch.private.json').exists():write(folder/'study_launch.private.json',receipt)
        if not launch.get('call_id'):
            ambiguous=(folder/'launch.json').exists()
            write(folder/'study_launch_blocked.json',dict(receipt,reason='ambiguous_dispatch' if ambiguous else 'pre_dispatch_failure'))
            if ambiguous:
                def uncertain(ledger):
                    owned=next(j for j in ledger['jobs'] if j['run_id']==next_job['run_id'])
                    owned.update(status='spawning',dispatch_ambiguity=True)
                    if receipt.get('app_id'):owned['app_id']=receipt['app_id']
                self.edit_budget(uncertain)
            return {'stage':'action_required_ambiguous_launch' if ambiguous else 'action_required_launch_preflight',
                'run_id':next_job['run_id'],'paid_work_launched':None if ambiguous else False}
        def spawned(ledger):
            entry=next(j for j in ledger['jobs'] if j['run_id']==next_job['run_id'])
            entry.update(status='spawned',call_id=launch['call_id'],hard_cpu_cores=4,hard_memory_gib=32,timeout_seconds=1800)
            if receipt.get('app_id'):entry['app_id']=receipt['app_id']
        self.edit_budget(spawned)
        self.journal('in_progress',f"Study {next_job['selector']} seed {next_job['seed']} launched",
            f"One separately funded {next_job['token_budget']}-token arm launched from its reviewed frozen plan; protected funds retained. No test, teacher or serving work was launched.",next_job['run_id']+'-study-launched')
        return {'stage':'spawned','run_id':next_job['run_id'],'call_id':launch['call_id'],'app_id':receipt.get('app_id'),'paid_work_launched':True}


class FundingWait(RuntimeError):pass


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['tick'],nargs='?',default='tick')
    parser.add_argument('--grid',type=Path,required=True);parser.add_argument('--review',type=Path);parser.add_argument('--advance',action='store_true')
    args=parser.parse_args()
    print(json.dumps(StudyRunner(args.grid,review=args.review).tick(advance=args.advance)))
