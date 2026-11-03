"""Mock providers only; all budget files are disposable private fixtures."""
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import study_runner as runner


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n',encoding='utf-8')


def fixture(root,*,budgets=(32768,),free=27):
    grid=root/'grid';state=root/'state';state.mkdir();studies=[];folders=[]
    for budget in budgets:
        level=grid/f'tokens{budget}';jobs=[]
        for seed,selector in runner.ORDER:
            run_id=f'fixture_t{budget}_s{seed}_{selector}';folder=level/'arms'/run_id
            data={'development':[{'id':f'dev:{i}','gold_answer':'7','prompt':'Fixture only'} for i in range(64)]}
            payload=(json.dumps(data)+'\n').encode();folder.mkdir(parents=True)
            (folder/'input.json').write_bytes(payload)
            plan={'run_id':run_id,'seed':seed,'selector_name':selector,'checkpoint_name':selector,
                'token_budget':budget,'optimizer_updates':budget//1024,'input_sha256':__import__('hashlib').sha256(payload).hexdigest(),
                'protocol_hash':'fixture-protocol','development_ids':[r['id'] for r in data['development']]}
            write(folder/'plan.json',plan)
            jobs.append({'run_id':run_id,'seed':seed,'selector':selector,'folder':folder.relative_to(level).as_posix(),
                'protocol_hash':'fixture-protocol'})
            folders.append(folder)
        write(level/'manifest.json',{'token_budget':budget,'jobs':jobs})
        studies.append({'folder':level.name,'token_budget':budget,'manifest_sha256':runner.sha(level/'manifest.json')})
    write(grid/'grid_manifest.json',{'studies':studies})
    write(grid/'reviewed_for_launch.json',{'reviewed':True,'grid_manifest_sha256':runner.sha(grid/'grid_manifest.json'),
        'runner_sha256':runner.sha(Path(runner.__file__)),'approved_token_budgets':list(budgets),
        'approved_selectors':['random','skill','gradient'],'approved_seeds':[42,43],'protected_modal_usd':5})
    write(state/'budget.json',{'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':30-free,'deepseek':0},
        'reserved':{'modal':0,'deepseek':0},'jobs':[],
        'modal_observation':{'queried_at_utc':runner.now()},
        'modal_budget_accounting':{'issues':[],'new_paid_launches_allowed':True,'collection_lag_minutes':15}})
    return grid,state,folders


class FakeBackend:
    def __init__(self):self.calls=[];self.outcomes={};self.tasks=[];self.ambiguous=False;self.state=None
    def refresh(self,state):
        self.calls.append(('refresh',));self.state=state
        ledger=runner.read(state/'budget.json');ledger['modal_observation']['queried_at_utc']=runner.now();write(state/'budget.json',ledger)
    def apps(self):self.calls.append(('apps',));return self.tasks
    def launch(self,folder):
        self.calls.append(('launch',folder.name));call_id='fc-'+folder.name
        write(folder/'launch.json',{'status':'spawning'} if self.ambiguous else {'call_id':call_id,'status':'spawned'})
        return {'app_id':'ap-'+folder.name,'return_code':0}
    def poll(self,folder,call_id):
        self.calls.append(('poll',folder.name,call_id))
        kind=self.outcomes.get(folder.name,'running')
        if kind=='running':return {'kind':'running','remote_status':{'stage':'training'}}
        if kind=='failed':return {'kind':'failed','error_type':'UserCodeException'}
        plan=runner.read(folder/'plan.json');data=runner.read(folder/'input.json')
        outcomes=[dict(row,response='#### 0',generated_tokens=3,truncated=False,elapsed_seconds=.1) for row in data['development']]
        return {'kind':'completed','result':{'stage':'completed','plan':plan,'supervised_tokens':plan['token_budget'],
            'optimizer_updates':plan['token_budget']//1024,'held_out_test_used':False,
            'evaluations':{plan['selector_name']:outcomes},'elapsed_seconds':12.5}}


