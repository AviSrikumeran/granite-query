import assert from 'node:assert/strict';
import {STEPS,stateAt,activeStep} from './trace.mjs';
assert.equal(new Set(STEPS.map(step=>step.id)).size,STEPS.length);
for(const step of STEPS){assert.ok(step.start>=0&&step.end<=100&&step.start<step.end);if(step.parent){const parent=STEPS.find(value=>value.id===step.parent);assert.ok(parent);assert.ok(step.depth>parent.depth);assert.ok(step.start>=parent.start);}}
for(let p=-5;p<=105;p+=.5){const states=stateAt(p);assert.equal(states.length,STEPS.length);for(const step of states)assert.ok(Number.isFinite(step.fraction)&&step.fraction>=0&&step.fraction<=1);assert.ok(STEPS.some(step=>step.id===activeStep(p).id));}
assert.equal(stateAt(-10)[0].fraction,0);assert.equal(stateAt(120).every(step=>step.state==='complete'),true);assert.equal(activeStep(30).id,'scores');assert.equal(activeStep(70).id,'uncertainty');assert.equal(activeStep(100).id,'answer');
console.log('Workflow sequence: unique IDs, bounded ranges, ancestry, every sampled state and expected active steps passed.');
