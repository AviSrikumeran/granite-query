import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import accomplishments


class AccomplishmentTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent / 'runs/test_accomplishments'
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name)
        self.runs = self.root / 'granite_query/cloud/runs'

    def tearDown(self):
        self.temporary.cleanup()

    def save(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding='utf-8')

    def arm(self,seed,arm,correct=55,ids=None):
        ids=ids or [f'dev:{i}' for i in range(64)]
        folder=f'granite_query/cloud/runs/student_valuation32768_seed{seed}_{arm}_v1/'
        self.save(folder+'plan.json',{'development_ids':ids})
        self.save(folder+'result.json',{'stage':'completed','supervised_tokens':32768,'optimizer_updates':32,
            'plan':{'development_ids':ids},'evaluations':{arm:[{'id':key,'response':'#### '+('1' if i<correct else '2'),
                'gold_answer':'1','truncated':False,'generated_tokens':2,'elapsed_seconds':.1} for i,key in enumerate(ids)]}})

    def test_plans_are_not_mistaken_for_launched_or_completed_work(self):
        self.save('granite_query/cloud/runs/matched_eval64_v1/plan.json', {'run_id': 'matched_eval64_v1'})
        self.save('granite_query/cloud/runs/granite_full120_v1/plan.json', {'train_ids': ['fixture']})
        public = accomplishments.build(self.root)
        self.assertFalse(public['accuracy_improved'])
        self.assertTrue(all(row['status'] == 'queued' for row in public['current_work']))
        self.assertFalse(any('64-question Granite benchmark fully recovered' == row['title'] for row in public['completed']))

    def test_partial_final_implementation_precedes_api_without_claiming_execution(self):
        self.save('progress/FINAL_SCALE_IMPLEMENTATION.json',
            {'stage':'partial_implementation_not_execution_ready'})
        api=self.root/'granite_query/cloud/modal_api.py'
        api.parent.mkdir(parents=True,exist_ok=True);api.write_text('# prepared fixture')
        public=accomplishments.build(self.root)
        rows=public['current_work'];titles=[row['title'] for row in rows]
        final=next(row for row in rows if row['title']=='Larger final benchmark implementation and funding review')
        self.assertEqual(final['status'],'queued')
        self.assertLess(titles.index(final['title']),titles.index('Capped Granite API trial'))
        self.assertIn('remain incomplete',final['detail'])
        self.assertIn('no new paid call',final['detail'])
        self.assertFalse(public['accuracy_improved'])

    def test_failed_original_and_running_resume_are_separate_and_redacted(self):
        self.save('granite_query/cloud/runs/matched_eval64_v1/remote_status.json', {
            'stage': 'failed', 'error_type': 'TimeoutError',
            'error': 'DO_NOT_EXPORT_PRIVATE_ERROR sk-abcdefghijklmnop', 'raw_response': 'PRIVATE_REASONING'})
        self.save('granite_query/cloud/runs/matched_eval64_resume1/plan.json', {'resume_from': 'matched_eval64_v1'})
        self.save('granite_query/cloud/runs/matched_eval64_resume1/launch.json', {
            'call_id': 'fc-fixture', 'DEEPSEEK_API_KEY': 'PRIVATE_KEY'})
        self.save('granite_query/cloud/runs/matched_eval64_resume1/remote_status.json', {
            'stage': 'ranked32_evaluation', 'local_path': 'C:\\Users\\private\\data'})
        public = accomplishments.build(self.root)
        phases = {row['title']: row['status'] for row in public['current_work']}
        self.assertEqual(phases['Original 64-question Granite attempt'], 'failed')
        self.assertEqual(phases['Resume of unfinished 64-question evaluations'], 'running')
        exported = (self.root / 'docs/project-status.json').read_text(encoding='utf-8')
        for secret in ('PRIVATE_KEY', 'PRIVATE_REASONING', 'DO_NOT_EXPORT', 'sk-abcdefghijklmnop', 'C:\\\\Users'):
            self.assertNotIn(secret, exported)
        self.assertTrue((self.root / 'progress/ACCOMPLISHMENTS.md').exists())

    def test_worker_completed_stage_without_results_is_not_completed(self):
        self.save('granite_query/cloud/runs/matched_eval64_v1/launch.json', {'call_id': 'fc-fixture'})
        self.save('granite_query/cloud/runs/matched_eval64_v1/remote_status.json', {'stage': 'completed'})
        public = accomplishments.build(self.root)
        self.assertEqual(public['current_work'][0]['status'], 'running')
        self.assertIn('recovering', public['current_work'][0]['detail'])

    def test_four_controlled_arms_report_actual_values_only_after_complete_results(self):
        for seed,random,skill in ((42,55,53),(43,57,56)):
            self.arm(seed,'random',random); self.arm(seed,'valued',skill)
        public=accomplishments.build(self.root)
        item=next(row for row in public['completed'] if row['title']=='First equal-token random versus skill experiment completed')
        self.assertIn('seed 42: random 55/64, skill and diversity 53/64',item['detail'])
        self.assertIn('seed 43: random 57/64, skill and diversity 56/64',item['detail'])
        self.assertIn('did not beat random in either seed',item['detail'])
        states={row['title']:row['status'] for row in public['current_work']}
        self.assertEqual(states['First student-aware equal-token experiment'],'completed')
        # Values must be recomputed from actual saved responses, not hardcoded.
        self.arm(42,'random',54)
        updated=accomplishments.build(self.root)
        item=next(row for row in updated['completed'] if row['title']=='First equal-token random versus skill experiment completed')
        self.assertIn('random 54/64',item['detail'])

    def test_result_filenames_and_mismatched_questions_do_not_complete_block(self):
        for seed in (42,43):
            for arm in ('random','valued'):
                folder=f'granite_query/cloud/runs/student_valuation32768_seed{seed}_{arm}_v1/'
                self.save(folder+'plan.json',{'run_id':'fixture'})
                self.save(folder+'result.json',{})
        public=accomplishments.build(self.root)
        self.assertFalse(any(row['title']=='First equal-token random versus skill experiment completed' for row in public['completed']))
        for seed in (42,43):
            for arm in ('random','valued'):
                self.arm(seed,arm)
        self.arm(43,'valued',ids=[f'other-dev:{i}' for i in range(64)])
        public=accomplishments.build(self.root)
        self.assertFalse(any(row['title']=='First equal-token random versus skill experiment completed' for row in public['completed']))

    def test_completed_math_teacher_pool_is_not_completed_granite_training(self):
        self.save('granite_query/cloud/runs/math_source_teacher1800_v1/teacher_summary.json',{
            'stage':'completed','requested':1800,'completed':1800,'eligible':1565,
            'supervised_tokens_available':150750,'eligible_by_source':{'ChilleD/SVAMP':571},
            'raw_responses':['PRIVATE_TEACHER_RESPONSE'],'account_secret':'PRIVATE_KEY'})
        self.save('granite_query/cloud/runs/math_source_cohort1800_v1/manifest.json',{'sources':[
            {'repo':'ChilleD/SVAMP','revision':'a'*40,'accepted_prompts':600,'reference_type':'human_dataset_answer'}]})
        public=accomplishments.build(self.root)
        item=next(row for row in public['completed'] if row['title']=='New multi-source DeepSeek teaching pool completed')
        self.assertIn('1,800/1,800',item['detail']); self.assertIn('1,565',item['detail'])
        self.assertIn('150,750',item['detail']); self.assertIn('not completed Granite training',item['detail'])
        source=next(row for row in public['dataset_coverage'] if row['name']=='ChilleD/SVAMP')
        self.assertEqual(source['status'],'teacher_pool_completed')
        self.assertIn('571',source['used_for'])
        exported=json.dumps(public)
        self.assertNotIn('PRIVATE_TEACHER_RESPONSE',exported); self.assertNotIn('PRIVATE_KEY',exported)

    def test_gradient_plan_launch_partial_and_complete_stages_are_distinct(self):
        folder='granite_query/cloud/runs/gradient_features_math_v1/'
        self.save(folder+'plan.json',{'protocol':{'candidate_ids':['a','b'],'target_ids':['c'],
            'config':{'checkpoint_updates':[4,8]}},'private_path':'C:\\Users\\PRIVATE'})
        self.save(folder+'reviewed_for_launch.json',{'reviewed':True})
        def phase():
            public=accomplishments.build(self.root)
            return next(row for row in public['current_work'] if row['title']=='Model-gradient data selection on the new math cohort'),public
        self.assertEqual(phase()[0]['status'],'queued')
        self.save(folder+'launch.json',{'status':'spawning'})
        self.assertEqual(phase()[0]['status'],'blocked')
        self.save(folder+'launch.json',{'call_id':'fc-fixture','api_key':'PRIVATE_KEY'})
        self.save(folder+'remote_status.json',{'stage':'collecting_candidate','completed_features':2,'raw_trace':'PRIVATE_TRACE'})
        self.assertEqual(phase()[0]['status'],'running')
        self.save(folder+'result.json',{'stage':'bounded_stop','projected_features_complete':False,'public_summary':{}})
        self.assertEqual(phase()[0]['status'],'stopped')
        self.save(folder+'result.json',{'stage':'completed','projected_features_complete':True,'public_summary':{
            'completed_features':6,'total_features':6,'candidates':2,'selection_development_targets':1},'raw':'PRIVATE_RESULT'})
        state,public=phase()
        self.assertEqual(state['status'],'completed')
        self.assertIn('not a measured Granite accuracy gain',state['detail'])
        exported=json.dumps(public)
        for value in ('PRIVATE_KEY','PRIVATE_TRACE','PRIVATE_RESULT','C:\\\\Users'):
            self.assertNotIn(value,exported)

    def test_grid_counts_actual_arms_and_names_next_work_before_api(self):
        prefix='granite_query/cloud/runs/data_efficiency_math_v1/'
        self.save(prefix+'grid_manifest.json',{'studies':[{'folder':'tokens1024','jobs':2}]})
        jobs=[{'folder':'arms/'+selector,'selector':selector,'checkpoint_name':selector,'seed':42} for selector in ('random','gradient')]
        self.save(prefix+'tokens1024/manifest.json',{'token_budget':1024,'jobs':jobs,'common_pool':{'sha256':'a'*64}})
        ids=[f'dev:{i}' for i in range(64)]
        for selector in ('random','gradient'):
            plan={'development_ids':ids,'checkpoint_name':selector,'selector_name':selector,'seed':42,'common_pool_sha256':'a'*64}
            self.save(prefix+'tokens1024/arms/'+selector+'/plan.json',plan)
            if selector=='random':
                self.save(prefix+'tokens1024/arms/'+selector+'/result.json',{'stage':'completed','supervised_tokens':1024,
                    'optimizer_updates':1,'plan':plan,'evaluations':{selector:[{'id':key,'response':'#### 1','gold_answer':'1',
                        'elapsed_seconds':.1,'generated_tokens':2,'truncated':False} for key in ids]}})
        source=self.root/'granite_query/cloud/modal_api.py';source.parent.mkdir(parents=True,exist_ok=True);source.touch()
        public=accomplishments.build(self.root)
        row=next(r for r in public['current_work'] if r['title']=='New math-cohort data-efficiency training grid')
        self.assertEqual(row['status'],'queued')
        self.assertIn('1 completed',row['detail']);self.assertIn('gradient, seed 42, 1,024',row['detail'])
        titles=[r['title'] for r in public['current_work']]
        self.assertLess(titles.index(row['title']),titles.index('Capped Granite API trial'))
        self.save(prefix+'tokens1024/arms/gradient/launch.json',{'call_id':'fc-fixture'})
        public=accomplishments.build(self.root)
        row=next(r for r in public['current_work'] if r['title']=='New math-cohort data-efficiency training grid')
        self.assertEqual(row['status'],'running');self.assertIn('Poll the existing call',row['detail'])

    def test_missing_grid_study_does_not_shrink_planned_count_into_completion(self):
        prefix='granite_query/cloud/runs/data_efficiency_math_v1/'
        self.save(prefix+'grid_manifest.json',{'studies':[{'folder':'missing-study','jobs':6}]})
        public=accomplishments.build(self.root)
        row=next(r for r in public['current_work'] if r['title']=='New math-cohort data-efficiency training grid')
        self.assertEqual(row['status'],'blocked');self.assertIn('0/6 arm plans',row['detail'])

    def test_watcher_snapshot_names_funding_wait_without_exporting_private_state(self):
        folder=self.root/'granite_query/cloud/runs/data_efficiency_math_v1'
        path='granite_query/cloud/runs/data_efficiency_math_v1/study_watch_state.json'
        value={'stage':'watching','updated_at_utc':'2026-11-03T20:50:00+00:00',
               'watcher_pid':999,'scope':{'secret':'PRIVATE_KEY'},
               'current':{'result':{'stage':'waiting_for_protected_phase_funding','error':'PRIVATE_TRACE'}}}
        self.save(path,value)
        detail=accomplishments._watch_snapshot_detail(folder)
        self.assertIn('waiting for billing reconciliation and protected phase funding',detail)
        self.assertIn('recorded snapshot',detail)
        self.assertNotIn('PRIVATE',detail);self.assertNotIn('999',detail)
        value.update(stage='stopped',stop_reason='PRIVATE_ACCOUNT_ERROR')
        self.save(path,value)
        detail=accomplishments._watch_snapshot_detail(folder)
        self.assertIn('stopped',detail);self.assertNotIn('PRIVATE',detail)
        value['updated_at_utc']='PRIVATE_TRACE'
        self.save(path,value)
        self.assertEqual(accomplishments._watch_snapshot_detail(folder),'')

    def test_human_gain_needs_complete_matched_baseline_comparison(self):
        report={'status':'partial','completed_jobs':2,'jobs':{
            'baseline':{'status':'completed','metrics':{'numeric_correct':180}},
            'random':{'status':'completed','metrics':{'numeric_correct':182}},
            'skill':{'status':'queued','metrics':None}},
            'runtime_and_review':{'calibration':{'status':'validated'},'pair_review':'reviewed'},
            'comparisons':{'random_vs_baseline':{'status':'unavailable'},'skill_vs_baseline':{'status':'unavailable'}}}
        with patch('cloud.human_study_report.build',return_value=report), patch('human_study_report.build',return_value=report):
            state,detail,gains=accomplishments._human_study_phase(self.runs,self.root)
            self.assertEqual(gains,[]);self.assertIn('182/200',detail);self.assertIn('skill: queued',detail)
            report['comparisons']['random_vs_baseline']['status']='completed'
            self.assertEqual(accomplishments._human_study_phase(self.runs,self.root)[2],[('random',182,180)])
            report['jobs']['random']['status']='running'
            self.assertEqual(accomplishments._human_study_phase(self.runs,self.root)[2],[])

    def test_unapproved_higher_budget_does_not_hide_the_next_project_stage(self):
        prefix='granite_query/cloud/runs/data_efficiency_math_v1/'
        self.save(prefix+'grid_manifest.json',{'studies':[{'folder':'one','jobs':1},{'folder':'two','jobs':1}]})
        self.save(prefix+'reviewed_for_launch.json',{'reviewed':True,'approved_token_budgets':[1024]})
        for study,budget,name in (('one',1024,'approved'),('two',2048,'deferred')):
            self.save(prefix+study+'/manifest.json',{'token_budget':budget,'jobs':[
                {'folder':'arms/'+name,'selector':'random','checkpoint_name':'random','seed':42}]})
            self.save(prefix+study+'/arms/'+name+'/plan.json',{})
        with patch.object(accomplishments,'_phase',side_effect=lambda path,*args:('completed' if path.name=='approved' else 'queued','',{})):
            state,detail=accomplishments._grid_phase(self.runs/'data_efficiency_math_v1')
        self.assertEqual(state,'deferred');self.assertIn('1 reviewed arms are complete',detail)
        self.assertIn('higher-budget plans are deferred',detail)
        self.assertIn('1 deferred reference plan',detail)
        self.assertNotIn('1 queued',detail)
        self.assertNotIn('The next prepared arm is',detail)

    def test_latest_same_protocol_feature_continuation_replaces_old_terminal_row(self):
        prefix='granite_query/cloud/runs/'
        protocol={'candidate_ids':['a','b'],'target_ids':['c'],'config':{'checkpoint_updates':[4,8]}}
        self.save(prefix+'gradient_features_math_v1/plan.json',{'protocol':protocol,'protocol_hash':'a'*64})
        self.save(prefix+'gradient_features_math_v1/result.json',{'stage':'calibration_refused'})
        self.save(prefix+'gradient_features_math_resume1/plan.json',{
            'protocol':protocol,'protocol_hash':'a'*64,'resume_from':'gradient_features_math_v1'})
        self.save(prefix+'gradient_features_math_resume1/launch.json',{'call_id':'fc-resume-fixture'})
        self.save(prefix+'gradient_features_math_resume1/remote_status.json',{'stage':'collecting_candidate','completed_features':3})
        value=accomplishments.build(self.root)
        row=next(r for r in value['current_work'] if r['title']=='Model-gradient data selection on the new math cohort')
        self.assertEqual(row['status'],'running');self.assertIn('Separate continuation',row['detail'])
        self.assertIn('3/6 features',row['detail'])
        self.save(prefix+'gradient_features_math_resume1/remote_status.json',{'stage':'restoring_saved_artifacts'})
        self.save(prefix+'gradient_features_math_resume1/recovery_decision.json',{
            'protocol_hash':'a'*64,'completed_features':3,'remaining_features':3})
        value=accomplishments.build(self.root)
        row=next(r for r in value['current_work'] if r['title']=='Model-gradient data selection on the new math cohort')
        self.assertIn('3 already verified features',row['detail'])
        self.assertIn('no new missing-feature completions',row['detail'])
        self.assertNotIn('0/6 features',row['detail'])

    def test_human_question_preparation_and_partial_teacher_are_not_granite_use(self):
        self.save('progress/HUMAN_MATH_COHORT.json',{'stage':'prepared_unpaid','actual_teaching_prompts':2048,
            'actual_development_holdout':200,'actual_valid_capacity':6053,
            'ancestry_exclusions':{'combined_unique_gsm_exclusions':994},'raw_reference':'PRIVATE_REFERENCE'})
        self.save('progress/HUMAN_MATH_TEACHER.json',{'stage':'awaiting_next_chunk','requested':2048,'completed':512,
            'eligible':490,'supervised_tokens_available':45000,'raw_response':'PRIVATE_RESPONSE'})
        public=accomplishments.build(self.root)
        prepared=next(row for row in public['completed'] if row['title']=='New human-reference teaching and development split frozen')
        self.assertIn('2,048',prepared['detail']);self.assertIn('200',prepared['detail'])
        self.assertIn('semantic correctness',prepared['detail']);self.assertIn('lineage is incomplete',prepared['detail'])
        teacher=next(row for row in public['current_work'] if row['title']=='Human-reference DeepSeek teaching chunks')
        self.assertEqual(teacher['status'],'queued');self.assertIn('512/2,048',teacher['detail'])
        self.assertIn('no later chunk',teacher['detail']);self.assertIn('not evidence that Granite used',teacher['detail'])
        self.assertFalse(any(row['title']=='Human-reference DeepSeek teaching pool completed' for row in public['completed']))
        self.assertFalse(public['accuracy_improved'])
        self.assertNotIn('PRIVATE',json.dumps(public))

    def test_human_collector_lock_pid_is_recorded_not_independently_assumed_alive(self):
        summary={'stage':'collecting','requested':2048,'completed':17,'eligible':15,'supervised_tokens_available':1000}
        self.save('progress/HUMAN_MATH_TEACHER.json',summary)
        def teacher():
            p=accomplishments.build(self.root)
            return next(row for row in p['current_work'] if row['title']=='Human-reference DeepSeek teaching chunks')
        self.assertEqual(teacher()['status'],'blocked')
        folder=self.runs/'human_math_teacher2048_v1';folder.mkdir(parents=True)
        (folder/'collector.lock').write_text('12345',encoding='ascii')
        item=teacher();self.assertEqual(item['status'],'running')
        self.assertIn('PID 12345',item['detail']);self.assertIn('verify that process',item['detail'])
        (folder/'collector.lock').write_text('PRIVATE_TOKEN',encoding='ascii')
        item=teacher();self.assertEqual(item['status'],'blocked')
        self.assertNotIn('PRIVATE_TOKEN',item['detail'])
        (folder/'collector.lock').unlink()
        self.save('progress/HUMAN_MATH_TEACHER.json',dict(summary,stage='completed',completed=512))
        self.assertEqual(teacher()['status'],'blocked')
        self.save('progress/HUMAN_MATH_TEACHER.json',dict(summary,stage='completed',completed=2048))
        self.assertEqual(teacher()['status'],'completed')


