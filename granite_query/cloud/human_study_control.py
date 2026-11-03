"""Independent human-reference study. Default prepares locally; paid advance is explicit.

The existing three-selector watcher and every pinned source remain unchanged.
No imports, preparation, inspection or verification call providers or reserve funds.
"""
from datetime import datetime,timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from cloud import student_valuation as skill
from cloud.valuation_contract import validate_arm
from cloud.comparison_control import require_fresh_modal_budget
from cloud.comparison_metrics import summarize
from cloud.study_runner import StudyRunner,Backend,exclusive

VERSION='human-reference64k-dev200-v2'
DEFAULT=ROOT/'runs/human_study64k_dev200_seed42_v2'
POOL=ROOT/'runs/human_math_teacher2048_v1'
DEV=ROOT/'runs/human_math_cohort2048_dev200_v1/development.jsonl'
WEAKNESS=ROOT/'runs/student_valuation_dev64_v1/weakness.json'
WATCH=ROOT/'runs/data_efficiency_math_v1/study_watch_state.json'
PINNED=('student_valuation.py','valuation_contract.py','modal_valuation.py','modal_train.py','study_runner.py',
        'comparison_control.py','budget_reconcile.py','comparison_metrics.py','../ranking/verification.py')
COMMON={'model':skill.MODEL,'revision':skill.REVISION,'seed':42,'tokens_per_update':1024,
    'learning_rate':2e-5,'lora_r':8,'lora_alpha':16,'context_limit':2048,
    'max_new_tokens':512,'enable_thinking':False,'do_sample':False,
    'evaluation_batch_size':8,'evaluation_kind':'development','gpu':'A100-80GB',
    'timeout_seconds':1800,'application_training_guard_seconds':1400,
    'application_evaluation_guard_seconds':1600,'hard_cpu_cores':4,'hard_memory_gib':32,
    'reserved_usd':3,'latency_measurement':'amortized batched GPU wall time; not single-request latency'}

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()

