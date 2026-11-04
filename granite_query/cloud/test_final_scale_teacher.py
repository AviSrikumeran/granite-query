"""Invented1000/1319 metadata and private synthetic wire fixtures only."""
import copy
from datetime import datetime, timezone, timedelta
import io
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cloud import final_scale_teacher as teacher
from cloud import final_scale_teacher_receipts as api
from cloud.test_final_scale_receipts import fixture


def setup_fixture(count=1000):
    value,binding=fixture(count)
    rows=[{'id':q['id'],'source_index':q['source_index'],'prompt':'INVENTED arithmetic question '+str(i),
        'gold_answer':'7','source_split':'test','role':'final_eval_only','training_eligible':False}
        for i,q in enumerate(binding['questions'])]
    requested=[]
    for position,(row,q) in enumerate(zip(rows,binding['questions'])):
        q['input_sha256']=teacher.loader.question_input_hash(row,value)
        body=teacher.payload(row,value)
        requested.append({'id':row['id'],'global_position':position,'input_sha256':q['input_sha256'],
                          'request_sha256':api.digest(body),'payload':body})
    binding=api.sealed({k:v for k,v in binding.items() if k!='binding_sha256'},'binding_sha256')
    manifest=api.build_manifest(value,binding,seal_sha256='a'*64,bundle_id='fixture-bundle',
                                request_manifest_sha256=api.digest(requested))
    return value,binding,rows,requested,manifest


def wire(*,correct=True,finish='stop',usage=True,model='deepseek-v4-pro',prompt_tokens=12):
    value={'model':model,'system_fingerprint':'fixture','choices':[{'finish_reason':finish,
        'message':{'content':'PRIVATE_SYNTHETIC\u2028TRACE\u0085\n#### '+('7' if correct else '8'),'reasoning_content':''}}]}
    if usage:value['usage']={'prompt_tokens':prompt_tokens,'completion_tokens':8,'completion_tokens_details':{'reasoning_tokens':0}}
    return (' \n'+json.dumps(value,ensure_ascii=False)+'\n ').encode('utf-8')


class ReceiptTests(unittest.TestCase):
    def test_target_shape_hashes_caps_and_no_reduced_denominator(self):
        for count in (1000,1319):
            value,binding,_,_,manifest=setup_fixture(count)
            self.assertEqual(api.validate_manifest(value,binding,manifest),manifest)
            self.assertEqual(api.aggregate(manifest,binding,[])['metrics'],None)
            self.assertEqual(manifest['reserved_usd_required'],'5' if count==1000 else '7')
        changed=copy.deepcopy(manifest);changed['settings']['thinking']['type']='enabled'
        changed=api.sealed({k:v for k,v in changed.items() if k!='manifest_sha256'},'manifest_sha256')
        with self.assertRaises(ValueError):api.validate_manifest(value,binding,changed)

    def test_wire_replay_and_failure_correctness(self):
        _,binding,_,requests,m=setup_fixture()
        outcomes=[]
        for pos,q in enumerate(binding['questions']):
            intent=api.make_intent(m,q,pos,request_sha256=requests[pos]['request_sha256'],phase_approval_sha256='b'*64)
            if pos==0:r=api.failure(m,q,pos,intent,kind='input_limit')
            elif pos==1:r=api.from_wire(m,q,pos,intent,wire(finish='length'),elapsed_seconds=.1)
            elif pos==2:r=api.from_wire(m,q,pos,intent,wire(),elapsed_seconds=.1,http_status=401)
            else:r=api.from_wire(m,q,pos,intent,wire(),elapsed_seconds=.1)
            outcomes.append(r)
        summary=api.aggregate(m,binding,outcomes)
        self.assertEqual(summary['metrics']['count'],1000)
        self.assertEqual(summary['metrics']['numeric_correct'],997)
        self.assertEqual(api.halt_reason(outcomes[2]),'http_401')
        q=binding['questions'][3];intent=api.make_intent(m,q,3,request_sha256=requests[3]['request_sha256'],phase_approval_sha256='b'*64)
        bad=copy.deepcopy(outcomes[3]);bad['response']='TAMPERED\n#### 7'
        bad=api.sealed({k:v for k,v in bad.items() if k!='receipt_sha256'},'receipt_sha256')
        with self.assertRaises(ValueError):api.validate_attempt(m,q,3,intent,bad,request_sha256=requests[3]['request_sha256'],wire=wire())
        excessive=api.from_wire(m,q,3,intent,wire(prompt_tokens=2001),elapsed_seconds=.1)
        self.assertEqual(api.halt_reason(excessive),'provider_token_bound')
        badfinish=b'{"model":"deepseek-v4-pro","choices":[{"finish_reason":NaN,"message":{"content":"#### 7"}}]}'
        invalid=api.from_wire(m,q,3,intent,badfinish,elapsed_seconds=.1)
        self.assertEqual(invalid['outcome'],'api_failure');self.assertIsNone(invalid['usage'])

    def test_new_phase_after_halt_is_explicit(self):
        _,binding,_,_,m=setup_fixture()
        ids=[q['id'] for q in binding['questions']]
        initial=api.phase_template(m,ids,'fixture-teacher',phase_id='phase0');initial['approved']=True
        api.validate_phase(m,initial,ids,reservation_id='fixture-teacher')
        with self.assertRaises(ValueError):api.validate_phase(m,initial,ids[1:],reservation_id='fixture-teacher',halt_sha256='c'*64)
        fresh=api.phase_template(m,ids[1:],'fixture-teacher',phase_id='phase1',halt_sha256='c'*64);fresh['approved']=True
        api.validate_phase(m,fresh,ids[1:],reservation_id='fixture-teacher',halt_sha256='c'*64,prior_approval_sha256=api.digest(initial))


