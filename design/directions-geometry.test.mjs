import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,readdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve,dirname,sep} from 'node:path';
import {BOOT,traceBoxes} from '../docs/playground/directions/engine/geometry.mjs';
import {DIRECTIONS,POSES,PART_COUNT,FORMATIONS,PROOF_EDGES,proofNodes,PERIOD,HOLD,formationAt,blendParts,layoutFor} from '../docs/playground/directions/forms.mjs';

test('all nine formations fit the fixed renderer capacity with finite geometry',()=>{
  for(const id of DIRECTIONS)for(const pose of POSES){
    const parts=FORMATIONS[id][pose];assert.equal(parts.length,PART_COUNT);
    for(const part of parts){assert.ok([...part.center,...part.half].every(Number.isFinite));assert.ok(part.half.every(v=>v>=0));assert.ok(part.center.every(v=>Math.abs(v)<1.7));}
  }
  const count=id=>FORMATIONS[id].locked.filter(b=>b.half.every(v=>v>.001)).length;
  assert.equal(count('blocks'),18);assert.equal(count('frames'),36);assert.ok(count('branches')>25);
});

test('proof paths form one rooted tree with five separated conclusions',()=>{
  const reached=new Set([0]);
  while(true){const before=reached.size;for(const [a,b] of PROOF_EDGES)if(reached.has(a))reached.add(b);if(before===reached.size)break;}
  assert.equal(reached.size,10);assert.equal(PROOF_EDGES.length,9);
  const leaves=[...reached].filter(i=>!PROOF_EDGES.some(([from])=>from===i));assert.equal(leaves.length,5);
  for(const pose of POSES){
    const nodes=proofNodes(pose),screen=leaves.map(i=>{const [x,y,z]=nodes[i];return [.8660254*(x-z),.5*(x+z)-y];});
    for(let i=0;i<screen.length;i++)for(let j=i+1;j<screen.length;j++)assert.ok(Math.hypot(screen[i][0]-screen[j][0],screen[i][1]-screen[j][1])>.45);
  }
});

test('the three neutral silhouettes differ and preserve negative space',()=>{
  const signatures=[];
  for(const id of DIRECTIONS){
    let signature='',filled=0;
    for(let y=-2.1;y<=2.1;y+=.1)for(let x=-2.1;x<=2.1;x+=.1){const hit=!!traceBoxes(x,y,FORMATIONS[id].locked);signature+=hit?'1':'0';if(hit)filled++;}
    assert.ok(filled>150&&filled<1200,`${id}: ${filled}`);signatures.push(signature);
  }
  assert.equal(new Set(signatures).size,3);
});

test('shared pose changes interpolate without resetting the identity or clock',()=>{
  for(const id of DIRECTIONS){
    const from=FORMATIONS[id].locked,to=FORMATIONS[id].open;
    assert.deepEqual(blendParts(from,to,0),from);assert.deepEqual(blendParts(from,to,1),to);
    for(let n=0;n<=20;n++){
      const scene=formationAt(id,BOOT+HOLD+n/40);
      assert.equal(scene.boxes.length,PART_COUNT);for(const p of scene.boxes)assert.ok([...p.center,...p.half].every(Number.isFinite));
    }
    assert.deepEqual(formationAt(id,BOOT),formationAt(id,BOOT+PERIOD));
    assert.deepEqual(formationAt(id,0,'open'),formationAt(id,100,'open'));
  }
  for(const time of [0,1,6.15,6.35,11.4,16.2]){
    const states=DIRECTIONS.map(id=>formationAt(id,time).state);assert.deepEqual(states[0],states[1]);assert.deepEqual(states[1],states[2]);
  }
});

test('all view sizes preserve the accepted glyph-to-world ratio',()=>{
  for(const [w,h] of [[320,440],[460,520],[380,330],[660,490]]){
    const l=layoutFor(w,h);assert.equal(l.center[0],w/2);assert.ok(l.unit>45);assert.ok(l.center[1]-2.3*l.unit>0);assert.ok(l.center[1]+2.3*l.unit<h);
    assert.ok(Math.abs(l.pitch/l.unit-6.4/95)<1e-9);assert.equal(l.left,0);assert.equal(l.right,w);
  }
});

test('the comparison has no runtime imports from the protected playground',async()=>{
  const root=fileURLToPath(new URL('../docs/playground/directions/',import.meta.url));
  async function walk(path){const entries=await readdir(path,{withFileTypes:true});return (await Promise.all(entries.map(e=>e.isDirectory()?walk(resolve(path,e.name)):[resolve(path,e.name)]))).flat();}
  for(const path of (await walk(root)).filter(p=>p.endsWith('.mjs'))){
    const source=await readFile(path,'utf8');for(const match of source.matchAll(/from\s+['"]([^'"]+)['"]/g)){
      if(!match[1].startsWith('.'))continue;
      const dependency=resolve(dirname(path),match[1].split('?')[0]);assert.ok(dependency.startsWith(root.replace(/[\\/]$/,'')+sep),dependency);
      await readFile(dependency,'utf8');
    }
  }
});
