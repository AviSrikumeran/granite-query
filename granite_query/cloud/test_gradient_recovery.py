import json
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace
import gradient_feature_control as control
from cloud import gradient_recovery as recovery
from cloud.gradient_feature_contract import canonical,sha,fixed_config
import test_gradient_features as fixtures


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canonical(value))


def fixture(folder,*,first_count=28,later_count=16,include_final_snapshot=True,later_seconds=.4):
    toy=fixtures.FeatureTests();toy.config=fixed_config();data,plan=toy.payload();plan['run_id']=folder.name
    folder.mkdir();write(folder/'plan.json',plan);write(folder/'input.json',data)
    write(folder/'launch.json',{'call_id':'fixture-call'});write(folder/'terminal.json',{
        'stage':'calibration_refused','call_id':'fixture-call','confirmed_terminal':True})
    write(folder/'cohort_manifest.json',{'fixture':True})
    for name in ('candidates.jsonl','targets.jsonl'):(folder/name).write_text('{}\n')
    source_hashes={}
    for name in recovery.SOURCE_FILES:
        target=folder/'execution_sources'/name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(recovery.ROOT/name,target);source_hashes[name]=recovery.file_sha(target)
    write(folder/'execution_sources.json',{'protocol_hash':plan['protocol_hash'],'call_id':'fixture-call',
        'files_sha256':source_hashes,'capture_timing':'Synthetic fixture capture'})
    root=folder/'recovery_artifacts';root.mkdir();write(root/'plan.json',plan)
    layout=[{'name':'fixture-lora','shape':[2621440],'numel':2621440}];layout_hash=sha(canonical(layout))
    write(root/'parameter_layout.json',{'layout':layout,'sha256':layout_hash,'parameters':2621440})
    write(root/'projection.json',{'parameter_layout_sha256':layout_hash,'mapping_sha256':'b'*64,
        'dimension':1024,'seed':plan['protocol']['config']['projection_seed'],'family':'countsketch_shake256_v1'})
    binary={}
    for step in (4,8):
        if step==8 and not include_final_snapshot:continue
        base=root/f'snapshots/update{step:03}';write(base/'adapter/adapter_config.json',{'fixture':True})
        files={'optimizer.pt':'c'*64,'adapter/adapter_config.json':recovery.file_sha(base/'adapter/adapter_config.json'),
            'adapter/adapter_model.safetensors':'d'*64}
        binary.update({f'snapshots/update{step:03}/'+name:value for name,value in files.items() if not name.endswith('.json')})
        write(base/'READY.json',{'protocol_hash':plan['protocol_hash'],'updates':step,'supervised_tokens':step*1024,
            'layout_sha256':layout_hash,'files_sha256':files})
    for step,count in ((4,first_count),(8,later_count)):
        ordered=[('candidate',r) for r in data['candidates']]+[('target',r) for r in data['targets']]
        if step==8:
            ids=set(data['calibration_ids'])
            ordered=[('candidate',r) for r in data['candidates'] if r['id'] in ids]+[pair for pair in ordered if pair[1]['id'] not in ids]
        for role,row in ordered[:count]:
            value={'id':row['id'],'question_sha256':row['question_sha256'],'raw_response_sha256':row['raw_response_sha256'],
                'checkpoint_id':f'update{step:03}','parameter_layout_sha256':layout_hash,'projection_mapping_sha256':'b'*64,
                'protocol_hash':plan['protocol_hash'],'role':role,'gradient_type':'less_adam' if role=='candidate' else 'sgd',
                'elapsed_seconds':later_seconds if step==8 else .4,'feature':[1.0]+[0.0]*1023}
            value['record_sha256']=sha(canonical(value))
            write(root/f'features/update{step:03}/{role}/{sha(row["id"].encode())}.json',value)
    write(root/'calibration.json',{'protocol_hash':plan['protocol_hash'],'checkpoint_id':'update008',
        'decision':'refuse_full_collection','actual_samples':16,'margin':1.25,
        'mean_seconds':later_seconds,'p75_seconds':later_seconds})
    write(root/'result.json',{'stage':'calibration_refused','protocol_hash':plan['protocol_hash'],
        'public_summary':{'completed_features':first_count+later_count,'total_features':56}})
    hashes={p.relative_to(root).as_posix():recovery.file_sha(p) for p in root.rglob('*.json')};hashes.update(binary)
    write(folder/'recovery_remote_manifest.json',{'call_id':'fixture-call','protocol_hash':plan['protocol_hash'],
        'terminal_stage':'calibration_refused','files_sha256':hashes})
    return data,plan