def write(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.human.'+str(os.getpid())+'.tmp')
    for attempt in range(4):
        try:
            tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');tmp.replace(path)
            return
        except PermissionError:
            if attempt==3:raise
            time.sleep(.05*(2**attempt))

def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as handle:json.dump(value,handle,indent=2,ensure_ascii=False)

def safe_folder(path):
    path=Path(path).resolve()
    if not path.is_relative_to((ROOT/'runs').resolve()):raise ValueError('Study artifacts must remain inside ignored cloud/runs')
    return path

def plan_for(run_id,data,dev,*,selector):
    arm=data.get('arm');budget=arm['token_budget'] if arm else 0
    protocol=dict(COMMON,mode='train_evaluate' if arm else 'evaluate_saved',
        arm=arm['arm'] if arm else 'baseline',checkpoint_name=selector,selector_name=selector,
        token_budget=budget,optimizer_updates=budget//1024,development_ids=[r['id'] for r in dev],
        input_sha256=digest_bytes(json.dumps(data,ensure_ascii=False,indent=2).encode()),
        fresh_base=True,data_repetition=False,official_test_used=False,
        experiment_version=VERSION)
    return dict(protocol,run_id=run_id,protocol_hash=digest(protocol))

def digest_bytes(value):return hashlib.sha256(value).hexdigest()

def arm_forecast(arm):
    rows=validate_arm(arm)
    return {'examples':len(rows),'response_windows':sum(len(u['microbatches']) for u in arm['updates']),
        'forwarded_input_tokens':sum(len(rows[w['id']]['input_ids']) for u in arm['updates'] for w in u['microbatches']),
        'supervised_tokens':arm['token_budget'],'updates':arm['optimizer_updates']}

def prepare(output=DEFAULT,*,pool=POOL,development=DEV,weakness=WEAKNESS,tokenizer=None):
    """The human study is fixed at1930 candidates,200 development rows and64k."""
    expected_pool,expected_dev,expected_tokens,token_budget=1930,200,223827,65536
    output=safe_folder(output);pool=safe_folder(pool)
    development=Path(development).resolve();weakness=Path(weakness).resolve()
    if output.exists():raise FileExistsError('Use a new independent immutable study directory')
    summary=read(pool/'teacher_summary.json')
    if (summary.get('stage')!='completed' or summary.get('completed')!=summary.get('requested')
            or summary.get('eligible')!=expected_pool or summary.get('official_test_accessed') is not False
            or any((pool/p).exists() for p in ('collector.lock','teacher.lock'))):
        raise ValueError('Human teacher pool is not finalized and isolated')
    raw=skill.read_jsonl(pool/'eligible.jsonl');dev=skill.read_jsonl(development);signal=read(weakness)
    if len(raw)!=expected_pool or len(dev)!=expected_dev or len({r['id'] for r in dev})!=expected_dev:
        raise ValueError('Pool/development counts or IDs differ')
    if any(r.get('source_split')!='train' for r in raw+dev):raise ValueError('Only training-split development and teaching data accepted')
    if any(r.get('reference_type')!='human_dataset_answer_with_exact_annotation_checks'
           or r.get('reference_annotations_verified') is not True
           or r.get('reference_match_is_independent_gold') is not True for r in raw):
        raise ValueError('Human source/reference qualification missing')
    if ({r['id'] for r in raw}&{r['id'] for r in dev}
            or {skill.normalized_question(r['prompt']) for r in raw}&{skill.normalized_question(r['prompt']) for r in dev}):
        raise ValueError('Teaching and development questions overlap')
    if set(signal.get('provenance',{}).get('question_ids',[]))&{r['id'] for r in dev}:
        raise ValueError('New development outcomes cannot define initial weakness signal')
    paths={'teacher_pool':pool/'eligible.jsonl','teacher_summary':pool/'teacher_summary.json',
           'development':development,'weakness':weakness}
    source_hashes={name:sha(path) for name,path in paths.items()}
    output.mkdir(parents=True)
    (output/'development.jsonl').write_bytes(development.read_bytes())
    tokenizer=tokenizer or skill.load_tokenizer(local_files_only=True)
    skill.prepare(pool/'eligible.jsonl',weakness,output/'prepared_pool',exclude_paths=(development,),tokenizer=tokenizer)
    prepared=skill.read_jsonl(output/'prepared_pool/eligible.jsonl')
    if len(prepared)!=expected_pool or sum(r['response_tokens'] for r in prepared)!=expected_tokens:
        raise ValueError('Re-encoding changed human pool count/capacity; preserve partial artifacts and investigate')
    selection=skill.select(output/'prepared_pool',output/'selection',token_budget,seed=42,tokens_per_update=1024)
    jobs=[]
    public_dev=[{k:r[k] for k in ('id','prompt','gold_answer')} for r in dev]
    for selector,slot in (('baseline',None),('random','random'),('skill','valued')):
        data={'development':public_dev}
        if slot:data['arm']=read(output/'selection'/(slot+'_input.json'))
        run_id=output.name+'_seed42_'+selector;folder=output/'arms'/run_id;folder.mkdir(parents=True)
        plan=plan_for(run_id,data,public_dev,selector=selector)
        write_new(folder/'plan.json',plan)
        (folder/'input.json').write_bytes(json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'))
        jobs.append({'run_id':run_id,'selector':selector,'seed':42,'token_budget':plan['token_budget'],
            'folder':folder.relative_to(output).as_posix(),'protocol_hash':plan['protocol_hash'],
            'input_sha256':plan['input_sha256'],'required_reservation_usd':3,
            'forecast':arm_forecast(data['arm']) if slot else {'evaluation_only':True}})
    if any(sha(path)!=source_hashes[name] for name,path in paths.items()):raise ValueError('Input changed during human preparation')
    artifacts={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    manifest={'schema_version':1,'version':VERSION,'stage':'prepared_unpaid','paid_work_launched':False,
        'created_at_utc':now(),'expected_pool':expected_pool,'expected_dev':expected_dev,'available_tokens':expected_tokens,
        'token_budget':token_budget,'seed':42,'selectors':['random','skill'],'official_test_accessed':False,
        'protected_modal_usd':5,'source_paths':{k:str(v) for k,v in paths.items()},'sources':source_hashes,
        'controller_sha256':sha(Path(__file__)),'code_sha256':{name:sha(ROOT/name) for name in PINNED},
        'jobs':jobs,'artifacts_sha256':artifacts,
        'calibration_contract':{'required_before_pair_approval':True,'forecast_limit_seconds':1250,
            'completion_planning_guard_seconds':1550,'actual_worker_training_guard_seconds':1400,
            'actual_worker_evaluation_guard_seconds':1600,'hard_timeout_seconds':1800,
            'formula':'80 + 1.25 * measured_baseline200_generation_seconds + 0.0032 * exact_forwarded_input_tokens'},
        'limitations':['Seed42 exploratory source/curriculum transfer, not robust causal attribution.',
            'New200 is development, not final test; currentLR/r8 and output protocol remain fixed.',
            'No new gradient, teacher, final-test or serving work is included.',
            'Existing worker has1400/1600 checks;1550 is a planning target, not a new runtime guard.']}
    write_new(output/'study_manifest.json',manifest)
    return verify(output)

def verify(output):
    output=safe_folder(output);m=read(output/'study_manifest.json')
    if m.get('version')!=VERSION or m.get('paid_work_launched') is not False or m.get('official_test_accessed') is not False:
        raise ValueError('Unknown or unsafe human-study manifest')
    if (m.get('expected_pool')!=1930 or m.get('expected_dev')!=200 or m.get('available_tokens')!=223827
            or m.get('token_budget')!=65536 or m.get('seed')!=42 or m.get('protected_modal_usd')!=5
            or m.get('selectors')!=['random','skill']):raise ValueError('Human study identity or fixed capacity differs')
    if m.get('controller_sha256')!=sha(Path(__file__)):raise ValueError('Human controller changed after freezing')
    if set(m['code_sha256'])!=set(PINNED):raise ValueError('Pinned execution source set differs')
    for name,expected in m['code_sha256'].items():
        if name not in PINNED or sha(ROOT/name)!=expected:raise ValueError('Pinned helper/worker source changed')
    for name,path in m['source_paths'].items():
        if sha(path)!=m['sources'][name]:raise ValueError('Human source changed')
    for relative,expected in m['artifacts_sha256'].items():
        path=(output/relative).resolve()
        if not path.is_relative_to(output) or sha(path)!=expected:raise ValueError('Prepared artifact changed or escaped study')
    dev=skill.read_jsonl(output/'development.jsonl');ids=[r['id'] for r in dev]
    if len(ids)!=m['expected_dev'] or len(set(ids))!=len(ids) or any(r.get('source_split')!='train' for r in dev):
        raise ValueError('Development identities/split differ')
    pool_rows=skill.read_jsonl(output/'prepared_pool/eligible.jsonl');pool={r['id']:r for r in pool_rows}
    if len(pool)!=m['expected_pool'] or sum(r['response_tokens'] for r in pool_rows)!=m['available_tokens']:
        raise ValueError('Prepared human capacity changed')
    if set(pool)&set(ids):raise ValueError('Pool and development IDs overlap')
    if len(m['jobs'])!=3 or {j['selector'] for j in m['jobs']}!={'baseline','random','skill'}:
        raise ValueError('Require one baseline and exactly one matched random/skill pair')
    seen=set()
    for job in m['jobs']:
        folder=(output/job['folder']).resolve()
        if not folder.is_relative_to(output) or job['run_id'] in seen:raise ValueError('Unsafe or duplicate human job')
        seen.add(job['run_id']);p=read(folder/'plan.json');data=read(folder/'input.json')
        if p!=plan_for(job['run_id'],data,dev,selector=job['selector']):raise ValueError('Frozen human plan differs from exact recipe')
        if p['protocol_hash']!=job['protocol_hash'] or sha(folder/'input.json')!=job['input_sha256']:
            raise ValueError('Input or protocol checksum differs')
        if data['development']!=[{k:r[k] for k in ('id','prompt','gold_answer')} for r in dev]:
            raise ValueError('Development payload/reference/order changed')
        if job['selector']=='baseline':
            if 'arm' in data or p['token_budget']!=0:raise ValueError('Baseline must be untouched')
        else:
            arm=data['arm'];training=validate_arm(arm)
            if (arm['token_budget']!=m['token_budget'] or arm['tokens_per_update']!=1024
                    or p['optimizer_updates']!=m['token_budget']//1024 or set(training)&set(ids)):
                raise ValueError('Exact human budget or holdout isolation failed')
            for key,row in training.items():
                source=pool.get(key)
                if source is None or row['input_ids']!=source['prefix_ids']+source['answer_ids']:
                    raise ValueError('Training row differs from pinned human pool')
                if any(row[k]!=source[k] for k in ('prompt','response','gold_answer','raw_response_sha256')):
                    raise ValueError('Teacher trace or reference changed')
            if arm_forecast(arm)!=job['forecast']:raise ValueError('Prepared compute forecast changed')
    return {'stage':'verified_prepared_unpaid','jobs':3,'pool':len(pool),'development':len(ids),
        'token_budget':m['token_budget'],'baseline_calibration_present':(output/'calibration.json').exists(),
        'paid_work_launched':False}

class HumanRunner(StudyRunner):
    def __init__(self,study=DEFAULT,*,review=None,state_dir=None,backend=None,watch_state=WATCH,journal=None):
        super().__init__(study,review=review,state_dir=state_dir,backend=backend,verifier=verify,journal=journal)
        self.explicit_review=Path(review).resolve() if review else None
        self.watch_state=Path(watch_state)

    def load(self):
        verify(self.grid);self.manifest=read(self.grid/'study_manifest.json');self.jobs=[]
        for job in self.manifest['jobs']:
            self.jobs.append(dict(job,folder_path=(self.grid/job['folder']).resolve(),plan=read(self.grid/job['folder']/'plan.json')))
        self.plan_issues=[]
        return self.manifest

    def watch_block(self):
        if (self.state/'study_watch.lock').exists():return True
        if self.watch_state.exists():return read(self.watch_state).get('stage')!='stopped'
        return False

    def validate_result(self,job,result):
        if (not isinstance(result,dict) or result.get('stage')!='completed' or result.get('plan')!=job['plan']
                or result.get('supervised_tokens')!=job['token_budget']
                or result.get('optimizer_updates')!=job['token_budget']//1024
                or set(result.get('evaluations',{}))!={job['selector']}
                or result.get('held_out_test_used') is not False):raise ValueError('Human output contract differs')
        if (not isinstance(result.get('elapsed_seconds'),(int,float))
                or not math.isfinite(result['elapsed_seconds']) or not 0<result['elapsed_seconds']<=1805):
            raise ValueError('Human result elapsed time is invalid')
        expected=read(job['folder_path']/'input.json')['development'];rows=result['evaluations'][job['selector']]
        if len(rows)!=self.manifest['expected_dev'] or [r['id'] for r in rows]!=[r['id'] for r in expected]:
            raise ValueError('Human output question IDs/count/order differ')
        for row,reference in zip(rows,expected):
            if str(row['gold_answer'])!=str(reference['gold_answer']):raise ValueError('Human output gold reference differs')
            if (not isinstance(row.get('response'),str) or type(row.get('truncated')) is not bool
                    or type(row.get('generated_tokens')) is not int or not 0<=row['generated_tokens']<=512
                    or not isinstance(row.get('elapsed_seconds'),(int,float))
                    or not math.isfinite(row['elapsed_seconds']) or row['elapsed_seconds']<0):
                raise ValueError('Human output timing/generation invalid')
        return {job['selector']:summarize(rows)}

    def review_for(self,phase):
        path=self.explicit_review or self.grid/('review_'+phase+'.json');value=read(path)
        expected=[j['run_id'] for j in self.jobs if (j['selector']=='baseline')==(phase=='baseline')]
        if (value.get('reviewed') is not True or value.get('phase')!=phase
                or value.get('study_manifest_sha256')!=sha(self.grid/'study_manifest.json')
                or value.get('controller_sha256')!=sha(Path(__file__))
                or value.get('protected_modal_usd')!=5 or value.get('approved_run_ids')!=expected):
            raise ValueError('Root approval must bind this exact independent phase and protected5')
        if phase=='pair':
            calibration=self.calibrate()
            if (value.get('calibration_sha256')!=sha(self.grid/'calibration.json')
                    or not calibration.get('pair_runtime_feasible')):raise ValueError('Pair needs reviewed baseline calibration')
        return value

    def calibrate(self):
        self.load();base=next(j for j in self.jobs if j['selector']=='baseline');folder=base['folder_path']
        if self.recover()['blocked']:raise ValueError('Baseline call identity remains ambiguous')
        terminal=read(folder/'study_terminal.json');result=read(folder/'result.json')
        launch=read(folder/'launch.json')
        if (terminal.get('kind')!='completed' or not terminal.get('call_id')
                or terminal['call_id']!=launch.get('call_id')
                or terminal.get('result_sha256')!=sha(folder/'result.json')):
            raise ValueError('Calibration requires a completed uniquely identified baseline call')
        metrics=self.validate_result(base,result)['baseline']
        evaluation_seconds=metrics['latency_seconds_total']
        forecasts={j['selector']:round(80+1.25*evaluation_seconds+0.0032*j['forecast']['forwarded_input_tokens'],3)
                   for j in self.jobs if j['selector']!='baseline'}
        value={'schema_version':1,'created_at_utc':now(),'study_manifest_sha256':sha(self.grid/'study_manifest.json'),
            'baseline_call_id':terminal['call_id'],'baseline_result_sha256':sha(folder/'result.json'),
            'baseline_elapsed_seconds':result['elapsed_seconds'],'baseline_generation_seconds':evaluation_seconds,
            'baseline_truncated':metrics['truncated'],'forecast_seconds':forecasts,
            'formula':self.manifest['calibration_contract']['formula'],
            'pair_runtime_feasible':result['elapsed_seconds']<1550 and max(forecasts.values())<=1250,
            'actual_worker_guards':{'training':1400,'evaluation':1600,'hard_timeout':1800}}
        target=self.grid/'calibration.json'
        if target.exists():
            old=read(target)
            if {k:v for k,v in old.items() if k!='created_at_utc'}!={k:v for k,v in value.items() if k!='created_at_utc'}:
                raise ValueError('Existing immutable calibration differs from baseline evidence')
            return old
        write_new(target,value)
        self.journal('completed','Human baseline200 calibrated',
            'Completed baseline development outputs and observed generation time were validated. Human pair remains separately reviewed and unfunded until protected phase funding is available.',
            self.grid.name+'-baseline-calibrated')
        return value

    def recover(self):
        """Only reconcile call identity from saved owned evidence; never resubmit."""
        self.load();ledger=read(self.state/'budget.json');recovered=[];blocked=[]
        owned=[j for j in ledger['jobs'] if j.get('human_study_manifest_sha256')==sha(self.grid/'study_manifest.json')]
        for field in ('run_id','call_id','human_claim_id'):
            values=[j[field] for j in owned if j.get(field)]
            if len(values)!=len(set(values)):raise ValueError('Duplicate owned human job/call/claim identity')
        for job in self.jobs:
            folder=job['folder_path'];matches=[j for j in ledger['jobs'] if j['run_id']==job['run_id']]
            if len(matches)>1:raise ValueError('Duplicate ledger job identity')
            entry=matches[0] if matches else None
            claim=folder/'human_claim.json';launch=folder/'launch.json'
            if not entry:
                if any((folder/p).exists() for p in ('launch.json','human_claim.json','result.json')):blocked.append(job['run_id'])
                continue
            if (entry.get('human_study_manifest_sha256')!=sha(self.grid/'study_manifest.json')
                    or entry.get('protocol_hash')!=job['protocol_hash']):raise ValueError('Foreign human reservation identity')
            if launch.exists() or entry.get('call_id'):
                if (not claim.exists() or read(claim).get('claim_id')!=entry.get('human_claim_id')
                        or read(claim).get('study_manifest_sha256')!=sha(self.grid/'study_manifest.json')
                        or read(claim).get('protocol_hash')!=job['protocol_hash']):
                    raise ValueError('Missing or foreign unique dispatch claim')
                if launch.exists() and entry.get('call_id') not in (None,read(launch).get('call_id')):
                    raise ValueError('Launch and owned ledger call identities differ')
            if not launch.exists() and entry.get('call_id'):
                if not claim.exists() or read(claim).get('claim_id')!=entry.get('human_claim_id'):
                    raise ValueError('Missing/mismatched unique dispatch claim')
                write(launch,{'run_id':job['run_id'],'call_id':entry['call_id'],'app_id':entry.get('app_id'),'status':'recovered_from_owned_ledger'})
                recovered.append(job['run_id'])
            elif claim.exists() and not launch.exists():blocked.append(job['run_id'])
        return {'stage':'ambiguous_dispatch_requires_review' if blocked else 'recovered_local_evidence',
            'recovered':recovered,'blocked':blocked,'paid_work_launched':False}

    def allocate_phase(self,jobs):
        def change(ledger):
            require_fresh_modal_budget(ledger,new_reservation=True)
            if not ledger.get('modal_budget_accounting') or not 0<ledger['limits']['modal']<=30:
                raise ValueError('Fresh supported Modal accounting and existing ceiling required')
            existing={j['run_id']:j for j in ledger['jobs']};missing=[j for j in jobs if j['run_id'] not in existing]
            free=ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']
            if free<3*len(missing)+5:raise HumanFundingWait('Whole human phase plus protected5 unavailable')
            for job in jobs:
                old=existing.get(job['run_id'])
                if old and (old.get('service','modal')!='modal' or old.get('status')!='reserved'
                        or old.get('reserved_usd')!=3 or old.get('human_study_manifest_sha256')!=sha(self.grid/'study_manifest.json')
                        or old.get('protocol_hash')!=job['protocol_hash']):raise ValueError('Existing phase reservation differs')
            for job in missing:
                ledger['jobs'].append({'run_id':job['run_id'],'service':'modal','status':'reserved','reserved_usd':3,
                    'created_at_utc':now(),'human_study_manifest_sha256':sha(self.grid/'study_manifest.json'),
                    'protocol_hash':job['protocol_hash']})
            ledger['reserved']['modal']+=3*len(missing)
        self.edit_budget(change)

    def tick(self,*,advance=False):
        if not (self.grid/'study_manifest.json').exists():return {'stage':'awaiting_prepared_human_study','paid_work_launched':False}
        self.load()
        if not advance:
            return {'stage':'inspect','jobs':3,'current_watcher_blocks_advance':self.watch_block(),
                'baseline_calibration_present':(self.grid/'calibration.json').exists(),
                'pair_approval_blocked':not (self.grid/'calibration.json').exists(),'paid_work_launched':False}
        if self.watch_block():return {'stage':'current_watcher_blocks_advance','paid_work_launched':False}
        self.state.mkdir(parents=True,exist_ok=True)
        try:
            with exclusive(self.state/'human_study_tick.lock'):
                recovery=self.recover()
                if recovery['blocked']:return recovery
                running,blocked=self.reconcile_calls()
                if blocked:return {'stage':'action_required_owned_call','issues':blocked,'paid_work_launched':False}
                if running:return {'stage':'owned_human_call_running','run_ids':running,'paid_work_launched':False}
                base=self.jobs[0]
                terminal=base['folder_path']/'study_terminal.json'
                baseline_done=terminal.exists() and read(terminal).get('kind')=='completed'
                phase='pair' if baseline_done else 'baseline'
                if phase=='pair' and not (self.grid/'calibration.json').exists():
                    return {'stage':'baseline_calibration_required_before_pair_approval','paid_work_launched':False}
                try:self.review_for(phase)
                except (ValueError,FileNotFoundError,KeyError):return {'stage':'root_'+phase+'_review_required','paid_work_launched':False}
                jobs=[j for j in self.jobs if (j['selector']=='baseline')==(phase=='baseline')]
                pending=[j for j in jobs if not (j['folder_path']/'study_terminal.json').exists()]
                if not pending:return {'stage':'human_phase_completed','paid_work_launched':False}
                try:self.backend.refresh(self.state)
                except Exception:return {'stage':'fresh_provider_observation_required','paid_work_launched':False}
                try:apps=self.backend.apps()
                except Exception:return {'stage':'app_monitoring_blocked','paid_work_launched':False}
                if self.watch_block():return {'stage':'current_watcher_blocks_advance','paid_work_launched':False}
                if any(int(a.get('tasks',0))>0 for a in apps):return {'stage':'outside_modal_task_blocks_advance','paid_work_launched':False}
                try:self.allocate_phase(pending)
                except HumanFundingWait:return {'stage':'whole_phase_plus_protected5_funding_required','paid_work_launched':False}
                except (RuntimeError,ValueError):return {'stage':'fresh_phase_funding_contract_required','paid_work_launched':False}
                job=pending[0];folder=job['folder_path'];self.load();self.review_for(phase)
                if self.watch_block():return {'stage':'current_watcher_blocks_advance','paid_work_launched':False}
                if (folder/'human_claim.json').exists() or (folder/'launch.json').exists():
                    return {'stage':'unique_dispatch_already_claimed','paid_work_launched':False}
                claim={'claim_id':uuid.uuid4().hex,'run_id':job['run_id'],'protocol_hash':job['protocol_hash'],
                    'study_manifest_sha256':sha(self.grid/'study_manifest.json'),'at_utc':now()}
                write_new(folder/'human_claim.json',claim)
                def bind(ledger):
                    require_fresh_modal_budget(ledger,new_reservation=True)
                    if self.watch_block():raise ValueError('Current watcher now blocks dispatch')
                    if ledger['limits']['modal']-ledger['estimated_spend']['modal']-ledger['reserved']['modal']<5:
                        raise HumanFundingWait('Protected5 must still remain immediately before dispatch')
                    entry=next(j for j in ledger['jobs'] if j['run_id']==job['run_id'])
                    if entry.get('status')!='reserved' or entry.get('human_claim_id'):raise ValueError('Dispatch claim already bound')
                    entry['human_claim_id']=claim['claim_id']
                self.edit_budget(bind)
                self.dispatch_attempted=True
                receipt=self.backend.launch(folder)
                launch=read(folder/'launch.json') if (folder/'launch.json').exists() else {}
                if not launch.get('call_id'):
                    write(folder/'human_launch_blocked.json',{'reason':'ambiguous_dispatch','receipt':receipt})
                    return {'stage':'ambiguous_dispatch_requires_review','paid_work_launched':None}
                def spawned(ledger):
                    entry=next(j for j in ledger['jobs'] if j['run_id']==job['run_id'])
                    entry.update(status='spawned',call_id=launch['call_id'],app_id=receipt.get('app_id'))
                self.edit_budget(spawned)
                self.journal('in_progress','Human-study '+job['selector']+' launched',
                    'One independently prepared human-reference development call was claimed and launched with protected5 retained. No existing grid, teacher or official-test job was launched.',
                    job['run_id']+'-human-launched')
                return {'stage':'human_call_spawned','run_id':job['run_id'],'call_id':launch['call_id'],'paid_work_launched':True}
        except FileExistsError:return {'stage':'human_tick_or_claim_locked','paid_work_launched':None if self.dispatch_attempted else False}

    def poll_only(self):
        self.load();recovery=self.recover()
        if recovery['blocked']:return recovery
        running,blocked=self.reconcile_calls()
        return {'stage':'human_calls_running' if running else 'human_calls_reconciled','running':running,'blocked':blocked,'paid_work_launched':False}

class HumanFundingWait(RuntimeError):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',choices=('prepare','verify','inspect','tick','poll','recover','calibrate'),default='prepare')
    parser.add_argument('--output',type=Path,default=DEFAULT)
    parser.add_argument('--review',type=Path)
    parser.add_argument('--advance',action='store_true')
    args=parser.parse_args()
    if args.advance and args.action!='tick':parser.error('--advance is only valid with tick')
    if args.action=='prepare':result=prepare(args.output)
    elif args.action=='verify':result=verify(args.output)
    else:
        runner=HumanRunner(args.output,review=args.review)
        result=(runner.tick(advance=args.advance) if args.action in ('inspect','tick') else
                runner.poll_only() if args.action=='poll' else runner.recover() if args.action=='recover' else runner.calibrate())
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
