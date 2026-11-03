"""Synthetic, unpaid protocol checks; no tokenizer/model downloads or API calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import data_efficiency_control as control
from cloud.gradient_feature_contract import fixed_config,build_warmup,calibration_ids,canonical
from cloud.gradient_valuation import score_file


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False)+'\n',encoding='utf-8')


def rows(path,values):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(value,ensure_ascii=False)+'\n' for value in values),encoding='utf-8')


def fixture(root,*,recorded_hashes=False):
    pool=root/'teacher';features=root/'features';scores=root/'scores'
    pool.mkdir();features.mkdir()
    sources=['ChilleD/SVAMP','math-ai/TemplateGSM','nvidia/OpenMathInstruct-2']
    origins=['human_dataset_answer','procedurally_generated_result','synthetic_majority_vote_answer']
    teachers=[];encoded=[]
    for index in range(48):
        origin=0 if index<24 else index%3
        prompt=f'Item {index}: a rectangle costs 3 plus 4 dollars. What is the cost?'
        response='3 plus 4 is 7.\n#### 7';response_hash=hashlib.sha256(response.encode()).hexdigest()
        row={'id':f'fixture:{index:03}','prompt':prompt,'response':response,'gold_answer':'7',
            'source':sources[origin],'source_split':'train','reference_type':origins[origin],
            'reference_match_is_independent_gold':origin==0,'teacher_model':'deepseek-v4-pro',
            'teacher_revision':'deepseek-v4-pro','finish_reason':'stop','eligible':True,'truncated':False,
            'raw_response_sha256':response_hash,'verification':'verified_final_answer',
            'generation':{'prompt_version':'matched-granite-concise-nonthinking-v1',
                'settings':{'model':'deepseek-v4-pro','max_tokens':1024,'thinking':{'type':'disabled'}},
                'raw_response_sha256':response_hash},
            'raw':{'choices':[{'message':{'content':response},'finish_reason':'stop'}]}}
        if not recorded_hashes:
            row.pop('raw_response_sha256')
            row['generation'].pop('raw_response_sha256')
        teachers.append(row)
        encoded.append(dict(row,prefix_ids=[1,2],answer_ids=[4]*128+[3],verified_final_answer=True,
            raw_response_sha256=response_hash,
            question_sha256=hashlib.sha256(control.skill.normalized_question(prompt).encode()).hexdigest(),
            response_tokens=129,input_tokens=131))
    rows(pool/'eligible.jsonl',teachers);rows(pool/'teacher_results.jsonl',teachers)
    write(pool/'teacher_summary.json',{'run_id':pool.name,'stage':'completed','requested':48,'completed':48,
        'eligible':48,'official_test_accessed':False})
    candidates=encoded[24:];targets=[dict(row,group='math') for row in encoded[:24]]
    config=fixed_config(dimension=512)
    data={'candidates':candidates,'targets':targets,'warmup':build_warmup(candidates,config),
        'calibration_ids':calibration_ids(candidates,16)}
    tokenizer={'model':control.skill.MODEL,'revision':control.skill.REVISION,
        'backend_sha256':'a'*64,'chat_template_sha256':'b'*64}
    provenance={'eligible_sha256':control.sha(pool/'eligible.jsonl'),
        'teacher_summary_sha256':control.sha(pool/'teacher_summary.json'),
        'official_test_used':False,'tokenizer':tokenizer}
    protocol={'config':config,'input_sha256':hashlib.sha256(canonical(data)).hexdigest(),
        'sources':provenance,'candidate_ids':[r['id'] for r in candidates],'target_ids':[r['id'] for r in targets]}
    protocol_hash=hashlib.sha256(canonical(protocol)).hexdigest()
    plan={'run_id':features.name,'protocol':protocol,'protocol_hash':protocol_hash}
    write(features/'plan.json',plan);write(features/'input.json',data)
    projection={'family':'countsketch_shake256_v1','dimension':512,'seed':config['projection_seed'],
        'parameter_layout_sha256':'e'*64,'mapping_sha256':'d'*64,'device':'cpu','dtype':'float32'}
    checkpoints=[]
    for step in (4,8):
        checkpoint={'id':f'update{step:03}','weight':1.75e-5 if step==4 else 2e-5,
            'candidate_gradient_type':'less_adam','target_gradient_type':'sgd'}
        for role,records in (('candidate',candidates),('target',targets)):
            projected=[]
            for index,row in enumerate(records):
                vector=[1.0,index/100 if role=='candidate' else 0]+[0.0]*510
                value={'id':row['id'],'source_split':'train','question_sha256':row['question_sha256'],
                    'raw_response_sha256':row['raw_response_sha256'],'verified_final_answer':True,
                    'checkpoint_id':checkpoint['id'],'parameter_layout_sha256':'e'*64,
                    'projection_mapping_sha256':'d'*64,'protocol_hash':protocol_hash,'role':role,
                    'gradient_type':'less_adam' if role=='candidate' else 'sgd','feature':vector}
                if role=='target':value['group']='math'
                value['record_sha256']=hashlib.sha256(canonical(value)).hexdigest()
                projected.append(value)
            checkpoint['candidates' if role=='candidate' else 'targets']=projected
        checkpoints.append(checkpoint)
    payload={'protocol_hash':protocol_hash,'official_test_used':False,'target_role':'selection_development',
        'projection':projection,'checkpoints':checkpoints}
    write(features/'features_payload.json',payload)
    write(features/'result.json',{'stage':'completed','projected_features_complete':True,
        'protocol_hash':protocol_hash,'feature_payload_sha256':control.sha(features/'features_payload.json')})
    score_file(features/'features_payload.json',scores)
    development=root/'development.jsonl'
    rows(development,[{'id':f'dev:{i:03}','prompt':f'Development item {i}: count 7 apples.',
        'gold_answer':'7','source_split':'train'} for i in range(64)])
    weakness=root/'weakness.json'
    write(weakness,{'provenance':{'source_kind':'development_predictions','source_split':'train','official_test_used':False},
        'skills':{'geometry':{'smoothed_error_rate':.7},'cost_accounting':{'smoothed_error_rate':.4}}})
    return pool,features,scores,weakness,development


class DataEfficiencyTests(unittest.TestCase):
    def temporary(self):
        parent=control.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def test_three_selectors_two_seeds_share_exact_tokens_targets_and_inference(self):
        with self.temporary() as temporary:
            root=Path(temporary);inputs=fixture(root);output=root/'study'
            manifest=control.prepare(*inputs,output,token_budget=1024)
            self.assertEqual(len(manifest['jobs']),6)
            self.assertEqual(manifest['common_pool']['candidates'],24)
            self.assertEqual(manifest['common_pool']['heldout_gradient_targets'],24)
            self.assertFalse(manifest['paid_work_launched'])
            target_ids={f'fixture:{i:03}' for i in range(24)}
            for job in manifest['jobs']:
                folder=output/job['folder'];plan=control.load(folder/'plan.json');data=control.load(folder/'input.json')
                indexed=control.validate_arm(data['arm'])
                self.assertEqual(sum(r['supervised_tokens'] for r in indexed.values()),1024)
                self.assertEqual(len(data['arm']['updates']),1)
                self.assertFalse(set(indexed)&target_ids)
                self.assertEqual(plan['learning_rate'],2e-5)
                self.assertEqual(plan['max_new_tokens'],512)
                self.assertEqual(plan['evaluation_batch_size'],8)
                self.assertEqual(plan['checkpoint_name'],job['selector'])
                self.assertEqual(plan['arm'],'random' if job['selector']=='random' else 'valued')
                self.assertTrue(plan['fresh_base'])
                self.assertEqual(len(data['development']),64)
                exposure=manifest['exposures'][str(job['seed'])][job['selector']]
                self.assertEqual(sum(exposure['supervised_tokens_by_source'].values()),1024)
                self.assertEqual(exposure['partial_supervised_tails'],1)
            self.assertEqual(control.verify(output)['jobs'],6)
            with self.assertRaises(FileExistsError):control.prepare(*inputs,output,token_budget=1024)

    def test_insufficient_tokens_refuses_repetition_before_creating_plans(self):
        with self.temporary() as temporary:
            root=Path(temporary);inputs=fixture(root);output=root/'too_large'
            with self.assertRaisesRegex(ValueError,'without repetition'):
                control.prepare(*inputs,output,token_budget=4096)
            self.assertFalse(output.exists())

    def test_live_teacher_and_partial_features_cannot_create_plans(self):
        with self.temporary() as temporary:
            root=Path(temporary);inputs=fixture(root);pool,features,*_=inputs
            (pool/'collector.lock').write_text('other-owner')
            with self.assertRaisesRegex(ValueError,'locked'):control.prepare(*inputs,root/'bad1',token_budget=1024)
            (pool/'collector.lock').unlink()
            result=control.load(features/'result.json');result['stage']='bounded_stop';write(features/'result.json',result)
            with self.assertRaisesRegex(ValueError,'completed immutable'):control.prepare(*inputs,root/'bad2',token_budget=1024)
            self.assertFalse((root/'bad1').exists());self.assertFalse((root/'bad2').exists())

    def test_rehashed_wrong_scores_still_fail_against_complete_projected_features(self):
        with self.temporary() as temporary:
            root=Path(temporary);inputs=fixture(root);scores=inputs[2]
            values=control.skill.read_jsonl(scores/'scores.jsonl');values[0]['score']=123.0;rows(scores/'scores.jsonl',values)
            manifest=control.load(scores/'manifest.json');manifest['scores_sha256']=control.sha(scores/'scores.jsonl');write(scores/'manifest.json',manifest)
            with self.assertRaisesRegex(ValueError,'audited complete feature'):control.prepare(*inputs,root/'bad',token_budget=1024)

    def test_source_and_artifact_mutation_are_detected(self):
        with self.temporary() as temporary:
            root=Path(temporary);inputs=fixture(root);output=root/'study'
            manifest=control.prepare(*inputs,output,token_budget=1024)
            job=manifest['jobs'][0];path=output/job['folder']/'input.json'
            path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'Immutable prepared artifact'):control.verify(output)

    def test_optional_recorded_response_hash_cannot_override_original_receipt(self):
        with self.temporary() as temporary:
            root=Path(temporary);inputs=fixture(root,recorded_hashes=True);pool=inputs[0]
            values=control.skill.read_jsonl(pool/'eligible.jsonl')
            values[0]['raw_response_sha256']='0'*64;rows(pool/'eligible.jsonl',values)
            with self.assertRaisesRegex(ValueError,'Recorded original response hash'):
                control.prepare(*inputs,root/'bad',token_budget=1024)

    def test_budget_grid_is_prospective_and_labels_near_all_data_reference(self):
        with self.temporary() as temporary:
            root=Path(temporary);inputs=fixture(root);output=root/'grid'
            grid=control.prepare_grid(*inputs,output,token_budgets=(1024,2048,3072))
            self.assertEqual(grid['token_budgets'],[1024,2048,3072])
            self.assertEqual(sum(s['jobs'] for s in grid['studies']),18)
            self.assertEqual(grid['studies'][0]['budget_role'],'selection_contrast')
            self.assertEqual(grid['studies'][-1]['budget_role'],'near_all_data_reference')
            self.assertFalse(grid['paid_work_launched'])
            self.assertEqual(control.verify(output)['jobs'],18)


if __name__=='__main__':
    unittest.main()
