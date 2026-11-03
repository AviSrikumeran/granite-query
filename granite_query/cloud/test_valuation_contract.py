import copy
import unittest
from valuation_contract import validate_arm,window_labels,trim_generation


def fixture():
    first={'id':'a','input_ids':[10,11,20,21,22,23,24],
        'labels':[-100,-100,20,21,22,23,24],'attention_mask':[1]*7,
        'prefix_tokens':2,'full_response_tokens':5,'supervised_tokens':5}
    second={'id':'b','input_ids':[30,40,41,42,43],
        'labels':[-100,40,41,42,-100],'attention_mask':[1]*5,
        'prefix_tokens':1,'full_response_tokens':4,'supervised_tokens':3}
    return {'arm':'valued','token_budget':8,'tokens_per_update':4,'optimizer_updates':2,
        'training':[first,second],'updates':[
            {'index':0,'supervised_tokens':4,'microbatches':[
                {'id':'a','answer_start':0,'answer_end':4,'supervised_tokens':4,'loss_weight':1.0}]},
            {'index':1,'supervised_tokens':4,'microbatches':[
                {'id':'a','answer_start':4,'answer_end':5,'supervised_tokens':1,'loss_weight':0.25},
                {'id':'b','answer_start':0,'answer_end':3,'supervised_tokens':3,'loss_weight':0.75}]}]}


class ContractTests(unittest.TestCase):
    def test_exact_token_coverage_and_boundary_window(self):
        arm=fixture()
        rows=validate_arm(arm)
        masked=window_labels(rows['a'],arm['updates'][1]['microbatches'][0])
        self.assertEqual(masked,[-100,-100,-100,-100,-100,-100,24])
        self.assertEqual(sum(row['supervised_tokens'] for row in rows.values()),8)

    def test_token_weighting_equals_mean_not_mean_of_means(self):
        # First microbatch has one token at loss2; second has three at loss4.
        windows=fixture()['updates'][1]['microbatches']
        weighted=sum(loss*w['loss_weight'] for loss,w in zip([2.0,4.0],windows))
        self.assertEqual(weighted,(2+4+4+4)/4)
        self.assertNotEqual(weighted,(2+4)/2)

    def test_reject_wrong_weight_and_duplicate_exposure(self):
        arm=fixture()
        arm['updates'][1]['microbatches'][0]['loss_weight']=0.5
        with self.assertRaises(ValueError): validate_arm(arm)
        arm=fixture()
        arm['updates'][1]['microbatches'][0]['answer_start']=3
        with self.assertRaises(ValueError): validate_arm(arm)

    def test_eos_and_generated_suffix_only(self):
        self.assertEqual(trim_generation([7,8,9,9,9],[9],5),([7,8,9],False))
        self.assertEqual(trim_generation([7,8,6],[9],3),([7,8,6],True))
        self.assertEqual(trim_generation([7,8,9],[9],3),([7,8,9],False))
        self.assertEqual(trim_generation([7,8,10,9],[9,10],4),([7,8,10],False))


if __name__=='__main__':
    unittest.main()
