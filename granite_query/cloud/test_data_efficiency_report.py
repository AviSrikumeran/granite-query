import copy
import json
from pathlib import Path
import tempfile
import unittest

import data_efficiency_report as report
import data_efficiency_control as control
from test_data_efficiency_control import fixture,write


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=control.ROOT/'runs')
        self.root=Path(self.temp.name);self.grid=self.root/'grid';self.workspace=self.root/'site'
        self.inputs=fixture(self.root)
        control.prepare_grid(*self.inputs,self.grid,token_budgets=(1024,2048))

    def tearDown(self):
        self.temp.cleanup()

    def arm_folder(self,budget,seed,selector):
        grid=control.load(self.grid/'grid_manifest.json')
        descriptor=next(s for s in grid['studies'] if s['token_budget']==budget)
        study=self.grid/descriptor['folder'];manifest=control.load(study/'manifest.json')
        job=next(j for j in manifest['jobs'] if j['seed']==seed and j['selector']==selector)
        return study/job['folder']

    def complete(self,budget,seed,selector,correct):
        folder=self.arm_folder(budget,seed,selector)
        plan=control.load(folder/'plan.json');data=control.load(folder/'input.json')
        rows=[dict(id=row['id'],response='#### '+('7' if index<correct else '8'),gold_answer='7',
            truncated=False,generated_tokens=2,elapsed_seconds=.1) for index,row in enumerate(data['development'])]
        result=dict(stage='completed',arm=control.SLOT[selector],plan=plan,
            supervised_tokens=budget,optimizer_updates=budget//1024,held_out_test_used=False,
            evaluations={selector:rows},elapsed_seconds=50,
            raw_private='PRIVATE_RAW_RESPONSE',account_key='sk-PRIVATE_DO_NOT_EXPORT')
        write(folder/'result.json',result)
        return folder,result

    def build(self,render=False):
        return report.build(grid=self.grid,workspace=self.workspace,render=render,
            paired_fn=lambda a,b:report.paired(a,b,resamples=100,seed=9))

    def baseline(self,correct=None):
        folder=self.root/'student_baseline_batched64_v1';folder.mkdir(exist_ok=True)
        arm=self.arm_folder(1024,42,'random');training_plan=control.load(arm/'plan.json')
        data={'development':control.load(arm/'input.json')['development']}
        raw=(json.dumps(data,indent=2)+'\n').encode();(folder/'input.json').write_bytes(raw)
        plan=dict(mode='evaluate_saved',model=control.skill.MODEL,revision=control.skill.REVISION,
            seed=42,checkpoint_name='baseline',context_limit=2048,max_new_tokens=512,enable_thinking=False,
            do_sample=False,evaluation_batch_size=8,evaluation_kind='development',training_performed=False,adapter_from=None,
            development_ids=training_plan['development_ids'],development_source_sha256=training_plan['development_source_sha256'],
            input_sha256=report.file_hash(folder/'input.json'),source_code_sha256={
                name:report.file_hash(report.ROOT/name) for name in ('modal_valuation.py','valuation_contract.py')})
        plan=dict(plan,protocol_hash=control.digest(plan),run_id=folder.name);write(folder/'plan.json',plan)
        write(folder/'launch.json',{'call_id':'fc-baseline-fixture'})
        if correct is not None:
            rows=[dict(id=row['id'],response='#### '+('7' if index<correct else '8'),gold_answer='7',
                elapsed_seconds=.1,generated_tokens=2,truncated=False) for index,row in enumerate(data['development'])]
            write(folder/'result.json',dict(stage='completed',arm='evaluation_only',plan=plan,
                supervised_tokens=0,optimizer_updates=0,held_out_test_used=False,evaluations={'baseline':rows}))
        return folder

    def test_prepared_and_running_arms_never_become_zero_accuracy_points(self):
        value=self.build()
        self.assertEqual(value['completed_arms'],0);self.assertEqual(value['points'],[])
        self.assertEqual(value['figures'],[])
        self.assertTrue(all('metrics' not in arm for b in value['budgets'] for s in b['seeds'] for arm in s['arms'].values()))
        folder=self.arm_folder(1024,42,'gradient')
        write(folder/'launch.json',{'call_id':'fc-fixture'})
        write(folder/'remote_status.json',{'stage':'training','error':'PRIVATE_ERROR'})
        value=self.build()
        self.assertEqual(value['budgets'][0]['seeds'][0]['arms']['gradient']['status'],'running')
        self.assertEqual(value['points'],[])

    def test_legacy_valued_slot_is_split_into_skill_and_gradient_and_paired(self):
        self.complete(1024,42,'random',48)
        self.complete(1024,42,'skill',50)
        self.complete(1024,42,'gradient',52)
        value=self.build()
        self.assertEqual(value['completed_arms'],3)
        seed=value['budgets'][0]['seeds'][0]
        self.assertEqual(seed['arms']['gradient']['worker_arm_slot'],'valued')
        self.assertEqual(seed['arms']['gradient']['checkpoint_name'],'gradient')
        self.assertEqual(seed['arms']['skill']['checkpoint_name'],'skill')
        self.assertEqual(seed['comparisons']['gradient_vs_random']['corrected'],4)
        self.assertEqual(seed['comparisons']['gradient_vs_random']['regressed'],0)
        self.assertEqual(seed['comparisons']['gradient_vs_random']['difference_percentage_points'],6.25)
        self.assertEqual(len(value['points']),3)
        self.assertNotIn('selectors',value['budgets'][0]['seed_variation'])
        exported=(self.workspace/'docs/data-efficiency-results.json').read_text()
        for private in ('PRIVATE_RAW_RESPONSE','PRIVATE_ERROR','sk-PRIVATE','source_paths','dev:000'):
            self.assertNotIn(private,exported)

    def test_two_seed_summary_is_descriptive_only_when_both_triples_complete(self):
        for seed,counts in ((42,(48,50,52)),(43,(50,49,54))):
            for selector,count in zip(report.SELECTORS,counts):
                self.complete(1024,seed,selector,count)
        value=self.build();summary=value['budgets'][0]['seed_variation']
        self.assertEqual(summary['complete_seed_triples'],2)
        self.assertEqual(summary['selectors']['gradient']['min_correct'],52)
        self.assertEqual(summary['selectors']['gradient']['max_correct'],54)
        self.assertEqual(summary['selectors']['gradient']['mean_accuracy_percent'],100*53/64)
        self.assertEqual(value['budgets'][1]['completed_arms'],0)
        self.assertFalse(value['historical_four_arms_included'])
        self.assertTrue(all(p['token_budget']==1024 for p in value['points']))

    def test_wrong_actual_tokens_checkpoint_or_reference_are_not_reported(self):
        for selector in report.SELECTORS:
            folder,result=self.complete(1024,42,selector,52)
            if selector=='random':result['supervised_tokens']=1023
            elif selector=='skill':result['evaluations']={'valued':result['evaluations']['skill']}
            else:result['evaluations']['gradient'][0]['gold_answer']='99'
            write(folder/'result.json',result)
        value=self.build()
        self.assertEqual(value['points'],[])
        self.assertTrue(all(a['status']=='invalid_result' for a in value['budgets'][0]['seeds'][0]['arms'].values()))

    def test_immutable_preparation_mutation_fails_and_missing_grid_writes_nothing(self):
        missing=self.root/'missing'
        value=report.build(grid=missing,workspace=missing,render=False)
        self.assertEqual(value['status'],'not_prepared');self.assertFalse(missing.exists())
        folder=self.arm_folder(1024,42,'random')
        (folder/'input.json').write_text((folder/'input.json').read_text()+' ')
        with self.assertRaises(ValueError):self.build()

    def test_plot_exports_only_completed_points(self):
        self.complete(1024,42,'gradient',52)
        value=self.build(render=True)
        self.assertEqual(len(value['points']),1)
        self.assertEqual(len(value['figures']),2)
        for path in value['figures']:
            self.assertGreater((self.workspace/'docs'/path).stat().st_size,1000)
        svg=(self.workspace/'docs/figures/data-efficiency-development.svg').read_text()
        self.assertIn('gradient, seed 42',svg)
        self.assertNotIn('random, seed 42',svg)

    def test_feature_overhead_keeps_incomplete_resume_costs_and_counts_warmup_once(self):
        original=self.root/'feature-initial';resume=self.root/'feature-resume'
        protocol={'config':{'method':'less-inspired-countsketch-v1','warmup_tokens':8192}}
        write(original/'plan.json',{'protocol_hash':'a'*64,'protocol':protocol,'resume_from':None})
        write(original/'result.json',{'stage':'bounded_stop','public_summary':{'selector_warmup_tokens':8192}})
        write(original/'remote_status.json',{'stage':'bounded_stop','elapsed_seconds':1551.5})
        write(resume/'plan.json',{'protocol_hash':'a'*64,'protocol':protocol,'resume_from':original.name})
        write(resume/'result.json',{'stage':'completed','public_summary':{'selector_warmup_tokens':8192,'elapsed_seconds':621.25}})
        result=report.feature_overhead(resume/'plan.json')
        self.assertEqual(result['attempt_count'],2)
        self.assertEqual(result['feature_worker_elapsed_seconds'],2172.75)
        self.assertEqual(result['selector_warmup_supervised_tokens'],8192)
        self.assertEqual(len(result['prior_incomplete_attempts']),1)
        self.assertEqual(result['attempts'][0]['stage'],'bounded_stop')
        changed=control.load(original/'plan.json');changed['protocol_hash']='b'*64;write(original/'plan.json',changed)
        with self.assertRaises(ValueError):report.feature_overhead(resume/'plan.json')

    def test_batched_base_is_pending_until_real_zero_training_result_then_paired(self):
        self.baseline()
        value=self.build();base=value['batched_base_control']
        self.assertEqual(base['status'],'running');self.assertNotIn('metrics',base)
        self.complete(1024,42,'gradient',52);self.baseline(correct=60)
        value=self.build();base=value['batched_base_control']
        self.assertEqual(base['status'],'completed');self.assertEqual(base['metrics']['numeric_correct'],60)
        self.assertEqual(base['actual_supervised_tokens'],0);self.assertEqual(base['actual_optimizer_updates'],0)
        comparison=value['budgets'][0]['seeds'][0]['versus_batched_base']['gradient']
        self.assertEqual(comparison['regressed'],8);self.assertEqual(comparison['corrected'],0)

    def test_base_with_adapter_training_wrong_source_or_other_questions_is_rejected(self):
        folder=self.baseline(correct=60)
        original=control.load(folder/'plan.json');original_result=control.load(folder/'result.json')
        original_input=(folder/'input.json').read_bytes()
        for change in ('adapter','training','source','questions','prompt'):
            (folder/'input.json').write_bytes(original_input)
            plan=copy.deepcopy(original);result=copy.deepcopy(original_result)
            if change=='adapter':plan['adapter_from']='private-adapter'
            elif change=='training':result['optimizer_updates']=1
            elif change=='source':plan['source_code_sha256']['modal_valuation.py']='0'*64
            elif change=='questions':plan['development_source_sha256']='0'*64
            else:
                changed=control.load(folder/'input.json');changed['development'][0]['prompt']='Different fixture question'
                write(folder/'input.json',changed);plan['input_sha256']=report.file_hash(folder/'input.json')
            plan['protocol_hash']=control.digest({k:v for k,v in plan.items() if k not in ('run_id','protocol_hash')})
            result['plan']=plan;write(folder/'plan.json',plan);write(folder/'result.json',result)
            value=self.build()['batched_base_control']
            self.assertIn(value['status'],('invalid_plan','invalid_result'))
            self.assertNotIn('metrics',value)


if __name__=='__main__':
    unittest.main()
