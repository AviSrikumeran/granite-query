import test from 'node:test';
import assert from 'node:assert/strict';
import {revealAt,sequenceAt,layoutFor,PERIOD} from '../docs/playground/interlocking-reveal/forms.mjs';
import {rotate} from '../docs/playground/interlocking-reveal/engine/geometry.mjs';
import {materialColors,materialProfile} from '../docs/playground/interlocking-reveal/engine/material.mjs';
import {materialColors as baselineColors,materialProfile as baselineProfile} from '../docs/playground/purple/engine/material.mjs';

const active=scene=>scene.boxes.filter(b=>b.group!=='unused');
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} differs from ${b}`);
function penetrates(a,b){
  return a.center.every((v,k)=>Math.abs(v-b.center[k])<a.half[k]+b.half[k]-1e-7);
}
test('exactly three rigid groups keep their notches and dimensions throughout the loop',()=>{
  const rest=active(revealAt(0));
  for(let i=0;i<=400;i++){
    const scene=revealAt(i/400),parts=active(scene);
    assert.equal(scene.boxes.length,40);assert.equal(parts.length,10);
    assert.deepEqual([...new Set(parts.map(b=>b.group))],['left','right','core']);
    parts.forEach((b,j)=>{
      assert.ok([...b.center,...b.half,...b.rotation,b.emission].every(Number.isFinite));
      assert.deepEqual(b.half,rest[j].half);assert.deepEqual(b.rotation,[0,0,0,1]);
      b.center.forEach((v,k)=>close(v-rest[j].center[k],scene.offsets[b.group][k]));
    });
  }
});
test('the three moving pieces never penetrate each other during unlock, extraction or return',()=>{
  for(let i=0;i<=800;i++){
    const parts=active(revealAt(i/800));
    for(let a=0;a<parts.length;a++)for(let b=a+1;b<parts.length;b++){
      if(parts[a].group===parts[b].group)continue;
      assert.equal(penetrates(parts[a],parts[b]),false,`${parts[a].group}/${parts[b].group} collide at ${i}/800`);
    }
  }
});
test('selection precedes unlock, and the core returns before the pieces can close',()=>{
  for(let i=0;i<=800;i++){
    const scene=revealAt(i/800);
    if(scene.opening>0&&i/800<.83)close(scene.selected,1);
    if(scene.extraction>0)close(scene.opening,1);
    if(i/800>.83)close(scene.extraction,0);
  }
});
test('the complete cycle closes without a discontinuity or residual displacement',()=>{
  const start=revealAt(0),end=revealAt(1);
  assert.deepEqual(end.boxes,start.boxes);assert.equal(sequenceAt(PERIOD),0);
  for(const p of [.10,.20,.37,.55,.68,.83,.96,1]){
    const a=active(revealAt(p-1e-6)),b=active(revealAt(p+1e-6));
    a.forEach((v,i)=>v.center.forEach((n,k)=>assert.ok(Math.abs(n-b[i].center[k])<.0001)));
  }
});
test('all corners stay framed under mouse extremes on small and large views',()=>{
  for(const [w,h] of [[280,400],[335,400],[700,520],[840,560],[920,640]])for(let i=0;i<=40;i++)for(const turn of [-.105,.105])for(const tilt of [-.065,.065]){
    const layout=layoutFor(w,h),c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt);
    for(const b of active(revealAt(i/40)))for(const a of [-1,1])for(const d of [-1,1])for(const e of [-1,1]){
      const offset=rotate(b.rotation,b.half.map((v,k)=>v*[a,d,e][k])),v=b.center.map((n,k)=>n+offset[k]);
      const y=v[1]*ct+v[2]*st,z=-v[1]*st+v[2]*ct,q=[v[0]*c+z*s,y,-v[0]*s+z*c];
      const px=layout.center[0]+.8660254*(q[0]-q[2])*layout.unit,py=layout.center[1]+(.5*q[0]-q[1]+.5*q[2])*layout.unit;
      assert.ok(px>=5&&px<=w-5&&py>=5&&py<=h-22,`clipped ${b.group}, ${w}x${h}, p=${i/40}: ${px},${py}`);
    }
  }
});
test('the selected magenta palette and lighting profile preserve the established material',()=>{
  assert.deepEqual(materialColors('magenta'),baselineColors('magenta'));
  assert.deepEqual(materialProfile('magenta'),baselineProfile('magenta'));
});
