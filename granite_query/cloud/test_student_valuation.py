import json
from pathlib import Path
import tempfile
import unittest

import student_valuation as valuation


class FakeTokenizer:
    eos_token = '<eos>'
    chat_template = 'fixture-template'

    def apply_chat_template(self, messages, **kwargs):
        return '<user> ' + messages[0]['content'] + ' <assistant>'

    def __call__(self, text, **kwargs):
        return {'input_ids': list(range(1, len(text.split()) + 1))}


class ValuationTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent / 'runs/test_student_valuation'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def write_rows(self, name, rows):
        path = self.root / name
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        return path

    def pool(self):
        return [{'id': f'train:{i:03}', 'prompt': ('A monthly fee costs ' if i % 2 else 'A train travels miles per hour ') + str(i),
                 'response': ('Reasoning ' * (18 + i % 7)) + r'\boxed{13}',
                 'gold_answer': '13', 'source_split': 'train', 'verified_final_answer': True,
                 'verification': {'math_verify': True, 'complete': True, 'boxed_numeric_match': True, 'trace_truncated': False},
                 'generation': {'dataset': 'fixture', 'revision': 'fixed'}} for i in range(30)]

    def signal(self, **kwargs):
        return {'provenance': {'source_kind': 'development_skill_aggregates', 'source_split': 'train',
                              'official_test_used': False, 'question_ids': ['dev:1'], **kwargs},
                'skills': {'cost_accounting': {'smoothed_error_rate': 0.2},
                           'rates_and_units': {'smoothed_error_rate': 0.9}}}

    def test_exact_budget_equal_updates_common_order_and_immutable_outputs(self):
        pool = self.write_rows('pool.jsonl', self.pool())
        weakness = self.write_json('weakness.json', self.signal())
        prepared = self.root / 'prepared'
        valuation.prepare(pool, weakness, prepared, tokenizer=FakeTokenizer())
        result = valuation.select(prepared, self.root / 'selection', 256, seed=42, tokens_per_update=64)
        result2 = valuation.select(prepared, self.root / 'repeat', 256, seed=42, tokens_per_update=64)
        self.assertEqual(result['arms'], result2['arms'])
        for name in ('valued', 'random'):
            arm = json.loads((self.root / 'selection' / (name + '_input.json')).read_text())
            self.assertEqual(sum(label != -100 for row in arm['training'] for label in row['labels']), 256)
            self.assertEqual(arm['optimizer_updates'], 4)
            self.assertTrue(all(update['supervised_tokens'] == 64 for update in arm['updates']))
            self.assertTrue(all(abs(sum(batch['loss_weight'] for batch in update['microbatches']) - 1) < 1e-10 for update in arm['updates']))
            for row in arm['training']:
                self.assertEqual(len(row['input_ids']), row['prefix_tokens'] + row['full_response_tokens'])
                self.assertEqual(row['response'], next(r['response'] for r in self.pool() if r['id'] == row['id']))
            ids = [row['id'] for row in arm['training']]
            self.assertEqual(ids, sorted(ids, key=lambda i: valuation.digest_bytes(f'42:{i}'.encode())))
        self.assertEqual(result['arms']['valued']['supervised_tokens'], result['arms']['random']['supervised_tokens'])
        with self.assertRaises(FileExistsError):
            valuation.select(prepared, self.root / 'selection', 256, tokens_per_update=64)

    def test_verification_and_probe_overlap_are_gates_before_usefulness(self):
        rows = self.pool()
        rows[0]['prompt'] = 'Reserved evaluation prompt'
        rows[1]['verified_final_answer'] = False
        rows[2]['response'] = 'A solution. ' + r'\boxed{999}'
        rows[3]['truncated'] = True
        reserved_hash = valuation.digest_bytes(valuation.normalized_question(rows[0]['prompt']).encode())
        pool = self.write_rows('pool.jsonl', rows)
        weakness = self.write_json('weakness.json', self.signal(question_hashes=[reserved_hash]))
        prepared = self.root / 'prepared'
        manifest = valuation.prepare(pool, weakness, prepared, tokenizer=FakeTokenizer())
        eligible = valuation.read_jsonl(prepared / 'eligible.jsonl')
        self.assertFalse({row['id'] for row in eligible} & {r['id'] for r in rows[:4]})
        self.assertEqual(manifest['counts']['excluded'], 4)
        with self.assertRaises(ValueError):
            valuation.select(prepared, self.root / 'too-large', 100000, tokens_per_update=1000)

    def test_official_test_and_tampered_prepared_pool_are_rejected(self):
        with self.assertRaises(ValueError):
            valuation.read_jsonl(self.root / 'test.jsonl')
        rows = self.pool()
        rows[0]['source_split'] = 'test'
        pool = self.write_rows('pool.jsonl', rows)
        weakness = self.write_json('weakness.json', self.signal())
        with self.assertRaises(ValueError):
            valuation.prepare(pool, weakness, self.root / 'bad', tokenizer=FakeTokenizer())
        pool = self.write_rows('good.jsonl', self.pool())
        prepared = self.root / 'prepared'
        valuation.prepare(pool, weakness, prepared, tokenizer=FakeTokenizer())
        with (prepared / 'eligible.jsonl').open('a') as handle:
            handle.write('\n')
        with self.assertRaises(ValueError):
            valuation.select(prepared, self.root / 'tampered', 256, tokens_per_update=64)


if __name__ == '__main__':
    unittest.main()
