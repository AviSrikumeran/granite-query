import unittest
from decimal import Decimal
from cloud import source_reference_audit as audit


class SourceReferenceAuditTests(unittest.TestCase):
    def test_arithmetic_ast_computes_nested_decimal_operations(self):
        self.assertEqual(audit.arithmetic_value('( ( 4.0 - 2.0 ) + 3.0 )'), Decimal(5))
        self.assertEqual(audit.arithmetic_value('-(6/4) + 3'), Decimal('1.5'))

    def test_arbitrary_code_and_unbounded_syntax_are_rejected(self):
        for text in ['__import__("os").system("whoami")', 'open("secret")', '[1,2][0]',
                     '2**99999999', '(lambda: 1)()', 'True+1', '1e999']:
            with self.subTest(text=text), self.assertRaises((ValueError, SyntaxError)):
                audit.arithmetic_value(text)
        with self.assertRaises(ValueError): audit.arithmetic_value('1+' * 1100 + '1')

    def test_equation_conflict_is_separate_from_teacher_reference_match(self):
        raw = {'Equation': '((4-2)+3)', 'Answer': '1', 'Body': 'PRIVATE-CONTEXT', 'Question': 'PRIVATE-QUESTION'}
        row = {'gold_answer': '1', 'response': '#### 5',
               'prompt': raw['Body'] + '\n\n' + raw['Question'],
               'source_row_sha256': audit.sha(audit.canonical(raw).encode())}
        checked = audit.record_checks(row, raw)
        self.assertFalse(checked['equation_equals_reference'])
        self.assertFalse(checked['teacher_final_equals_reference'])
        self.assertTrue(checked['source_answer_equals_reference'])
        self.assertTrue(checked['raw_row_attribution_hash_matches'])
        self.assertNotIn('PRIVATE', str(checked))
        row['gold_answer'] = '5'
        self.assertTrue(audit.record_checks(row, raw)['teacher_final_equals_reference'])

    def test_complete_context_and_raw_hash_detect_projection_changes(self):
        raw = {'Equation': '3+4', 'Answer': '7', 'Body': 'Body', 'Question': 'Question'}
        row = {'gold_answer': '7', 'response': 'Reasoning.\n#### 7', 'prompt': 'Body\n\nQuestion',
               'source_row_sha256': audit.sha(audit.canonical(raw).encode())}
        self.assertTrue(all(audit.record_checks(row, raw).values()))
        row['prompt'] = 'Question'
        self.assertFalse(audit.record_checks(row, raw)['complete_context_projection_matches'])
        row['source_row_sha256'] = 'wrong'
        self.assertFalse(audit.record_checks(row, raw)['raw_row_attribution_hash_matches'])


if __name__ == '__main__':
    unittest.main()
