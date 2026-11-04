// Reference-matching formations reconstructed from the supplied Modal recording.
export const FORMS=['box','layers','cubes','stairs'];
export const FORM_LABELS={box:'Box',layers:'Separated plates',cubes:'Small cubes',stairs:'Stairs'};
export const BOX_COUNT=12,BOOT=1.55,HOLD=4.5,TRANSITION=.5,MORPH_START=.2,MORPH_END=.4;
export const STEP=HOLD+TRANSITION,PERIOD=STEP*FORMS.length;
const clamp=t=>Math.max(0,Math.min(1,t));
export const smooth=(a,b,t)=>{t=clamp((t-a)/(b-a));return t*t*(3-2*t);};
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const normalize=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
const solid=(center,half,kind=0)=>({center,half,kind,rotation:[0,0,0,1]});
const pad=boxes=>[...boxes,...Array.from({length:BOX_COUNT-boxes.length},()=>solid([0,0,0],[0,0,0]))];
function box(){
  const boxes=[];
  for(let axis=0;axis<3;axis++)for(const a of [-.9,.9])for(const b of [-.9,.9]){
    const center=[0,0,0],half=[.1,.1,.1];
    center[(axis+1)%3]=a;center[(axis+2)%3]=b;half[axis]=1;
    boxes.push(solid(center,half));
  }
  return boxes;
}
const layers=()=>pad([-.85,0,.85].map(y=>solid([0,y,0],[.95,.065,.95])));
function cubes(){
  const boxes=[];
  for(const x of [-.74,.74])for(const y of [-.74,.74])for(const z of [-.74,.74])boxes.push(solid([x,y,z],[.21,.21,.21]));
  return pad(boxes);
}
const stairs=()=>pad(Array.from({length:5},(_,i)=>{const top=.91-i*.38,bottom=-.95;return solid([0,(top+bottom)/2,-.76+i*.38],[.95,(top-bottom)/2,.19]);}));
export const SHAPES={box:box(),layers:layers(),cubes:cubes(),stairs:stairs()};
export const REFLECTIONS=[
  {name:'left',offset:[-1.92,-.05],scale:.98,aspect:1,mirror:[1,1,-1],strength:.44,fade:[1,0,-1.6,.4]},
  {name:'upper',offset:[1.45,-1.65],scale:.88,aspect:.6,mirror:[1,-1,1],strength:.36,fade:[0,1,-1.5,.6]},
  {name:'lower',offset:[1.55,1.5],scale:.76,aspect:.55,mirror:[-1,1,1],strength:.14,fade:[0,-1,-1.4,.6]}
];
export function layoutFor(width,height){
  const mobile=width<=600,unit=Math.min(136,Math.max(width*.074,Math.min(72,width*.165)));
  const centerY=mobile?Math.min(470,height*.65):width<=900?Math.min(440,height*.65):Math.min(556,height*.7);
  return {mobile,unit,pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,center:[width*.5,centerY],left:Math.max(0,width*.5-unit*3.8),right:Math.min(width,width*.5+unit*3.8),top:Math.max(mobile?320:300,centerY-unit*3.15),bottom:Math.min(height,centerY+unit*3.15)};
}
export function sceneBounds(boxes){
  const active=boxes.filter(b=>b.half.every(v=>v>.001)),lo=[0,1,2].map(k=>Math.min(...active.map(b=>b.center[k]-b.half[k]))),hi=[0,1,2].map(k=>Math.max(...active.map(b=>b.center[k]+b.half[k])));
  return {center:lo.map((v,k)=>(v+hi[k])/2),half:lo.map((v,k)=>(hi[k]-v)/2+.035)};
}

