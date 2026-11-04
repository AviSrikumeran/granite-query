import unittest
from decimal import Decimal
from cloud import efficiency_audit as a

class AuditContracts(unittest.TestCase):
 def test_shared_questions_and_caps_have_one_case_each(self):
  rows=[{'id':f'gsm8k:train:{i:05}','prompt':'Synthetic math fixture','gold_answer':'4'} for i in range(32)]
  for modes,service in [(a.GRANITE_MODES,'modal'),(a.DEEPSEEK_MODES,'deepseek')]:
   cases=a.cases(rows,modes,service)
   self.assertEqual(len(cases),32*len(modes)*2)
   self.assertEqual(len({c['id'] for c in cases}),len(cases))
   self.assertEqual({c['question_id'] for c in cases},{r['id'] for r in rows})
   for mode in modes:
    seeds={r['id']:{c['seed'] for c in cases if c['question_id']==r['id'] and c['mode']==mode} for r in rows}
    self.assertTrue(all(len(s)==1 for s in seeds.values()))
 def test_thinking_prefix_not_scored_as_final(self):
  self.assertEqual(a.split_response('The answer might be 17.','thinking'),('The answer might be 17.','',False))
  self.assertEqual(a.split_response('Check 2+2.\n</think>\n#### 4<|im_end|>','thinking'),('Check 2+2.','#### 4',True))
  self.assertEqual(a.split_response('#### 4<|im_end|>','nonthinking'),('','#### 4',True))
 def test_native_api_controls_and_equal_cap(self):
  row={'prompt':'Synthetic math fixture'}
  for mode in a.DEEPSEEK_MODES:
   for cap in a.CAPS:
    p=a.payload(row,mode,cap)
    self.assertEqual(p['max_tokens'],cap);self.assertEqual(p['messages'][0]['content'],a.PREFIX+row['prompt'])
    self.assertEqual(p['thinking']['type'],'disabled' if mode=='nonthinking' else 'enabled')
    if mode!='nonthinking':self.assertEqual(p['reasoning_effort'],mode);self.assertNotIn('temperature',p)
 def test_failed_and_capped_final_numbers_cannot_count(self):
  from cloud.comparison_metrics import score
  self.assertFalse(score({'response':'#### 4','gold_answer':'4','truncated':True})['correct'])
  self.assertTrue(score({'response':'#### 4','gold_answer':'4','truncated':False})['correct'])
 def test_entire_api_envelope_fits_existing_reservation(self):
  bound=Decimal(32)*(8*2000*Decimal('1.32')+4*sum(a.CAPS)*Decimal('3.96'))/Decimal(1000000)
  self.assertLessEqual(bound,Decimal(str(a.AMOUNTS['deepseek'])))

if __name__=='__main__':unittest.main()
