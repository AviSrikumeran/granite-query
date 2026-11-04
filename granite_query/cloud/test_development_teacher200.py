"""Invented TRAIN rows and mocked API transport only."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cloud import development_teacher200 as teacher


def wire():return json.dumps({'model':'deepseek-v4-pro','choices':[{'finish_reason':'stop',
    'message':{'content':'INVENTED\u2028steps\n#### 7','reasoning_content':''}}],
    'usage':{'prompt_tokens':10,'completion_tokens':8}},ensure_ascii=False).encode('utf-8')


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        parent=teacher.ROOT/'runs/test_development_teacher200';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.temp.name);self.output=self.root/'measurement'
        self.source=self.root/'invented_train_development.jsonl'
        data=[{'id':f'gsm8k:train:{i:05d}','prompt':f'INVENTED problem {i}','gold_answer':'7','source_split':'train',
               'reference_solution':'PRIVATE_REFERENCE_NEVER_TRANSMITTED'} for i in range(200)]
        raw=teacher.bytes_rows(data);self.source.write_bytes(raw)
        self.patches=[patch.object(teacher,'SOURCE',self.source),patch.object(teacher,'SOURCE_SHA',teacher.sha(raw))]
        for p in self.patches:p.start()
        teacher.prepare(self.output,authorized=True)
        self.manifest,self.reference,self.requests=teacher.validate(self.output)
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_unpaid_prepare_exact_match_no_gold_and_no_training_artifacts(self):
        self.assertEqual(teacher.COST,teacher.Decimal('0.933504'))
        self.assertEqual(len(self.requests),200)
        for request,row in zip(self.requests,self.reference):
            body=request['payload'];self.assertNotIn('gold_answer',body)
            self.assertEqual(body['messages'],[{'role':'user','content':teacher.contract.PREFIX+row['prompt']}])
            self.assertEqual(body['max_tokens'],512);self.assertEqual(body['thinking']['type'],'disabled')
        self.assertNotIn('PRIVATE_REFERENCE_NEVER_TRANSMITTED',(self.output/teacher.REQUESTS_FILE).read_text())
        self.assertFalse((self.output/'eligible.jsonl').exists());self.assertFalse((self.output/'requests.jsonl').exists())
        with patch.object(teacher,'validate',side_effect=AssertionError('inspect read source')):
            self.assertIsNone(teacher.inspect_metadata(self.output)['metrics'])
        with self.assertRaises(ValueError):teacher.collect(self.output,reservation_id='x')

    def test_exact200_calls_raw_recovery_and_no_resend(self):
        calls=[];guards=[]
        def transport(body,key):calls.append(body);return {'wire':wire(),'http_status':200,'response_header_bytes':10,'body_read_failed':False}
        result=teacher.collect(self.output,authorized=True,reservation_id='fixture',transport=transport,
            budget_guard=lambda:guards.append(1),key_provider=lambda:'INVENTED_KEY')
        self.assertEqual(len(calls),200);self.assertEqual(result['metrics']['numeric_correct'],200)
        self.assertEqual(result['metrics']['count'],200);self.assertFalse(result['official_test_used'])
        self.assertGreaterEqual(len(guards),200)
        result=teacher.collect(self.output,authorized=True,reservation_id='unused',transport=lambda *a:self.fail('resend'),
            budget_guard=lambda:self.fail('unpaid recovery required budget'))
        self.assertEqual(result['retained'],200)
        row,request=self.reference[0],self.requests[0]
        saved=teacher.shared.paths(self.output,row['id'])[3];value=teacher.read(saved);value['response']='TAMPERED\n#### 7'
        teacher.shared.mutable_json(saved,value)
        with self.assertRaises(ValueError):teacher.recover(self.manifest,row,request,self.output)

    def test_account_halt_four_workers_preserves_wire_before_parse(self):
        barrier=threading.Barrier(4);lock=threading.Lock();calls=[];parse=teacher.parse_result
        def transport(body,key):
            with lock:calls.append(body);ordinal=len(calls)
            barrier.wait(timeout=10)
            return {'wire':wire(),'http_status':401 if ordinal==1 else 200,'response_header_bytes':10,'body_read_failed':False}
        def checked(m,row,request,intent,raw=None,*args,**kwargs):
            if raw is not None:self.assertEqual(teacher.shared.paths(self.output,row['id'])[1].read_bytes(),raw)
            return parse(m,row,request,intent,raw,*args,**kwargs)
        with patch.object(teacher,'parse_result',side_effect=checked):
            result=teacher.collect(self.output,authorized=True,reservation_id='fixture',transport=transport,
                budget_guard=lambda:None,key_provider=lambda:'INVENTED_KEY')
        self.assertEqual(len(calls),4);self.assertIsNone(result['metrics'])
        self.assertEqual(teacher.read(self.output/'halt.json')['reason'],'http_401')
        with self.assertRaises(RuntimeError):teacher.collect(self.output,authorized=True,reservation_id='fixture',
            transport=lambda *a:self.fail('unreviewed resume'),budget_guard=lambda:None)

    def test_budget_binding_and_final_credit_protection(self):
        m=self.manifest;job={'run_id':'fixture','service':'deepseek','status':'reserved','reserved_usd':1,
            'development_teacher200_manifest_sha256':m['manifest_sha256'],'development_teacher200_source_sha256':teacher.SOURCE_SHA,
            'development_teacher200_settings_sha256':m['settings_sha256']}
        ledger={'limits':{'deepseek':20},'estimated_spend':{'deepseek':14},'reserved':{'deepseek':1},'jobs':[job],
            'deepseek_budget_accounting':{'status':'conditional_wallet_inference','issues':[],'max_snapshot_age_minutes':15},
            'deepseek_wallet_observation':{'source':'Official GET /user/balance','queried_at_utc':datetime.now(timezone.utc).isoformat()}}
        with patch.object(teacher,'read',return_value=ledger):
            teacher.require_budget(m,'fixture')
            ledger['estimated_spend']['deepseek']=14.1
            with self.assertRaises(RuntimeError):teacher.require_budget(m,'fixture')
            ledger['estimated_spend']['deepseek']=14;job['development_teacher200_manifest_sha256']='bad'
            with self.assertRaises(RuntimeError):teacher.require_budget(m,'fixture')


if __name__=='__main__':unittest.main()
