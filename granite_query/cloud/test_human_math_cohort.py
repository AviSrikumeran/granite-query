import unittest
from fractions import Fraction
from pathlib import Path
import tempfile
import json
from cloud import human_math_cohort as cohort


class HumanCohortTests(unittest.TestCase):
    def test_fraction_arithmetic_avoids_float_rounding(self):
        self.assertEqual(cohort.exact_arithmetic('0.1+0.2'), Fraction(3,10))
        self.assertEqual(cohort.exact_arithmetic('1,200/3'), Fraction(400))
        self.assertEqual(cohort.exact_arithmetic('(3/4)**2'), Fraction(9,16))
        for value in ['__import__("os")', 'x+1', '[1][0]', '2**9999999', 'True+1']:
            with self.assertRaises((ValueError,SyntaxError)):
                cohort.exact_arithmetic(value)

    def test_annotations_require_exact_values_and_final_link(self):
        proof, status, _ = cohort.annotation_check('A <<0.1+0.2=0.3>>0.3 result.\n#### 0.3', '0.3')
        self.assertEqual(status,'exact_annotations_and_final')
        self.assertTrue(proof['last_annotation_matches_final'])
        self.assertIsNone(cohort.annotation_check('A <<3+4=8>>8 result.\n#### 8','8')[0])
        self.assertEqual(cohort.annotation_check('A <<3+4=7>>7 result.\n#### 8','8')[1], 'final_not_last_annotation')
        self.assertEqual(cohort.annotation_check('A <<1/3=0.33>>0.33 result.\n#### 0.33','0.33')[1], 'nonexact_possible_rounding')
        self.assertEqual(cohort.annotation_check('No executable annotations.\n#### 7','7')[1], 'no_arithmetic_annotations')

    def test_request_question_extraction_never_uses_gold(self):
        from cloud.matched_teacher import PREFIX
        row={'id':'gsm8k:train:00001','payload':{'messages':[{'role':'user','content':PREFIX+'3 plus 4?'}]},'gold_answer':'PRIVATE'}
        self.assertEqual(cohort.extract_question(row)['prompt'],'3 plus 4?')
        with self.assertRaises(ValueError):
            cohort.extract_question(dict(row,source_split='test'))

    def test_ancestry_excludes_ids_exact_questions_and_numeric_variants(self):
        canonical=[{'id':'gsm8k:train:00001','prompt':'Ann had 3 apples and bought 4 apples. How many apples does Ann have?'},
                   {'id':'gsm8k:train:00002','prompt':'A different longer question about a train.'}]
        exclusions=[{'id':'new:1','prompt':'Ann had 7 apples and bought 9 apples. How many apples does Ann have?'},
                    {'id':'new:2','prompt':'Unrelated template question','source':'math-ai/TemplateGSM','template_id':2}]
        ids, counts=cohort.ancestry_exclusions(canonical,exclusions)
        self.assertEqual(ids,{'gsm8k:train:00001','gsm8k:train:00002'})
        self.assertEqual(counts['conservative_template_id_ancestry'],1)
        self.assertEqual(counts['numeric_masked_lexical_near_ancestry'],1)

    def test_existing_frozen_artifacts_are_checked_without_rewriting(self):
        parent=cohort.ROOT/'runs/test_human_math_cohort'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            root=Path(temporary)
            plan={}
            for name,key in [('candidates.jsonl','teaching_sha256'),('development.jsonl','development_sha256'),('requests.jsonl','requests_sha256')]:
                raw=b'{"fixture":true}\n'
                (root/name).write_bytes(raw)
                plan[key]=cohort.sha(raw)
            (root/'plan.json').write_text(json.dumps(plan))
            (root/'manifest.json').write_text('{"stage":"prepared_unpaid"}')
            self.assertEqual(cohort.validate_frozen(root)['stage'],'prepared_unpaid')
            (root/'candidates.jsonl').write_bytes(b'changed')
            with self.assertRaises(RuntimeError):cohort.validate_frozen(root)


if __name__=='__main__':unittest.main()
