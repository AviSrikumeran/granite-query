from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from gradient_artifact_cache import ArtifactCache,canonical,digest


def rows():
    return ([{'id':'candidate','source_split':'train','verified_final_answer':True,'question_sha256':'a'*64,'raw_response_sha256':'b'*64}],
        [{'id':'target','source_split':'train','verified_final_answer':True,'question_sha256':'c'*64,'raw_response_sha256':'d'*64,'group':'math'}])


def cache(root,name,**extra):
    candidates,targets=rows()
    return ArtifactCache(root,name,protocol_hash='1'*64,parameter_layout_sha256='2'*64,
        projection_mapping_sha256='3'*64,dimension=2,candidates=candidates,targets=targets,**extra)


def feature(row,role='candidate',step=4):
    value={'id':row['id'],'question_sha256':row['question_sha256'],'raw_response_sha256':row['raw_response_sha256'],
        'checkpoint_id':f'update{step:03}','parameter_layout_sha256':'2'*64,'projection_mapping_sha256':'3'*64,
        'protocol_hash':'1'*64,'role':role,'gradient_type':'less_adam' if role=='candidate' else 'sgd','feature':[.25,-.75]}
    value.update(source_split='train',verified_final_answer=True)
    if role=='target':value['group']=row['group']
    value['record_sha256']=digest(canonical(value));return value


def snapshot(owner,step=4):
    base=owner.child/f'snapshots/update{step:03}';files={}
    for name in ('optimizer.pt','adapter/adapter_config.json','adapter/adapter_model.safetensors'):
        path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('fixture '+name).encode())
        files[name]=digest(path.read_bytes())
    value={'protocol_hash':'1'*64,'updates':step,'supervised_tokens':step*1024,'layout_sha256':'2'*64,'files_sha256':files}
    owner.publish_snapshot(step,value)


