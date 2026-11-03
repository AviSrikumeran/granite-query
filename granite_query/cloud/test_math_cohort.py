import unittest
from cloud import math_cohort as cohort


class CohortTests(unittest.TestCase):
    def test_svamp_preserves_body_and_question_without_reference_leakage(self):
        wrapper = {'row_idx': 1, 'truncated_cells': [], 'row': {'Body': 'Ann has 3 cakes.',
                   'Question': 'She buys 4. How many now?', 'Answer': 7}}
        row, reason = cohort.adapt(cohort.SOURCES[0], wrapper, set())
        self.assertEqual(row['prompt'], 'Ann has 3 cakes.\n\nShe buys 4. How many now?')
        self.assertEqual(row['gold_answer'], '7')
        self.assertEqual(row['reference_type'], 'human_dataset_answer')
        self.assertFalse(row['training_ready'])

    def test_template_source_and_prior_id_lineage_guard(self):
        wrapper = {'row_idx': 5001, 'truncated_cells': [], 'row': {'problem': '3 plus 4?',
                   'result': '7', 'template_id': 5, 'source': 'gsm8k-train-round2-seed42'}}
        self.assertEqual(cohort.adapt(cohort.SOURCES[1], wrapper, {5})[1], 'template_id_matches_excluded_gsm8k_id')
        row, _ = cohort.adapt(cohort.SOURCES[1], wrapper, set())
        self.assertEqual(row['template_id'], 5)
        self.assertEqual(row['reference_type'], 'procedurally_generated_result')
        wrapper['row']['source'] = 'gsm8k-test'
        self.assertIsNone(cohort.adapt(cohort.SOURCES[1], wrapper, set())[0])

    def test_openmath_only_numeric_augmented_gsm8k_and_explicit_majority_origin(self):
        wrapper = {'row_idx': 42, 'truncated_cells': [], 'row': {'problem': '3 plus 4?',
                   'expected_answer': '7', 'problem_source': 'augmented_math'}}
        self.assertEqual(cohort.adapt(cohort.SOURCES[2], wrapper, set())[1], 'not_augmented_gsm8k')
        wrapper['row']['problem_source'] = 'augmented_gsm8k'
        row, _ = cohort.adapt(cohort.SOURCES[2], wrapper, set())
        self.assertEqual(row['reference_type'], 'synthetic_majority_vote_answer')
        self.assertFalse(row['reference_verified_by_this_stage'])
        wrapper['row']['expected_answer'] = 'x+1'
        self.assertIsNone(cohort.adapt(cohort.SOURCES[2], wrapper, set())[0])

    def test_context_and_bounded_offsets(self):
        wrapper = {'row_idx': 1, 'truncated_cells': [], 'row': {'Body': 'Long ' * 500,
                   'Question': 'How many?', 'Answer': 7}}
        self.assertEqual(cohort.adapt(cohort.SOURCES[0], wrapper, set())[1], 'prospective_teacher_input_byte_bound')
        for source in cohort.SOURCES:
            offsets = cohort.offsets(source)
            self.assertEqual(offsets, cohort.offsets(source))
            self.assertEqual(len(offsets), len(set(offsets)))
            self.assertLessEqual(len(offsets) * 50, source['max_examined'])
            self.assertTrue(all(0 <= offset < source['rows'] for offset in offsets))


if __name__ == '__main__':
    unittest.main()
