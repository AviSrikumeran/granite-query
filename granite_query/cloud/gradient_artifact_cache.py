"""Future stdlib-only, copy-free cache for immutable gradient artifact lineage.

No integration or cloud calls occur here. Callers must confirm a run terminal
before sealing its inventory. Sealed parents are read-only: JSON is verified on
first read and cached, while returned values are copies. A new child may append
missing records; it cannot replace any record already resolved in its lineage.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import re

TERMINAL={'completed','bounded_stop','calibration_refused','failed'}


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()


def digest(value):return hashlib.sha256(value).hexdigest()
def valid_hash(value):return isinstance(value,str) and bool(re.fullmatch('[0-9a-f]{64}',value))
def safe_name(value):return isinstance(value,str) and bool(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',value))


class ArtifactCache:
    def __init__(self,artifact_root,child_run_id,*,protocol_hash,parameter_layout_sha256,
                 projection_mapping_sha256,dimension,candidates,targets,parent=None,
                 max_depth=4,checkpoint_updates=(4,8),read_bytes=None):
        if not safe_name(child_run_id) or not 1<=max_depth<=8 or type(dimension) is not int or not 1<=dimension<=8192:
            raise ValueError('Invalid run identity, bounded lineage depth or feature dimension')
        if not all(valid_hash(value) for value in (protocol_hash,parameter_layout_sha256,projection_mapping_sha256)):
            raise ValueError('Require immutable protocol/layout/projection hashes')
        self.root=Path(artifact_root).resolve();self.child_id=child_run_id
        self.child=self._run_path(child_run_id);self.parent=copy.deepcopy(parent)
        self.max_depth=max_depth;self._reader=read_bytes or (lambda path:path.read_bytes())
        if (not checkpoint_updates or len(checkpoint_updates)>4 or len(set(checkpoint_updates))!=len(checkpoint_updates)
                or any(type(step) is not int or not 1<=step<=999 for step in checkpoint_updates)):
            raise ValueError('Require bounded frozen checkpoint identities')
        self.checkpoints=tuple(checkpoint_updates)
        self._json={};self._file_hashes={};self._features={};self._snapshots={};self._parents=[]
        self._rows={};ordered=[]
        for role,rows in (('candidate',candidates),('target',targets)):
            for row in rows:
                if ((role,row.get('id')) in self._rows or not isinstance(row.get('id'),str)
                        or not valid_hash(row.get('question_sha256')) or not valid_hash(row.get('raw_response_sha256'))
                        or row.get('source_split')!='train' or row.get('verified_final_answer') is not True):
                    raise ValueError('Rows require distinct verified training identities')
                self._rows[(role,row['id'])]=copy.deepcopy(row)
                if role=='target' and (not isinstance(row.get('group'),str) or not row['group']):
                    raise ValueError('Target groups must remain explicit and immutable')
                ordered.append({'role':role,'id':row['id'],'question_sha256':row['question_sha256'],
                    'raw_response_sha256':row['raw_response_sha256'],'group':row.get('group')})
        if (not candidates or not targets or {r['id'] for r in candidates}&{r['id'] for r in targets}
                or {r['question_sha256'] for r in candidates}&{r['question_sha256'] for r in targets}):
            raise ValueError('Require nonempty disjoint candidate and target identities')
        self.identity={'protocol_hash':protocol_hash,'parameter_layout_sha256':parameter_layout_sha256,
            'projection_mapping_sha256':projection_mapping_sha256,'dimension':dimension,
            'checkpoint_updates':list(self.checkpoints),
            'rows_sha256':digest(canonical(ordered))}
        if (self.child/'lineage_manifest.json').exists():raise ValueError('A sealed run cannot be reopened for writes')
        self.child.mkdir(parents=True,exist_ok=True)
        if parent:self._load_parent(parent,set([child_run_id]),0)

    def _run_path(self,run_id):
        if not safe_name(run_id):raise ValueError('Unsafe lineage run ID')
        path=(self.root/run_id).resolve()
        if not path.is_relative_to(self.root):raise ValueError('Lineage path escapes artifact root')
        return path

    def _path(self,run_id,relative):
        token=PurePosixPath(relative)
        if token.is_absolute() or '..' in token.parts or '\\' in relative:
            raise ValueError('Unsafe artifact-relative path')
        root=self._run_path(run_id);path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('Artifact path escapes its owning run')
        return path

    def _read_json(self,path,expected=None):
        path=Path(path).resolve()
        if path not in self._json:
            limit=64*1024*1024 if path.name=='lineage_manifest.json' else 2*1024*1024
            if path.stat().st_size>limit:raise ValueError('Bounded immutable JSON read limit exceeded')
            raw=self._reader(path)
            if expected is not None and digest(raw)!=expected:raise ValueError('Immutable JSON hash changed: '+path.name)
            self._json[path]=(json.loads(raw.decode('utf-8-sig')),digest(raw))
        value,actual=self._json[path]
        if expected is not None and actual!=expected:raise ValueError('JSON was rebound to another immutable hash')
        return copy.deepcopy(value)

    def _hash_file(self,path):
        path=Path(path).resolve()
        if path not in self._file_hashes:
            value=hashlib.sha256()
            with path.open('rb') as handle:
                for block in iter(lambda:handle.read(1024*1024),b''):value.update(block)
            self._file_hashes[path]=value.hexdigest()
        return self._file_hashes[path]

    def _load_parent(self,link,seen,depth):
        if depth>=self.max_depth:raise ValueError('Parent lineage exceeds its bounded depth')
        run_id=link.get('run_id')
        if run_id in seen:raise ValueError('Cycle in immutable parent lineage')
        if not valid_hash(link.get('manifest_sha256')):raise ValueError('Parent manifest hash is required')
        seen=set(seen);seen.add(run_id)
        manifest=self._read_json(self._path(run_id,'lineage_manifest.json'),link['manifest_sha256'])
        if (manifest.get('schema_version')!=1 or manifest.get('run_id')!=run_id
                or manifest.get('identity')!=self.identity or manifest.get('stage') not in TERMINAL
                or manifest.get('confirmed_terminal') is not True or not manifest.get('call_id')
                or not valid_hash(manifest.get('execution_sources_sha256'))):
            raise ValueError('Parent protocol/pool/layout/projection or terminal identity differs')
        allowed={self._key(step,role,row_id) for step in self.checkpoints for role,row_id in self._rows}
        if not isinstance(manifest.get('features'),dict) or not isinstance(manifest.get('snapshots'),dict):
            raise ValueError('Parent artifact inventory is missing')
        for key,entry in manifest['features'].items():
            if key not in allowed or entry.get('path')!='features/'+key+'.json' or not valid_hash(entry.get('sha256')):
                raise ValueError('Parent feature inventory silently changed the frozen pool/checkpoints')
        for step,entry in manifest['snapshots'].items():
            if step not in {str(value) for value in self.checkpoints} or entry.get('path')!=f'snapshots/update{int(step):03}/READY.json' or not valid_hash(entry.get('sha256')):
                raise ValueError('Parent snapshot inventory changed')
        self._parents.append(manifest)
        if manifest.get('parent'):self._load_parent(manifest['parent'],seen,depth+1)

    def _key(self,step,role,row_id):
        if type(step) is not int or step not in self.checkpoints or role not in ('candidate','target') or (role,row_id) not in self._rows:
            raise ValueError('Unknown checkpoint/role/row identity')
        return f'update{step:03}/{role}/{digest(row_id.encode())}'

    def _entry(self,key):
        found=[]
        if key in self._features:found.append((self.child_id,self._features[key]))
        for manifest in self._parents:
            if key in manifest['features']:found.append((manifest['run_id'],manifest['features'][key]))
        if not found:return None
        if len({entry['sha256'] for _,entry in found})!=1:raise ValueError('A feature key has divergent immutable parent values')
        return found[0]

    def _validate_feature(self,value,step,role,row):
        unsigned={key:item for key,item in value.items() if key!='record_sha256'}
        expected={'id':row['id'],'question_sha256':row['question_sha256'],'raw_response_sha256':row['raw_response_sha256'],
            'checkpoint_id':f'update{step:03}','parameter_layout_sha256':self.identity['parameter_layout_sha256'],
            'projection_mapping_sha256':self.identity['projection_mapping_sha256'],
            'protocol_hash':self.identity['protocol_hash'],'role':role,
            'source_split':'train','verified_final_answer':True,
            'gradient_type':'less_adam' if role=='candidate' else 'sgd'}
        if value.get('record_sha256')!=digest(canonical(unsigned)) or any(value.get(key)!=item for key,item in expected.items()):
            raise ValueError('Gradient feature content/identity changed')
        vector=value.get('feature',[])
        if (len(vector)!=self.identity['dimension'] or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in vector)
                or math.fsum(x*x for x in vector)<=1e-30):
            raise ValueError('Invalid projected feature; no gradient values are transformed by the cache')
        if role=='target' and value.get('group')!=row.get('group'):raise ValueError('Target group changed')

    def feature(self,step,role,row_id):
        key=self._key(step,role,row_id);resolved=self._entry(key)
        if resolved is None:return None
        run_id,entry=resolved
        if entry.get('path')!='features/'+key+'.json':raise ValueError('Feature inventory path differs from its key')
        value=self._read_json(self._path(run_id,entry['path']),entry['sha256'])
        self._validate_feature(value,step,role,self._rows[(role,row_id)])
        return value

    def feature_count(self,step,role):
        keys={self._key(step,role,row_id) for stored_role,row_id in self._rows if stored_role==role}
        return sum(self._entry(key) is not None for key in keys)

    def append_feature(self,step,role,row_id,value):
        self._writable();key=self._key(step,role,row_id)
        self._validate_feature(value,step,role,self._rows[(role,row_id)])
        raw=canonical(value);existing=self._entry(key)
        if existing:
            if existing[1]['sha256']!=digest(raw):raise ValueError('Append would overwrite a resolved immutable feature')
            # Resolve/read its original path; never copy a parent into the child.
            self.feature(step,role,row_id)
            return self._path(existing[0],existing[1]['path'])
        path=self._path(self.child_id,'features/'+key+'.json');self._write_exclusive(path,raw)
        self._features[key]={'path':'features/'+key+'.json','sha256':digest(raw)}
        return path

    def snapshot(self,step):
        if type(step) is not int or step not in self.checkpoints:raise ValueError('Unknown frozen checkpoint')
        candidates=[]
        if str(step) in self._snapshots:candidates.append((self.child_id,self._snapshots[str(step)]))
        for manifest in self._parents:
            if str(step) in manifest['snapshots']:candidates.append((manifest['run_id'],manifest['snapshots'][str(step)]))
        if not candidates:return None
        if len({entry['sha256'] for _,entry in candidates})!=1:raise ValueError('Snapshot identity diverges across parents')
        run_id,entry=candidates[0]
        if entry['path']!=f'snapshots/update{step:03}/READY.json':raise ValueError('Snapshot path changed')
        path=self._path(run_id,entry['path']);ready=self._read_json(path,entry['sha256'])
        self._validate_snapshot(run_id,step,ready)
        return {'run_id':run_id,'directory':str(path.parent),'ready':ready}

    def _validate_snapshot(self,run_id,step,ready):
        if (ready.get('protocol_hash')!=self.identity['protocol_hash'] or ready.get('updates')!=step
                or ready.get('layout_sha256')!=self.identity['parameter_layout_sha256']
                or ready.get('supervised_tokens')!=step*1024):raise ValueError('Snapshot identity changed')
        files=ready.get('files_sha256',{})
        if not {'optimizer.pt','adapter/adapter_config.json','adapter/adapter_model.safetensors'}<=set(files):
            raise ValueError('Snapshot must preserve adapter and optimizer')
        for relative,expected in files.items():
            if not valid_hash(expected) or self._hash_file(self._path(run_id,f'snapshots/update{step:03}/'+relative))!=expected:
                raise ValueError('Immutable snapshot file changed')

    def publish_snapshot(self,step,ready):
        self._writable()
        if self.snapshot(step) is not None:raise ValueError('Cannot replace an inherited/ready snapshot')
        self._validate_snapshot(self.child_id,step,ready)
        relative=f'snapshots/update{step:03}/READY.json';raw=canonical(ready)
        self._write_exclusive(self._path(self.child_id,relative),raw)
        self._snapshots[str(step)]={'path':relative,'sha256':digest(raw)}

    def index_existing_terminal(self,*,confirmed_terminal=False):
        """Audit legacy preserved outputs in place; never copy or rewrite them."""
        self._writable()
        if confirmed_terminal is not True:raise ValueError('Existing outputs need confirmed terminal ownership')
        for step in self.checkpoints:
            for role,row_id in self._rows:
                key=self._key(step,role,row_id);relative='features/'+key+'.json'
                path=self._path(self.child_id,relative)
                if not path.exists():continue
                value=self._read_json(path);self._validate_feature(value,step,role,self._rows[(role,row_id)])
                actual=self._json[path.resolve()][1];previous=self._entry(key)
                if previous and previous[1]['sha256']!=actual:raise ValueError('Legacy child recomputed a divergent parent feature')
                if not previous:self._features[key]={'path':relative,'sha256':actual}
            relative=f'snapshots/update{step:03}/READY.json';path=self._path(self.child_id,relative)
            if path.exists():
                ready=self._read_json(path);self._validate_snapshot(self.child_id,step,ready)
                actual=self._json[path.resolve()][1];inherited=self.snapshot(step)
                if inherited is not None and canonical(inherited['ready'])!=canonical(ready):
                    raise ValueError('Legacy child snapshot diverges from immutable parent')
                if inherited is None:self._snapshots[str(step)]={'path':relative,'sha256':actual}
        return {'local_features':len(self._features),'local_snapshots':len(self._snapshots),'files_copied':0}

    def _writable(self):
        if (self.child/'lineage_manifest.json').exists():raise ValueError('Sealed children are read-only')

    @staticmethod
    def _write_exclusive(path,raw):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())

    def seal_terminal(self,stage,*,confirmed_terminal=False,call_id,execution_sources_sha256):
        self._writable()
        if stage not in TERMINAL or confirmed_terminal is not True or not call_id or not valid_hash(execution_sources_sha256):
            raise ValueError('A confirmed terminal call and execution-source provenance are required')
        # Re-hash child bytes once at the seal boundary, catching external edits.
        for key,entry in self._features.items():
            path=self._path(self.child_id,entry['path'])
            if digest(path.read_bytes())!=entry['sha256']:raise ValueError('Child feature changed before terminal sealing')
        for step,entry in self._snapshots.items():
            path=self._path(self.child_id,entry['path'])
            if digest(path.read_bytes())!=entry['sha256']:raise ValueError('Child READY changed before terminal sealing')
            ready=json.loads(path.read_bytes());self._file_hashes.clear();self._validate_snapshot(self.child_id,int(step),ready)
        manifest={'schema_version':1,'run_id':self.child_id,'identity':self.identity,'parent':self.parent,
            'stage':stage,'confirmed_terminal':True,'call_id':call_id,'execution_sources_sha256':execution_sources_sha256,
            'features':self._features,'snapshots':self._snapshots,
            'policy':'Read-only sealed parents; lazy verified JSON; child-only exclusive append; no gradient transformations.'}
        raw=canonical(manifest);self._write_exclusive(self.child/'lineage_manifest.json',raw)
        return {'run_id':self.child_id,'manifest_sha256':digest(raw)}
