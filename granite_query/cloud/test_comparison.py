import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import comparison_control as control
from comparison_metrics import score

class ComparisonTests(unittest.TestCase):
    def test_scoring_distinguishes_format_and_truncation(self):
        base={'gold_answer':'13','response':'Calculation.\n#### $13','truncated':False}
        self.assertTrue(score(base)['correct'])
        self.assertFalse(score(base)['strict_format_correct'])
        self.assertFalse(score(dict(base,truncated=True))['correct'])
        self.assertTrue(score(dict(base,response='Thus the answer is 13.'))['correct'])
        self.assertTrue(score(dict(base,response='#### .5',gold_answer='0.5'))['correct'])

    def test_shared_pool_and_deterministic_selection(self):
        parent=Path(__file__).resolve().parent/'runs/test_comparison'
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root=Path(folder)
            rows=[{'id':f'train:{i:03}','prompt':f'Question {i}', 'response':'A calculation.\n#### 13',
                'gold_answer':'13','eligible':True,'source_split':'train',
                'teacher_model':'deepseek-v4-pro','teacher_revision':'api-test',
                'generation':{'prompt_version':'fixture','settings':{}},'selection_score':float(i)} for i in range(80)]
            (root/'teacher_results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            (root/'development.jsonl').write_text(json.dumps({'id':'dev:1','prompt':'Development','gold_answer':'1'})+'\n')
            (root/'plan.json').write_text('{}')
            with patch.object(control,'RUN',root),patch.object(control,'record'):
                control.select()
                first=json.loads((root/'plan.json').read_text())
                control.select()
                self.assertEqual(first,json.loads((root/'plan.json').read_text()))
                self.assertEqual(len(first['arms']['ranked']),32)
                self.assertEqual(set(first['arms']['ranked']),{r['id'] for r in rows[48:]})
                self.assertTrue(set(first['arms']['random'])<={r['id'] for r in rows})
                data=json.loads((root/'input.json').read_text())
                self.assertFalse({r['id'] for r in data['training']}&{r['id'] for r in data['development']})
                (root/'launch.json').write_text('{}')
                with self.assertRaises(RuntimeError):
                    control.select()

if __name__=='__main__':
    unittest.main()
