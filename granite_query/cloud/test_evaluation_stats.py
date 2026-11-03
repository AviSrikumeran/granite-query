import unittest
from cloud.evaluation_stats import paired


class PairedTests(unittest.TestCase):
    def row(self, key, correct=True):
        return {'id':key,'response':'#### '+('1' if correct else '2'),'gold_answer':'1'}

    def test_rejects_unmatched_questions_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            paired([self.row('a')],[self.row('b')])
        with self.assertRaises(ValueError):
            paired([self.row('a'),self.row('a')],[self.row('a')])

    def test_reports_direction_and_exact_discordance(self):
        old=[self.row(str(i)) for i in range(6)]
        new=[self.row(str(i),False) for i in range(6)]
        r=paired(old,new,resamples=100)
        self.assertEqual((r['corrected'],r['regressed']),(0,6))
        self.assertEqual(r['difference_percentage_points'],-100)
        self.assertEqual(r['mcnemar_exact_two_sided_p'],.03125)
        self.assertEqual(r['paired_bootstrap_95_interval_pp'],[-100,-100])

    def test_tie_can_have_changed_answers(self):
        r=paired([self.row('a'),self.row('b',False)], [self.row('a',False),self.row('b')],resamples=100)
        self.assertEqual((r['corrected'],r['regressed']),(1,1))
        self.assertEqual(r['difference_percentage_points'],0)


if __name__=='__main__':
    unittest.main()