class StudyRunnerTests(unittest.TestCase):
    def temporary(self):
        parent=runner.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)
    def make(self,grid,state,backend,*,verifier=None):
        return runner.StudyRunner(grid,state_dir=state,backend=backend,verifier=verifier or (lambda _:None),journal=lambda *args:None)

    def test_default_inspect_is_read_only_and_bad_review_never_launches(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary));backend=FakeBackend();r=self.make(grid,state,backend)
            before=(state/'budget.json').read_bytes()
            self.assertEqual(r.tick()['stage'],'inspect');self.assertEqual(backend.calls,[])
            self.assertEqual((state/'budget.json').read_bytes(),before)
            review=runner.read(grid/'reviewed_for_launch.json');review['runner_sha256']='changed';write(grid/'reviewed_for_launch.json',review)
            self.assertEqual(r.tick(advance=True)['stage'],'awaiting_valid_root_review_or_immutable_sources')
            self.assertFalse(any(c[0]=='launch' for c in backend.calls));self.assertEqual(runner.read(state/'budget.json')['jobs'],[])

    def test_primary_order_polls_first_and_does_not_gate_on_accuracy(self):
        with self.temporary() as temporary:
            grid,state,folders=fixture(Path(temporary));backend=FakeBackend();r=self.make(grid,state,backend)
            first=r.tick(advance=True);self.assertEqual(first['run_id'],folders[0].name)
            self.assertEqual(r.tick(advance=True)['stage'],'owned_call_running')
            self.assertEqual(sum(c[0]=='launch' for c in backend.calls),1)
            backend.outcomes[folders[0].name]='completed'
            second=r.tick(advance=True)
            self.assertEqual(second['run_id'],folders[1].name)
            self.assertEqual(runner.read(folders[0]/'metrics.json')['random']['numeric_correct'],0)
            ledger=runner.read(state/'budget.json')
            self.assertEqual(ledger['estimated_spend']['modal'],3)
            self.assertEqual(ledger['jobs'][0]['status'],'completed');self.assertEqual(ledger['jobs'][0]['runtime_seconds'],12.5)
            self.assertEqual(ledger['jobs'][1]['status'],'spawned')

    def test_higher_budget_requires_whole_triple_and_protected_funds(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary),budgets=(65536,),free=13)
            backend=FakeBackend();r=self.make(grid,state,backend)
            self.assertEqual(r.tick(advance=True)['stage'],'waiting_for_protected_phase_funding')
            self.assertEqual(runner.read(state/'budget.json')['jobs'],[])
            ledger=runner.read(state/'budget.json');ledger['estimated_spend']['modal']=16;write(state/'budget.json',ledger)
            self.assertEqual(r.tick(advance=True)['stage'],'spawned')
            ledger=runner.read(state/'budget.json')
            self.assertEqual(len(ledger['jobs']),3);self.assertEqual(ledger['reserved']['modal'],9)
            self.assertEqual(sum(j['status']=='spawned' for j in ledger['jobs']),1)

    def test_ambiguous_launch_and_terminal_failure_never_retrain(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary));backend=FakeBackend();backend.ambiguous=True;r=self.make(grid,state,backend)
            self.assertEqual(r.tick(advance=True)['stage'],'action_required_ambiguous_launch')
            self.assertEqual(runner.read(state/'budget.json')['jobs'][0]['status'],'spawning')
            self.assertEqual(r.tick(advance=True)['stage'],'action_required')
            self.assertEqual(sum(c[0]=='launch' for c in backend.calls),1)
        with self.temporary() as temporary:
            grid,state,folders=fixture(Path(temporary));backend=FakeBackend();r=self.make(grid,state,backend)
            r.tick(advance=True);backend.outcomes[folders[0].name]='failed'
            self.assertEqual(r.tick(advance=True)['stage'],'action_required')
            self.assertEqual(r.tick(advance=True)['stage'],'action_required')
            self.assertEqual(sum(c[0]=='launch' for c in backend.calls),1)

    def test_outside_gpu_and_gpu_lock_are_waits_not_nested_lock_acquisitions(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary));backend=FakeBackend();r=self.make(grid,state,backend)
            backend.tasks=[{'tasks':'1'}]
            self.assertEqual(r.tick(advance=True)['stage'],'waiting_for_outside_modal_task')
            self.assertEqual(runner.read(state/'budget.json')['jobs'],[])
            backend.tasks=[];(state/'gpu_launch.lock').write_text('other-owner')
            self.assertEqual(r.tick(advance=True)['stage'],'waiting_for_gpu_launch_lock')
            self.assertEqual((state/'gpu_launch.lock').read_text(),'other-owner')
            (state/'gpu_launch.lock').unlink()
            self.assertEqual(r.tick(advance=True)['stage'],'spawned')

    def test_ledger_call_identity_recovers_without_a_duplicate_dispatch_and_source_change_blocks_next(self):
        with self.temporary() as temporary:
            grid,state,folders=fixture(Path(temporary));backend=FakeBackend();r=self.make(grid,state,backend)
            r.tick(advance=True);(folders[0]/'launch.json').unlink()
            self.assertEqual(r.tick(advance=True)['stage'],'owned_call_running')
            self.assertEqual(sum(c[0]=='launch' for c in backend.calls),1)
            backend.outcomes[folders[0].name]='completed'
            def changed(_):raise ValueError('Frozen source changed')
            r=self.make(grid,state,backend,verifier=changed)
            self.assertEqual(r.tick(advance=True)['stage'],'awaiting_valid_root_review_or_immutable_sources')
            self.assertTrue((folders[0]/'study_terminal.json').exists())
            self.assertEqual(runner.read(state/'budget.json')['jobs'][0]['status'],'completed')
            self.assertEqual(sum(c[0]=='launch' for c in backend.calls),1)

    def test_shared_budget_and_tick_locks_wait_without_provider_or_paid_work(self):
        with self.temporary() as temporary:
            grid,state,_=fixture(Path(temporary));backend=FakeBackend();r=self.make(grid,state,backend)
            (state/'study_tick.lock').write_text('other-owner')
            self.assertEqual(r.tick(advance=True)['stage'],'waiting_for_tick_or_budget_lock')
            self.assertEqual(backend.calls,[])
            (state/'study_tick.lock').unlink();(state/'budget_reconcile.lock').write_text('budget-owner')
            self.assertEqual(r.tick(advance=True)['stage'],'waiting_for_budget_lock')
            self.assertEqual((state/'budget_reconcile.lock').read_text(),'budget-owner')
            self.assertEqual(backend.calls,[])

    def test_terminal_receipt_repairs_interrupted_ledger_write_without_repoll_or_retraining(self):
        with self.temporary() as temporary:
            grid,state,folders=fixture(Path(temporary));backend=FakeBackend();r=self.make(grid,state,backend)
            r.tick(advance=True);backend.outcomes[folders[0].name]='completed'
            with patch.object(r,'terminal',side_effect=FileExistsError('Other budget writer')):
                self.assertEqual(r.tick(advance=True)['stage'],'waiting_for_tick_or_budget_lock')
            self.assertTrue((folders[0]/'study_terminal.json').exists())
            count=sum(c[0]=='poll' for c in backend.calls)
            result=self.make(grid,state,backend).tick(advance=True)
            self.assertEqual(result['run_id'],folders[1].name)
            self.assertEqual(sum(c[0]=='poll' for c in backend.calls),count)
            self.assertEqual(runner.read(state/'budget.json')['jobs'][0]['status'],'completed')


if __name__=='__main__':unittest.main()
