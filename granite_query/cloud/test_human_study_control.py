import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import human_study_control as human

class BackendTokenizer:
    def to_str(self):return 'offline-fixture-tokenizer'

class Tokenizer:
    eos_token='<eos>'
    chat_template='offline fixture'
    backend_tokenizer=BackendTokenizer()
    def apply_chat_template(self,messages,**kwargs):return '<user> '+messages[0]['content']+' </user> <assistant>'
    def __call__(self,text,**kwargs):return {'input_ids':list(range(len(text.split())))}

def baseline_result(runner,job):
    data=human.read(job['folder_path']/'input.json')
    rows=[{'id':r['id'],'gold_answer':r['gold_answer'],'response':'Calculation.\n#### 13',
           'truncated':False,'generated_tokens':4,'elapsed_seconds':.1} for r in data['development']]
    return {'stage':'completed','run_id':job['run_id'],'plan':job['plan'],
        'supervised_tokens':job['token_budget'],'optimizer_updates':job['token_budget']//1024,
        'evaluations':{job['selector']:rows},'held_out_test_used':False,'elapsed_seconds':100}

class Backend:
    def __init__(self):self.refreshes=0;self.launches=0;self.polls=0;self.complete=False;self.runner=None
    def refresh(self,state):self.refreshes+=1
    def apps(self):return []
    def launch(self,folder):
        self.launches+=1
        human.write(folder/'launch.json',{'run_id':folder.name,'call_id':'fc-human-fixture-'+str(self.launches)})
        return {'return_code':0,'app_id':'ap-human-fixture'}
    def poll(self,folder,call_id):
        self.polls+=1
        if not self.complete:return {'kind':'running','remote_status':{'stage':'fixture'}}
        job=next(j for j in self.runner.jobs if j['folder_path']==folder)
        return {'kind':'completed','result':baseline_result(self.runner,job)}

class HumanStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent=human.ROOT/'runs/test_human_study_control';parent.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=parent);cls.root=Path(cls.temp.name).resolve()
        assert cls.root.is_relative_to((human.ROOT/'runs').resolve())
        cls.pool=cls.root/'pool';cls.pool.mkdir();rows=[]
        for i in range(1930):
            count=115 if i<53 else 116
            rows.append({'id':f'human:{i:04}','prompt':f'Question example {i}',
                'response':' '.join(['step']*(count-2))+'\n#### 13','gold_answer':'13','source_split':'train',
                'teacher_model':'deepseek-fixture','teacher_revision':'fixture',
                'generation':{'prompt_version':'fixture','settings':{}},
                'reference_type':'human_dataset_answer_with_exact_annotation_checks',
                'reference_annotations_verified':True,'reference_match_is_independent_gold':True})
        (cls.pool/'eligible.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        human.write(cls.pool/'teacher_summary.json',{'stage':'completed','requested':2048,'completed':2048,
            'eligible':1930,'official_test_accessed':False})
        cls.dev=cls.root/'development.jsonl'
        cls.dev.write_text(''.join(json.dumps({'id':f'dev:{i:03}','prompt':f'Unique development case {i}',
            'gold_answer':'13','source_split':'train'})+'\n' for i in range(200)),encoding='utf-8')
        cls.weak=cls.root/'weakness.json'
        human.write(cls.weak,{'provenance':{'source_kind':'training_probe_predictions','source_split':'train',
            'official_test_used':False,'question_ids':['old-probe'],'question_hashes':[]},
            'skills':{'arithmetic':{'smoothed_error_rate':.5}}})
        cls.template=cls.root/'template'
        human.prepare(cls.template,pool=cls.pool,development=cls.dev,weakness=cls.weak,tokenizer=Tokenizer())

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.grid=self.root/('study-'+self._testMethodName)
        shutil.copytree(self.template,self.grid)
        self.state=self.grid/'state';self.state.mkdir()
        self.backend=Backend()
        self.runner=human.HumanRunner(self.grid,state_dir=self.state,backend=self.backend,
            watch_state=self.grid/'watch_state.json',journal=lambda *args:None)
        self.backend.runner=self.runner
        self.ledger={'limits':{'modal':30,'deepseek':20},'estimated_spend':{'modal':1,'deepseek':0},
            'reserved':{'modal':0,'deepseek':0},'jobs':[],
            'modal_observation':{'queried_at_utc':datetime.now(timezone.utc).isoformat()},
            'modal_budget_accounting':{'new_paid_launches_allowed':True,'issues':[],'collection_lag_minutes':15}}
        human.write(self.state/'budget.json',self.ledger)

    def approve(self,phase):
        self.runner.load()
        review={'reviewed':True,'phase':phase,'study_manifest_sha256':human.sha(self.grid/'study_manifest.json'),
            'controller_sha256':human.sha(Path(human.__file__)),'protected_modal_usd':5,
            'approved_run_ids':[j['run_id'] for j in self.runner.jobs if (j['selector']=='baseline')==(phase=='baseline')]}
        if phase=='pair':review['calibration_sha256']=human.sha(self.grid/'calibration.json')
        human.write(self.grid/('review_'+phase+'.json'),review)

    def complete_baseline(self):
        self.approve('baseline');self.assertEqual(self.runner.tick(advance=True)['stage'],'human_call_spawned')
        self.backend.complete=True;self.runner.poll_only();self.runner.calibrate()

    def test_unpaid_inspect_and_current_watcher_block(self):
        original=(self.state/'budget.json').read_bytes()
        self.assertEqual(self.runner.tick()['stage'],'inspect')
        (self.state/'study_watch.lock').write_text('owned by current watcher')
        self.assertEqual(self.runner.tick(advance=True)['stage'],'current_watcher_blocks_advance')
        self.assertEqual(self.backend.refreshes,0);self.assertEqual(self.backend.launches,0)
        self.assertEqual((self.state/'budget.json').read_bytes(),original)

    def test_exact_pool_holdout_and_recipe(self):
        self.assertEqual(human.verify(self.grid)['development'],200)
        self.runner.load()
        for job in self.runner.jobs[1:]:
            data=human.read(job['folder_path']/'input.json');arm=data['arm']
            self.assertEqual(arm['token_budget'],65536);self.assertEqual(arm['optimizer_updates'],64)
            self.assertFalse({r['id'] for r in arm['training']}&set(job['plan']['development_ids']))
            self.assertEqual(job['plan']['application_training_guard_seconds'],1400)
            self.assertEqual(job['plan']['application_evaluation_guard_seconds'],1600)
        path=self.runner.jobs[1]['folder_path']/'input.json';path.write_text('{}')
        with self.assertRaises(ValueError):human.verify(self.grid)

    def test_unique_claim_and_no_duplicate_provider_launch(self):
        self.approve('baseline')
        self.assertEqual(self.runner.tick(advance=True)['stage'],'human_call_spawned')
        self.assertEqual(self.runner.tick(advance=True)['stage'],'owned_human_call_running')
        self.assertEqual(self.backend.launches,1)
        self.assertTrue((self.runner.jobs[0]['folder_path']/'human_claim.json').exists())

    def test_pinned_image_and_verification_sources_required(self):
        path=self.grid/'study_manifest.json';manifest=human.read(path)
        self.assertIn('modal_train.py',manifest['code_sha256'])
        self.assertIn('../ranking/verification.py',manifest['code_sha256'])
        manifest['code_sha256'].pop('modal_train.py');human.write(path,manifest)
        with self.assertRaises(ValueError):human.verify(self.grid)

    def test_pair_requires_calibration_and_whole_phase_plus_protected5(self):
        self.approve('baseline');self.runner.load()
        human.write(self.grid/'review_pair.json',{'reviewed':True})
        with self.assertRaises((ValueError,FileNotFoundError)):self.runner.review_for('pair')
        self.complete_baseline();self.approve('pair')
        ledger=human.read(self.state/'budget.json');ledger['estimated_spend']['modal']=20;ledger['reserved']['modal']=0
        human.write(self.state/'budget.json',ledger)
        self.assertEqual(self.runner.tick(advance=True)['stage'],'whole_phase_plus_protected5_funding_required')
        self.assertEqual(self.backend.launches,1)
        ledger['estimated_spend']['modal']=18;human.write(self.state/'budget.json',ledger)
        self.backend.complete=False
        self.assertEqual(self.runner.tick(advance=True)['stage'],'human_call_spawned')
        saved=human.read(self.state/'budget.json')
        self.assertEqual(len([j for j in saved['jobs'] if j['status'] in ('reserved','spawned')]),2)
        self.assertEqual(saved['reserved']['modal'],6)

    def test_stale_observation_refuses_new_reservation(self):
        self.approve('baseline');self.ledger['modal_observation']['queried_at_utc']='2000-01-01T00:00:00+00:00'
        human.write(self.state/'budget.json',self.ledger)
        self.assertEqual(self.runner.tick(advance=True)['stage'],'fresh_phase_funding_contract_required')
        self.assertEqual(self.backend.launches,0);self.assertEqual(human.read(self.state/'budget.json')['jobs'],[])

    def test_recover_from_owned_ledger_and_reject_wrong_output(self):
        self.approve('baseline');self.runner.tick(advance=True);job=self.runner.jobs[0]
        (job['folder_path']/'launch.json').unlink()
        result=self.runner.recover();self.assertEqual(result['recovered'],[job['run_id']])
        bad=baseline_result(self.runner,job);bad['evaluations']['baseline'][0]['gold_answer']='wrong'
        with self.assertRaises(ValueError):self.runner.validate_result(job,bad)

if __name__=='__main__':unittest.main()
