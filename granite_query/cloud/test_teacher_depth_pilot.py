"""Adversarial native-boundary and durable-pilot checks; all API data is invented."""
from contextlib import ExitStack
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from cloud import teacher_depth_pilot as pilot


class SeamTokenizer:
    """A reversible greedy tokenizer with merges crossing both possible seams."""
    eos_token='<|im_end|>';eos_token_id=100257
    tokens={'<|im_start|>':1,'<|im_end|>':100257,'<think>':2,'</think>':3,'\nR':10,'\n</think>':11}
    reverse={value:key for key,value in tokens.items()}
    def apply_chat_template(self,messages,**kwargs):
        assert kwargs=={'tokenize':False,'add_generation_prompt':True,'enable_thinking':True}
        return '<|im_start|>user\n'+messages[0]['content']+'<|im_end|>\n<|im_start|>assistant\n<think>\n'
    def encode(self,text,add_special_tokens=False):
        assert add_special_tokens is False
        result=[];index=0
        for_limit=sorted(self.tokens,key=len,reverse=True)
        while index<len(text):
            token=next((value for value in for_limit if text.startswith(value,index)),None)
            if token is not None:result.append(self.tokens[token]);index+=len(token)
            else:result.append(ord(text[index])+200000);index+=1
        return result
    def decode(self,ids,**kwargs):
        return ''.join(self.reverse[value] if value in self.reverse else chr(value-200000) for value in ids)


def question(index=0):
    return {'id':f'gsm8k:train:{index:05d}','source_split':'train','prompt':f'Fixture item {index}: what is 3 plus 4?',
        'gold_answer':'7','reference_solution':'PRIVATE_REFERENCE_ANNOTATION'}


def wire(mode,*,content='Visible arithmetic.\n#### 7',reasoning=None,model='deepseek-v4-pro',usage=None,finish='stop'):
    if reasoning is None:reasoning='R calculate 3 + 4 carefully.' if mode=='thinking' else ''
    value={'model':model,'choices':[{'finish_reason':finish,'message':{'content':content,'reasoning_content':reasoning}}],
        'usage':usage if usage is not None else {'prompt_tokens':40,'completion_tokens':30}}
    return json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')


def receipt(row,mode,**kwargs):
    request=next(r for r in pilot.requests_for([row]) if r['mode']==mode)
    return pilot.result_from_wire(request,row,wire(mode,**kwargs),{'started_at_utc':'2026-11-03T00:00:00+00:00'})


