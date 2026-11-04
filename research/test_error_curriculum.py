from copy import deepcopy
import unittest
from research import build_error_curriculum as c

class CurriculumIntegrity(unittest.TestCase):
 def row(self,variant):
  row=next(r for r in c.synthetic() if r['variant']==variant)
  row['training_ready']=False;row['target']=c.render(row['steps'],row['gold_answer'],row.get('note',''))
  return row
 def test_explicit_semantic_contrasts_change_answers(self):
  pairs=[('sequential','parallel'),('new_gifts','already_counted'),('all_attendees','apprentices_only')]
  for a,b in pairs:
   left,right=self.row(a),self.row(b);c.verify_row(left);c.verify_row(right)
   self.assertNotEqual(left['gold_answer'],right['gold_answer'])
 def test_dropped_gifts_rejected_even_when_wrong_answer_is_self_consistent(self):
  row=self.row('new_gifts');row['steps']=[('Balance','48+7+5-8-2','50','tokens')];row['gold_answer']='50';row['target']=c.render(row['steps'],row['gold_answer'])
  with self.assertRaisesRegex(ValueError,'semantic variant'):c.verify_row(row)
 def test_broken_intermediate_math_cannot_hide_behind_correct_final(self):
  row=self.row('all_attendees');row['steps'][1]=('Brushes','21*2','36','brushes');row['target']=c.render(row['steps'],row['gold_answer'])
  with self.assertRaisesRegex(ValueError,'intermediate'):c.verify_row(row)
 def test_only_approved_complete_target_is_exported(self):
  row=self.row('new_gifts');row['target']='#### 57'
  with self.assertRaisesRegex(ValueError,'complete solution'):c.verify_row(row)
  row=self.row('new_gifts');row['training_ready']=True
  with self.assertRaisesRegex(ValueError,'training authorization'):c.verify_row(row)

if __name__=='__main__':unittest.main()
