"""Fixture checks for the historical four-arm chart's separate batch8 base bar."""
import json
from pathlib import Path
import shutil
import unittest

import research_charts as charts
import test_data_efficiency_report as fixtures


class MatchedChartTests(unittest.TestCase):
    def setUp(self):
        self.context=fixtures.ReportTests();self.context.setUp()
        self.root=self.context.root/'chart-cloud'
        self.addCleanup(self.context.tearDown)
        baseline=self.context.baseline(correct=58)
        destination=self.root/'runs/student_baseline_batched64_v1'
        shutil.copytree(baseline,destination)
        development=self.root/'runs/matched_eval64_v1/development.jsonl'
        development.parent.mkdir(parents=True)
        shutil.copyfile(self.context.inputs[-1],development)
        rows=[json.loads(line) for line in development.read_text().split('\n') if line.strip()]
        self.ids={row['id'] for row in rows}
        for seed,counts in ((42,(55,53)),(43,(57,56))):
            for arm,correct in zip(('random','valued'),counts):
                plan={'development_ids':[r['id'] for r in rows],'model':'ibm-granite/granite-4.2-3b',
                    'revision':'4e9c275e232f10211ec88644d106a1f6a1b60e06','evaluation_batch_size':8,
                    'max_new_tokens':512,'enable_thinking':False,'do_sample':False}
                result={'stage':'completed','plan':plan,'supervised_tokens':32768,'optimizer_updates':32,
                    'evaluations':{arm:[dict(id=row['id'],response='#### '+('7' if i<correct else '8'),gold_answer='7',
                        elapsed_seconds=.1,generated_tokens=2,truncated=False) for i,row in enumerate(rows)]}}
                folder=self.root/f'runs/student_valuation32768_seed{seed}_{arm}_v1';folder.mkdir(parents=True)
                (folder/'result.json').write_text(json.dumps(result))

    def test_verified_base_adds_reference_bar_without_counting_a_fifth_training_arm(self):
        items,public=charts.token_matched_series(self.root,self.ids)
        self.assertEqual(len(items),5)
        self.assertEqual(items[0][1]['numeric_correct'],58)
        self.assertIn('Untouched base',items[0][0])
        self.assertEqual(public['completed_arms'],4);self.assertEqual(public['planned_arms'],4)
        self.assertEqual(len(public['correct']),4)
        self.assertEqual(public['batched_baseline']['actual_supervised_tokens'],0)
        self.assertFalse(any('DeepSeek' in name for name,_ in items))

    def test_pending_or_invalid_base_never_becomes_a_zero_or_trained_bar(self):
        path=self.root/'runs/student_baseline_batched64_v1/result.json'
        saved=path.read_text();path.unlink()
        items,public=charts.token_matched_series(self.root,self.ids)
        self.assertEqual(len(items),4);self.assertEqual(public['completed_arms'],4)
        self.assertEqual(public['batched_baseline']['status'],'running')
        result=json.loads(saved);result['optimizer_updates']=1;path.write_text(json.dumps(result))
        items,public=charts.token_matched_series(self.root,self.ids)
        self.assertEqual(len(items),4);self.assertEqual(public['batched_baseline']['status'],'invalid_result')


if __name__=='__main__':
    unittest.main()
