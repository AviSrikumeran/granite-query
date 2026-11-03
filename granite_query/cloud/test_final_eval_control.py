"""Fixtures contain no official questions, weights, network or paid work."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import final_eval_control as control


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value)+'\n',encoding='utf-8')


def fixture(root):
    chosen=root/'chosen';adapter=chosen/'adapter';adapter.mkdir(parents=True)
    plan={'run_id':'chosen','mode':'train_evaluate','model':control.MODEL,'revision':control.REVISION,
        'checkpoint_name':'gradient','development_ids':[f'fixture-dev:{i}' for i in range(64)]}
    predictions=[{'id':key,'gold_answer':'7','response':'A fixture answer.\n#### 7',
        'generated_tokens':8,'elapsed_seconds':.1,'truncated':False} for key in plan['development_ids']]
    result={'stage':'completed','plan':plan,'held_out_test_used':False,'evaluations':{'gradient':predictions}}
    write(chosen/'plan.json',plan);write(chosen/'result.json',result)
    write(adapter/'adapter_config.json',{'base_model_name_or_path':control.MODEL,'r':8,
        'lora_alpha':16,'lora_dropout':0.0,'target_modules':['q_proj','v_proj']})
    (adapter/'adapter_model.safetensors').write_bytes(b'opaque fixture bytes, never loaded as a model')
    roles={}
    for role in sorted(control.ROLES):
        path=root/(role+'.py');path.write_text('# Synthetic non-executed fixture\n')
        roles[role]={'path':str(path),'sha256':control.sha(path),'capabilities':control.CAPABILITIES[role]}
    review=root/'review.json';write(review,{'reviewed':True,'protocol_version':control.VERSION,'roles':roles})
    return chosen,adapter,review


class FinalEvalControlTests(unittest.TestCase):
    def temporary(self):
        parent=control.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def test_preparation_samples_indices_without_test_access_and_blocks_unreviewed_loader(self):
        with self.temporary() as temporary:
            root=Path(temporary);chosen,adapter,_=fixture(root);output=root/'final'
            with patch.object(control,'ACCESS',root/'access.json'):
                frozen=control.freeze(chosen,adapter,output)
            data=frozen['protocol']['dataset']
            self.assertEqual(len(set(data['indices'])),256)
            self.assertEqual(data['indices'],sorted(data['indices']))
            self.assertTrue(all(0<=index<1319 for index in data['indices']))
            self.assertFalse(data['full_test_evaluation'])
            self.assertFalse((root/'access.json').exists())
            owner=control.load(output/'access_owner.json')['owner_token']
            with self.assertRaisesRegex(ValueError,'execution sources'):
                control.begin_access(output,owner_token=owner,loader_authorized=True)
            self.assertEqual(control.public_summary(frozen)['api_trial_output_cap'],512)
            self.assertEqual(control.public_summary(frozen)['max_output_tokens'],512)
            self.assertEqual(control.public_summary(frozen)['api_trial_request_cap'],20)
            self.assertTrue(control.public_summary(frozen)['api_nominal_output_cap_matches_benchmark'])
            self.assertFalse(control.public_summary(frozen)['api_execution_configuration_matches_benchmark'])
            self.assertFalse(frozen['protocol']['serving_trial_separate']['execution_configuration_matches_benchmark'])

    def test_one_durable_owner_can_resume_but_cannot_tune_after_access(self):
        with self.temporary() as temporary:
            root=Path(temporary);chosen,adapter,review=fixture(root);output=root/'final'
            with patch.object(control,'ACCESS',root/'access.json'):
                control.freeze(chosen,adapter,output,execution_review=review)
                owner=control.load(output/'access_owner.json')['owner_token']
                with self.assertRaisesRegex(ValueError,'actual loader authorization'):
                    control.begin_access(output,owner_token=owner)
                self.assertFalse((root/'access.json').exists())
                first=control.begin_access(output,owner_token=owner,loader_authorized=True)
                resumed=control.begin_access(output,owner_token=owner,loader_authorized=True)
                self.assertFalse(first['resume']);self.assertTrue(resumed['resume'])
                self.assertEqual(resumed['test_access_count'],1)
                with self.assertRaisesRegex(ValueError,'different durable owner'):
                    control.begin_access(output,owner_token='another-owner',loader_authorized=True)
                with self.assertRaisesRegex(ValueError,'no new checkpoint/protocol'):
                    control.freeze(chosen,adapter,root/'retuned',execution_review=review)

    def test_hash_matched_dataset_receipt_is_idempotent_and_rejects_fresh_sample(self):
        with self.temporary() as temporary:
            root=Path(temporary);chosen,adapter,review=fixture(root);output=root/'final'
            with patch.object(control,'ACCESS',root/'access.json'):
                frozen=control.freeze(chosen,adapter,output,execution_review=review)
            owner=control.load(output/'access_owner.json')['owner_token']
            control.begin_access(output,owner_token=owner,loader_authorized=True)
            args={'owner_token':owner,'dataset_sha256':'a'*64,'population_count':1319,
                'sample_rows_sha256':'b'*64,'indices':frozen['protocol']['dataset']['indices']}
            self.assertFalse(control.bind_dataset_receipt(output,**args)['resume'])
            self.assertTrue(control.bind_dataset_receipt(output,**args)['resume'])
            args['sample_rows_sha256']='c'*64
            with self.assertRaisesRegex(ValueError,'dataset/sample changed'):
                control.bind_dataset_receipt(output,**args)

    def test_incomplete_adapter_or_changed_weights_fail_closed(self):
        with self.temporary() as temporary:
            root=Path(temporary);chosen,adapter,review=fixture(root);output=root/'final'
            with patch.object(control,'ACCESS',root/'access.json'):
                control.freeze(chosen,adapter,output,execution_review=review)
            (adapter/'adapter_model.safetensors').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'adapter changed'):control.verify(output)
            (adapter/'adapter_model.safetensors').unlink()
            with self.assertRaisesRegex(ValueError,'weights are required'):
                control.chosen_checkpoint(chosen,adapter)

    def test_changed_executor_or_final_protocol_cannot_begin_access(self):
        with self.temporary() as temporary:
            root=Path(temporary);chosen,adapter,review=fixture(root);output=root/'final'
            with patch.object(control,'ACCESS',root/'access.json'):
                control.freeze(chosen,adapter,output,execution_review=review)
            (root/'test_loader.py').write_text('# changed executor\n')
            owner=control.load(output/'access_owner.json')['owner_token']
            with self.assertRaisesRegex(ValueError,'executor changed'):
                control.begin_access(output,owner_token=owner,loader_authorized=True)
            self.assertFalse((root/'access.json').exists())


if __name__=='__main__':unittest.main()
