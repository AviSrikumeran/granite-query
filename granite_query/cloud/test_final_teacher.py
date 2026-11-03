"""Synthetic sample only: no official questions, provider traffic or budget writes."""
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch,Mock

import final_teacher as teacher


class FinalTeacherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=teacher.ROOT/'runs')
        self.root=Path(self.temp.name);self.final=self.root/'sealed';self.inputs=self.root/'inputs';self.output=self.root/'teacher'
        protocol={'execution_ready':True,'execution_sources':{'roles':{'deepseek_evaluator':{
            'path':str(Path(teacher.__file__).resolve()),'sha256':teacher.seal.sha(Path(teacher.__file__)),
            'capabilities':teacher.CAPABILITIES,'dependencies':{'final_test_loader.py':{
                'sha256':teacher.seal.sha(teacher.ROOT/'final_test_loader.py')}}}}},
            'teacher':{'enabled':True,'model':'deepseek-v4-pro','thinking':{'type':'disabled'},'max_tokens':512,
                'temperature':0,'max_attempts':256,'automatic_retries':0,'max_concurrent_requests':4,
                'filter_on_answer_correctness':False,'peak_request_cost_bound_usd':1.2},
            'inference':{'user_prefix':teacher.seal.PREFIX,'max_new_tokens':512},
            'dataset':{'sample_count':256,'indices':list(range(256))}}
        self.manifest={'protocol':protocol,'freeze_sha256':teacher.seal.digest(protocol)}
        self.rows=[{'id':f'gsm8k:test:{i:05d}','prompt':f'Synthetic item {i}. Compute a toy sum.',
            'gold_answer':'7','source_split':'test','role':'final_eval_only','training_eligible':False} for i in range(256)]
        self.refresh()
        self.verify_patch=patch.object(teacher.seal,'verify',side_effect=lambda _:self.manifest);self.verify_patch.start()
        self.load_patch=patch.object(teacher.loader,'load_prepared',side_effect=lambda *_:(self.manifest,self.sample,self.raw,self.rows))
        self.loader_mock=self.load_patch.start()
        self.calls=[]

    def tearDown(self):
        self.load_patch.stop();self.verify_patch.stop();self.temp.cleanup()

    def refresh(self):
        self.raw=b''.join(teacher.loader.encoded(row) for row in self.rows)
        self.sample={'role':'final_eval_only','freeze_sha256':self.manifest['freeze_sha256'],
            'sample_rows_sha256':teacher.loader.sha_bytes(self.raw),'dataset_sha256':'a'*64,'count':256,
            'ids':[r['id'] for r in self.rows],'official_test_used':True,'training_eligible':False}

    def transport(self,payload,key):
        self.assertEqual(key,'fixture-only-key')
        self.assertEqual(payload['max_tokens'],512);self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertEqual(payload['temperature'],0);self.assertNotIn('gold_answer',payload)
        index=int(re.search(r'Synthetic item (\d+)',payload['messages'][0]['content']).group(1))
        self.calls.append(index)
        return json.dumps({'model':'deepseek-v4-pro-fixture','choices':[{'message':{'content':'#### '+('7' if index%2==0 else '9')},
            'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':3}}).encode()

    def collect(self,**kwargs):
        return teacher.collect(self.final,self.inputs,self.output,transport=self.transport,
            budget_guard=lambda:None,key_provider=lambda:'fixture-only-key',**kwargs)

    def test_all_wrong_and_correct_attempts_retained_and_raw_recovery_never_retransmits(self):
        result=self.collect()
        self.assertEqual(len(self.calls),256);self.assertEqual(result['completed_count'],256)
        self.assertEqual(result['numeric_correct'],128);self.assertFalse(result['filter_on_answer_correctness'])
        self.assertFalse(result['training_eligible']);self.assertEqual(result['max_tokens'],512)
        records=[json.loads(line) for line in (self.output/'results.jsonl').read_text().split('\n') if line.strip()]
        self.assertEqual(len(records),256)
        removed=records[0]
        (self.output/'results.jsonl').write_text(''.join(teacher.canonical(r)+'\n' for r in records[1:]),encoding='utf-8')
        _,saved,_=teacher.paths(self.output,removed['id']);saved.unlink()
        self.calls.clear();self.collect()
        self.assertEqual(self.calls,[])
        restored=teacher.seal.load(saved)
        self.assertTrue(restored['latency_recovered_without_timing'])
        self.assertEqual(restored['raw_receipt_sha256'],removed['raw_receipt_sha256'])

    def test_missing_funds_or_wrong_review_refuse_before_prepared_input_access(self):
        with self.assertRaises(RuntimeError):
            teacher.collect(self.final,self.inputs,self.output,budget_guard=Mock(side_effect=RuntimeError('not reserved')))
        self.loader_mock.assert_not_called();self.assertFalse(self.output.exists())
        entry=self.manifest['protocol']['execution_sources']['roles']['deepseek_evaluator']
        entry['sha256']='0'*64;self.manifest['freeze_sha256']=teacher.seal.digest(self.manifest['protocol'])
        with self.assertRaises(ValueError):self.collect()
        self.loader_mock.assert_not_called();self.assertEqual(self.calls,[])

    def test_ambiguous_marker_is_not_automatically_retried(self):
        self.output.mkdir();(self.output/'attempts').mkdir()
        row=self.rows[0];marker,_,_=teacher.paths(self.output,row['id'])
        teacher.seal.write_once(marker,{'id':row['id'],'request_sha256':teacher.digest(teacher.payload(row,self.manifest)),
            'freeze_sha256':self.manifest['freeze_sha256']})
        with self.assertRaisesRegex(RuntimeError,'Ambiguous'):self.collect()
        self.assertEqual(self.calls,[])

    def test_prepared_role_or_sample_hash_change_is_rejected(self):
        self.rows[0]['training_eligible']=True;self.refresh()
        with self.assertRaises(ValueError):self.collect()
        self.assertFalse(self.output.exists());self.assertEqual(self.calls,[])

    def test_oversized_question_retains_bounded_failure_without_dispatch(self):
        row=dict(self.rows[0],prompt='x'*2000)
        self.output.mkdir();(self.output/'attempts').mkdir()
        result=teacher.attempt(row,self.output,'fixture-only-key',self.manifest,transport=self.transport,budget_guard=lambda:None)
        self.assertTrue(result['failed']);self.assertEqual(result['error_type'],'InputByteLimit')
        self.assertFalse(result['transmitted']);self.assertFalse(result['scoring']['correct'])
        self.assertEqual(self.calls,[])

    def test_real_reservation_guard_rejects_insufficient_or_stale_accounting(self):
        path=self.root/'budget.json'
        ledger={'limits':{'deepseek':20},'estimated_spend':{'deepseek':1},'reserved':{'deepseek':2},
            'deepseek_budget_accounting':{'issues':[],'max_snapshot_age_minutes':15},
            'deepseek_wallet_observation':{'queried_at_utc':teacher.now()},
            'jobs':[{'run_id':'fixture-final-teacher','service':'deepseek','status':'reserved','reserved_usd':2}]}
        path.write_text(json.dumps(ledger))
        teacher.require_budget('fixture-final-teacher',self.manifest['protocol']['teacher'],ledger_path=path)
        ledger['jobs'][0]['reserved_usd']=1;path.write_text(json.dumps(ledger))
        with self.assertRaises(RuntimeError):
            teacher.require_budget('fixture-final-teacher',self.manifest['protocol']['teacher'],ledger_path=path)
        ledger['jobs'][0]['reserved_usd']=2;ledger['deepseek_wallet_observation']['queried_at_utc']='2000-01-01T00:00:00+00:00'
        path.write_text(json.dumps(ledger))
        with self.assertRaises(RuntimeError):
            teacher.require_budget('fixture-final-teacher',self.manifest['protocol']['teacher'],ledger_path=path)

    def test_failed_attempt_is_saved_without_exception_text_or_retry(self):
        self.output.mkdir();(self.output/'attempts').mkdir()
        calls=[]
        def failing(payload,key):
            calls.append(1)
            raise teacher.urllib.error.URLError('PRIVATE_EXCEPTION_TOKEN')
        result=teacher.attempt(self.rows[0],self.output,'fixture-only-key',self.manifest,
                               transport=failing,budget_guard=lambda:None)
        self.assertTrue(result['failed']);self.assertEqual(calls,[1]);self.assertFalse(result['scoring']['correct'])
        self.assertNotIn('PRIVATE_EXCEPTION_TOKEN',json.dumps(result))
        marker,saved,receipt=teacher.paths(self.output,self.rows[0]['id'])
        self.assertTrue(marker.exists());self.assertTrue(saved.exists());self.assertFalse(receipt.exists())


if __name__=='__main__':
    unittest.main()
