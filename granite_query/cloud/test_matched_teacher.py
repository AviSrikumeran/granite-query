import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import matched_teacher as collector


class MatchedTeacherTests(unittest.TestCase):
    def test_request_excludes_reference_and_gold(self):
        row = {'id': 'example', 'prompt': 'What is one plus one?',
               'gold_answer': 'PRIVATE_GOLD', 'reference_solution': 'PRIVATE_REFERENCE'}
        payload = collector.build_payload(row)
        text = json.dumps(payload)
        self.assertNotIn('PRIVATE_GOLD', text)
        self.assertNotIn('PRIVATE_REFERENCE', text)
        self.assertEqual(payload['messages'], [{'role': 'user', 'content': collector.PREFIX + row['prompt']}])

    def test_wrong_answers_retained_and_resume_does_not_repeat_calls(self):
        parent = Path(__file__).resolve().parent / 'runs/matched_teacher16_v1/test_work'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            root = Path(temporary)
            inputs = root / 'inputs.jsonl'
            inputs.write_text(json.dumps({'id': 'train:test', 'prompt': 'One plus zero?',
                                         'gold_answer': '1', 'source_split': 'train'})+'\n')
            raw = {'model': collector.MODEL, 'choices': [{'finish_reason': 'stop',
                   'message': {'content': 'A wrong calculation.\n#### 2'}}],
                   'usage': {'prompt_tokens': 10, 'completion_tokens': 8}}
            with patch.object(collector, 'credential', return_value='fake-test-only'), \
                 patch.object(collector.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(json.dumps(raw).encode())) as request:
                first = collector.evaluate(inputs, root / 'output', workers=1)
                second = collector.evaluate(inputs, root / 'output', workers=1)
                self.assertEqual(request.call_count, 1)
            self.assertEqual(first['completed_count'], 1)
            self.assertEqual(first['numeric_correct'], 0)
            self.assertEqual(first, second)
            saved = [json.loads(line) for line in (root/'output/results.jsonl').read_text().split('\n') if line]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]['response'], 'A wrong calculation.\n#### 2')


if __name__ == '__main__':
    unittest.main()