class ArtifactCacheTests(unittest.TestCase):
    def temporary(self):
        parent=Path(__file__).parent/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def parent(self,root):
        owner=cache(root,'parent');owner.append_feature(4,'candidate','candidate',feature(rows()[0][0]));snapshot(owner)
        return owner.seal_terminal('calibration_refused',confirmed_terminal=True,call_id='original-call',execution_sources_sha256='4'*64)

    def test_parent_json_is_lazy_cached_once_and_no_tree_is_copied(self):
        with self.temporary() as temporary:
            root=Path(temporary);parent=self.parent(root);reads=Counter()
            def reader(path):reads[path]+=1;return path.read_bytes()
            child=cache(root,'child',parent=parent,read_bytes=reader)
            self.assertEqual(child.feature_count(4,'candidate'),1)
            self.assertFalse((root/'child/features').exists())
            first=child.feature(4,'candidate','candidate');first['feature'][0]=999
            self.assertEqual(child.feature(4,'candidate','candidate')['feature'],[.25,-.75])
            self.assertTrue(all(count==1 for count in reads.values()))
            self.assertEqual(child.snapshot(4)['run_id'],'parent')
            self.assertEqual(child.snapshot(4)['run_id'],'parent')
            self.assertTrue(all(count==1 for count in reads.values()))
            self.assertFalse((root/'child/snapshots').exists())

    def test_child_appends_only_missing_features_and_keeps_parent_bytes_unchanged(self):
        with self.temporary() as temporary:
            root=Path(temporary);parent=self.parent(root)
            before={p.relative_to(root/'parent'):p.read_bytes() for p in (root/'parent').rglob('*') if p.is_file()}
            child=cache(root,'child',parent=parent)
            child.append_feature(4,'candidate','candidate',feature(rows()[0][0]))
            self.assertFalse((root/'child/features').exists())
            child.append_feature(4,'target','target',feature(rows()[1][0],'target'))
            value=feature(rows()[0][0]);value['feature']=[1,1];value['record_sha256']=digest(canonical({k:v for k,v in value.items() if k!='record_sha256'}))
            with self.assertRaisesRegex(ValueError,'overwrite'):child.append_feature(4,'candidate','candidate',value)
            link=child.seal_terminal('completed',confirmed_terminal=True,call_id='child-call',execution_sources_sha256='5'*64)
            grandchild=cache(root,'grandchild',parent=link)
            self.assertEqual(grandchild.feature_count(4,'candidate'),1);self.assertEqual(grandchild.feature_count(4,'target'),1)
            self.assertEqual(before,{p.relative_to(root/'parent'):p.read_bytes() for p in (root/'parent').rglob('*') if p.is_file()})
            with self.assertRaisesRegex(ValueError,'read-only'):child.append_feature(8,'candidate','candidate',feature(rows()[0][0],step=8))

    def test_wrong_protocol_pool_manifest_hash_and_depth_are_rejected(self):
        with self.temporary() as temporary:
            root=Path(temporary);parent=self.parent(root)
            candidates,targets=rows();candidates[0]['raw_response_sha256']='e'*64
            with self.assertRaisesRegex(ValueError,'protocol/pool'):
                ArtifactCache(root,'wrong-pool',protocol_hash='1'*64,parameter_layout_sha256='2'*64,
                    projection_mapping_sha256='3'*64,dimension=2,candidates=candidates,targets=targets,parent=parent)
            candidates,targets=rows()
            with self.assertRaisesRegex(ValueError,'protocol/pool'):
                ArtifactCache(root,'wrong-protocol',protocol_hash='9'*64,parameter_layout_sha256='2'*64,
                    projection_mapping_sha256='3'*64,dimension=2,candidates=candidates,targets=targets,parent=parent)
            with self.assertRaisesRegex(ValueError,'hash changed'):cache(root,'bad-hash',parent=dict(parent,manifest_sha256='0'*64))
            child=cache(root,'child',parent=parent);link=child.seal_terminal('bounded_stop',confirmed_terminal=True,call_id='c',execution_sources_sha256='4'*64)
            with self.assertRaisesRegex(ValueError,'bounded depth'):cache(root,'too-deep',parent=link,max_depth=1)

    def test_feature_and_snapshot_mutation_are_detected_before_use(self):
        with self.temporary() as temporary:
            root=Path(temporary);parent=self.parent(root)
            path=next((root/'parent/features').rglob('*.json'));path.write_bytes(path.read_bytes()+b' ')
            child=cache(root,'child',parent=parent)
            with self.assertRaisesRegex(ValueError,'JSON hash changed'):child.feature(4,'candidate','candidate')
        with self.temporary() as temporary:
            root=Path(temporary);parent=self.parent(root)
            (root/'parent/snapshots/update004/optimizer.pt').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'snapshot file changed'):cache(root,'child',parent=parent).snapshot(4)

    def test_terminal_proof_and_path_escape_are_required(self):
        with self.temporary() as temporary:
            root=Path(temporary);owner=cache(root,'child')
            with self.assertRaisesRegex(ValueError,'confirmed terminal'):
                owner.seal_terminal('completed',confirmed_terminal=False,call_id='c',execution_sources_sha256='4'*64)
            with self.assertRaisesRegex(ValueError,'run identity'):cache(root,'../parent')
            with self.assertRaisesRegex(ValueError,'Unsafe artifact'):
                owner._path('child','../outside.json')

    def test_existing_terminal_outputs_are_indexed_without_copying_or_rebinding(self):
        with self.temporary() as temporary:
            root=Path(temporary);legacy=cache(root,'legacy')
            legacy.append_feature(4,'candidate','candidate',feature(rows()[0][0]));snapshot(legacy)
            before={p.relative_to(legacy.child):p.read_bytes() for p in legacy.child.rglob('*') if p.is_file()}
            auditor=cache(root,'legacy')
            with self.assertRaisesRegex(ValueError,'confirmed terminal'):auditor.index_existing_terminal()
            counts=auditor.index_existing_terminal(confirmed_terminal=True)
            self.assertEqual(counts,{'local_features':1,'local_snapshots':1,'files_copied':0})
            link=auditor.seal_terminal('bounded_stop',confirmed_terminal=True,call_id='legacy-call',execution_sources_sha256='4'*64)
            child=cache(root,'child',parent=link)
            self.assertEqual(child.feature(4,'candidate','candidate')['feature'],[.25,-.75])
            self.assertTrue(all((legacy.child/relative).read_bytes()==value for relative,value in before.items()))


if __name__=='__main__':unittest.main()
