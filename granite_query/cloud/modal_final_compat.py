"""Unlaunched zero-training200-TRAIN-question PEFT compatibility producer.

There is no launch CLI. A future reviewed controller must fund, serialize and
dispatch this one bounded job and independently confirm its provider terminal.
"""
import gc
import importlib.metadata
import json
from pathlib import Path
import time
import modal

from .modal_train import image,artifacts,state
from . import final_scale_compat as compat
from . import modal_final_scale as shared
from . import final_scale_artifacts as artifact_checks
from . import granite_lora_layout as layout

ROOT=Path(__file__).resolve().parent
app=modal.App('granite-query-development-compat',include_source=False)


class Runtime(shared.Runtime):
    def begin(self,plan,descriptor,authorization,dispatch):
        if not state.put('final-compat-owner:'+plan['run_id'],{'call_id':self.call_id,'plan_sha256':plan['plan_sha256']},skip_if_exists=True):
            raise ValueError('Existing compatibility attempt must be reconciled, never repeated')
        self.intent=plan;self.proofs={};self.run_folder=shared._safe(self.root,'final-compat/'+plan['run_id'])
        self.run_folder.mkdir(parents=True,exist_ok=True);self.folder=self.run_folder
        for name,value in (('plan.json',plan),('input_descriptor.json',descriptor),('authorization.json',authorization),('dispatch.json',dispatch)):
            shared._write(self.run_folder/name,value)
        artifacts.commit()

    def status(self,stage,**details):
        value=dict(stage=stage,run_id=self.intent['run_id'],call_id=self.call_id,plan_sha256=self.intent['plan_sha256'],
            elapsed_seconds=self.elapsed(),official_test_used=False,training_performed=False,**details)
        shared._write(self.run_folder/'status.json',value,immutable=False)
        state['final-compat-status:'+self.intent['run_id']]=value;artifacts.commit()

    def select_role(self,role):
        if role not in ('base','chosen'):raise ValueError('Unknown compatibility role')
        self.role=role;self.folder=self.run_folder/'roles'/role;self.folder.mkdir(parents=True,exist_ok=True)

    def verify_assets(self,authorization):
        raw={name:importlib.metadata.version(name) for name in compat.DEPENDENCIES}
        self.dependencies={name:version.split('+',1)[0] for name,version in raw.items()}
        if self.dependencies!=compat.DEPENDENCIES:raise ValueError('Actual runtime package versions differ from pinned model image')
        self.raw_dependencies=raw
        self.source_proof=artifact_checks.verify_packaged_sources(ROOT,authorization['sealed']['contract']['protocol']['source_hashes'])
        super().verify_assets(authorization)
        self.asset_proof=json.loads((self.folder/'artifact_verification.json').read_text(encoding='utf-8'))

    def load_model(self,authorization,checkpoint,seed):
        # Explicit finite CPU values precede PEFT deserialization. The shared
        # loader then independently verifies all160 loaded parameter values.
        import torch
        from safetensors.torch import load_file
        config=json.loads(self.config_path.read_text(encoding='utf-8'))
        adapter_config=json.loads((self.adapter/'adapter_config.json').read_text(encoding='utf-8'))
        saved=load_file(str(self.adapter/'adapter_model.safetensors'),device='cpu')
        layout.validate_layout({name:list(t.shape) for name,t in saved.items()},config,adapter_config,key_format='peft_saved')
        if any(not bool(torch.isfinite(t).all()) for t in saved.values()):raise ValueError('Saved CPU adapter contains nonfinite values')
        del saved
        super().load_model(authorization,checkpoint,seed)
        loaded=json.loads((self.folder/'runtime_model_verification.json').read_text(encoding='utf-8'))
        if (loaded.get('complete_expected_layout_verified') is not True or loaded.get('tensor_count')!=160
                or loaded.get('runtime_peft_load_verified') is not True or loaded.get('runtime_adapter_values_match_sealed_file') is not True):
            raise ValueError('Actual complete PEFT layout/value verification is missing')
        self.proofs[checkpoint]={'peft_load_succeeded':True,'runtime_layout_verified':True,
            'loaded_adapter_values_verified':True,'finite_saved_cpu_values':True,
            'baseline_adapter_unloaded':loaded['baseline_adapter_unloaded'],'dependency_versions':self.dependencies,
            'raw_dependency_versions':self.raw_dependencies,'source_bundle_sha256':self.source_proof['source_bundle_sha256'],
            'model_config_sha256':self.asset_proof['model_config_sha256'],
            'adapter_inventory_sha256':self.asset_proof['adapter_inventory_sha256'],
            'adapter_model_sha256':self.asset_proof['adapter_files_sha256']['adapter_model.safetensors'],
            'tensor_count':160,'parameter_count':layout.PARAMETER_COUNT}

    def release_model(self):
        import torch
        if hasattr(self,'model'):del self.model
        if hasattr(self,'tokenizer'):del self.tokenizer
        gc.collect();torch.cuda.empty_cache()

    def finish(self,result):
        shared._write(self.run_folder/'result.json',result)
        if result.get('runtime_evidence') is not None:
            shared._write(self.run_folder/'runtime_evidence.json',result['runtime_evidence'])
        artifacts.commit()


