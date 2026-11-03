import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cloud import human_math_teacher as teacher
from test_prepare_verified_math import TinyTokenizer


class HumanTeacherTests(unittest.TestCase):
    def setUp(self):
        parent=teacher.ROOT/'runs/test_human_math_teacher'
        parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent)
        self.root=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def fixture(self):
        rows=[{'id':f'gsm8k:train:{i:05d}','prompt':'3 plus 4?', 'gold_answer':'7','source_split':'train',
               'reference_type':'human_dataset_answer_with_exact_annotation_checks'} for i in range(2048)]
        chunks=[]
        for index in range(4):
            selected=rows[index*512:(index+1)*512]
            requests=[{'id':row['id'],'payload':teacher.transport.build_payload(row)} for row in selected]
            folder=self.root/'chunks'/f'{index:03d}'
            folder.mkdir(parents=True)
            (folder/'candidates.jsonl').write_bytes(teacher.raw_rows(selected))
            (folder/'requests.jsonl').write_bytes(teacher.raw_rows(requests))
            chunks.append({'index':index,'ids':[row['id'] for row in selected],
                'candidates_sha256':teacher.source.sha(teacher.raw_rows(selected)),
                'requests_sha256':teacher.source.sha(teacher.raw_rows(requests)),
                'budget_job_id':f'chunk{index}-teacher','reserved_usd_required':4,
                'conservative_max_cost_usd':3.42786048})
        plan={'run_id':'fixture','chunks':chunks}
        teacher._write(self.root/'plan.json',plan)
        results=[]
        for row in rows[:511]:
            raw=dict(row,teacher_model=teacher.transport.MODEL,teacher_revision='fixture-revision',response='3 plus 4 equals7.\n#### 7',
                finish_reason='stop',failed=False,truncated=False,request_sha256=teacher._digest(teacher.transport.build_payload(row)),
                generation={'prompt_version':teacher.transport.PROMPT_VERSION,'settings':{}},raw=None)
            results.append(teacher.transport.verify(raw,TinyTokenizer()))
        (self.root/'teacher_results.jsonl').write_bytes(teacher.raw_rows(results))
        return rows,results

    def test_only_explicit_chunk_can_run(self):
        for value in (None,-1,4):
            with self.assertRaises(ValueError):teacher.collect(self.root,value)

    def test_funded_chunk_stops_at512_and_preserves_ambiguity(self):
        rows,initial=self.fixture()
        response={'model':teacher.transport.MODEL,'choices':[{'finish_reason':'stop','message':{'content':'3 plus4 equals7.\n#### 7'}}],
                  'usage':{'prompt_tokens':20,'completion_tokens':10}}
        with patch.object(teacher,'other_collector_locks',return_value=[]), \
             patch.object(teacher,'assert_reserved') as funding, \
             patch.object(teacher,'load_tokenizer',return_value=TinyTokenizer()), \
             patch.object(teacher,'record'),patch.object(teacher,'PUBLIC',self.root/'public.json'), \
             patch.object(teacher.transport,'credential',return_value='test-only-fixture'), \
             patch.object(teacher.transport.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps(response).encode())) as request:
            result=teacher.collect(self.root,0,1)
            self.assertEqual(result['completed'],512)
            self.assertEqual(result['stage'],'awaiting_next_chunk')
            self.assertEqual(result['excluded_development_count'],200)
            self.assertEqual(request.call_count,1)
            self.assertEqual(funding.call_args.args[0]['budget_job_id'],'chunk0-teacher')
            teacher.collect(self.root,0,1)
            self.assertEqual(request.call_count,1)
            (self.root/'teacher_results.jsonl').write_bytes(teacher.raw_rows(initial))
            teacher.collect(self.root,0,1)
            self.assertEqual(request.call_count,1)
            (self.root/'teacher_results.jsonl').write_bytes(teacher.raw_rows(initial))
            _,saved=teacher._attempt_paths(self.root/'chunks/000',rows[511]['id'])
            saved.unlink()
            with self.assertRaisesRegex(RuntimeError,'Ambiguous'):
                teacher.collect(self.root,0,1)
            self.assertEqual(request.call_count,1)

    def test_skip_or_tamper_stops_before_teacher_request(self):
        self.fixture()
        with patch.object(teacher,'other_collector_locks',return_value=[]), \
             patch.object(teacher,'assert_reserved'),patch.object(teacher,'load_tokenizer',return_value=TinyTokenizer()):
            with self.assertRaisesRegex(RuntimeError,'Earlier chunk'):
                teacher.collect(self.root,1,1)
        (self.root/'chunks/000/requests.jsonl').write_text('changed')
        with self.assertRaises((ValueError,json.JSONDecodeError)):
            teacher.collect(self.root,0,1)


if __name__=='__main__':unittest.main()