// The recording shows a brief reshaping under the flare, not a hard cut.
export function switchState(from,to,elapsed){
  const t=Math.max(0,elapsed),transitioning=t<TRANSITION;
  const flash=t<.15?smooth(0,.15,t):1-smooth(.15,TRANSITION,t),blend=smooth(MORPH_START,MORPH_END,t);
  const focus=blend<.5?from:to;
  return {from,to,focus,blend,flash:transitioning?flash:0,transitioning,phase:transitioning?(t<MORPH_START?'flare':t<MORPH_END?'reshape':'settle'):'hold'};
}
export function stateAt(time,mode='auto'){
  if(FORMS.includes(mode))return {from:mode,to:mode,focus:mode,blend:0,flash:0,transitioning:false,phase:'hold'};
  const clock=((time%PERIOD)+PERIOD)%PERIOD,index=Math.floor(clock/STEP),elapsed=clock-index*STEP,from=FORMS[index];
  if(elapsed<HOLD)return {from,to:from,focus:from,blend:0,flash:0,transitioning:false,phase:'hold'};
  return switchState(from,FORMS[(index+1)%FORMS.length],elapsed-HOLD);
}
export function boxesAt(time,mode='auto'){
  const state=stateAt(time,mode);return {state,boxes:mixBoxes(SHAPES[state.from],SHAPES[state.to],state.blend)};
}
export function mixBoxes(from,to,t){
  if(t<=1e-9)return from;if(t>=1-1e-9)return to;
  const active=boxes=>boxes.filter(b=>b.half.every(v=>v>.001));
  const start=active(from),end=active(to),nearest=(point,boxes)=>boxes.reduce((best,b)=>Math.hypot(...b.center.map((v,k)=>v-point[k]))<Math.hypot(...best.center.map((v,k)=>v-point[k]))?b:best);
  return from.map((a,i)=>{
    const b=to[i],ac=a.half.every(v=>v>.001)?a.center:nearest(b.center,start).center,bc=b.half.every(v=>v>.001)?b.center:nearest(a.center,end).center;
    return {center:ac.map((v,k)=>v+(bc[k]-v)*t),half:a.half.map((v,k)=>v+(b.half[k]-v)*t),rotation:[0,0,0,1],kind:t<.5?a.kind:b.kind};
  });
}
export function revealAt(time,seed,rim=0,radius=1){
  const front=smooth(.96,1.23,time)*2.4,delay=radius+seed*.09;
  const filled=smooth(delay-.1,delay+.16,front)*smooth(.92,1.02,time);
  return Math.max(filled,seed>.982?.55*rim:0);
}
export function startupFlare(time){return smooth(.96,1.12,time)*(1-smooth(1.12,BOOT,time));}
export function pointerPose(x,y,width,height,active=true){
  const limit=v=>Math.max(-1,Math.min(1,v));
  return {turn:active?limit(x/width*2-1)*.105:0,tilt:active?limit(y/height*2-1)*.065:0};
}
export function lightDirection(time){return normalize([.9,.3+.1*Math.sin(time*.31),.3+.45*Math.sin(time*.43)]);}
export function surfaceLight(normal,point,rim,time){
  const diffuse=Math.max(0,dot(normal,lightDirection(time))),band=Math.pow(.5+.5*Math.sin(dot(point,[2.4,2.8,-1.4])-time*1.45),3);
  return .17+diffuse*.32+rim*.2+band*(.2+diffuse*.25+rim*.18);
}
export function highlightFlare(light,flash){return light+flash*.8*smooth(.48,.85,light);}
export function paletteRamp(hex){
  const base=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
  return {base,shadow:base.map(v=>v*.24),highlight:base.map((v,i)=>v+(1-v)*[.58,.65,.1][i])};
}
export function rotate(q,v){
  const uv=cross(q,v),uuv=cross(q,uv);
  return v.map((n,i)=>n+2*(q[3]*uv[i]+uuv[i]));
}
export function cameraRotate(p,turn=0,tilt=0){
  const c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt);
  const x=p[0]*c-p[2]*s,z=p[0]*s+p[2]*c;
  return [x,p[1]*ct-z*st,p[1]*st+z*ct];
}
export function traceBoxes(screenX,screenY,boxes,turn=0,tilt=0,time=0,mirror=[1,1,1]){
  const x=screenX/1.7320508;
  const origin=cameraRotate([x+8,-screenY+8,-x+8],turn,tilt).map((v,k)=>v*mirror[k]),direction=cameraRotate([-.57735027,-.57735027,-.57735027],turn,tilt).map((v,k)=>v*mirror[k]);
  let nearest=1000,hit=null;
  for(const [boxIndex,box] of boxes.entries()){
    if(box.half.some(v=>v<.001))continue;
    const inverse=[-box.rotation[0],-box.rotation[1],-box.rotation[2],box.rotation[3]];
    const o=rotate(inverse,origin.map((v,k)=>v-box.center[k])),d=rotate(inverse,direction),near=[],far=[];
    for(let k=0;k<3;k++){const inv=1/(Math.abs(d[k])<1e-6?1e-6:d[k]),a=(-box.half[k]-o[k])*inv,b=(box.half[k]-o[k])*inv;near[k]=Math.min(a,b);far[k]=Math.max(a,b);}
    const entry=Math.max(...near),exit=Math.min(...far);
    if(entry<=exit&&exit>0&&entry<nearest){
      nearest=entry;const position=o.map((v,k)=>v+d[k]*entry),margins=position.map((v,k)=>Math.max(0,box.half[k]-Math.abs(v))).sort((a,b)=>a-b);
      const axis=near.indexOf(entry),normal=[0,0,0];normal[axis]=-Math.sign(d[axis]);
      const worldNormal=rotate(box.rotation,normal).map((v,k)=>v*mirror[k]),world=origin.map((v,k)=>(v+direction[k]*entry)*mirror[k]);
      const rim=Math.exp(-Math.pow(margins[1]/.1,2));
      hit={boxIndex,rim,normal:worldNormal,world,light:surfaceLight(worldNormal,world,rim,time),depth:entry};
    }
  }
  return hit;
}
export function reflectionVisible(x,y,boxes,turn=0,tilt=0){const b=sceneBounds(boxes);return traceBoxes(x,y,[{...b,rotation:[0,0,0,1],kind:0}],turn,tilt)?0:1;}
