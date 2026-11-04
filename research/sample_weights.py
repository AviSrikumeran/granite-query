"""Inspect real BF16 scalar values; comparison bodies remain remote."""
import json
import math
from pathlib import Path
import struct
import numpy as np
import requests
from inspect_models import ROOT, url, save

REPOS=['ibm-granite/granite-4.2-3b','tiiuae/Falcon-H1-3B-Instruct','allenai/Olmo-3-7B-Instruct','Qwen/Qwen3-4B','deepseek-ai/DeepSeek-R1-Distill-Qwen-7B']

def bf16(raw):
 return (np.frombuffer(raw,dtype='<u2').astype(np.uint32)<<16).view(np.float32)

samples=[]
for repo in REPOS:
 folder=ROOT/'models'/repo.replace('/','--')
 audit=json.loads((folder/'audit.json').read_text())
 key='model.layers.0.self_attn.q_proj.weight'
 for filename in audit['canonical_weight_files']:
  hp=folder/(filename+'.header.json')
  if not hp.exists():continue
  h=json.loads(hp.read_text())
  if key not in h:continue
  t=h[key];assert t['dtype']=='BF16'
  local=folder/filename
  if local.exists():
   with local.open('rb') as f:
    n=struct.unpack('<Q',f.read(8))[0]; start=8+n+t['data_offsets'][0];f.seek(start);raw=f.read(2048)
  else:
   # Header length may include padding; get exact prefix remotely.
   address=url(repo,audit['revision'],filename)
   with requests.get(address,headers={'Range':'bytes=0-7','Accept-Encoding':'identity'},stream=True,timeout=(20,90)) as r:
    r.raise_for_status();n=struct.unpack('<Q',r.raw.read(8))[0]
   start=8+n+t['data_offsets'][0]
   with requests.get(address,headers={'Range':f'bytes={start}-{start+2047}','Accept-Encoding':'identity'},stream=True,timeout=(20,90)) as r:
    r.raise_for_status()
    if r.status_code!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-'):
     raise ValueError('Range not honored; refusing to download comparison body')
    raw=r.raw.read(2048)
  values=bf16(raw);assert len(values)==1024 and np.isfinite(values).all()
  samples.append({'repo':repo,'revision':audit['revision'],'tensor':key,'shape':t['shape'],'dtype':'BF16','sample_elements':1024,'method':'First 1024 consecutive scalars in row-major storage, reshaped 32 by 32 only for display. Not a 32 by 32 submatrix.','values':[float(x) for x in values],'mean':float(values.mean()),'std':float(values.std()),'min':float(values.min()),'max':float(values.max())})
  print(json.dumps({'sampled':repo,'std':float(values.std())}),flush=True)
  break
save(ROOT/'scalar_samples.json',{'meaning':'Artifact inspection only. Different models use different learned coordinate systems; colors, magnitudes and zeros do not establish quality, reasoning efficiency or causal deficits. Comparison samples were fetched with byte ranges, not full checkpoint downloads.','samples':samples})

# Verify every stored Granite scalar is finite, without loading a model or using GPU.
folder=ROOT/'models'/'ibm-granite--granite-4.2-3b'
total=bad=zeros=0
for p in sorted(folder.glob('*.safetensors')):
 with p.open('rb') as f:
  n=struct.unpack('<Q',f.read(8))[0]; h=json.loads(f.read(n)); base=8+n
 for key,t in h.items():
  if key=='__metadata__':continue
  assert t['dtype']=='BF16'
  start,end=t['data_offsets'];count=math.prod(t['shape']);assert end-start==count*2
  mapped=np.memmap(p,dtype='<u2',mode='r',offset=base+start,shape=(count,))
  for offset in range(0,count,8_000_000):
   chunk=mapped[offset:offset+8_000_000]
   bad+=int(np.count_nonzero((chunk & 0x7f80)==0x7f80))
   zeros+=int(np.count_nonzero((chunk & 0x7fff)==0))
  total+=count
  del mapped
save(ROOT/'granite_value_audit.json',{'repo':REPOS[0],'revision':json.loads((folder/'audit.json').read_text())['revision'],'scalar_elements_checked':total,'nonfinite_elements':bad,'exact_zero_elements':zeros,'method':'Bitwise BF16 exponent scan of all weight tensors in 8M-element chunks. Does not execute model code or inference.','finite':bad==0})
print(json.dumps({'granite_scalars_checked':total,'nonfinite':bad,'zeros':zeros}),flush=True)
