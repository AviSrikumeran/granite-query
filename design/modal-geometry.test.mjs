import test from 'node:test';
import assert from 'node:assert/strict';
import {FORMS,SHAPES,BOX_COUNT,PERIOD,HOLD,STEP,TRANSITION,stateAt,boxesAt,mixBoxes,traceBoxes} from '../docs/playground/modal/geometry.mjs';

test('each observed form has a distinct finite scene with a fixed camera envelope',()=>{
  const scenes=[];
  for(const form of FORMS){
    assert.equal(SHAPES[form].length,BOX_COUNT);
    scenes.push(JSON.stringify(SHAPES[form]));
    for(const box of SHAPES[form])for(let k=0;k<3;k++){
      assert.ok(Number.isFinite(box.center[k])&&box.half[k]>0);
      assert.ok(Math.abs(box.center[k])+box.half[k]<=1.1);
    }
  }
  assert.equal(new Set(scenes).size,FORMS.length);
});
test('automatic playback holds all four forms and loops continuously',()=>{
  FORMS.forEach((form,i)=>assert.equal(stateAt(i*STEP+HOLD/2).focus,form));
  assert.deepEqual(boxesAt(0),boxesAt(PERIOD));
  assert.equal(stateAt(HOLD/2).transitioning,false);
  assert.equal(stateAt(HOLD+.5).transitioning,true);
  const before=boxesAt(PERIOD-1e-5).boxes,after=boxesAt(0).boxes;
  for(let i=0;i<BOX_COUNT;i++)for(let k=0;k<3;k++)assert.ok(Math.abs(before[i].half[k]-after[i].half[k])<1e-5);
});
test('manual review pins geometry while the animation clock can keep running',()=>{
  for(const form of FORMS)assert.deepEqual(boxesAt(1,form).boxes,boxesAt(19,form).boxes);
});
test('ray-box sampling distinguishes a solid layer from the open cage',()=>{
  assert.equal(traceBoxes(.45,-.5,SHAPES.box),null);
  assert.ok(traceBoxes(.45,-.5,SHAPES.layers));
  assert.equal(traceBoxes(8,8,SHAPES.layers),null);
});

test('a transition spreads movement across frames instead of a sharp mid-cycle burst',()=>{
  let largest=0;
  for(let i=0;i<FORMS.length;i++){
    let previous=boxesAt(i*STEP+HOLD).boxes;
    for(let frame=1;frame<=Math.ceil(TRANSITION*60);frame++){
      const next=boxesAt(i*STEP+HOLD+Math.min(TRANSITION,frame/60)).boxes;
      next.forEach((box,j)=>['center','half'].forEach(key=>box[key].forEach((v,k)=>{largest=Math.max(largest,Math.abs(v-previous[j][key][k]));})));
      previous=next;
    }
  }
  assert.ok(largest<.03,`part moved ${largest} world units in one 60 Hz frame`);
});

test('interrupted transitions can restart from their displayed geometry without a jump',()=>{
  const displayed=boxesAt(HOLD+TRANSITION*.41).boxes;
  assert.deepEqual(mixBoxes(displayed,SHAPES.cubes,0),displayed);
  assert.deepEqual(mixBoxes(displayed,SHAPES.cubes,1),SHAPES.cubes);
});
