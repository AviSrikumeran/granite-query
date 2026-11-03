import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from valuation_report import COMMON,validate_plan,teacher_provenance,seed_variation,ids_hash


def plan():
    value=dict(COMMON,seed=42,arm='random',development_ids=[f'dev:{i}' for i in range(64)],
        development_source_sha256='devhash',selection_manifest_sha256='selectionhash',arm_source_sha256='armhash')
    protocol_hash=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(value,run_id='fixture',protocol_hash=protocol_hash)


def check(value):
    validate_plan(value,seed=42,arm='random',dev_ids=[f'dev:{i}' for i in range(64)],
        dev_sha='devhash',selection_sha='selectionhash',arm_sha='armhash')


class ValuationReportTests(unittest.TestCase):
    def test_protocol_and_common_source_guards(self):
        check(plan())
        for field,value in [('token_budget',8192),('learning_rate',1e-4),
                            ('selection_manifest_sha256','otherpool'),('seed',43),
                            ('development_ids',[f'other:{i}' for i in range(64)])]:
            changed=plan();changed[field]=value
            with self.assertRaises(ValueError): check(changed)

    def test_seed_variation_not_fabricated_from_partial_pairs(self):
        pairs={'42':{'status':'completed'},'43':{'status':'partial'}}
        self.assertFalse(seed_variation(pairs)['available'])
        complete={}
        for seed,random_count,valued_count in [(42,55,56),(43,54,56)]:
            complete[str(seed)]={'status':'completed','arms':{
                'random':{'metrics':{'numeric_correct':random_count}},
                'valued':{'metrics':{'numeric_correct':valued_count}}},
                'paired_valued_vs_random':{'difference_percentage_points':100*(valued_count-random_count)/64}}
        variation=seed_variation(complete)
        self.assertTrue(variation['available'])
        self.assertEqual(variation['n_seeds'],2)
        self.assertAlmostEqual(variation['valued_minus_random']['mean_difference_pp'],100*1.5/64)

    def test_teacher_identity_and_public_provenance_exclude_private_text(self):
        parent=Path(__file__).resolve().parent/'runs/local_check_tmp'
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root=Path(folder)
            row={'id':'PRIVATE_ID','prompt':'PRIVATE_QUESTION','response':'PRIVATE_TEACHER_TRACE',
                'teacher_model':'deepseek-v4-pro','teacher_revision':'deepseek-v4-pro','source_split':'train',
                'verified_final_answer':True,'trace_truncated':False,
                'generation':{'settings':{'model':'deepseek-v4-pro','max_tokens':1024,'thinking':{'type':'disabled'}}}}
            row['raw_response_sha256']=hashlib.sha256(row['response'].encode()).hexdigest()
            def write_fixture():
                pool=root/'eligible.jsonl'
                pool.write_text(json.dumps(row)+'\n')
                manifest={'official_test_used':False,'eligible_sha256':hashlib.sha256(pool.read_bytes()).hexdigest(),
                    'weakness_provenance':{'source_kind':'development_predictions'},'counts':{'eligible':1}}
                (root/'manifest.json').write_text(json.dumps(manifest))
            write_fixture()
            _,public=teacher_provenance(root)
            text=json.dumps(public)
            self.assertNotIn('PRIVATE_ID',text)
            self.assertNotIn('PRIVATE_QUESTION',text)
            self.assertNotIn('PRIVATE_TEACHER_TRACE',text)
            row['generation']['settings']['thinking']['type']='enabled'
            write_fixture()
            with self.assertRaises(ValueError): teacher_provenance(root)

    def test_question_set_hash_is_order_invariant_but_detects_new_questions(self):
        self.assertEqual(ids_hash(['a','b']),ids_hash(['b','a']))
        self.assertNotEqual(ids_hash(['a','b']),ids_hash(['a','c']))


if __name__=='__main__':
    unittest.main()
