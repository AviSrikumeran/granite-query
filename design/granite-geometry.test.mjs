import test from 'node:test';
import assert from 'node:assert/strict';
import {FORMS,SHAPES,BOX_COUNT,HOLD,TRANSITION,STEP,PERIOD,boxesAt,mixBoxes,slerp,rotate,traceBoxes} from '../docs/playground/granite/geometry.mjs';
const close=(a,b,tolerance=1e-8)=>assert.ok(Math.abs(a-b)<tolerance,`${a} != ${b}`);

test('all four original forms contain sixteen finite oriented solids',()=>{
  const signatures=[];
  for(const form of FORMS){
    assert.equal(SHAPES[form].length,BOX_COUNT);signatures.push(JSON.stringify(SHAPES[form]));
    for(const box of SHAPES[form]){
      assert.ok([...box.center,...box.half,...box.rotation].every(Number.isFinite));
      assert.ok(box.half.every(v=>v>0));close(Math.hypot(...box.rotation),1);
      assert.ok(box.center.every(v=>Math.abs(v)<1.3));assert.ok(box.half.every(v=>v<1.3));
    }
  }
  assert.equal(new Set(signatures).size,4);
});
test('quaternion interpolation takes the short route and preserves unit length',()=>{
  const q=SHAPES.loop[0].rotation,opposite=q.map(v=>-v);
  for(const t of [0,.2,.5,.8,1]){
    const result=slerp(q,opposite,t);close(Math.hypot(...result),1);
    rotate(result,[1,2,3]).forEach((v,i)=>close(v,rotate(q,[1,2,3])[i]));
  }
});
test('the complete sequence loops at identical geometry without orientation flips',()=>{
  assert.deepEqual(boxesAt(0),boxesAt(PERIOD));
  for(const form of FORMS)assert.deepEqual(boxesAt(1,form).boxes,boxesAt(20,form).boxes);
  const before=boxesAt(PERIOD-1e-5).boxes,after=boxesAt(0).boxes;
  before.forEach((box,i)=>{
    box.center.forEach((v,k)=>close(v,after[i].center[k],1e-6));
    close(Math.abs(box.rotation.reduce((sum,v,k)=>sum+v*after[i].rotation[k],0)),1,1e-6);
  });
});
test('morphs bound position changes and keep rotations valid at every sampled frame',()=>{
  let maximum=0;
  for(let i=0;i<4;i++){
    let previous=boxesAt(i*STEP+HOLD).boxes;
    for(let frame=1;frame<=Math.ceil(TRANSITION*60);frame++){
      const boxes=boxesAt(i*STEP+HOLD+Math.min(TRANSITION,frame/60)).boxes;
      boxes.forEach((box,j)=>{
        close(Math.hypot(...box.rotation),1,1e-6);
        for(const key of ['center','half'])box[key].forEach((v,k)=>{maximum=Math.max(maximum,Math.abs(v-previous[j][key][k]));});
      });previous=boxes;
    }
  }
  assert.ok(maximum<.03,`part moved ${maximum} units in one 60 Hz frame`);
});
test('an interrupted morph begins at the displayed position and orientation',()=>{
  const displayed=boxesAt(HOLD+TRANSITION*.43).boxes;
  assert.deepEqual(mixBoxes(displayed,SHAPES.helix,0),displayed);
  assert.deepEqual(mixBoxes(displayed,SHAPES.helix,1),SHAPES.helix);
});
test('the fallback ray test handles oriented solids and misses outside the scene',()=>{
  const q=[0,Math.sin(Math.PI/8),0,Math.cos(Math.PI/8)];
  const box={center:[0,0,0],half:[1,.4,.4],rotation:q};
  assert.ok(traceBoxes(0,0,[box]));assert.equal(traceBoxes(8,8,[box]),null);
  const v=rotate(q,[1,0,0]);close(v[0],Math.SQRT1_2);close(v[2],-Math.SQRT1_2);
});