def run_compat(plan,descriptor,authorization,dispatch,*,runtime):
    """Fakeable orchestration: no input before actual asset/PEFT/value checks."""
    compat.validate_metadata(plan,descriptor,authorization);compat.validate_dispatch(plan,authorization,dispatch)
    runtime.begin(plan,descriptor,authorization,dispatch)
    evaluations={'base':[],'chosen':[]};batches={'base':[],'chosen':[]};timings={}
    payload=None;rows=None;stage='failed';error_type=None;raw_pending=False
    try:
        for role in ('base','chosen'):
            if runtime.elapsed()>1600:stage='timed_out';break
            role_started=runtime.elapsed()
            runtime.select_role(role);runtime.status('verifying_sources_and_adapter',checkpoint=role)
            runtime.verify_assets(authorization);runtime.status('loading_model',checkpoint=role)
            runtime.load_model(authorization,role,plan['seed'])
            if payload is None:
                payload=runtime.read_input(descriptor)
                rows=compat.validate_payload(payload,plan,authorization)
            generation_seconds=0;subset_sizes=[]
            for start in range(0,200,8):
                if runtime.elapsed()>1600:stage='timed_out';break
                batch_rows=rows[start:start+8];counts=runtime.input_counts(batch_rows)
                if len(counts)!=len(batch_rows) or any(type(n) is not int or n<1 for n in counts):raise ValueError('Tokenizer lost development inputs')
                eligible=[row for row,count in zip(batch_rows,counts) if count<=1536]
                failed=False;tokens=[];elapsed=0
                if eligible:
                    before=time.monotonic()
                    try:tokens,elapsed=runtime.generate(eligible)
                    except Exception:
                        failed=True;elapsed=time.monotonic()-before
                raw={'role':compat.ROLE,'checkpoint':role,'plan_sha256':plan['plan_sha256'],'call_id':runtime.call_id,
                    'start':start,'count':len(batch_rows),'question_ids':[r['id'] for r in batch_rows],
                    'input_tokens':counts,'generated_ids':tokens,'generation_failed':failed,
                    'generation_elapsed_seconds':elapsed,'eos_token_ids':list(runtime.eos)}
                raw_pending=True
                raw_sha=runtime.write_raw(start,raw)
                derived=compat.derive_batch(rows,raw,runtime.decode)
                if raw_sha!=derived['raw_sha256']:raise ValueError('Derived development batch differs from durable raw bytes')
                runtime.write_batch(start,derived);batches[role].append(derived);evaluations[role].extend(derived['rows']);raw_pending=False
                generation_seconds+=elapsed;subset_sizes.append(len(eligible))
                runtime.status('evaluation',checkpoint=role,completed=len(evaluations[role]),requested=200)
                if failed:stage='failed';break
            timings[role]={'generation_seconds':generation_seconds,'role_wall_seconds':runtime.elapsed()-role_started,
                'actual_generation_batch_sizes':subset_sizes,'retained_count':len(evaluations[role])}
            if len(evaluations[role])!=200 or any(r['outcome']=='failed' for r in evaluations[role]):break
            runtime.release_model()
        if all(len(evaluations[r])==200 and not any(x['outcome']=='failed' for x in evaluations[r]) for r in evaluations):stage='completed'
    except Exception as error:
        stage='failed';error_type=type(error).__name__
    result={'schema_version':1,'role':compat.ROLE,'run_id':plan['run_id'],'plan_sha256':plan['plan_sha256'],
        'stage':stage,'call_id':runtime.call_id,'official_test_used':False,'training_performed':False,
        'evaluations':evaluations,'batches':batches,'runtime_evidence':None,'raw_pending':raw_pending,
        'error_type':error_type,'elapsed_seconds':runtime.elapsed(),'runtime_timings':timings}
    if stage=='completed':
        try:
            if any(timings[r]['generation_seconds']<=0 for r in ('base','chosen')):raise ValueError('Actual positive generation timing is required')
            value=authorization['sealed']['contract']
            calibration=compat.calibration_record(value,evaluations,timings,result['elapsed_seconds'])
            result['runtime_evidence']=compat.make_evidence(value,plan,authorization,call_id=runtime.call_id,
                proofs=runtime.proofs,calibration=calibration,evaluations=evaluations)
            compat.validate_result(value,plan,payload,result)
        except Exception as error:
            result.update(stage='failed',runtime_evidence=None,error_type=type(error).__name__)
    runtime.finish(result)
    return result


@app.function(image=image,gpu='A100-80GB',cpu=(4,4),memory=(32768,32768),timeout=1800,
    startup_timeout=120,retries=0,max_containers=1,min_containers=0,buffer_containers=0,
    scaledown_window=2,volumes={'/artifacts':artifacts})
def evaluate(plan:dict,descriptor:dict,authorization:dict,dispatch:dict):
    return run_compat(plan,descriptor,authorization,dispatch,runtime=Runtime())
