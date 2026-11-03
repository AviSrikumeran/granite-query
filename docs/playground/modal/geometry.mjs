// Authored geometry reconstructed from observed forms, not extracted shader code.
export const FORMS = ['box', 'layers', 'stairs', 'cubes'];
export const FORM_LABELS = {box:'Box', layers:'Layers', stairs:'Stairs', cubes:'Small cubes'};
export const HOLD = 3.2;
export const TRANSITION = 1.8;
export const STEP = HOLD + TRANSITION;
export const PERIOD = STEP * FORMS.length;
export const BOX_COUNT = 12;

const block = (center, half) => ({center, half});
const dormant = () => block([0,0,0], [.001,.001,.001]);
function makeBox() {
  const boxes = [];
  for(let axis=0;axis<3;axis++) for(const a of [-.9,.9]) for(const b of [-.9,.9]) {
    const center=[0,0,0], half=[.1,.1,.1];
    center[(axis+1)%3]=a;center[(axis+2)%3]=b;half[axis]=1;
    boxes.push(block(center,half));
  }
  return boxes;
}
function makeLayers() {
  return [-.85,0,.85].map(y=>block([0,y,0],[1.03,.065,1.03]));
}
function makeStairs() {
  return Array.from({length:5},(_,i)=>{
    const top=.96-i*.39, bottom=-1;
    return block([0,(top+bottom)/2,-.8+i*.4],[1.03,(top-bottom)/2,.2]);
  });
}
function makeCubes() {
  const boxes=[];
  for(const x of [-.83,.83]) for(const y of [-.83,.83]) for(const z of [-.83,.83]) boxes.push(block([x,y,z],[.235,.235,.235]));
  return boxes;
}
export const SHAPES = Object.fromEntries(Object.entries({box:makeBox(),layers:makeLayers(),stairs:makeStairs(),cubes:makeCubes()}).map(([key,boxes])=>[key,Array.from({length:BOX_COUNT},(_,i)=>boxes[i]||dormant())]));

const smooth = t => t*t*t*(t*(t*6-15)+10);
export function stateAt(time, mode='auto') {
  if(FORMS.includes(mode))return {from:mode,to:mode,blend:0,focus:mode,transitioning:false};
  const clock=((time%PERIOD)+PERIOD)%PERIOD;
  const index=Math.floor(clock/STEP), elapsed=clock-index*STEP;
  const blend=smooth(Math.max(0,Math.min(1,(elapsed-HOLD)/TRANSITION)));
  const from=FORMS[index],to=FORMS[(index+1)%FORMS.length];
  return {from,to,blend,focus:blend<.5?from:to,transitioning:elapsed>HOLD};
}
export function boxesAt(time, mode='auto') {
  const state=stateAt(time,mode);
  const boxes=SHAPES[state.from].map((source,i)=>{
    const target=SHAPES[state.to][i];
    // Small per-part offsets give an assembly sequence instead of a global scale pulse.
    const delay=(i%4)*.035;
    const raw=Math.max(0,Math.min(1,(state.blend-delay)/(1-delay)));
    const t=smooth(raw);
    return block(source.center.map((v,k)=>v+(target.center[k]-v)*t),source.half.map((v,k)=>v+(target.half[k]-v)*t));
  });
  return {state,boxes};
}

// The fallback samples the same orthographic scene as the WebGL renderer.
export function traceBoxes(screenX,screenY,boxes,turn=0) {
  const c=Math.cos(turn),s=Math.sin(turn), x=screenX/1.7320508;
  const raw=[x+8,-screenY+8,-x+8], ray=[-.57735027,-.57735027,-.57735027];
  const origin=[raw[0]*c-raw[2]*s,raw[1],raw[0]*s+raw[2]*c];
  const direction=[ray[0]*c-ray[2]*s,ray[1],ray[0]*s+ray[2]*c];
  let closest=Infinity,hit=null;
  for(const box of boxes) {
    if(Math.min(...box.half)<.004)continue;
    const near=[],far=[];
    for(let k=0;k<3;k++) {const a=(box.center[k]-box.half[k]-origin[k])/direction[k], b=(box.center[k]+box.half[k]-origin[k])/direction[k];near[k]=Math.min(a,b);far[k]=Math.max(a,b);}
    const entry=Math.max(...near),exit=Math.min(...far);
    if(entry<=exit&&exit>0&&entry<closest) {
      closest=entry;
      const position=origin.map((v,k)=>v+direction[k]*entry);
      const margins=position.map((v,k)=>Math.max(0,box.half[k]-Math.abs(v-box.center[k]))).sort((a,b)=>a-b);
      const axis=near.indexOf(entry);
      hit={rim:Math.exp(-Math.pow(margins[1]/.095,2)),shade:[.7,.48,.86][axis],depth:entry};
    }
  }
  return hit;
}