class NewGridGainTests(unittest.TestCase):
    """Synthetic private plans/results exercise the real grid and base validators."""
    tearDown=AccomplishmentTests.tearDown

    def setUp(self):
        AccomplishmentTests.setUp(self)
        import data_efficiency_control as control
        import data_efficiency_report as report
        from test_data_efficiency_control import fixture,write
        self.control,self.report,self.write=control,report,write
        self.runs.mkdir(parents=True)
        self.grid=self.runs/'data_efficiency_math_v1'
        control.prepare_grid(*fixture(self.runs),self.grid,token_budgets=(1024,))
        descriptor=control.load(self.grid/'grid_manifest.json')['studies'][0]
        self.study=self.grid/descriptor['folder']
        self.manifest=control.load(self.study/'manifest.json')
        first=self.study/self.manifest['jobs'][0]['folder']
        first_plan=control.load(first/'plan.json')
        data={'development':control.load(first/'input.json')['development']}
        base=self.runs/'student_baseline_batched64_v1';base.mkdir()
        write(base/'input.json',data)
        plan=dict(mode='evaluate_saved',model=control.skill.MODEL,revision=control.skill.REVISION,
            seed=42,checkpoint_name='baseline',context_limit=2048,max_new_tokens=512,enable_thinking=False,
            do_sample=False,evaluation_batch_size=8,evaluation_kind='development',training_performed=False,adapter_from=None,
            development_ids=first_plan['development_ids'],development_source_sha256=first_plan['development_source_sha256'],
            input_sha256=report.file_hash(base/'input.json'),source_code_sha256={
                name:report.file_hash(report.ROOT/name) for name in ('modal_valuation.py','valuation_contract.py')})
        plan=dict(plan,protocol_hash=control.digest(plan),run_id=base.name)
        write(base/'plan.json',plan)
        self.base_result=dict(stage='completed',arm='evaluation_only',plan=plan,
            supervised_tokens=0,optimizer_updates=0,held_out_test_used=False,
            evaluations={'baseline':self.rows(data['development'],58)})
        self.base=base;write(base/'result.json',self.base_result)

    @staticmethod
    def rows(development,correct):
        return [dict(id=row['id'],response='#### '+('7' if i<correct else '8'),gold_answer='7',
            elapsed_seconds=.1,generated_tokens=2,truncated=False) for i,row in enumerate(development)]

    def complete(self,selector='random',correct=59):
        job=next(j for j in self.manifest['jobs'] if j['seed']==42 and j['selector']==selector)
        folder=self.study/job['folder'];plan=self.control.load(folder/'plan.json')
        data=self.control.load(folder/'input.json')
        result=dict(stage='completed',arm=self.control.SLOT[selector],plan=plan,
            supervised_tokens=1024,optimizer_updates=1,held_out_test_used=False,
            evaluations={selector:self.rows(data['development'],correct)})
        self.write(folder/'result.json',result)
        return folder,result

    def test_new_grid_gain_is_measured_against_validated_matched_base(self):
        for correct in (57,58,59):
            self.complete(correct=correct)
            public=accomplishments.build(self.root)
            self.assertEqual(public['accuracy_improved'],correct>58)
            if correct>58:
                item=next(r for r in public['completed'] if r['title']=='New-cohort checkpoint measured a development gain')
                self.assertIn('random, seed 42, 1,024 tokens: 59/64',item['detail'])
                self.assertIn('not final-test validation or evidence that a selector beats random',item['detail'])
                self.assertIn('Robust or final-test evidence that the new selection method outperforms random.',public['not_done'])

    def test_valid_new_cohort_training_removes_only_its_missing_claim(self):
        missing='Completed Granite training/evaluation on the new multi-source math cohort; source imports and teacher collection are separate stages.'
        # A public count is not evidence that any private training arm completed.
        self.write(self.root/'docs/data-efficiency-results.json',{'status':'completed','completed_arms':12})
        before=accomplishments.build(self.root)
        self.assertIn(missing,before['not_done'])
        self.assertFalse(before['accuracy_improved'])
        folder,valid=self.complete(correct=57)
        after=accomplishments.build(self.root)
        self.assertNotIn(missing,after['not_done'])
        self.assertIn('new multi-source math cohort has 1 validated Granite training/evaluation arm',after['summary'])
        self.assertFalse(after['accuracy_improved'])
        self.assertIn('Robust or final-test evidence that the new selection method outperforms random.',after['not_done'])
        invalid=copy.deepcopy(valid);invalid['supervised_tokens']=1023
        self.write(folder/'result.json',invalid)
        reconciled=accomplishments.build(self.root)
        self.assertIn(missing,reconciled['not_done'])
        self.assertFalse(reconciled['accuracy_improved'])
        self.assertNotIn('cohort has 1 validated',reconciled['summary'])

    def test_training_completion_does_not_require_a_completed_gain_baseline(self):
        self.complete(correct=57)
        pending=copy.deepcopy(self.base_result);pending['stage']='running'
        self.write(self.base/'result.json',pending)
        evidence=accomplishments._grid_development_gain(self.grid)
        self.assertEqual(evidence['validated_completed_arms'],1)
        self.assertIsNone(evidence['baseline_numeric_correct'])
        self.assertEqual(evidence['improved'],[])
        public=accomplishments.build(self.root)
        self.assertIn('new multi-source math cohort has 1 validated',public['summary'])
        self.assertFalse(public['accuracy_improved'])

    def test_pending_wrong_tokens_questions_or_checkpoint_cannot_claim_gain(self):
        self.assertFalse(accomplishments.build(self.root)['accuracy_improved'])
        folder,valid=self.complete(selector='gradient')
        for change in ('pending','tokens','questions','checkpoint','actual_plan'):
            result=copy.deepcopy(valid)
            if change=='pending':result['stage']='running'
            elif change=='tokens':result['supervised_tokens']=1023
            elif change=='questions':result['evaluations']['gradient'][0]['id']='other-question'
            elif change=='checkpoint':result['evaluations']={'valued':result['evaluations']['gradient']}
            else:result['plan']['max_new_tokens']=4096
            self.write(folder/'result.json',result)
            with self.subTest(change=change):
                self.assertFalse(accomplishments.build(self.root)['accuracy_improved'])

    def test_invalid_base_or_mutated_frozen_input_cannot_claim_gain(self):
        folder,_=self.complete()
        for change in ('training','source','questions'):
            result=copy.deepcopy(self.base_result)
            if change=='training':result['optimizer_updates']=1
            elif change=='source':result['plan']['source_code_sha256']['modal_valuation.py']='0'*64
            else:result['evaluations']['baseline'][0]['id']='other-question'
            self.write(self.base/'result.json',result)
            with self.subTest(change=change):
                self.assertFalse(accomplishments.build(self.root)['accuracy_improved'])
        self.write(self.base/'result.json',self.base_result)
        (folder/'input.json').write_text((folder/'input.json').read_text()+' ')
        self.assertFalse(accomplishments.build(self.root)['accuracy_improved'])


if __name__ == '__main__':
    unittest.main()