class TeacherDepthTests(unittest.TestCase):
    def temporary(self):
        parent=pilot.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def test_explicit_boundary_retains_tokens_that_naive_full_string_slicing_would_mask(self):
        tokenizer=SeamTokenizer();row=question();prefix=None
        for mode,reasoning in (('concise',''),('thinking','R original reasoning\u2028with UTF8 π')):
            value=pilot.encode_target(row,mode,reasoning,'Original answer.\n#### 7',tokenizer)
            count=value['prefix_tokens'];pfx=value['input_ids'][:count];suffix=value['input_ids'][count:]
            if prefix is not None:self.assertEqual(pfx,prefix)
            prefix=pfx
            self.assertTrue(all(label==-100 for label in value['labels'][:count]))
            self.assertEqual(value['labels'][count:],suffix)
            self.assertEqual(suffix[-1],100257);self.assertEqual(suffix.count(100257),1)
            decoded=tokenizer.decode(value['input_ids'])
            # Full-string BPE merges the prefix's trailing LF into the suffix.
            full=tokenizer.encode(decoded)
            self.assertNotEqual(full,value['input_ids'])
            self.assertNotEqual(tokenizer.decode(full[count:]),tokenizer.decode(suffix))
            self.assertIn(reasoning,decoded)
            self.assertEqual(value['original_reasoning_sha256'],pilot.sha(reasoning.encode()))

    def test_full_fit_and_channel_rejections_do_not_truncate_or_manufacture_complete_traces(self):
        tokenizer=SeamTokenizer();row=question()
        good=pilot.verify_result(receipt(row,'thinking'),row,tokenizer)
        self.assertTrue(good['eligible']);self.assertFalse(good['verification']['intermediate_reasoning_verified'])
        missing=pilot.verify_result(receipt(row,'thinking',reasoning=''),row,tokenizer)
        self.assertIn('missing_reasoning_channel',missing['rejection_reasons'])
        unexpected=pilot.verify_result(receipt(row,'concise',reasoning='R unexpected'),row,tokenizer)
        self.assertIn('unexpected_concise_reasoning_channel',unexpected['rejection_reasons'])
        reserved=pilot.verify_result(receipt(row,'thinking',reasoning='R </think> injected'),row,tokenizer)
        self.assertFalse(reserved['verification']['channels_preserved']);self.assertFalse(reserved['eligible'])
        long='R'+'x'*5000
        over=pilot.verify_result(receipt(row,'thinking',reasoning=long),row,tokenizer)
        self.assertFalse(over['eligible']);self.assertFalse(over['verification']['context_fit'])
        self.assertGreater(over['encoding']['context_tokens'],4096)
        self.assertIn(long,tokenizer.decode(over['encoding']['input_ids']))
        incomplete=pilot.verify_result(receipt(row,'thinking',finish='length'),row,tokenizer)
        self.assertTrue(incomplete['verification']['trace_truncated']);self.assertFalse(incomplete['eligible'])
        malformed=pilot.verify_result(receipt(row,'thinking',usage={'prompt_tokens':True,'completion_tokens':30}),row,tokenizer)
        self.assertFalse(malformed['eligible']);self.assertFalse(malformed['verification']['usage_present'])

    def test_exact_utf8_wire_precedes_parse_and_local_replace_retry_never_resends(self):
        with self.temporary() as temporary:
            output=Path(temporary);(output/'attempts').mkdir();row=question()
            request=next(r for r in pilot.requests_for([row]) if r['mode']=='thinking')
            raw=wire('thinking',reasoning='R original π\u2028second line\u0085end')
            _,wire_path,_=pilot.attempt_paths(output,request['id'])
            original=pilot.result_from_wire;replace=os.replace;tries=[]
            def parsed(*args):
                self.assertEqual(wire_path.read_bytes(),raw)
                return original(*args)
            def locked(source,target):
                if Path(target)==wire_path:
                    tries.append(1)
                    if len(tries)==1:raise PermissionError('Invented local sync lock')
                return replace(source,target)
            with patch.object(pilot.urllib.request,'urlopen',return_value=io.BytesIO(raw)) as api, \
                    patch.object(pilot,'result_from_wire',side_effect=parsed),patch.object(pilot.os,'replace',side_effect=locked), \
                    patch.object(pilot.time,'sleep'):
                result=pilot.call_request(request,row,output,'fixture-no-credential')
            self.assertFalse(result['failed']);self.assertEqual(api.call_count,1);self.assertEqual(len(tries),2)
            self.assertEqual(wire_path.read_bytes(),raw)
            self.assertEqual(pilot.recover_attempt(request,row,output)['reasoning_content'],'R original π\u2028second line\u0085end')
            records=[{'reasoning':'literal\u2028separator\u0085kept'},{'content':'second record'}]
            pilot.write_bytes(output/'unicode.jsonl',pilot.rows_bytes(records))
            self.assertEqual(pilot.read_rows(output/'unicode.jsonl'),records)

    def test_recovery_uses_original_receipt_and_rejects_tampering_or_ambiguous_marker(self):
        with self.temporary() as temporary:
            output=Path(temporary);(output/'attempts').mkdir();row=question();request=pilot.requests_for([row])[0]
            raw=wire(request['mode'])
            with patch.object(pilot.urllib.request,'urlopen',return_value=io.BytesIO(raw)) as api:
                pilot.call_request(request,row,output,'fixture-no-credential')
            marker_path,wire_path,result_path=pilot.attempt_paths(output,request['id'])
            result_path.unlink()
            with patch.object(pilot.urllib.request,'urlopen',side_effect=AssertionError('Recovery must not send')):
                recovered=pilot.recover_attempt(request,row,output)
            self.assertTrue(recovered['recovered_from_durable_wire']);self.assertEqual(api.call_count,1)
            changed=json.loads(result_path.read_text(encoding='utf-8'));changed['response']='Forged answer.\n#### 99'
            result_path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'original wire response'):pilot.recover_attempt(request,row,output)
            result_path.unlink();wire_path.unlink()
            with self.assertRaisesRegex(RuntimeError,'Ambiguous prior transmission'):pilot.recover_attempt(request,row,output)
            self.assertTrue(marker_path.exists())

    def test_pair_ids_cost_ceiling_no_gold_payload_and_train_only_boundary(self):
        rows=[question(i) for i in range(32)];requests=pilot.requests_for(rows)
        self.assertEqual(len(requests),64);self.assertEqual(len({r['id'] for r in requests}),64)
        self.assertLessEqual(pilot.COST_BOUND,Decimal('1'))
        for row in rows:
            pair=[request for request in requests if request['question_id']==row['id']]
            self.assertEqual({r['mode'] for r in pair},{'concise','thinking'})
            self.assertNotEqual(pilot.attempt_paths(Path('unused'),pair[0]['id']),pilot.attempt_paths(Path('unused'),pair[1]['id']))
        sentinel=dict(question(),gold_answer='PRIVATE_GOLD',reference_solution='PRIVATE_REFERENCE')
        self.assertNotIn('PRIVATE',json.dumps(pilot.payload(sentinel,'thinking')))
        with self.assertRaises(ValueError):pilot.payload(dict(sentinel,source_split='test'),'thinking')
        with self.temporary() as temporary:
            output=Path(temporary);invalid=[question(i) for i in range(33)]
            pilot.write_bytes(output/'candidates.jsonl',pilot.rows_bytes(invalid))
            pilot.write_bytes(output/'requests.jsonl',pilot.rows_bytes(pilot.requests_for(invalid)))
            pilot.write_json(output/'plan.json',{'candidate_count':33,'max_attempts':66})
            with patch.object(pilot.source,'load_source',side_effect=AssertionError('Must reject count before source access')):
                with self.assertRaises(ValueError):pilot.validate_run(output,SeamTokenizer())

    def collector_fixture(self,output,funding):
        rows=[question(i) for i in range(32)];requests=pilot.requests_for(rows)
        plan={'run_id':output.name,'budget_job_id':output.name+'-teacher','reserved_usd_required':1}
        stack=ExitStack()
        stack.enter_context(patch.object(pilot,'load_tokenizer',return_value=SeamTokenizer()))
        stack.enter_context(patch.object(pilot,'validate_run',return_value=(plan,rows,requests)))
        stack.enter_context(patch.object(pilot,'other_collector_locks',return_value=[]))
        stack.enter_context(patch.object(pilot,'assert_no_study_owner'))
        stack.enter_context(patch.object(pilot,'credential',return_value='fixture-no-credential'))
        stack.enter_context(patch.object(pilot,'assert_funding',side_effect=funding))
        stack.enter_context(patch.object(pilot,'summarize',side_effect=lambda output,plan,rows,results,stage,halt=None:
            {'stage':stage,'completed_original_calls':len(results),'halt_reason':halt} ))
        return stack

    @staticmethod
    def fake_api(request,**kwargs):
        body=json.loads(request.data);mode='thinking' if body['thinking']['type']=='enabled' else 'concise'
        return io.BytesIO(wire(mode))

    def test_collector_dispatches_at_most64_and_recovery_sends_zero_more(self):
        with self.temporary() as temporary:
            output=Path(temporary);events=[]
            def funding(plan):events.append('funding')
            def api(request,**kwargs):
                self.assertEqual(events[-1],'funding');events.append('api')
                return self.fake_api(request,**kwargs)
            with self.collector_fixture(output,funding),patch.object(pilot.urllib.request,'urlopen',side_effect=api) as provider:
                first=pilot.collect(output,workers=1)
                # Completed receipt reconciliation may proceed without claiming
                # global spending ownership or touching funding/provider APIs.
                with patch.object(pilot,'assert_no_study_owner',side_effect=AssertionError('No pending dispatch')):
                    second=pilot.collect(output,workers=1)
            self.assertEqual(first['stage'],'completed');self.assertEqual(second['stage'],'completed')
            self.assertEqual(provider.call_count,64)
            self.assertEqual(events.count('funding'),65)
            self.assertEqual(len(list((output/'attempts').glob('*.attempt.json'))),64)
            self.assertFalse((output/'collector.lock').exists())

    def test_global_study_lease_or_nonterminal_state_blocks_new_dispatch(self):
        with self.temporary() as temporary:
            root=Path(temporary);study=root/'separate-study';study.mkdir()
            lease=study/'study_watch.lock';lease.write_text('999999999',encoding='ascii')
            # Stale-looking PIDs do not authorize clearing another owner's lease.
            with self.assertRaisesRegex(RuntimeError,'owner release'):pilot.assert_no_study_owner(root)
            self.assertTrue(lease.exists());lease.unlink()
            tick=study/'study_tick.lock';tick.write_text('fixture',encoding='ascii')
            with self.assertRaisesRegex(RuntimeError,'owner release'):pilot.assert_no_study_owner(root)
            tick.unlink();state=study/'study_watch_state.json'
            state.write_text(json.dumps({'stage':'watching'}),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'Nonterminal'):pilot.assert_no_study_owner(root)
            state.write_text('{invalid',encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'Unverifiable'):pilot.assert_no_study_owner(root)
            state.write_text(json.dumps({'stage':'stopped'}),encoding='utf-8')
            pilot.assert_no_study_owner(root)

    def test_stale_funding_and_persistent_account_failure_stop_future_dispatches(self):
        with self.temporary() as temporary:
            output=Path(temporary);checks=[]
            def funding(plan):
                checks.append(1)
                if len(checks)==3:raise RuntimeError('Invented stale observation')
            with self.collector_fixture(output,funding),patch.object(pilot.urllib.request,'urlopen',side_effect=self.fake_api) as provider:
                result=pilot.collect(output,workers=1)
            self.assertEqual(provider.call_count,1);self.assertEqual(result['halt_reason'],'fresh_funding_guard_stopped')
            self.assertEqual(result['completed_original_calls'],1)
        with self.temporary() as temporary:
            output=Path(temporary);failure=urllib.error.HTTPError(pilot.API_URL,402,'fixture account error',{},None)
            with self.collector_fixture(output,lambda _:None),patch.object(pilot.urllib.request,'urlopen',side_effect=failure) as provider:
                first=pilot.collect(output,workers=1);second=pilot.collect(output,workers=1)
            self.assertEqual(provider.call_count,1);self.assertEqual(first['stage'],'halted')
            self.assertEqual(second['halt_reason'],'prior_failed_or_unbounded_attempt_requires_review')

    def test_public_feasibility_summary_contains_no_prompts_or_original_channels(self):
        with self.temporary() as temporary:
            output=Path(temporary);row=question();row['prompt']='PRIVATE_QUESTION_SENTINEL'
            results=[pilot.verify_result(receipt(row,mode,reasoning='R PRIVATE_REASONING_SENTINEL' if mode=='thinking' else '',
                content='PRIVATE_VISIBLE_SENTINEL\n#### 7'),row,SeamTokenizer()) for mode in pilot.MODES]
            plan={'run_id':'fixture','conservative_max_cost_usd':float(pilot.COST_BOUND),'prior_exposure_limit':'Fixture-only provenance',
                **{key:'a'*64 for key in ('candidates_sha256','requests_sha256','protocol_sha256','design_sha256')}}
            with patch.object(pilot,'PUBLIC',output/'sanitized.json'):
                summary=pilot.summarize(output,plan,[row],results,'completed')
            self.assertEqual(summary['eligible_question_pairs'],1)
            self.assertFalse(summary['new_student_training']);self.assertFalse(summary['official_test_accessed'])
            published=(output/'sanitized.json').read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE_QUESTION_SENTINEL',published)
            self.assertNotIn('PRIVATE_REASONING_SENTINEL',published)
            self.assertNotIn('PRIVATE_VISIBLE_SENTINEL',published)


if __name__=='__main__':unittest.main()
