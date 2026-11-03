import copy
import json
from pathlib import Path
import tempfile
import unittest

import gradient_feature_contract as contract
import gradient_feature_control as control
import gradient_valuation as scoring


class FakeTokenizer:
    eos_token='<eos>'
    chat_template='test-only-template'
    def apply_chat_template(self,messages,**kwargs):
        return '<user> '+messages[0]['content']+' <assistant>'
    def __call__(self,text,**kwargs):
        return {'input_ids':list(range(1,len(text.split())+1))}


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent/'runs')
        self.root=Path(self.temp.name)
        self.config=contract.fixed_config()

    def tearDown(self):
        self.temp.cleanup()

    def row(self,index,target=False):
        row=dict(id=f'train:{index}',source_split='train',prompt=f'Item {index} costs dollars.',
                 response='A complete calculation. #### 13',gold_answer='13',
                 teacher_model='deepseek-v4-pro',teacher_revision='fixture',
                 generation={'prompt_version':'fixture','settings':{}},
                 prefix_ids=[1,2,3],answer_ids=[4,5,6,7,8],verified_final_answer=True,
                 question_sha256=contract.sha(str(index).encode()),raw_response_sha256=contract.sha(b'response'),
                 reference_match_is_independent_gold=True)
        if target:
            row['group']='cost_accounting'
        return row

    def payload(self):
        candidates=[self.row(i) for i in range(24)]
        targets=[self.row(100+i,True) for i in range(4)]
        data=dict(candidates=candidates,targets=targets,warmup=contract.build_warmup(candidates,self.config),
                  calibration_ids=contract.calibration_ids(candidates,16))
        protocol=dict(config=self.config,input_sha256=contract.sha(contract.canonical(data)),
                      candidate_ids=[r['id'] for r in candidates],target_ids=[r['id'] for r in targets])
        plan=dict(run_id='test-feature-v1',protocol=protocol,protocol_hash=contract.sha(contract.canonical(protocol)))
        return data,plan

    def test_exact_warmup_masks_and_repeated_exposures(self):
        data,plan=self.payload()
        self.assertEqual(contract.validate_input(data,plan),self.config)
        self.assertEqual(len(data['warmup']['updates']),8)
        by_id={r['id']:r for r in data['candidates']}
        count=0; passes=[]
        for update in data['warmup']['updates']:
            self.assertEqual(update['supervised_tokens'],1024)
            self.assertAlmostEqual(sum(w['loss_weight'] for w in update['microbatches']),1)
            for window in update['microbatches']:
                row=by_id[window['id']]
                labels=contract.labels_for(row,window['answer_start'],window['answer_end'])
                self.assertTrue(all(x==-100 for x in labels[:len(row['prefix_ids'])]))
                count+=sum(x!=-100 for x in labels); passes.append(window['exposure_pass'])
        self.assertEqual(count,8192)
        self.assertGreater(max(passes),0)

    def test_countsketch_is_deterministic_linear_and_uses_no_dense_matrix(self):
        a,b=[1.,2.,-3.,4.],[3.,-2.,6.,1.]
        actual=contract.countsketch_reference(a,16,7)
        self.assertEqual(actual,contract.countsketch_reference(a,16,7))
        added=contract.countsketch_reference([x+y for x,y in zip(a,b)],16,7)
        other=contract.countsketch_reference(b,16,7)
        self.assertEqual(added,[x+y for x,y in zip(actual,other)])
        buckets,signs,digest=contract.countsketch_mapping(4,16,7)
        self.assertEqual(len(buckets),4); self.assertEqual(len(signs),4)
        self.assertEqual(len(contract.mapping_bytes(4,7)),20)
        self.assertEqual(contract.mapping_bytes(4,7),contract.mapping_bytes(100,7)[:20])

    def test_resume_and_feature_identities_cannot_change(self):
        data,plan=self.payload(); other=copy.deepcopy(plan)
        other['run_id']='new-resume'
        contract.validate_resume(plan,other)
        other['protocol']['candidate_ids'][0]='changed'
        with self.assertRaises(ValueError):
            contract.validate_resume(plan,other)
        row=data['candidates'][0]
        feature=dict(id=row['id'],question_sha256=row['question_sha256'],raw_response_sha256=row['raw_response_sha256'],
            checkpoint_id='update004',parameter_layout_sha256='a'*64,projection_mapping_sha256='b'*64,feature=[1,0])
        feature['record_sha256']=contract.sha(contract.canonical(feature))
        contract.validate_feature(feature,row,'update004','a'*64,'b'*64,2)
        with self.assertRaises(ValueError):
            contract.validate_feature(feature,row,'update008','a'*64,'b'*64,2)
        with self.assertRaises(ValueError):
            contract.validate_feature(feature,row,'update004','a'*64,'c'*64,2)
        feature['feature'][0]=.5
        with self.assertRaises(ValueError):
            contract.validate_feature(feature,row,'update004','a'*64,'b'*64,2)

    def test_rejects_test_overlap_mutated_masks_and_resource_changes(self):
        for change in ('test','overlap','mask','gpu'):
            data,plan=self.payload()
            if change=='test':
                data['targets'][0]['source_split']='test'
            elif change=='overlap':
                data['targets'][0]['question_sha256']=data['candidates'][0]['question_sha256']
            elif change=='mask':
                data['warmup']['updates'][0]['microbatches'][0]['answer_start']=1
            else:
                plan['protocol']['config']['cpu_cores']=8
            plan['protocol']['input_sha256']=contract.sha(contract.canonical(data))
            plan['protocol_hash']=contract.sha(contract.canonical(plan['protocol']))
            with self.assertRaises(ValueError,msg=change):
                contract.validate_input(data,plan)

    def test_prepare_refuses_growing_pool_and_freezes_new_disjoint_cohort(self):
        pool=self.root/'teacher'; pool.mkdir()
        control.write_new(pool/'teacher_summary.json',dict(stage='running',official_test_accessed=False,eligible=48))
        with self.assertRaises(ValueError):
            control.prepare(pool,self.root/'not-prepared',tokenizer=FakeTokenizer())
        control.save(pool/'teacher_summary.json',dict(stage='completed',official_test_accessed=False,eligible=48,run_id='toy'))
        rows=[]
        for index in range(48):
            row=self.row(index)
            row['reference_type']='human_dataset_answer'
            for key in ('prefix_ids','answer_ids','question_sha256','raw_response_sha256'):
                del row[key]
            rows.append(row)
        (pool/'eligible.jsonl').write_bytes(b''.join(contract.canonical(r) for r in rows))
        output=self.root/'new-feature-cohort'
        plan=control.prepare(pool,output,tokenizer=FakeTokenizer())
        data=control.read(output/'input.json')
        self.assertEqual(len(data['candidates']),24); self.assertEqual(len(data['targets']),24)
        self.assertFalse({r['id'] for r in data['candidates']}&{r['id'] for r in data['targets']})
        self.assertFalse(plan['reviewed_for_launch'])
        self.assertFalse((output/'launch.json').exists())
        with self.assertRaises(FileExistsError):
            control.prepare(pool,output,tokenizer=FakeTokenizer())

    def test_scoring_explicitly_accepts_adapted_projection_family(self):
        from test_gradient_valuation import GradientTests
        payload=GradientTests().payload()
        payload['projection']['family']=contract.PROJECTION_FAMILY
        result=scoring.score_projected(payload)
        self.assertEqual(result[0]['id'],'a:aligned')


if __name__=='__main__':
    unittest.main()
