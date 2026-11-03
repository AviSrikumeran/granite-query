import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

import gradient_valuation as gradient


class GradientTests(unittest.TestCase):
    def record(self,key,feature,group=None):
        row = dict(id=key,feature=feature,source_split='train',question_sha256=key[0]*64,
                   verified_final_answer=True)
        if group:
            row['group'] = group
        return row

    def payload(self):
        candidates = [self.record('a:aligned',[1,0]),self.record('b:opposed',[-1,0]),
                      self.record('c:orthogonal',[0,1])]
        targets = [self.record('d:target',[2,0],'math'),self.record('e:target',[4,0],'math')]
        return dict(official_test_used=False,target_role='selection_development',
            projection=dict(family='rademacher_jl',dimension=2,seed=42,parameter_layout_sha256='f'*64),
            checkpoints=[dict(id='warmup4',weight=1,candidate_gradient_type='less_adam',
                              target_gradient_type='sgd',candidates=candidates,targets=targets)])

    def test_aligned_opposed_scale_invariance_and_checkpoint_aggregation(self):
        payload = self.payload()
        rows = gradient.score_projected(payload)
        self.assertEqual([row['id'] for row in rows],['a:aligned','c:orthogonal','b:opposed'])
        self.assertEqual([row['score'] for row in rows],[1,0,-1])
        changed = copy.deepcopy(payload['checkpoints'][0])
        changed['id'],changed['weight'] = 'warmup8',3
        for row in changed['candidates']:
            row['feature'] = [-7*x for x in row['feature']]
        payload['checkpoints'].append(changed)
        results = {row['id']:row['score'] for row in gradient.score_projected(payload)}
        self.assertAlmostEqual(results['a:aligned'],-.5)
        self.assertAlmostEqual(results['b:opposed'],.5)

    def test_aggregation_policies_are_explicit_and_distinct(self):
        payload = self.payload()
        payload['checkpoints'][0]['targets'][1]['feature'] = [0,20]
        code = {row['id']:row['score'] for row in gradient.score_projected(payload)}
        paper = {row['id']:row['score'] for row in gradient.score_projected(payload,reduction='cosine_to_mean_gradient')}
        self.assertEqual(code['a:aligned'],.5)
        self.assertEqual(code['c:orthogonal'],.5)
        self.assertGreater(paper['c:orthogonal'],paper['a:aligned'])
        self.assertNotEqual(code,paper)

    def test_group_max_is_after_checkpoint_accumulation(self):
        payload = self.payload()
        first = payload['checkpoints'][0]
        first['targets'][0]['group'] = 'x'
        first['targets'][0]['feature'] = [1,0]
        first['targets'][1]['group'] = 'y'
        first['targets'][1]['feature'] = [0,1]
        second = copy.deepcopy(first)
        second['id'] = 'warmup8'
        second['targets'][0]['feature'] = [-1,0]
        second['targets'][1]['feature'] = [1,0]
        payload['checkpoints'].append(second)
        result = {row['id']:row for row in gradient.score_projected(payload)}
        self.assertEqual(result['a:aligned']['per_group'],{'x':0,'y':.5})
        self.assertEqual(result['a:aligned']['score'],.5)

    def test_export_preserves_source_hash_and_never_overwrites_scores(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'runs') as folder:
            root = Path(folder)
            source = root/'features.json'
            source.write_text(json.dumps(self.payload()),encoding='utf-8')
            result = gradient.score_file(source,root/'scores')
            self.assertEqual(result['candidates'],3)
            self.assertFalse(result['paid_work_launched'])
            self.assertEqual(result['source_sha256'],gradient.hashlib.sha256(source.read_bytes()).hexdigest())
            before = (root/'scores'/'scores.jsonl').read_bytes()
            with self.assertRaises(FileExistsError):
                gradient.score_file(source,root/'scores')
            self.assertEqual(before,(root/'scores'/'scores.jsonl').read_bytes())

    def test_reference_projection_linear_deterministic_and_bounded(self):
        first,second = [1,2,-3],[3,-1,5]
        projected = gradient.rademacher_reference(first,32,seed=7)
        self.assertEqual(projected,gradient.rademacher_reference(first,32,seed=7))
        summed = gradient.rademacher_reference([a+b for a,b in zip(first,second)],32,seed=7)
        other = gradient.rademacher_reference(second,32,seed=7)
        for a,b,c in zip(summed,projected,other):
            self.assertAlmostEqual(a,b+c)
        with self.assertRaises(ValueError):
            gradient.rademacher_reference([1]*1000,8192)

    def test_optimizer_moments_are_readonly_and_proxy_formula_matches(self):
        g,m,v = [1,-2],[.1,.2],[.01,.04]
        saved = copy.deepcopy((g,m,v))
        actual = gradient.less_adam_direction(g,m,v)
        self.assertEqual(saved,(g,m,v))
        expected = [(.9*x+.1*y)/math.sqrt(.999*z+.001*y*y+1e-8) for y,x,z in zip(g,m,v)]
        for a,b in zip(actual,expected):
            self.assertAlmostEqual(a,b)

    def test_rejects_test_overlap_zero_nonfinite_and_changed_ids(self):
        for change in ('test','overlap','zero','nan','ids'):
            payload = self.payload()
            if change == 'test':
                payload['checkpoints'][0]['targets'][0]['source_split'] = 'test'
            elif change == 'overlap':
                payload['checkpoints'][0]['targets'][0]['question_sha256'] = 'a'*64
            elif change == 'zero':
                payload['checkpoints'][0]['candidates'][0]['feature'] = [0,0]
            elif change == 'nan':
                payload['checkpoints'][0]['targets'][0]['feature'] = [float('nan'),1]
            else:
                other = copy.deepcopy(payload['checkpoints'][0])
                other['id'] = 'warmup8'
                other['candidates'][0]['id'] = 'f:different'
                payload['checkpoints'].append(other)
            with self.assertRaises(ValueError,msg=change):
                gradient.score_projected(payload)
        with self.assertRaises(ValueError):
            gradient.score_file(Path(__file__).parent/'runs'/'official_test.json','unused')


if __name__ == '__main__':
    unittest.main()
