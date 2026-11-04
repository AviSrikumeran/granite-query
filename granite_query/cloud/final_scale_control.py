"""Versioned final-scale controller. Inspection is metadata-only by default.

No command here chooses a checkpoint, invents a review, or bypasses the single
global test owner. Production use still needs actual reviewed source/weight
inventories, runtime compatibility evidence and whole-bundle funding.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from cloud import final_scale_contract as contract_api
from cloud import final_scale_funding as funding
from cloud import final_scale_loader as loader
from cloud import final_scale_seal as seal
from cloud import final_scale_receipts as receipts

ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'runs'
STATE=PRIVATE/'supervisor'
MAX_JSON=24*1024*1024
VERSION='final-scale-controller-v1'


def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return contract_api.digest(value)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe(path):
    path=Path(os.path.abspath(path));root=Path(os.path.abspath(PRIVATE))
    if not path.is_relative_to(root) or path==root:
        raise ValueError('Controller outputs must remain in a distinct ignored run directory')
    for name in path.relative_to(root).parts:
        stem=name.split('.')[0].upper()
        if (name.endswith(('.', ' ')) or stem in {'CON','PRN','AUX','NUL'}
                or re.fullmatch(r'(COM|LPT)[1-9]',stem)):
            raise ValueError('Ambiguous or reserved private path component')
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():
            raise ValueError('Linked controller paths are forbidden')
        if part==root:break
    return path


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def read(path):
    path=safe(path)
    if not path.is_file() or path.stat().st_size>MAX_JSON:raise ValueError('Missing or oversized private JSON')
    return json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=_pairs,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def write(path,value,*,immutable=False):
    path=safe(path);data=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()
    if len(data)>MAX_JSON:raise ValueError('Private JSON exceeds its bound')
    path.parent.mkdir(parents=True,exist_ok=True)
    if immutable:
        try:
            with path.open('xb') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
        except FileExistsError:
            if read(path)!=value:raise ValueError('Immutable controller artifact changed')
    else:
        temp=safe(path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending'))
        with temp.open('xb') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
        temp.replace(path)


def write_bytes(path,data):
    path=safe(path)
    if not isinstance(data,bytes) or len(data)>MAX_JSON:raise ValueError('Invalid bounded raw receipt')
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
    except FileExistsError:
        if path.read_bytes()!=data:raise ValueError('Original immutable bytes changed')


def upload_immutable(volume,files):
    """Idempotent known-byte staging; refuse conflicting existing Volume data."""
    pending=[]
    for source,remote in files:
        source=safe(source)
        expected=sha(source);size=source.stat().st_size;hasher=hashlib.sha256();seen=0
        try:
            for part in volume.read_file(remote):
                seen+=len(part)
                if seen>size:raise ValueError('Existing remote artifact exceeds the sealed bytes')
                hasher.update(part)
        except FileNotFoundError:pending.append((source,remote));continue
        if seen!=size or hasher.hexdigest()!=expected:raise ValueError('Existing remote artifact conflicts with immutable bundle')
    if pending:
        # A concurrent creator causes a conflict, never an overwrite. Preserve
        # the parent claim for reconciliation rather than retry transmission.
        with volume.batch_upload(force=False) as batch:
            for source,remote in pending:batch.put_file(str(source),remote)


@contextmanager
def exclusive(path):
    path=safe(path);token=uuid.uuid4().hex
    with path.open('x',encoding='ascii') as handle:handle.write(token);handle.flush();os.fsync(handle.fileno())
    try:yield
    finally:
        # Never delete a lease that was replaced by an unknown owner.
        if path.exists() and not path.is_symlink() and path.read_text(encoding='ascii')==token:path.unlink()


def source_review(sealed,review):
    expected={'reviewed','controller_sha256','freeze_sha256','seal_sha256',
        'source_bundle_sha256','preaccess_runtime_evidence_path','preaccess_runtime_evidence_sha256'}
    if (not isinstance(review,dict) or set(review)!=expected or review['reviewed'] is not True
            or review['controller_sha256']!=sha(__file__) or review['freeze_sha256']!=sealed['contract']['freeze_sha256']
            or review['seal_sha256']!=sealed['seal_sha256']
            or review['source_bundle_sha256']!=digest(sealed['contract']['protocol']['source_hashes'])
            or sealed['contract']['protocol']['source_hashes'].get(Path(__file__).name)!=sha(__file__)
            or Path(__file__).name not in sealed['contract']['protocol']['source_roles']['contract']):
        raise ValueError('Reviewed exact controller/source/seal evidence is required')
    required={'contract':('final_scale_control.py','final_scale_funding.py','deepseek_reconcile.py'),
        'checkpoint_validator':('final_scale_artifacts.py','granite_lora_layout.py'),
        'granite_executor':('final_scale_compat.py','modal_final_compat.py')}
    for role,names in required.items():
        for name in names:
            if (name not in sealed['contract']['protocol']['source_roles'][role]
                    or sealed['contract']['protocol']['source_hashes'].get(name)!=sha(ROOT/name)):
                raise ValueError('Controller accounting/artifact dependency is not physically source bound')
    contract_api.require_hash(review['preaccess_runtime_evidence_sha256'])
    return review


def runtime_evidence(sealed,review):
    """Require hash-bound development-only reload evidence before source access.

    This does not retrofit byte identity into earlier development runs. The
    evidence must be produced after hashing the actual selected adapter.
    """
    path=safe(review['preaccess_runtime_evidence_path'])
    if sha(path)!=review['preaccess_runtime_evidence_sha256']:raise ValueError('Runtime evidence bytes changed')
    evidence=read(path);value={k:v for k,v in evidence.items() if k!='evidence_sha256'}
    selected=sealed['contract']['protocol']['selected']
    from cloud import granite_lora_layout as layout_policy
    expected_dependencies={'torch':'2.6.0','transformers':'4.57.1','peft':'0.17.1',
        'accelerate':'1.10.1','safetensors':'0.6.2'}
    if (evidence.get('evidence_sha256')!=digest(value) or evidence.get('role')!='development_runtime_compatibility'
            or evidence.get('official_test_used') is not False or evidence.get('training_performed') is not False
            or evidence.get('model')!=contract_api.MODEL or evidence.get('revision')!=contract_api.REVISION
            or evidence.get('adapter_inventory_sha256')!=selected['adapter_inventory_sha256']
            or evidence.get('peft_load_succeeded') is not True or evidence.get('runtime_layout_verified') is not True
            or evidence.get('loaded_adapter_values_verified') is not True
            or evidence.get('source_bundle_sha256')!=digest(sealed['contract']['protocol']['source_hashes'])
            or evidence.get('model_config_sha256')!=layout_policy.EVIDENCE['local_config']['sha256']
            or evidence.get('adapter_model_sha256')!=sealed['checkpoint']['adapter_files_sha256']['adapter_model.safetensors']
            or evidence.get('layout_policy_version')!=layout_policy.VERSION
            or evidence.get('model_image_source_sha256')!=sealed['contract']['protocol']['source_hashes'].get('modal_train.py')
            or evidence.get('dependency_versions')!=expected_dependencies
            or evidence.get('inference_sha256')!=digest(sealed['contract']['protocol']['inference'])
            or evidence.get('development_count')!=200 or evidence.get('stage')!='completed'):
        raise ValueError('Actual hashed-adapter development reload evidence remains missing')
    terminal=read(path.with_name('provider_terminal.json'))
    result=read(path.with_name('provider_result.json'))
    if (terminal.get('confirmed_terminal') is not True or terminal.get('kind')!='completed'
            or not re.fullmatch(r'fc-[A-Za-z0-9-]+',str(terminal.get('call_id','')))
            or terminal.get('call_id')!=evidence.get('call_id') or result.get('runtime_evidence')!=evidence
            or terminal.get('result_sha256')!=sha(path.with_name('provider_result.json'))):
        raise ValueError('Provider-confirmed development reload result is required')
    from cloud import final_scale_compat as compatibility
    compatibility.validate_result(sealed['contract'],read(path.with_name('plan.json')),read(path.with_name('input.json')),result)
    if evidence.get('calibration',{}).get('runtime_feasible') is not True:
        raise ValueError('Actual paired development runtime does not support the frozen shards')
    return evidence


def prepare_bundle(seal_folder,input_folder,output,*,review_path,model_config_path):
    """Local metadata only. Does not reserve, load final rows or create permits."""
    seal_folder,input_folder,output=map(safe,(seal_folder,input_folder,output))
    if output.exists():raise FileExistsError('Use a new immutable bundle output')
    if not contract_api.NAME.fullmatch(output.name) or len(output.name)>90:raise ValueError('Bundle ID leaves insufficient room for immutable shard run IDs')
    if output.is_relative_to(STATE) or STATE.is_relative_to(output):raise ValueError('Bundle overlaps supervisor state')
    sealed=seal.verify(seal_folder);review=source_review(sealed,read(review_path))
    runtime_evidence(sealed,review)
    # Reuse loader destination policy before any controller directory write.
    seal._destination(seal_folder,sealed,input_folder)
    for protected in (seal_folder,input_folder,safe(sealed['checkpoint']['run_path'])):
        if output.is_relative_to(protected) or protected.is_relative_to(output):raise ValueError('Bundle overlaps seal/input/development artifacts')
    from cloud import final_scale_artifacts as artifacts
    config=safe(model_config_path)
    adapter=artifacts.verify_adapter(sealed['checkpoint']['adapter_path'],sealed['checkpoint']['adapter_files_sha256'],model_config_path=config)
    bundle={'schema_version':1,'version':VERSION,'bundle_id':output.name,'seal_folder':str(seal_folder),
        'input_folder':str(input_folder),'seal_sha256':sealed['seal_sha256'],'freeze_sha256':sealed['contract']['freeze_sha256'],
        'review':review,'model_config_path':str(config),'model_config_sha256':sha(config),
        'adapter_validation_sha256':digest(adapter),'stage':'prepared_metadata_only_not_funded'}
    output.mkdir(parents=True);write(output/'bundle.json',bundle,immutable=True)
    return {'stage':bundle['stage'],'official_test_accessed':False,'paid_work_launched':False}


class Backend:
    """All provider effects are behind explicit controller actions/test doubles."""
    def refresh(self,state):
        if state.resolve()!=STATE.resolve():raise ValueError('Production provider helpers require normal state')
        for service,script in (('modal','budget_reconcile.py'),('deepseek','deepseek_reconcile.py')):
            process=subprocess.run([sys.executable,'-X','utf8',str(ROOT/script),'--refresh'],cwd=ROOT.parent,
                capture_output=True,timeout=60,env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'))
            write(state/('final_scale_refresh_'+service+'.private.json'),{'at_utc':now(),'code':process.returncode,
                'stdout':process.stdout.decode('utf-8',errors='replace'),'stderr':process.stderr.decode('utf-8',errors='replace')})
            if process.returncode:raise RuntimeError('Supported funding observation failed; no automatic retry')

    def apps(self):
        process=subprocess.run([sys.executable,'-m','modal','app','list','--json'],capture_output=True,timeout=30,
            check=True,env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'))
        return json.loads(process.stdout.decode('utf-8'))

    def stage(self,folder,bundle):
        from cloud import final_scale_execution as execution
        descriptor=read(folder/'input_descriptor.json');authorization=read(folder/'authorization.json')
        intent=read(folder/'intent.json')
        execution.validate_remote_metadata(intent,descriptor,authorization)
        execution.validate_inputs(intent,authorization,read(folder/'payload.json'))
        if (intent['bundle_id']!=bundle['bundle_id'] or authorization['sealed']['seal_sha256']!=bundle['seal_sha256']
                or descriptor['volume_path'].split('/')[0]!=bundle['bundle_id']):
            raise ValueError('Staged upload is outside the reviewed bundle')
        payload=folder/'payload.json';config=safe(bundle['model_config_path'])
        if (sha(payload)!=descriptor['sha256'] or sha(config)!=authorization['model_config']['sha256']
                or config.stat().st_size!=authorization['model_config']['bytes']):
            raise ValueError('Staged payload/config bytes changed')
        import modal
        volume=modal.Volume.from_name('granite-query-training-artifacts',create_if_missing=False)
        files=[(payload,descriptor['volume_path']),(config,authorization['model_config']['volume_path'])]
        checkpoint=authorization['sealed']['checkpoint'];adapter=safe(checkpoint['adapter_path'])
        for name,expected in checkpoint['adapter_files_sha256'].items():
            source=safe(adapter/name)
            if not source.is_relative_to(adapter) or sha(source)!=expected:raise ValueError('Sealed adapter changed before staging')
            files.append((source,authorization['adapter_path']+'/'+name))
        upload_immutable(volume,files)

    def launch(self,folder):
        args=[sys.executable,'-X','utf8','-m','modal','run','--detach','-m','cloud.modal_final_scale','--job-folder',str(folder)]
        try:
            process=subprocess.run(args,cwd=ROOT.parent,capture_output=True,timeout=180,
                env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',MODAL_IMAGE_BUILDER_VERSION='2025.06'))
            out,err,code=process.stdout,process.stderr,process.returncode
        except subprocess.TimeoutExpired as error:out,err,code=error.stdout or b'',error.stderr or b'',None
        (folder/'launch.stdout.private.log').write_bytes(out);(folder/'launch.stderr.private.log').write_bytes(err)
        app=re.search(rb'ap-[A-Za-z0-9]+',out+b'\n'+err)
        return {'return_code':code,'app_id':app.group().decode() if app else None}

    def poll(self,folder,call_id):
        import modal
        from cloud import final_scale_execution as execution
        try:result=modal.FunctionCall.from_id(call_id).get(timeout=0);kind='completed'
        except TimeoutError:return {'kind':'running'}
        except (modal.exception.FunctionTimeoutError,modal.exception.UserCodeException) as error:
            result=None;kind='timed_out' if isinstance(error,modal.exception.FunctionTimeoutError) else 'failed'
        except Exception as error:return {'kind':'monitoring_error','error_type':type(error).__name__}
        volume=modal.Volume.from_name('granite-query-training-artifacts',create_if_missing=False)
        remote=execution.remote_directory(read(folder/'intent.json'))
        # Provider termination precedes any canonical terminal receipt. Preserve
        # orphan raw batches too; never discard them to make a paid resume fit.
        for sub in ('raw','batches'):
            try:entries=list(volume.iterdir(remote+'/'+sub))
            except FileNotFoundError:entries=[]
            if len(entries)>46:raise ValueError('Remote shard file count exceeds its bound')
            for entry in entries:
                name=Path(entry.path).name
                if not re.fullmatch(r'batch[0-9]{4}\.json',name):raise ValueError('Unexpected remote batch artifact')
                raw=b''.join(volume.read_file(entry.path))
                if len(raw)>MAX_JSON:raise ValueError('Oversized remote receipt')
                json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs)
                write_bytes(folder/sub/name,raw)
        return {'kind':kind,'result':result,'provider_call_id':call_id,'observed_at_utc':now()}

    def lookup(self,intent):
        import modal
        state=modal.Dict.from_name('granite-query-training-progress',create_if_missing=False)
        value=state.get('final-scale-owner:'+intent['run_id'],None)
        if value is None:return None
        from cloud import final_scale_execution as execution
        if (not isinstance(value,dict) or value.get('intent_sha256')!=intent['intent_sha256']
                or value.get('remote_directory')!=execution.remote_directory(intent)
                or not receipts.CALL.fullmatch(str(value.get('call_id','')))):
            raise ValueError('Remote owner does not match the unique dispatch intent')
        return value


class Controller:
    def __init__(self,output,*,state=None,backend=None,clock=now,decoder=None):
        self.output=safe(output);self.state=safe(state or STATE);self.backend=backend or Backend();self.clock=clock
        self.decoder=decoder

    def decode(self,ids):
        if self.decoder is None:
            from transformers import AutoTokenizer
            tokenizer=AutoTokenizer.from_pretrained(contract_api.MODEL,revision=contract_api.REVISION,
                cache_dir=ROOT/'runs/tokenizer_cache',local_files_only=True)
            self.decoder=lambda tokens:tokenizer.decode(tokens,skip_special_tokens=True)
        return self.decoder(ids)

    def load(self):
        bundle=read(self.output/'bundle.json')
        if bundle.get('version')!=VERSION or bundle.get('bundle_id')!=self.output.name:raise ValueError('Unknown bundle identity')
        sealed=seal.verify(bundle['seal_folder']);source_review(sealed,bundle['review']);runtime_evidence(sealed,bundle['review'])
        if bundle['seal_sha256']!=sealed['seal_sha256'] or bundle['freeze_sha256']!=sealed['contract']['freeze_sha256']:
            raise ValueError('Bundle seal changed')
        if sha(safe(bundle['model_config_path']))!=bundle['model_config_sha256']:raise ValueError('Pinned model config changed')
        return bundle,sealed

    def inspect(self):
        if not (self.output/'bundle.json').exists():return {'stage':'not_prepared','paid_work_launched':False,'official_test_accessed_by_inspection':False}
        # Deliberately metadata-only: does not open prepared sample or responses.
        bundle=read(self.output/'bundle.json');records=[]
        for p in sorted(self.output.glob('attempts/*/intent.json')):
            intent=read(p);folder=p.parent
            records.append({'run_id':intent['run_id'],'call_id':read(folder/'launch.json').get('call_id') if (folder/'launch.json').exists() else None,
                'terminal_saved':(folder/'terminal.json').exists(),'dispatch_started':(folder/'dispatch_started.json').exists()})
        return {'stage':bundle['stage'],'attempts':records,'paid_work_launched':False,'official_test_accessed_by_inspection':False}

    def edit_budget(self,change):
        path=self.state/'budget.json'
        with exclusive(self.state/'budget_reconcile.lock'):
            original=path.read_bytes();ledger=read(path);updated=change(ledger)
            if path.read_bytes()!=original:raise RuntimeError('Concurrent ledger change; no overwrite')
            write(path,updated)

    def allocate(self,*,authorized=False):
        if authorized is not True:raise ValueError('Explicit funded-action authorization required')
        bundle,sealed=self.load();self.backend.refresh(self.state)
        if any(int(a.get('tasks',0)) for a in self.backend.apps()):raise ValueError('Existing Modal tasks must reconcile before final allocation')
        def change(ledger):
            # Refresh only the supported funding observation. Approved sources,
            # checkpoint, price caps, calibration and envelope stay identical.
            # Preserve this separate allocation review; the immutable seal's
            # historical funding snapshot is never rewritten.
            allocation_review=dict(sealed['review'])
            allocation_review['funding_snapshot_sha256']=digest(funding.snapshot(ledger,as_of_utc=self.clock()))
            result=funding.allocate(ledger,sealed['contract'],allocation_review,seal_sha256=sealed['seal_sha256'],
                bundle_id=bundle['bundle_id'],as_of_utc=self.clock(),actual_source_hashes=sealed['contract']['protocol']['source_hashes'],
                calibration_record=sealed['calibration'])
            write(self.output/'allocation_review.json',allocation_review,immutable=True)
            return result
        self.edit_budget(change)
        write(self.output/'allocation.json',{'bundle_id':bundle['bundle_id'],'seal_sha256':sealed['seal_sha256'],
            'freeze_sha256':sealed['contract']['freeze_sha256'],'allocated_at_utc':self.clock()},immutable=True)
        return {'stage':'whole_bundle_reserved_before_access','paid_work_launched':False}

    def _begin_funded_access(self,bundle,sealed):
        """Fresh explicit access review for an already reserved whole bundle.

        Review's free-funds calculation subtracts only our two proven unused
        reservations from its planning view, avoiding double counting. Actual
        ledger commitments are never released or altered by this operation.
        """
        owner=seal.read_owner(bundle['seal_folder'])
        registry=seal._registry(sealed['access_registry_path'])
        if registry.exists():
            return seal.check_access(bundle['seal_folder'],owner_token=owner,destination=bundle['input_folder'])
        with exclusive(self.state/'budget_reconcile.lock'):
            ledger_path=self.state/'budget.json';ledger=read(ledger_path)
            escrow=funding.validate_escrow(ledger,sealed['contract'],bundle_id=bundle['bundle_id'],
                seal_sha256=sealed['seal_sha256'],as_of_utc=self.clock())
            if escrow['transferred_usd']!=0 or escrow['reserved_usd']!=escrow['original_escrow_usd']:
                raise ValueError('First access requires the whole unused original escrow')
            teacher=[j for j in ledger['jobs'] if j.get('run_id')==bundle['bundle_id']+'-teacher' and j.get('service')=='deepseek']
            if (len(teacher)!=1 or teacher[0].get('status')!='reserved'
                    or any(teacher[0].get(key)!=value for key,value in {
                        'final_scale_freeze_sha256':sealed['contract']['freeze_sha256'],
                        'final_scale_seal_sha256':sealed['seal_sha256'],'final_scale_bundle_id':bundle['bundle_id']}.items())
                    or contract_api.money(teacher[0]['reserved_usd'])<contract_api.money(sealed['contract']['protocol']['bounds']['teacher_reservation_usd'])):
                raise ValueError('First access requires the exact unused funded teacher phase')
            actual=funding.snapshot(ledger,as_of_utc=self.clock())
            planned=json.loads(json.dumps(actual))
            for service,amount in (('modal',escrow['reserved_usd']),('deepseek',teacher[0]['reserved_usd'])):
                held=contract_api.money(planned['reserved_usd'][service])-contract_api.money(amount)
                if held<0:raise ValueError('Own escrow is not present in actual liabilities')
                planned['reserved_usd'][service]=str(held)
            reviewed=dict(sealed['review'],funding_snapshot_sha256=digest(planned))
            contract_api.validate_review(sealed['contract'],reviewed,
                actual_source_hashes=sealed['contract']['protocol']['source_hashes'],calibration_record=sealed['calibration'],
                funding_snapshot=planned,as_of_utc=self.clock(),actual_pricing_sha256=sealed['pricing_sha256'])
            record={'role':'fresh_funded_access_review','seal_sha256':sealed['seal_sha256'],
                'freeze_sha256':sealed['contract']['freeze_sha256'],'ledger_sha256':sha(ledger_path),
                'actual_committed_funding_snapshot':actual,'planning_snapshot_before_own_allocation':planned,
                'own_reservations':{escrow['run_id']:escrow['reserved_usd'],teacher[0]['run_id']:teacher[0]['reserved_usd']},
                'review':reviewed,'reviewed_at_utc':self.clock(),'ledger_reservations_released':False}
            # One immutable review per first-access attempt. A crash before the
            # permit is preserved for explicit reconciliation, never replayed.
            write(self.output/'funded_access_review.json',record,immutable=True)
            identity=seal._permit_identity(sealed,seal._destination(bundle['seal_folder'],sealed,bundle['input_folder']))
            permit=seal._hash_record(dict(identity,stage='access_begun_before_source_read',began_at_utc=self.clock()),'permit_sha256')
            try:seal._write_once(registry,permit)
            except FileExistsError:return seal.check_access(bundle['seal_folder'],owner_token=owner,destination=bundle['input_folder'])
            return permit

    def prepare_inputs(self,*,authorized=False):
        if authorized is not True:raise ValueError('Explicit final-content authorization required')
        bundle,sealed=self.load();self.backend.refresh(self.state)
        funding.validate_escrow(read(self.state/'budget.json'),sealed['contract'],bundle_id=bundle['bundle_id'],
            seal_sha256=sealed['seal_sha256'],as_of_utc=self.clock())
        if any(int(a.get('tasks',0)) for a in self.backend.apps()):raise ValueError('Current GPU work must clear before final access')
        from cloud import final_scale_execution as execution
        from cloud import final_scale_artifacts as artifact_checks
        execution.validate_sealed_metadata(sealed)
        artifact_checks.verify_packaged_sources(ROOT,sealed['contract']['protocol']['source_hashes'])
        for path in (bundle['bundle_id']+'/adapter',bundle['bundle_id']+'/model_config.json',bundle['bundle_id']+'/inputs/preflight.json'):
            execution.volume_path(path)
        for checkpoint in ('base','chosen'):
            for shard in sealed['contract']['protocol']['shards']:
                for attempt in ('a0','a1'):
                    run=bundle['bundle_id']+'-'+checkpoint+'-'+shard['id']+'-'+attempt
                    if not contract_api.NAME.fullmatch(run):raise ValueError('Prepared run ID exceeds its bound')
                    execution.volume_path(bundle['bundle_id']+'/inputs/'+run+'.json')
        artifact_checks.verify_adapter(sealed['checkpoint']['adapter_path'],sealed['checkpoint']['adapter_files_sha256'],
            model_config_path=safe(bundle['model_config_path']))
        self._begin_funded_access(bundle,sealed)
        loader.prepare(bundle['seal_folder'],bundle['input_folder'],authorized=True)
        loaded=loader.load_prepared(bundle['seal_folder'],bundle['input_folder'],authorized=True)
        owner=seal.read_owner(bundle['seal_folder'])
        permit=seal.check_access(bundle['seal_folder'],owner_token=owner,destination=bundle['input_folder'])
        receipt=read(seal.dataset_receipt_path(sealed));config=safe(bundle['model_config_path'])
        authorization=execution.authorization_bundle(sealed,permit,receipt,
            adapter_path=bundle['bundle_id']+'/adapter',
            model_config_descriptor={'volume_path':bundle['bundle_id']+'/model_config.json','sha256':sha(config),'bytes':config.stat().st_size})
        write(self.output/'authorization.json',authorization,immutable=True)
        for checkpoint in ('base','chosen'):
            for shard in sealed['contract']['protocol']['shards']:
                self._prepare_attempt(bundle,sealed,loaded,authorization,checkpoint,shard['id'])
        return {'stage':'final_inputs_prepared','official_test_accessed':True,'paid_work_launched':False}

    def _prepare_attempt(self,bundle,sealed,loaded,authorization,checkpoint,shard_id,*,prior_attempts=None):
        from cloud import final_scale_execution as execution
        recovery=bool(prior_attempts);run=bundle['bundle_id']+'-'+checkpoint+'-'+shard_id+('-a1' if recovery else '-a0')
        folder=safe(self.output/'attempts'/run);shard=next(s for s in sealed['contract']['protocol']['shards'] if s['id']==shard_id)
        payload=execution.make_payload(authorization,loaded['binding'],loaded['rows'][shard['start']:shard['stop']],
            checkpoint=checkpoint,shard_id=shard_id,prior_attempts=prior_attempts)
        descriptor=execution.describe_input(payload,authorization,volume_path=bundle['bundle_id']+'/inputs/'+run+'.json',checkpoint=checkpoint,shard_id=shard_id)
        resume={k:descriptor[k] for k in ('parent_call_id','prefix_sha256','retained_count')} if recovery else None
        intent=execution.build_intent(sealed,descriptor,run_id=run,checkpoint=checkpoint,shard_id=shard_id,recovery=resume)
        folder.mkdir(parents=True,exist_ok=True)
        for name,value in (('intent.json',intent),('input_descriptor.json',descriptor),('authorization.json',authorization)):
            write(folder/name,value,immutable=True)
        raw=execution.payload_bytes(payload);target=safe(folder/'payload.json')
        try:
            with target.open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
        except FileExistsError:
            if target.read_bytes()!=raw:raise ValueError('Prepared immutable payload changed')
        return folder

    def _attempt(self,folder):
        intent=read(folder/'intent.json');launch=read(folder/'launch.json')
        batches=[read(p) for p in sorted((folder/'batches').glob('batch*.json'))]
        terminal=read(folder/'terminal.json') if (folder/'terminal.json').exists() else None
        if (folder/'completion_attestation.json').exists():
            from cloud import final_scale_execution as execution
            observation=read(folder/'provider_observation.json')
            proof={'call_id':launch['call_id'],'confirmed_terminal':True,'kind':observation['kind'],'observed_at_utc':observation['observed_at_utc']}
            expected=execution.reconcile_full_prefix(intent,read(folder/'authorization.json'),read(folder/'payload.json'),
                launch,batches,terminal,provider_terminal_proof=proof,
                raw_batch_hashes={str(int(p.stem.removeprefix('batch'))):sha(p) for p in (folder/'raw').glob('batch*.json')})
            if read(folder/'completion_attestation.json')!=expected:raise ValueError('Local completion attestation changed')
            return expected['completed_attempt']
        return {'launch':launch,'terminal':terminal,'batches':batches}

    def _derivation_record(self,folder,observation):
        from cloud import final_scale_execution as execution
        intent=read(folder/'intent.json');result=observation.get('result') or {};pending=result.get('raw_pending_record')
        if result.get('raw_pending'):
            candidate=result.get('worker_terminal') or {}
            if (not isinstance(pending,dict) or type(pending.get('start')) is not int
                    or candidate.get('raw_pending') is not True or candidate.get('raw_pending_start')!=pending['start']
                    or candidate.get('raw_pending_sha256')!=hashlib.sha256(execution.payload_bytes(pending)).hexdigest()):
                raise ValueError('Pending returned raw metadata changed')
            path=folder/'raw'/f"batch{pending['start']:04}.json"
            if not path.exists() or path.read_bytes()!=execution.payload_bytes(pending):raise ValueError('Returned original raw batch has not been preserved')
        hashes={str(int(p.stem.removeprefix('batch'))):sha(p) for p in sorted((folder/'raw').glob('batch*.json'))}
        return {'role':'unpaid_raw_derivation','intent_sha256':intent['intent_sha256'],
            'provider_observation_sha256':digest(observation),'raw_hashes':hashes,
            'raw_pending_record_sha256':hashlib.sha256(execution.payload_bytes(pending)).hexdigest() if pending else None,
            'new_generation_or_provider_request':False}

    def _check_derivation(self,folder,observation):
        path=folder/'raw_derivation_attestation.json'
        if not path.exists():raise ValueError('Original pending raw must be derived before any continuation')
        if read(path)!=self._derivation_record(folder,observation):raise ValueError('Raw derivation attestation does not bind current original evidence')

    def _validate_raw(self,folder,intent,launch,payload):
        from cloud import final_scale_execution as execution
        raw={p.name for p in (folder/'raw').glob('batch*.json')};derived={p.name for p in (folder/'batches').glob('batch*.json')}
        if raw!=derived:raise ValueError('Every raw batch needs unpaid deterministic derivation')
        observation=read(folder/'provider_observation.json')
        if (observation.get('provider_call_id')!=launch['call_id'] or observation.get('kind') not in ('completed','failed','timed_out')):
            raise ValueError('Actual provider terminal proof is required for saved outcomes')
        if (observation.get('result') or {}).get('raw_pending'):self._check_derivation(folder,observation)
        for path in sorted((folder/'batches').glob('batch*.json')):
            batch=read(path);raw_path=folder/'raw'/path.name
            if batch.get('raw_batch_sha256')!=sha(raw_path):raise ValueError('Original raw bytes changed')
            if execution.derive_raw_batch(intent,launch,read(raw_path),payload['binding'],self.decode)!=batch:
                raise ValueError('Saved decoded outcome differs from its original raw tokens')
        return observation

    def _settle(self,intent,launch,terminal,observation,folder):
        if (observation.get('provider_call_id')!=launch['call_id'] or observation.get('kind') not in ('completed','failed','timed_out')
                or terminal.get('call_id')!=launch['call_id'] or terminal.get('confirmed_terminal') is not True):
            raise ValueError('Provider termination and canonical receipt must match')
        def change(ledger):
            job=next(j for j in ledger['jobs'] if j.get('run_id')==intent['run_id'] and j.get('service','modal')=='modal')
            if (job.get('call_id') not in (None,launch['call_id']) or job.get('intent_sha256')!=intent['intent_sha256']):
                raise ValueError('Budget call or intent identity changed')
            job.update(status='completed' if terminal['stage']=='completed' else 'failed',call_id=launch['call_id'],
                terminal_observed_at_utc=observation['observed_at_utc'],finished_at_utc=observation['observed_at_utc'],
                terminal_time_basis='Provider-confirmed call termination observed at this upper-bound time; collection lag and app tasks still apply.',
                provider_terminal_observation_sha256=digest(observation))
            if (folder/'launch_observation.private.json').exists():
                app=read(folder/'launch_observation.private.json').get('app_id')
                if app:job['app_id']=app
            return ledger
        self.edit_budget(change)

    def poll(self):
        bundle,sealed=self.load();running=[];blocked=[]
        from cloud import final_scale_execution as execution
        for p in sorted(self.output.glob('attempts/*/intent.json')):
            folder=p.parent;intent=read(p)
            if not (folder/'launch.json').exists():
                if (folder/'dispatch_started.json').exists():blocked.append(folder.name+':ambiguous_dispatch')
                continue
            launch=read(folder/'launch.json')
            if launch!=execution.launch_receipt(intent,launch.get('call_id')):raise ValueError('Controller/worker launch identity differs')
            observation=(read(folder/'provider_observation.json') if (folder/'provider_observation.json').exists()
                else self.backend.poll(folder,launch['call_id']))
            if observation['kind']=='running':running.append(folder.name);continue
            if observation['kind']=='monitoring_error':blocked.append(folder.name+':monitoring_error');continue
            if observation.get('provider_call_id')!=launch['call_id']:raise ValueError('Provider terminal call differs')
            write(folder/'provider_observation.json',observation,immutable=True)
            raw={p.name for p in (folder/'raw').glob('batch*.json')};derived={p.name for p in (folder/'batches').glob('batch*.json')}
            result=observation.get('result') or {}
            if raw!=derived:blocked.append(folder.name+':raw_derivation_required');continue
            if result.get('raw_pending'):
                try:self._check_derivation(folder,observation)
                except ValueError:blocked.append(folder.name+':raw_derivation_required');continue
            payload=read(folder/'payload.json');prior=payload.get('prior_attempts',[])
            # Re-derive every retained outcome from exact raw tokens using the
            # pinned cached decoder; raw/derived hash agreement alone is not
            # proof that the decoded response was preserved correctly.
            for batch_path in sorted((folder/'batches').glob('batch*.json')):
                batch=read(batch_path);raw_path=folder/'raw'/batch_path.name
                if batch.get('raw_batch_sha256')!=sha(raw_path):raise ValueError('Raw file byte hash changed')
                derived=execution.derive_raw_batch(intent,launch,read(raw_path),payload['binding'],self.decode)
                if derived!=batch:raise ValueError('Derived response differs from saved raw token outcomes')
            prefix=[]
            if prior:
                recovered=receipts.recover_prefix(sealed['contract'],payload['binding'],intent['checkpoint'],intent['shard_id'],prior)
                prefix=recovered['rows']
            attempt=self._attempt(folder);batches=attempt['batches']
            rows=prefix+[r for batch in batches for r in batch['rows']]
            result=observation.get('result') or {};stage=result.get('stage') if observation['kind']=='completed' else observation['kind']
            if stage not in ('completed','failed','timed_out','cancelled'):stage='failed'
            # A failed function can nevertheless have durably committed every
            # logical outcome. Reconcile locally after validating the original
            # failed prefix, retaining provider failure separately; never pay
            # for a call that has no missing batch.
            original_terminal=execution.terminal_receipt(intent,launch,batches,prefix,stage,confirmed_terminal=True)
            if (folder/'terminal.json').exists():
                original_terminal=read(folder/'terminal.json')
            terminal=original_terminal
            attempt['terminal']=terminal
            recovered=receipts.recover_prefix(sealed['contract'],payload['binding'],intent['checkpoint'],intent['shard_id'],prior+[attempt])
            if stage!='completed' and recovered['retained_count']==recovered['expected_count']:
                write(folder/'terminal.json',original_terminal,immutable=True)
                proof={'call_id':launch['call_id'],'confirmed_terminal':True,'kind':observation['kind'],'observed_at_utc':observation['observed_at_utc']}
                attestation=execution.reconcile_full_prefix(intent,read(folder/'authorization.json'),payload,launch,batches,terminal,
                    provider_terminal_proof=proof,raw_batch_hashes={str(int(p.stem.removeprefix('batch'))):sha(p) for p in (folder/'raw').glob('batch*.json')})
                write(folder/'completion_attestation.json',attestation,immutable=True)
                terminal=attestation['completed_attempt']['terminal'];attempt['terminal']=terminal
                receipts.recover_prefix(sealed['contract'],payload['binding'],intent['checkpoint'],intent['shard_id'],prior+[attempt])
            write(folder/'terminal.json',original_terminal,immutable=True)
            self._settle(intent,launch,terminal,observation,folder)
            if terminal['stage']!='completed' and recovered['retained_count']<recovered['expected_count']:
                child=any(read(p).get('input_descriptor',{}).get('parent_call_id')==launch['call_id']
                    for p in self.output.glob('attempts/*/intent.json'))
                if not child:blocked.append(folder.name+':terminal_prefix_recovery_review_required')
        return {'stage':'monitoring' if running else 'action_required' if blocked else 'reconciled',
            'running':running,'blocked':blocked,'paid_work_launched':False}

    def derive_raw(self,*,authorized=False):
        """Unpaid replay of saved tokens only, with no generator or HTTP call."""
        if authorized is not True:raise ValueError('Explicit private final-content derivation authorization required')
        bundle,sealed=self.load()
        from cloud import final_scale_execution as execution
        with exclusive(self.state/'final_scale_tick.lock'):
            for p in sorted(self.output.glob('attempts/*/provider_observation.json')):
                folder=p.parent;observation=read(p);intent=read(folder/'intent.json');launch=read(folder/'launch.json')
                if observation.get('provider_call_id')!=launch['call_id'] or observation.get('kind') not in ('completed','failed','timed_out'):
                    raise ValueError('Raw derivation requires previously confirmed provider termination')
                result=observation.get('result') or {};payload=read(folder/'payload.json')
                execution.validate_inputs(intent,read(folder/'authorization.json'),payload)
                pending=result.get('raw_pending_record')
                if result.get('raw_pending'):
                    candidate=result.get('worker_terminal') or {}
                    if (not isinstance(pending,dict) or candidate.get('raw_pending') is not True
                            or candidate.get('raw_pending_start')!=pending.get('start')
                            or candidate.get('raw_pending_sha256')!=hashlib.sha256(execution.payload_bytes(pending)).hexdigest()):
                        raise ValueError('Original returned raw outcomes need manual reconciliation')
                    write_bytes(folder/'raw'/f"batch{pending['start']:04}.json",execution.payload_bytes(pending))
                hashes={}
                for raw_path in sorted((folder/'raw').glob('batch*.json')):
                    raw=read(raw_path);batch=execution.derive_raw_batch(intent,launch,raw,payload['binding'],self.decode)
                    if batch['raw_batch_sha256']!=sha(raw_path):raise ValueError('Original raw serialization/hash differs')
                    receipts.validate_batch(sealed['contract'],payload['binding'],batch)
                    write_bytes(folder/'batches'/raw_path.name,execution.payload_bytes(batch));hashes[str(batch['start'])]=sha(raw_path)
                attestation=self._derivation_record(folder,observation)
                write(folder/'raw_derivation_attestation.json',attestation,immutable=True)
        return self.poll()

    def prepare_recovery(self,checkpoint,shard_id,*,review_path,authorized=False):
        """One reviewed terminal-prefix continuation, never a repeated batch."""
        if authorized is not True:raise ValueError('Explicit final-content recovery preparation required')
        bundle,sealed=self.load();self.backend.refresh(self.state)
        from cloud import final_scale_execution as execution
        with exclusive(self.state/'final_scale_tick.lock'):
            if any(int(a.get('tasks',0)) for a in self.backend.apps()):raise ValueError('Existing Modal work must stop before recovery preparation')
            escrow=funding.validate_escrow(read(self.state/'budget.json'),sealed['contract'],bundle_id=bundle['bundle_id'],
                seal_sha256=sealed['seal_sha256'],as_of_utc=self.clock())
            if escrow['recovery_claimed']:raise ValueError('Global recovery allowance already used')
            folders=[p.parent for p in self.output.glob('attempts/*/intent.json')
                if read(p).get('checkpoint')==checkpoint and read(p).get('shard_id')==shard_id]
            if len(folders)!=1:raise ValueError('A continuation needs exactly one original attempt')
            folder=folders[0];attempt=self._attempt(folder);payload=read(folder/'payload.json')
            if not (folder/'provider_observation.json').exists():raise ValueError('Provider termination proof is missing')
            observation=read(folder/'provider_observation.json')
            if observation.get('kind') not in ('completed','failed','timed_out'):raise ValueError('Provider termination is not confirmed')
            if {p.name for p in (folder/'raw').glob('batch*.json')}!={p.name for p in (folder/'batches').glob('batch*.json')}:
                raise ValueError('Unpaid raw derivation must precede paid recovery')
            if (observation.get('result') or {}).get('raw_pending'):self._check_derivation(folder,observation)
            self._validate_raw(folder,read(folder/'intent.json'),attempt['launch'],payload)
            prefix=receipts.recover_prefix(sealed['contract'],payload['binding'],checkpoint,shard_id,[attempt])
            if not prefix['can_resume']:raise ValueError('No missing terminal-confirmed prefix exists; do not pay for replay')
            review=read(review_path)
            expected={'reviewed':True,'controller_sha256':sha(__file__),'freeze_sha256':sealed['contract']['freeze_sha256'],
                'seal_sha256':sealed['seal_sha256'],'parent_call_id':attempt['launch']['call_id'],
                'parent_terminal_sha256':attempt['terminal']['terminal_sha256'],'prefix_sha256':prefix['prefix_sha256'],
                'remaining_questions':prefix['expected_count']-prefix['retained_count'],'deterministic_failure_reconciled':True}
            if review!=expected:raise ValueError('Exact source/terminal/prefix recovery engineering review is required')
            loaded=loader.load_prepared(bundle['seal_folder'],bundle['input_folder'],authorized=True)
            output=self._prepare_attempt(bundle,sealed,loaded,read(self.output/'authorization.json'),checkpoint,shard_id,prior_attempts=[attempt])
            write(output/'recovery_review.json',review,immutable=True)
            return {'stage':'terminal_prefix_recovery_prepared','run_id':output.name,'paid_work_launched':False}

    def report(self,*,authorized=False,teacher_folder=None):
        """Revalidate private receipts before producing aggregate-only output."""
        if authorized is not True:raise ValueError('Explicit private final-content aggregation required')
        bundle,sealed=self.load();loaded=loader.load_prepared(bundle['seal_folder'],bundle['input_folder'],authorized=True)
        groups={'base':{},'chosen':{}}
        for p in sorted(self.output.glob('attempts/*/intent.json')):
            intent=read(p);folder=p.parent
            if not (folder/'launch.json').exists():continue
            attempt=self._attempt(folder)
            if attempt['terminal'] is not None:self._validate_raw(folder,intent,attempt['launch'],read(folder/'payload.json'))
            groups[intent['checkpoint']].setdefault(intent['shard_id'],[]).append(attempt)
        # Child lineage is immutable and must agree byte-for-byte with the
        # original retained attempts, not merely share a parent call ID.
        for by_shard in groups.values():
            for attempts in by_shard.values():
                for number,attempt in enumerate(attempts):
                    folder=next(p.parent for p in self.output.glob('attempts/*/launch.json') if read(p)['call_id']==attempt['launch']['call_id'])
                    if read(folder/'payload.json').get('prior_attempts',[])!=attempts[:number]:raise ValueError('Prepared continuation lineage changed')
        result=receipts.aggregate(sealed['contract'],loaded['binding'],groups)
        if teacher_folder is not None:
            from cloud import final_scale_teacher as teacher
            teacher_folder=safe(teacher_folder)
            teacher_sealed,binding,_,requested=teacher._context(bundle['seal_folder'],bundle['input_folder'],authorized=True)
            manifest=read(teacher_folder/'manifest.json')
            from cloud import final_scale_teacher_receipts as teacher_receipts
            teacher_receipts.validate_manifest(sealed['contract'],binding,manifest)
            if (manifest['bundle_id']!=bundle['bundle_id'] or manifest['seal_sha256']!=sealed['seal_sha256']
                    or teacher_sealed['seal_sha256']!=sealed['seal_sha256']
                    or digest(requested)!=manifest['request_manifest_sha256']
                    or (teacher_folder/teacher.REQUESTS_FILE).read_bytes()!=teacher.rows_bytes(requested)):
                raise ValueError('Teacher requests/bundle differ from the same frozen sample')
            outcomes=[]
            for question,request in zip(binding['questions'],requested):
                outcome=teacher.recover(manifest,question,request,teacher_folder)
                if outcome is not None:outcomes.append(outcome)
            result['teacher']=teacher_receipts.aggregate(manifest,binding,outcomes)
            if result['teacher']['status']=='completed' and result['paired_status']=='completed':
                from cloud.evaluation_stats import paired
                teacher_rows=teacher_receipts.scoring_rows(outcomes)
                comparisons={}
                for checkpoint in ('base','chosen'):
                    rows=[]
                    for shard in sealed['contract']['protocol']['shards']:
                        rows.extend(receipts.recover_prefix(sealed['contract'],binding,checkpoint,shard['id'],groups[checkpoint][shard['id']])['rows'])
                    normalized=[dict(row,truncated=row['truncated'] or row['outcome']!='generated') for row in rows]
                    comparisons[checkpoint+'_vs_teacher']=paired(teacher_rows,normalized)
                    comparisons[checkpoint+'_vs_teacher']['limitations']='Frozen same-question final comparison; one selected training run. Question intervals do not cover training-seed variation. Numeric scoring does not verify reasoning steps; teacher round trips and GPU batch timing are different scopes.'
                result['teacher_comparisons']=comparisons
        write(self.output/'aggregate.json',result)
        return result

    def prepare_teacher(self,*,authorized=False):
        if authorized is not True:raise ValueError('Explicit final teacher-content preparation required')
        bundle,sealed=self.load()
        from cloud import final_scale_teacher as teacher
        from cloud import final_scale_teacher_receipts as teacher_receipts
        output=safe(self.output/'teacher')
        result=teacher.prepare(bundle['seal_folder'],bundle['input_folder'],output,bundle_id=bundle['bundle_id'],authorized=True)
        manifest=read(output/'manifest.json')
        ids=contract_api.expected_ids(sealed['contract'])
        approval=teacher_receipts.phase_template(manifest,ids,bundle['bundle_id']+'-teacher',phase_id='initial')
        write(output/'phase_initial_template.json',approval,immutable=True)
        return dict(result,phase_approval_granted_by_preparation=False)

    def finalize(self,*,authorized=False):
        if authorized is not True:raise ValueError('Explicit final aggregation/settlement authorization required')
        bundle,sealed=self.load()
        if (self.output/'completed.json').exists():
            existing=read(self.output/'completed.json');result=self.report(authorized=True,teacher_folder=self.output/'teacher')
            if existing.get('freeze_sha256')!=sealed['contract']['freeze_sha256'] or existing.get('aggregate_sha256')!=digest(result):
                raise ValueError('Completed final aggregate changed; preserve existing completion')
            return {'stage':'final_bundle_already_completed','question_count':result['count'],'api_deployed':False,'paid_work_launched':False}
        status=self.poll()
        if status['running'] or status['blocked']:raise ValueError('Existing final calls must reconcile before settlement')
        result=self.report(authorized=True,teacher_folder=self.output/'teacher')
        if result['paired_status']!='completed' or result.get('teacher',{}).get('status')!='completed':
            raise ValueError('No partial denominator can complete the final bundle')
        self.backend.refresh(self.state)
        if any(int(a.get('tasks',0)) for a in self.backend.apps()):raise ValueError('GPU work remains active; do not release allowances')
        def settle(ledger):
            escrow=next(j for j in ledger['jobs'] if j['run_id']==bundle['bundle_id']+'-modal-escrow')
            teacher=next(j for j in ledger['jobs'] if j['run_id']==bundle['bundle_id']+'-teacher')
            aggregate_hash=digest(result)
            if (escrow.get('status')=='completed' and teacher.get('status')=='completed'
                    and escrow.get('final_aggregate_sha256')==aggregate_hash and teacher.get('final_aggregate_sha256')==aggregate_hash
                    and escrow.get('reserved_usd')==0):
                return ledger  # Crash recovery after atomic settlement, no second release.
            if escrow.get('status')!='reserved':raise ValueError('Escrow already settled; inspect saved completion')
            # Only never-dispatched escrow is released. Every GPU child keeps
            # its original allowance pending provider lag reconciliation.
            released=contract_api.money(escrow['reserved_usd'])
            ledger['reserved']['modal']=float(contract_api.money(ledger['reserved']['modal'])-released)
            escrow.update(status='completed',reserved_usd=0.,released_unused_usd=float(released),
                finished_at_utc=self.clock(),reason='unused final recovery/compute allowance; no paid call',final_aggregate_sha256=aggregate_hash)
            if teacher.get('status') not in ('reserved','collecting'):raise ValueError('Teacher liability requires reconciliation')
            estimated=contract_api.money(result['teacher']['recorded_peak_token_estimate_usd'])
            if result['teacher']['unknown_usage_attempts']:
                raise ValueError('Unknown teacher liabilities cannot be released')
            held=contract_api.money(teacher['reserved_usd'])
            teacher.update(status='completed',accounted_upper_estimate_usd=float(estimated),finished_at_utc=self.clock(),final_aggregate_sha256=aggregate_hash)
            ledger['reserved']['deepseek']=float(contract_api.money(ledger['reserved']['deepseek'])-held)
            return ledger
        self.edit_budget(settle)
        write(self.output/'completed.json',{'role':'final_eval_only','freeze_sha256':sealed['contract']['freeze_sha256'],
            'aggregate_sha256':digest(result),'completed_at_utc':self.clock(),'api_deployed':False},immutable=True)
        return {'stage':'final_bundle_completed','question_count':result['count'],'api_deployed':False,'paid_work_launched':False}

    def recover_dispatch(self,*,authorized=False):
        """Recover a transmitted call ID from its durable remote owner, no spawn."""
        if authorized is not True:raise ValueError('Explicit existing-call lookup authorization required')
        self.load();recovered=[];unknown=[]
        from cloud import final_scale_execution as execution
        with exclusive(self.state/'final_scale_tick.lock'):
            for p in sorted(self.output.glob('attempts/*/dispatch_started.json')):
                folder=p.parent
                if (folder/'launch.json').exists():continue
                intent=read(folder/'intent.json');claim=read(folder/'dispatch_claim.json')
                if claim!=execution.dispatch_claim(intent,claim.get('claim_id')):raise ValueError('Ambiguous launch claim changed')
                owner=self.backend.lookup(intent)
                if owner is None:unknown.append(folder.name);continue
                launch=execution.launch_receipt(intent,owner['call_id'])
                write(folder/'launch.json',launch,immutable=True)
                def bind(ledger):
                    job=next(j for j in ledger['jobs'] if j['run_id']==intent['run_id'])
                    if job.get('intent_sha256')!=intent['intent_sha256'] or job.get('claim_sha256')!=claim['claim_sha256']:
                        raise ValueError('Existing dispatch budget owner changed')
                    if job.get('call_id') not in (None,owner['call_id']):raise ValueError('Existing call identity differs')
                    job.update(status='spawned',call_id=owner['call_id']);return ledger
                self.edit_budget(bind);recovered.append(folder.name)
        return {'stage':'ambiguous_dispatch_remains' if unknown else 'existing_dispatch_reconciled',
            'recovered':recovered,'unknown':unknown,'paid_work_launched':False}

    def advance(self,*,authorized=False):
        if authorized is not True:raise ValueError('Explicit paid-dispatch authorization required')
        with exclusive(self.state/'final_scale_tick.lock'):
            bundle,sealed=self.load();status=self.poll()
            if status['running'] or status['blocked']:return status
            self.backend.refresh(self.state)
            with exclusive(self.state/'gpu_launch.lock'):
                if any(int(a.get('tasks',0)) for a in self.backend.apps()):return {'stage':'outside_gpu_work_active','paid_work_launched':False}
                folders=sorted(p.parent for p in self.output.glob('attempts/*/intent.json'))
                for folder in folders:
                    if (folder/'launch.json').exists():continue
                    if (folder/'dispatch_started.json').exists() or (folder/'dispatch_claim.json').exists():
                        return {'stage':'ambiguous_or_staged_claim_requires_reconciliation','paid_work_launched':False}
                    from cloud import final_scale_execution as execution
                    intent=read(folder/'intent.json')
                    execution.validate_remote_metadata(intent,read(folder/'input_descriptor.json'),read(folder/'authorization.json'))
                    execution.validate_inputs(intent,read(folder/'authorization.json'),read(folder/'payload.json'))
                    claim=execution.dispatch_claim(intent,uuid.uuid4().hex)
                    # Write before the ledger transfer and upload, then bind the
                    # exact claim before any possibly transmitted launch.
                    def transfer(ledger):
                        result=funding.transfer(ledger,sealed['contract'],bundle_id=bundle['bundle_id'],
                            seal_sha256=sealed['seal_sha256'],run_id=intent['run_id'],intent_sha256=intent['intent_sha256'],
                            claim_sha256=claim['claim_sha256'],as_of_utc=self.clock(),checkpoint=intent['checkpoint'],
                            shard_id=intent['shard_id'],is_recovery=bool(read(folder/'payload.json').get('prior_attempts')))
                        write(folder/'dispatch_claim.json',claim,immutable=True)
                        return result
                    self.edit_budget(transfer)
                    self.backend.stage(folder,bundle)
                    write(folder/'dispatch_started.json',{'claim_sha256':claim['claim_sha256'],'intent_sha256':intent['intent_sha256'],
                        'run_id':intent['run_id'],'stage':'dispatch_started'},immutable=True)
                    receipt=self.backend.launch(folder);write(folder/'launch_observation.private.json',receipt,immutable=True)
                    if not (folder/'launch.json').exists():return {'stage':'ambiguous_dispatch','paid_work_launched':None}
                    launch=read(folder/'launch.json')
                    if launch!=execution.launch_receipt(intent,launch.get('call_id')):raise ValueError('Returned launch identity differs')
                    def bind(ledger):
                        job=next(j for j in ledger['jobs'] if j['run_id']==intent['run_id'])
                        if job['claim_sha256']!=claim['claim_sha256']:raise ValueError('Dispatch claim changed')
                        job.update(status='spawned',call_id=launch['call_id'],app_id=receipt.get('app_id'));return ledger
                    self.edit_budget(bind)
                    return {'stage':'spawned','run_id':intent['run_id'],'call_id':launch['call_id'],'paid_work_launched':True}
            return {'stage':'no_unlaunched_original_attempts','paid_work_launched':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',choices=('inspect','prepare-bundle','allocate','prepare-inputs','poll','advance',
        'derive-raw','prepare-recovery','recover-dispatch','prepare-teacher','report','finalize'),default='inspect')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--authorized',action='store_true')
    for arg in ('seal-folder','input-folder','review-path','model-config-path'):parser.add_argument('--'+arg,type=Path)
    parser.add_argument('--checkpoint',choices=('base','chosen'));parser.add_argument('--shard-id')
    parser.add_argument('--teacher-folder',type=Path)
    args=parser.parse_args()
    if args.action=='prepare-bundle':
        if any(getattr(args,n) is None for n in ('seal_folder','input_folder','review_path','model_config_path')):parser.error('Preparation requires explicit seal/input/review/config paths')
        result=prepare_bundle(args.seal_folder,args.input_folder,args.output,review_path=args.review_path,model_config_path=args.model_config_path)
    else:
        runner=Controller(args.output)
        if args.action=='prepare-recovery':
            if not all((args.checkpoint,args.shard_id,args.review_path)):parser.error('Recovery needs exact checkpoint/shard/review')
            result=runner.prepare_recovery(args.checkpoint,args.shard_id,review_path=args.review_path,authorized=args.authorized)
        elif args.action=='report':result=runner.report(authorized=args.authorized,teacher_folder=args.teacher_folder)
        else:result=runner.inspect() if args.action=='inspect' else runner.poll() if args.action=='poll' else getattr(runner,args.action.replace('-','_'))(authorized=args.authorized)
    print(json.dumps(result))


if __name__=='__main__':main()