class GradientRecoveryTests(unittest.TestCase):
    def temporary(self):
        parent=recovery.ROOT/'runs/local_check_tmp';parent.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def test_full_earlier_checkpoint_and_partial_later_can_continue_without_replay(self):
        with self.temporary() as temporary:
            root=Path(temporary);folder=root/'original';_,previous=fixture(folder)
            decision=recovery.assess_continuation(folder)
            self.assertEqual(decision['completed_features'],44);self.assertEqual(decision['remaining_features'],12)
            self.assertLess(decision['forecast_fresh_call_seconds'],1550)
            resumed=control.prepare_resume(folder,root/'resume')
            self.assertEqual(resumed['protocol'],previous['protocol'])
            self.assertEqual(resumed['protocol_hash'],previous['protocol_hash'])
            self.assertFalse(resumed['reviewed_for_launch'])
            self.assertTrue((root/'resume/recovery_decision.json').exists())
            self.assertEqual(recovery.file_sha(root/'resume/execution_sources.json'),recovery.file_sha(folder/'execution_sources.json'))
            self.assertFalse((root/'resume/launch.json').exists())
            recovery.verify_execution_sources(root/'resume')
            write(root/'resume/launch.json',{'call_id':'fixture-new-call'})
            recovery.verify_execution_sources(root/'resume')

    def test_initial_calibration_only_or_incomplete_first_checkpoint_is_insufficient(self):
        for earlier,later,final_snapshot in ((16,0,False),(27,16,True)):
            with self.temporary() as temporary:
                folder=Path(temporary)/'original';fixture(folder,first_count=earlier,later_count=later,include_final_snapshot=final_snapshot)
                with self.assertRaises(ValueError):recovery.assess_continuation(folder)

    def test_no_final_snapshot_unfit_remaining_and_changed_source_are_refused(self):
        for condition in ('snapshot','runtime','source'):
            with self.temporary() as temporary:
                folder=Path(temporary)/'original'
                fixture(folder,include_final_snapshot=condition!='snapshot',later_seconds=100 if condition=='runtime' else .4)
                if condition=='source':(folder/'execution_sources/modal_gradient_features.py').write_text('changed source')
                with self.assertRaises(ValueError):recovery.assess_continuation(folder)

    def test_unconfirmed_call_or_changed_snapshot_hash_cannot_continue(self):
        with self.temporary() as temporary:
            folder=Path(temporary)/'original';fixture(folder)
            write(folder/'terminal.json',{'stage':'calibration_refused','call_id':'different','confirmed_terminal':True})
            with self.assertRaisesRegex(ValueError,'exact feature call'):recovery.assess_continuation(folder)
        with self.temporary() as temporary:
            folder=Path(temporary)/'original';fixture(folder)
            inventory=recovery.read(folder/'recovery_remote_manifest.json')
            inventory['files_sha256']['snapshots/update008/optimizer.pt']='0'*64
            write(folder/'recovery_remote_manifest.json',inventory)
            with self.assertRaisesRegex(ValueError,'checkpoint file missing or changed'):recovery.assess_continuation(folder)

    def test_bounded_evidence_reader_uses_authenticated_cache_without_gpu_work(self):
        with self.temporary() as temporary:
            folder=Path(temporary)/'original';fixture(folder);root=folder/'recovery_artifacts'
            (folder/'recovery_remote_manifest.json').unlink()
            for step in (4,8):
                base=root/f'snapshots/update{step:03}';ready=recovery.read(base/'READY.json')
                for name in ('optimizer.pt','adapter/adapter_model.safetensors'):
                    path=base/name;path.write_bytes(f'opaque fixture checkpoint {step} {name}'.encode())
                    ready['files_sha256'][name]=recovery.file_sha(path)
                write(base/'READY.json',ready)
            files={folder.name+'/'+p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            calls=[]
            class FakeVolume:
                def listdir(self,path,recursive=True):
                    return [SimpleNamespace(path=name,size=len(raw),mtime=1,type=1) for name,raw in files.items()]
                def read_file(self,path):
                    calls.append(path);yield files[path]
            result=recovery.download_evidence(folder,volume=FakeVolume())
            self.assertEqual(result['stage'],'same_protocol_continuation_permitted')
            count=len(calls)
            self.assertGreater(count,44)
            self.assertTrue(recovery.download_evidence(folder,volume=FakeVolume())['existing'])
            self.assertEqual(len(calls),count)
            self.assertTrue((folder/'recovery_read_receipts').exists())


if __name__=='__main__':unittest.main()