class CollectorTests(unittest.TestCase):
    def setUp(self):
        parent=teacher.ROOT/'runs/test_final_scale_teacher';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.output=Path(self.temp.name)
        self.value,self.binding,self.rows,self.requests,self.manifest=setup_fixture()
        self.context=({'contract':self.value,'seal_sha256':'a'*64},self.binding,self.rows,self.requests)
        teacher.loader.ensure_json(self.output/'manifest.json',self.manifest)
        teacher.loader.ensure_bytes(self.output/teacher.REQUESTS_FILE,teacher.rows_bytes(self.requests))
        self.approval_path=self.output/'approval.json'

    def tearDown(self):self.temp.cleanup()

    def approve(self,ids=None,halt=None,phase='phase0'):
        ids=ids or [r['id'] for r in self.requests]
        approval=api.phase_template(self.manifest,ids,'root-bundle-teacher',phase_id=phase,
            halt_sha256=halt['halt_sha256'] if halt else None)
        approval['approved']=True
        teacher.mutable_json(self.approval_path,approval)
        return approval

    def test_default_metadata_never_loads_sample_and_authorization_is_explicit(self):
        with patch.object(teacher,'_context',side_effect=AssertionError('official content read')):
            self.assertFalse(teacher.inspect_metadata(self.output)['official_content_read'])
        with self.assertRaises(ValueError):teacher.collect('x','y',self.output,reservation_id='x',phase_approval_path='y')
        with self.assertRaises(ValueError):teacher.prepare('x','y',self.output,bundle_id='fixture')

    def test_funding_helpers_must_be_physically_source_bound(self):
        roles={k:list(v) for k,v in teacher.SOURCE_ROLES.items()}
        hashes={name:teacher.sha((teacher.ROOT/name).read_bytes()) for names in roles.values() for name in names}
        sealed={'contract':{'protocol':{'source_roles':roles,'source_hashes':hashes}}}
        teacher._sources(sealed)
        roles['teacher_executor'].remove('deepseek_reconcile.py')
        with self.assertRaises(ValueError):teacher._sources(sealed)

    def test_http_error_wire_is_preserved_before_parse_and_never_retried(self):
        approval=self.approve();phase_sha=api.digest(approval)
        (self.output/'attempts').mkdir();(self.output/'phases').mkdir()
        teacher.loader.ensure_json(self.output/'phases'/(phase_sha+'.json'),{'approval':approval,'request_ids':[r['id'] for r in self.requests]})
        q=self.binding['questions'][0];request=self.requests[0];raw=b'{ "error": "PRIVATE_FIXTURE" }\n'
        real=api.from_wire
        def parse(*args,**kwargs):
            self.assertEqual(teacher.paths(self.output,request['id'])[1].read_bytes(),raw)
            return real(*args,**kwargs)
        transport=lambda *args:{'wire':raw,'http_status':401,'response_header_bytes':20}
        with patch.object(api,'from_wire',side_effect=parse),patch.object(teacher,'require_budget') as budget:
            result=teacher.attempt(self.manifest,q,request,self.output,'INVENTED_KEY',phase_sha256=phase_sha,
                transport=transport,budget_guard=budget)
        self.assertEqual(result['http_status'],401);self.assertEqual(api.halt_reason(result),'http_401')
        self.assertEqual(teacher.recover(self.manifest,q,request,self.output),result)
        with self.assertRaises(FileExistsError):
            teacher.attempt(self.manifest,q,request,self.output,'INVENTED_KEY',phase_sha256=phase_sha,
                transport=lambda *a:self.fail('resend'),budget_guard=lambda:None)
        teacher.paths(self.output,request['id'])[3].unlink()
        self.assertEqual(teacher.recover(self.manifest,q,request,self.output),result)

    def test_halt_resume_approval_and_exact_original_ceiling(self):
        self.approve();calls=[];guard=[]
        def transport(body,key):
            calls.append(body)
            return {'wire':wire(usage=len(calls)!=1),'http_status':200,'response_header_bytes':20}
        def fast_summary(output,manifest,binding,results,stage):
            # The dedicated receipt test checks full aggregation. Avoid1000
            # repeated summary/fsync passes in this bounded-dispatch fixture.
            return api.aggregate(manifest,binding,results) if len(results)==manifest['sample_count'] else {'metrics':None,'stage':stage}
        with patch.object(teacher,'_context',return_value=self.context),patch.object(teacher,'_summary',side_effect=fast_summary),patch.object(teacher.os,'fsync'):
            result=teacher.collect('fake','fake',self.output,authorized=True,workers=1,reservation_id='root-bundle-teacher',
                phase_approval_path=self.approval_path,transport=transport,budget_guard=lambda:guard.append(True),key_provider=lambda:'INVENTED_KEY')
            self.assertEqual(len(calls),1);self.assertIsNone(result['metrics'])
            with self.assertRaises(ValueError):
                teacher.collect('fake','fake',self.output,authorized=True,workers=1,reservation_id='root-bundle-teacher',
                    phase_approval_path=self.approval_path,transport=transport,budget_guard=lambda:None,key_provider=lambda:'INVENTED_KEY')
            halt=teacher.seal.read(self.output/'halt.json')
            self.approve([r['id'] for r in self.requests[1:]],halt,'phase1')
            result=teacher.collect('fake','fake',self.output,authorized=True,workers=4,reservation_id='root-bundle-teacher',
                phase_approval_path=self.approval_path,transport=transport,budget_guard=lambda:guard.append(True),key_provider=lambda:'INVENTED_KEY')
            self.assertEqual(len(calls),1000);self.assertEqual(result['metrics']['count'],1000)
            self.assertEqual(result['metrics']['numeric_correct'],999)
            result=teacher.collect('fake','fake',self.output,authorized=True,reservation_id='unused',phase_approval_path='unused',
                transport=lambda *a:self.fail('resend'),budget_guard=lambda:self.fail('unpaid recovery checked funding'))
            self.assertEqual(result['status'],'completed');self.assertEqual(len(calls),1000)
        self.assertGreaterEqual(len(guard),1000)
        history=teacher.read_rows(self.output/'results.jsonl')
        self.assertEqual(len(history),1000);self.assertEqual(len({r['id'] for r in history}),1000)
        self.assertIn('\u2028',history[-1]['response'])

    def test_http_transport_retains_error_body_without_headers_or_credentials(self):
        raw=b'{"error":"SYNTHETIC_RATE_LIMIT"}\n'
        error=teacher.urllib.error.HTTPError(teacher.API_URL,429,'fixture',{'Content-Type':'application/json'},io.BytesIO(raw))
        with patch.object(teacher.urllib.request,'urlopen',side_effect=error) as opened:
            envelope=teacher.http({'model':'deepseek-v4-pro'},'INVENTED_SECRET')
        self.assertEqual(envelope['wire'],raw);self.assertEqual(envelope['http_status'],429)
        self.assertEqual(opened.call_count,1)
        self.assertNotIn('INVENTED_SECRET',repr(envelope));self.assertNotIn('headers',envelope)
        class Partial(io.BytesIO):
            def read(self,*args):raise http.client.IncompleteRead(b'{partial',10)
        error=teacher.urllib.error.HTTPError(teacher.API_URL,429,'fixture',{},Partial())
        with patch.object(teacher.urllib.request,'urlopen',side_effect=error):
            envelope=teacher.http({},'INVENTED_SECRET')
        self.assertEqual(envelope['wire'],b'{partial');self.assertTrue(envelope['body_read_failed'])
        self.assertEqual(envelope['http_status'],429)

    def test_missing_raw_intent_cannot_resend_and_budget_identity_is_bound(self):
        approval=self.approve();phase_sha=api.digest(approval)
        (self.output/'attempts').mkdir();(self.output/'phases').mkdir()
        teacher.loader.ensure_json(self.output/'phases'/(phase_sha+'.json'),{'approval':approval,'request_ids':[r['id'] for r in self.requests]})
        q=self.binding['questions'][0];request=self.requests[0]
        intent=api.make_intent(self.manifest,q,0,request_sha256=request['request_sha256'],phase_approval_sha256=phase_sha)
        teacher.loader.ensure_json(teacher.paths(self.output,request['id'])[0],intent)
        with self.assertRaisesRegex(RuntimeError,'Ambiguous'):teacher.recover(self.manifest,q,request,self.output)
        ledger={'limits':{'deepseek':20},'estimated_spend':{'deepseek':1},'reserved':{'deepseek':5},
            'deepseek_budget_accounting':{'status':'conditional_wallet_inference','issues':[],'max_snapshot_age_minutes':15},
            'deepseek_wallet_observation':{'queried_at_utc':datetime.now(timezone.utc).isoformat(),'source':'Official GET /user/balance'},
            'jobs':[{'run_id':'bundle-teacher','service':'deepseek','status':'reserved','reserved_usd':5,
                'final_scale_freeze_sha256':self.manifest['freeze_sha256'],'final_scale_seal_sha256':self.manifest['seal_sha256'],
                'final_scale_bundle_id':self.manifest['bundle_id']}]}
        path=self.output/'ledger.json';teacher.mutable_json(path,ledger)
        teacher.require_budget(self.manifest,'bundle-teacher',ledger_path=path)
        ledger['jobs'][0]['final_scale_bundle_id']='foreign';teacher.mutable_json(path,ledger)
        with self.assertRaises(RuntimeError):teacher.require_budget(self.manifest,'bundle-teacher',ledger_path=path)
        ledger['jobs'][0]['final_scale_bundle_id']=self.manifest['bundle_id']
        ledger['deepseek_wallet_observation']['queried_at_utc']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
        teacher.mutable_json(path,ledger)
        with self.assertRaises(RuntimeError):teacher.require_budget(self.manifest,'bundle-teacher',ledger_path=path)

    def test_account_halt_drains_only_four_dispatched_requests(self):
        self.approve();barrier=threading.Barrier(4);lock=threading.Lock();calls=[]
        def transport(body,key):
            with lock:calls.append(body);ordinal=len(calls)
            barrier.wait(timeout=10)
            return {'wire':wire(),'http_status':429 if ordinal==1 else 200,'response_header_bytes':20}
        with patch.object(teacher,'_context',return_value=self.context):
            result=teacher.collect('fake','fake',self.output,authorized=True,workers=4,reservation_id='root-bundle-teacher',
                phase_approval_path=self.approval_path,transport=transport,budget_guard=lambda:None,key_provider=lambda:'INVENTED_KEY')
        self.assertEqual(len(calls),4);self.assertEqual(result['retained_count'],4);self.assertIsNone(result['metrics'])
        self.assertEqual(teacher.seal.read(self.output/'halt.json')['reason'],'http_429')

    def test_funding_failure_never_transmits(self):
        self.approve()
        with patch.object(teacher,'_context',return_value=self.context):
            with self.assertRaises(RuntimeError):
                teacher.collect('fake','fake',self.output,authorized=True,reservation_id='root-bundle-teacher',
                    phase_approval_path=self.approval_path,transport=lambda *a:self.fail('unfunded dispatch'),
                    budget_guard=lambda:(_ for _ in ()).throw(RuntimeError('fixture stale funding')))
        self.assertFalse(list((self.output/'attempts').glob('*.intent.json')))


if __name__=='__main__':unittest.main()
