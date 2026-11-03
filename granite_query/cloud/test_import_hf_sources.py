import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import import_hf_sources as source


class SourceImportTests(unittest.TestCase):
    def test_no_evaluation_split_selection_or_implicit_test_fallback(self):
        payload = {'splits': [{'config': 'default', 'split': 'test'},
                              {'config': 'main', 'split': 'train'}]}
        self.assertEqual(source.choose_train_split({'repo': 'a/b'}, payload)['split'], 'train')
        self.assertIsNone(source.choose_train_split({'repo': 'a/b'}, {'splits': payload['splits'][:1]}))
        with self.assertRaises(ValueError):
            source.choose_train_split({'preferred_splits': ['test']}, payload)
        self.assertEqual(source.choose_train_split({'preferred_splits': ['cot']},
                         {'splits': [{'config': 'default', 'split': 'cot'}]})['split'], 'cot')

    def test_numeric_adapter_keeps_required_context_and_refuses_letter_labels(self):
        prompt, gold = source.prompt_and_reference({'Body': 'Ann has 3 cakes.',
            'Question': 'She buys 4 more. How many?', 'Answer': '7'})
        self.assertIn('Ann has 3 cakes.', prompt)
        self.assertIn('4 more', prompt)
        self.assertEqual(gold, '7')
        self.assertEqual(source.prompt_and_reference({'question': 'A choice?', 'answer': 'B'})[1], None)
        self.assertEqual(source.prompt_and_reference({'question': 'Math?', 'answer': 'x+1'})[1], None)
        self.assertEqual(source.prompt_and_reference({'question': 'Math?', 'answer': 'Explanation\n#### 13'})[1], '13')

    def test_public_snapshot_is_explicit_allowlist_without_raw_examples(self):
        manifest = {'run_id': 'fixture', 'stage': 'importing', 'target_imported_datasets': 40,
            'sources': [{'repo': 'a/b', 'family': 'shared', 'domain': 'numeric_math',
                'status': 'sample_imported', 'sample_rows': 4, 'metadata_reviewed': True,
                'numeric_reference_prompts': 2, 'raw': 'PRIVATE-REASONING',
                'prompt': 'PRIVATE-QUESTION', 'credentials': 'PRIVATE-CREDENTIALS'},
                {'repo': 'a/c', 'family': 'shared', 'domain': 'numeric_math', 'status': 'queued'}]}
        public = source.public_snapshot(manifest)
        self.assertEqual(public['actually_imported_sources'], 1)
        self.assertEqual(public['actually_imported_families'], 1)
        self.assertEqual(public['training_ready_examples'], 0)
        self.assertNotIn('PRIVATE', json.dumps(public))

    def test_revision_mismatch_reads_no_row_body(self):
        class Response:
            headers = {'x-revision': 'wrong'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, count): raise AssertionError('Unpinned rows must not be read')
        parent = source.ROOT / '.test_work'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            folder = Path(temporary)
            http = source.SourceHTTP(folder)
            with patch.object(source.urllib.request, 'urlopen', return_value=Response()):
                with self.assertRaises(source.RevisionMismatch):
                    http.get('https://datasets-server.huggingface.co/rows?dataset=a%2Fb', folder / 'row.json', revision='expected')
            self.assertEqual(http.network_bytes, 0)


if __name__ == '__main__':
    unittest.main()
