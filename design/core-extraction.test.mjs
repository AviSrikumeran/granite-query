import test from 'node:test';
import assert from 'node:assert/strict';
import {extractionAt,BASELINE,sequenceAt,layoutFor} from '../docs/playground/core-extraction/forms.mjs';
import {FORMATIONS} from '../docs/playground/purple/forms.mjs';

const overlaps=(a,b)=>a.center.every((v,k)=>Math.abs(v-b.center[k])<a.half[k]+b.half[k]-1e-6);
test('reference geometry is an exact snapshot of the accepted clear blocks',()=>{
  assert.deepEqual(BASELINE,FORMATIONS.clear.locked);
});
test('the core remains clear of shell sections throughout extraction',()=>{
  for(let i=0;i<=300;i++){
    const scene=extractionAt(i/300);
    assert.equal(scene.boxes.length,40);
    const active=scene.boxes.filter(p=>p.half.every(v=>v>.001));
    for(const part of active)assert.ok([...part.center,...part.half,part.emission].every(Number.isFinite));
    const core=active.filter(p=>p.role==='core'),shell=active.filter(p=>p.role!=='core');
    assert.equal(core.length,8);
    for(const a of core)for(const b of shell)assert.equal(overlaps(a,b),false,`collision at ${i}/300 with ${b.role}`);
    for(let a=0;a<core.length;a++)for(let b=a+1;b<core.length;b++)assert.equal(overlaps(core[a],core[b]),false);
    if(scene.lift>0)assert.equal(scene.opening,1,'clear the lid before lifting');
  }
});
test('the released core clears the housing and keeps stable module dimensions',()=>{
  const closed=extractionAt(0),released=extractionAt(1);
  assert.equal(closed.stage.id,'closed');assert.equal(released.stage.id,'extracted');
  const core=released.boxes.filter(p=>p.role==='core');
  assert.ok(Math.min(...core.map(p=>p.center[1]-p.half[1]))>1.15);
  assert.deepEqual(core.map(p=>p.half),closed.boxes.filter(p=>p.role==='core').map(p=>p.half));
});
test('the loop holds extraction before a continuous return to closed',()=>{
  assert.equal(sequenceAt(0),0);assert.equal(sequenceAt(8),1);assert.equal(sequenceAt(9),1);assert.equal(sequenceAt(12),0);
  for(const t of [8,10,12])assert.ok(Math.abs(sequenceAt(t-.00001)-sequenceAt(t+.00001))<.0001);
});
test('opened parts fit the canvas at pointer extremes on narrow and wide views',()=>{
  for(const [width,height] of [[335,420],[555,470],[760,470]])for(const progress of [0,.22,.52,.75,1])for(const turn of [-.105,0,.105])for(const tilt of [-.065,0,.065]){
    const layout=layoutFor(width,height),c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt);
    for(const part of extractionAt(progress).boxes.filter(p=>p.half.every(v=>v>.001)))for(const a of [-1,1])for(const b of [-1,1])for(const d of [-1,1]){
      const p=part.center.map((v,k)=>v+part.half[k]*[a,b,d][k]),y=p[1]*ct+p[2]*st,z=-p[1]*st+p[2]*ct,q=[p[0]*c+z*s,y,-p[0]*s+z*c];
      const x=layout.center[0]+.8660254*(q[0]-q[2])*layout.unit,py=layout.center[1]+(.5*q[0]-q[1]+.5*q[2])*layout.unit;
      assert.ok(x>=4&&x<=width-4&&py>=4&&py<=height-4,`clipped ${part.role} at ${width}px, progress ${progress}`);
    }
  }
});
