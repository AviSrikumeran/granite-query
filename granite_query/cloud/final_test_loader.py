"""Permit-first bounded final-test loader. Imported code never accesses test data.

Only an explicit authorized future invocation may fetch the pinned split. A
durable attempt precedes HTTP; ambiguous attempts never trigger another fetch.
Recoveries reuse persisted source/sample bytes and matching hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request

from cloud import final_eval_control as seal
from ranking.verification import numeric_answer

MAX_SOURCE_BYTES=8*1024*1024


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def rows_bytes(rows):return b''.join(encoded(row) for row in rows)
def sha_bytes(value):return hashlib.sha256(value).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic(path,value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('wb') as handle:handle.write(encoded(value));handle.flush();os.fsync(handle.fileno())
    temporary.replace(path)


def require_role(manifest,role,implementation,*,dependencies=()):
    protocol=manifest['protocol']
    if seal.digest(protocol)!=manifest['freeze_sha256'] or not protocol.get('execution_ready'):
        raise ValueError('A sealed reviewed final execution protocol is required')
    entry=protocol['execution_sources']['roles'][role]
    if (entry.get('capabilities')!=seal.CAPABILITIES[role]
            or entry.get('sha256')!=seal.sha(implementation)
            or entry.get('path','').replace('\\','/').split('/')[-1]!=Path(implementation).name):
        raise ValueError('This implementation differs from the reviewed final executor: '+role)
    for dependency in dependencies:
        name=Path(dependency).name
        expected=entry.get('dependencies',{}).get(name,{})
        if expected.get('sha256')!=seal.sha(dependency):
            raise ValueError('Reviewed final dependency missing or changed: '+name)
    return entry


def require_packaged_sources(manifest):
    """The remote image uses Linux paths; frozen local paths identify basenames."""
    root=Path(__file__).resolve().parent
    for entry in manifest['protocol']['source_code'].values():
        name=entry['path'].replace('\\','/').split('/')[-1]
        path=root/name
        if path.suffix!='.py' or not path.is_file() or seal.sha(path)!=entry['sha256']:
            raise ValueError('Frozen packaged final source changed: '+name)


def source_url(manifest):
    data=manifest['protocol']['dataset']
    if (data['repository']!='openai/grade-school-math'
            or data['revision']!='3101c7d5072418e28b9008a6636bde82a006892c'
            or data['relative_path']!='grade_school_math/data/test.jsonl'):
        raise ValueError('Final source must be the predeclared pinned canonical file')
    return 'https://raw.githubusercontent.com/'+data['repository']+'/'+data['revision']+'/'+data['relative_path']


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'GraniteQuery-FinalEvaluation/1.0'})
    with urllib.request.urlopen(request,timeout=30) as response:
        raw=response.read(MAX_SOURCE_BYTES+1)
    if len(raw)>MAX_SOURCE_BYTES:raise ValueError('Canonical final source exceeds the bounded download cap')
    return raw


def select(raw,manifest):
    if not isinstance(raw,bytes) or len(raw)>MAX_SOURCE_BYTES:
        raise ValueError('Final source must be bounded complete bytes')
    population=[json.loads(line) for line in raw.decode('utf-8-sig').split('\n') if line.strip()]
    if len(population)!=1319:raise ValueError('Canonical test population differs from the frozen1319 rows')
    selected=[]
    for index in manifest['protocol']['dataset']['indices']:
        row=population[index]
        if not isinstance(row.get('question'),str) or not row['question'].strip() or not isinstance(row.get('answer'),str) or '####' not in row['answer']:
            raise ValueError('Canonical final record schema differs')
        final=row['answer'].rsplit('####',1)[1].strip()
        if numeric_answer(final) is None:raise ValueError('Final reference is not a plain numeric answer')
        selected.append({'id':f'gsm8k:test:{index:05d}','prompt':row['question'],'gold_answer':final,
            'source_split':'test','role':'final_eval_only','training_eligible':False})
    if len(selected)!=256 or len({r['id'] for r in selected})!=256:raise ValueError('Final subset identity changed')
    return selected


def validate_sample(raw,sample_manifest,manifest):
    if (sample_manifest.get('freeze_sha256')!=manifest['freeze_sha256']
            or sample_manifest.get('sample_rows_sha256')!=sha_bytes(raw)
            or sample_manifest.get('count')!=256 or sample_manifest.get('role')!='final_eval_only'
            or sample_manifest.get('training_eligible') is not False or sample_manifest.get('official_test_used') is not True):
        raise ValueError('Prepared final sample provenance differs')
    rows=[json.loads(line) for line in raw.decode('utf-8-sig').split('\n') if line.strip()]
    expected=[f'gsm8k:test:{i:05d}' for i in manifest['protocol']['dataset']['indices']]
    if [r.get('id') for r in rows]!=expected or sample_manifest.get('ids')!=expected:
        raise ValueError('Prepared final question identities/order differ')
    for row in rows:
        if (row.get('source_split')!='test' or row.get('role')!='final_eval_only'
                or row.get('training_eligible') is not False or not isinstance(row.get('prompt'),str)
                or not row['prompt'].strip() or numeric_answer(str(row.get('gold_answer',''))) is None):
            raise ValueError('Final sample cannot become training-eligible or change references')
    return rows


def load_prepared(final_folder,input_folder):
    manifest=seal.verify(final_folder);input_folder=seal.private(input_folder)
    sample=read(input_folder/'sample_manifest.json');raw=(input_folder/'sample.jsonl').read_bytes()
    rows=validate_sample(raw,sample,manifest)
    registry=Path(manifest['protocol']['access_registry_path'])
    permit=read(registry);receipt=read(registry.with_name(registry.stem+'.dataset_receipt.json'))
    if (permit.get('freeze_sha256')!=manifest['freeze_sha256']
            or permit.get('owner_sha256')!=manifest['protocol']['access_owner_sha256']
            or receipt.get('freeze_sha256')!=manifest['freeze_sha256']
            or receipt.get('owner_sha256')!=manifest['protocol']['access_owner_sha256']
            or receipt.get('sample_rows_sha256')!=sample['sample_rows_sha256']
            or receipt.get('dataset_sha256')!=sample['dataset_sha256']):
        raise ValueError('Prepared sample lacks the durable sealed dataset receipt')
    return manifest,sample,raw,rows


def prepare(final_folder,output,*,authorized=False,fetcher=fetch):
    manifest=seal.verify(final_folder);require_role(manifest,'test_loader',Path(__file__))
    if not authorized:raise ValueError('Explicit final-test access authorization is required')
    output=seal.private(output);output.mkdir(parents=True,exist_ok=True)
    owner=read(Path(final_folder)/'access_owner.json')['owner_token']
    permit=seal.begin_access(final_folder,owner_token=owner,loader_authorized=True)
    registry=Path(manifest['protocol']['access_registry_path'])
    destination=registry.with_name(registry.stem+'.loader_owner.json')
    destination_identity={'freeze_sha256':manifest['freeze_sha256'],'owner_sha256':seal.digest(owner),'output_path':str(output)}
    try:seal.write_once(destination,destination_identity)
    except FileExistsError:
        if read(destination)!=destination_identity:
            raise ValueError('Another persisted loader destination owns this access; no fresh download')
    lock=output/'loader.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode())
        marker=output/'fetch_started.json';source=output/'source.jsonl';pending=output/'source.download'
        if source.exists():
            raw=source.read_bytes()
        elif marker.exists():
            # A completed persisted download is recoverable without a new GET.
            if not pending.exists():raise ValueError('Ambiguous prior final fetch; no automatic fresh download')
            raw=pending.read_bytes();select(raw,manifest)
            pending.replace(source)
        else:
            # Exclusive durable intent is written before any network operation.
            seal.write_once(marker,{'freeze_sha256':manifest['freeze_sha256'],'owner_sha256':seal.digest(owner),
                'source_url_sha256':sha_bytes(source_url(manifest).encode()),'started_at_utc':seal.now()})
            raw=fetcher(source_url(manifest))
            select(raw,manifest)
            with pending.open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
            pending.replace(source)
        marker_value=read(marker)
        if marker_value.get('freeze_sha256')!=manifest['freeze_sha256'] or marker_value.get('owner_sha256')!=seal.digest(owner):
            raise ValueError('Persisted final fetch belongs to another protocol/owner')
        selected=select(raw,manifest);sample_raw=rows_bytes(selected)
        source_hash=sha_bytes(raw);sample_hash=sha_bytes(sample_raw)
        receipt=seal.bind_dataset_receipt(final_folder,owner_token=owner,dataset_sha256=source_hash,
            population_count=1319,sample_rows_sha256=sample_hash,indices=manifest['protocol']['dataset']['indices'])
        value={'role':'final_eval_only','freeze_sha256':manifest['freeze_sha256'],'count':256,
            'sample_rows_sha256':sample_hash,'dataset_sha256':source_hash,'ids':[r['id'] for r in selected],
            'source_split':'test','official_test_used':True,'full_test_evaluation':False,'training_eligible':False}
        sample_path=output/'sample.jsonl'
        if sample_path.exists() and sample_path.read_bytes()!=sample_raw:raise ValueError('Persisted final sample changed')
        if not sample_path.exists():
            with sample_path.open('xb') as handle:handle.write(sample_raw);handle.flush();os.fsync(handle.fileno())
        manifest_path=output/'sample_manifest.json'
        if manifest_path.exists() and read(manifest_path)!=value:raise ValueError('Persisted final sample manifest changed')
        if not manifest_path.exists():seal.write_once(manifest_path,value)
        return {'stage':'prepared_final_eval_only','count':256,'resume':permit['resume'] or receipt['resume'],
            'official_test_used':True,'training_eligible':False,'paid_work_launched':False}
    finally:
        os.close(fd);lock.unlink()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final-folder',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--authorize-final-test-access',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(args.final_folder,args.output,authorized=args.authorize_final_test_access)))
