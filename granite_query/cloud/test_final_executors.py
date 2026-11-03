"""All 1319 fixture rows are invented; no official source or network is opened."""
import json
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch
from test_final_eval_control import fixture
from cloud import final_eval_control as seal
from cloud import final_test_loader as loader
from cloud import final_eval_jobs as jobs


def ready(root):
    chosen,adapter,review=fixture(root)
    value=seal.load(review)
    value['roles']['test_loader'].update(path=str(jobs.ROOT/'final_test_loader.py'),sha256=seal.sha(jobs.ROOT/'final_test_loader.py'))
    value['roles']['granite_evaluator'].update(path=str(jobs.ROOT/'modal_final_eval.py'),sha256=seal.sha(jobs.ROOT/'modal_final_eval.py'),
        dependencies={name:{'path':str(jobs.ROOT/name),'sha256':seal.sha(jobs.ROOT/name)} for name in jobs.DEPS})
    review.write_text(json.dumps(value))
    final=root/'sealed'
    with patch.object(seal,'ACCESS',root/'access.json'):
        seal.freeze(chosen,adapter,final,execution_review=review)
    raw=b''.join(loader.encoded({'question':f'Invented fixture question {i}, what is 3 plus 4?',
        'answer':'Synthetic calculation only.\n#### 7'}) for i in range(1319))
    return final,raw


class FinalExecutorTests(unittest.TestCase):
    def temporary(self):
        parent=jobs.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def test_authorization_precedes_permit_and_permit_precedes_single_fetch(self):
        with self.temporary() as temporary:
            root=Path(temporary);final,raw=ready(root);output=root/'sample';calls=[]
            def fetch(url):
                self.assertTrue((root/'access.json').exists())
                self.assertEqual(seal.load(root/'access.json')['test_access_count'],1)
                calls.append(url);return raw
            with self.assertRaisesRegex(ValueError,'authorization'):
                loader.prepare(final,output,fetcher=fetch)
            self.assertFalse((root/'access.json').exists())
            first=loader.prepare(final,output,authorized=True,fetcher=fetch)
            second=loader.prepare(final,output,authorized=True,fetcher=lambda _:self.fail('Repeated network fetch'))
            self.assertEqual(len(calls),1);self.assertFalse(first['resume']);self.assertTrue(second['resume'])
            _,meta,_,records=loader.load_prepared(final,output)
            self.assertEqual(len(records),256)
            self.assertTrue(all(r['role']=='final_eval_only' and r['training_eligible'] is False for r in records))
            self.assertFalse(meta['full_test_evaluation'])
            with self.assertRaisesRegex(ValueError,'destination owns'):
                loader.prepare(final,root/'another_destination',authorized=True,fetcher=lambda _:self.fail('Fresh untracked fetch'))

    def test_ambiguous_fetch_never_retries_and_hash_changed_cache_is_refused(self):
        with self.temporary() as temporary:
            root=Path(temporary);final,_=ready(root);output=root/'sample';calls=[]
            def broken(_):calls.append(1);raise RuntimeError('Invented transport interruption')
            with self.assertRaises(RuntimeError):loader.prepare(final,output,authorized=True,fetcher=broken)
            with self.assertRaisesRegex(ValueError,'Ambiguous prior'):
                loader.prepare(final,output,authorized=True,fetcher=broken)
            self.assertEqual(len(calls),1)
        with self.temporary() as temporary:
            root=Path(temporary);final,raw=ready(root);output=root/'sample'
            loader.prepare(final,output,authorized=True,fetcher=lambda _:raw)
            with (output/'source.jsonl').open('ab') as handle:handle.write(b' ')
            with self.assertRaisesRegex(ValueError,'dataset/sample changed'):
                loader.prepare(final,output,authorized=True,fetcher=lambda _:self.fail('Refetched mutated cache'))

    def test_base_chosen_jobs_match_and_recovery_requires_terminal_identity(self):
        with self.temporary() as temporary:
            root=Path(temporary);final,raw=ready(root);sample=root/'sample'
            loader.prepare(final,sample,authorized=True,fetcher=lambda _:raw)
            for checkpoint in ('base','chosen'):
                jobs.prepare(final,sample,root/('job_'+checkpoint),checkpoint=checkpoint)
            base=seal.load(root/'job_base/plan.json');chosen=seal.load(root/'job_chosen/plan.json')
            self.assertEqual(base['input_sha256'],chosen['input_sha256'])
            self.assertEqual(base['max_new_tokens'],512);self.assertEqual(chosen['evaluation_batch_size'],8)
            self.assertEqual(base['freeze_sha256'],chosen['freeze_sha256'])
            seal.write_once(root/'job_base/launch.json',{'call_id':'fixture-call'})
            seal.write_once(root/'job_base/terminal.json',{'call_id':'fixture-call','confirmed_terminal':False,'stage':'failed'})
            with self.assertRaisesRegex(ValueError,'Confirm the old'):jobs.prepare_resume(root/'job_base',root/'resume')
            loader.atomic(root/'job_base/terminal.json',{'call_id':'fixture-call','confirmed_terminal':True,'stage':'bounded_stop'})
            jobs.prepare_resume(root/'job_base',root/'resume')
            resumed=seal.load(root/'resume/plan.json')
            self.assertEqual(resumed['protocol_hash'],base['protocol_hash'])
            self.assertEqual(resumed['resume_from'],'job_base')

    def test_durable_batch_hash_and_question_prefix_are_checked(self):
        with self.temporary() as temporary:
            root=Path(temporary);final,raw=ready(root);sample=root/'sample'
            loader.prepare(final,sample,authorized=True,fetcher=lambda _:raw)
            jobs.prepare(final,sample,root/'base',checkpoint='base')
            manifest=seal.load(root/'base/seal.json');plan=seal.load(root/'base/plan.json')
            source=jobs.validate_payload(seal.load(root/'base/input.json'),plan,manifest)
            rows=[dict(id=r['id'],gold_answer=r['gold_answer'],freeze_sha256=manifest['freeze_sha256'],response='#### 7') for r in source[:8]]
            saved={'start':0,'rows':rows,'rows_sha256':loader.sha_bytes(loader.encoded(rows)),
                'freeze_sha256':manifest['freeze_sha256'],'protocol_hash':plan['protocol_hash']}
            self.assertEqual(len(jobs.validate_batch(saved,source,plan,manifest)),8)
            saved['rows'][0]['response']='changed'
            with self.assertRaisesRegex(ValueError,'hash changed'):jobs.validate_batch(saved,source,plan,manifest)

    def test_volume_adapter_hashes_are_checked_without_loading_a_model(self):
        with self.temporary() as temporary:
            root=Path(temporary);final,_=ready(root);manifest=seal.verify(final)
            volume=root/'volume';adapter=volume/'chosen/adapter'
            shutil.copytree(root/'chosen/adapter',adapter)
            self.assertEqual(jobs.validated_adapter(volume,manifest),adapter)
            (adapter/'adapter_model.safetensors').write_bytes(b'changed volume weights')
            with self.assertRaisesRegex(ValueError,'before final model loading'):
                jobs.validated_adapter(volume,manifest)


if __name__=='__main__':unittest.main()
