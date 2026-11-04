import test from 'node:test';
import assert from 'node:assert/strict';
import {clawAt,referenceAt,PROOF_EDGES,sequenceAt,layoutFor} from '../docs/playground/claw-extraction/forms.mjs';
import {extractionAt} from '../docs/playground/core-extraction/forms.mjs';
import {proofNodes} from '../docs/playground/directions/forms.mjs';
import {rotate} from '../docs/playground/claw-extraction/engine/geometry.mjs';

const dot=(a,b)=>a.reduce((sum,v,i)=>sum+v*b[i],0),sub=(a,b)=>a.map((v,i)=>v-b[i]);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const axes=box=>[[1,0,0],[0,1,0],[0,0,1]].map(v=>rotate(box.rotation,v));
function penetrates(a,b){
  const aa=axes(a),ba=axes(b),delta=sub(b.center,a.center),candidates=[...aa,...ba,...aa.flatMap(u=>ba.map(v=>cross(u,v)))];
  for(const raw of candidates){
    const norm=Math.hypot(...raw);if(norm<1e-7)continue;const axis=raw.map(v=>v/norm);
    const ra=aa.reduce((sum,v,i)=>sum+Math.abs(dot(axis,v))*a.half[i],0),rb=ba.reduce((sum,v,i)=>sum+Math.abs(dot(axis,v))*b.half[i],0);
    if(Math.abs(dot(delta,axis))>=ra+rb-1e-6)return false;
  }
  return true;
}
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);

test('the reference samples the previous extraction without changing its geometry',()=>{
  for(const p of [0,.22,.32,.55,.69,.85,1])assert.deepEqual(referenceAt(p),extractionAt(p));
});
test('the initial claw graph is the proof branch graph with a fixed placement',()=>{
  const scene=clawAt(0),expected=proofNodes().map(p=>[p[0]*.62,-p[1]*.62+3,p[2]*.62]);
  assert.deepEqual(scene.nodes,expected);assert.equal(PROOF_EDGES.length,9);assert.equal(scene.nodes.length,10);
});
test('all nine oriented links stay attached to their joints throughout the morph and lift',()=>{
  for(let i=0;i<=160;i++){
    const scene=clawAt(i/160);assert.equal(scene.boxes.length,40);
    for(const box of scene.boxes){assert.ok([...box.center,...box.half,...box.rotation,box.emission].every(Number.isFinite));near(Math.hypot(...box.rotation),1);}
    PROOF_EDGES.forEach(([from,to],index)=>{
      const beam=scene.boxes.find(p=>p.role===`edge-${index}`),d=rotate(beam.rotation,[0,beam.half[1]-.015,0]);
      beam.center.forEach((v,k)=>{near(v-d[k],scene.nodes[from][k]);near(v+d[k],scene.nodes[to][k]);});
    });
  }
});
test('the shell clears before reaching and the grip closes before lifting',()=>{
  for(let i=0;i<=200;i++){
    const s=clawAt(i/200);
    if(s.approach>0){near(s.opening,1);near(s.morph,1);}
    if(s.grip>0)near(s.approach,1);
    if(s.lift>0)near(s.grip,1);
  }
});
test('the five contact pads touch the core and retain their relative pose during the pull',()=>{
  const start=clawAt(.69),initialCore=start.boxes.filter(p=>p.role==='core');
  for(const p of [.70,.75,.82,.90,1]){
    const scene=clawAt(p),core=scene.boxes.filter(p=>p.role==='core'),dx=.28*scene.lift,dy=1.78*scene.lift;
    core.forEach((b,i)=>{near(b.center[0]-initialCore[i].center[0],dx);near(b.center[1]-initialCore[i].center[1],dy);});
    for(let i=5;i<10;i++)scene.nodes[i].forEach((v,k)=>near(v-start.nodes[i][k],[dx,dy,0][k]));
    const xmax=Math.max(...core.map(b=>b.center[0]+b.half[0])),zmax=Math.max(...core.map(b=>b.center[2]+b.half[2])),zmin=Math.min(...core.map(b=>b.center[2]-b.half[2]));
    for(const i of [5,6])near(scene.nodes[i][0]-scene.boxes.find(p=>p.role===`joint-${i}`).half[0],xmax);
    for(const i of [7,8])near(scene.nodes[i][2]-scene.boxes.find(p=>p.role===`joint-${i}`).half[2],zmax);
    near(scene.nodes[9][2]+scene.boxes.find(p=>p.role==='joint-9').half[2],zmin);
  }
});
test('claw and core avoid shell penetration and the open fingers avoid the core',()=>{
  for(let i=0;i<=200;i++){
    const scene=clawAt(i/200),active=scene.boxes.filter(p=>p.half.every(v=>v>.001)),shell=active.filter(p=>!p.role.startsWith('joint-')&&!p.role.startsWith('edge-')&&p.role!=='core'),core=active.filter(p=>p.role==='core'),claw=active.filter(p=>p.role.startsWith('joint-')||p.role.startsWith('edge-'));
    for(const part of [...core,...claw])for(const wall of shell)assert.equal(penetrates(part,wall),false,`${part.role} hits ${wall.role} at ${i}/200`);
    for(const part of claw)for(const cell of core)assert.equal(penetrates(part,cell),false,`${part.role} penetrates core at ${i}/200`);
  }
});
test('all rotated parts remain framed at pointer extremes on narrow and wide canvases',()=>{
  for(const [w,h] of [[335,420],[555,470],[760,470]])for(const p of [0,.12,.26,.32,.45,.55,.69,.82,1])for(const turn of [-.105,.105])for(const tilt of [-.065,.065]){
    const layout=layoutFor(w,h),c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt);
    for(const b of clawAt(p).boxes.filter(p=>p.half.every(v=>v>.001)))for(const a of [-1,1])for(const d of [-1,1])for(const e of [-1,1]){
      const offset=rotate(b.rotation,b.half.map((v,i)=>v*[a,d,e][i])),v=b.center.map((x,i)=>x+offset[i]),y=v[1]*ct+v[2]*st,z=-v[1]*st+v[2]*ct,q=[v[0]*c+z*s,y,-v[0]*s+z*c];
      const px=layout.center[0]+.8660254*(q[0]-q[2])*layout.unit,py=layout.center[1]+(.5*q[0]-q[1]+.5*q[2])*layout.unit;
      assert.ok(px>=4&&px<=w-4&&py>=4&&py<=h-4,`clipped ${b.role} at ${w}px, progress ${p}`);
    }
  }
});
test('the loop holds a secure pickup before returning continuously',()=>{
  assert.equal(sequenceAt(0),0);assert.equal(sequenceAt(12),1);assert.equal(sequenceAt(13.5),1);assert.equal(sequenceAt(18),0);
  for(const t of [12,14.5,18])assert.ok(Math.abs(sequenceAt(t-.00001)-sequenceAt(t+.00001))<.0001);
});
