// Independently authored forms. Fixed GPU slots do not imply moving parts.
export const FORMS=['frames','steps','slabs','tiers'];
export const FORM_LABELS={frames:'Nested squares',steps:'Stepped blocks',slabs:'Stacked slabs',tiers:'Rounded tiers'};
export const BOX_COUNT=16,BOOT=1.15,HOLD=4.8,TRANSITION=.46,SWITCH_AT=.17;
export const STEP=HOLD+TRANSITION,PERIOD=STEP*FORMS.length;
const clamp=t=>Math.max(0,Math.min(1,t));
export const smooth=(a,b,t)=>{t=clamp((t-a)/(b-a));return t*t*(3-2*t);};
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const normalize=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
const solid=(center,half,kind=0)=>({center,half,kind,rotation:[0,0,0,1]});
const pad=boxes=>[...boxes,...Array.from({length:BOX_COUNT-boxes.length},()=>solid([0,0,0],[0,0,0]))];
function frames(){
  const boxes=[];
  for(let i=0;i<4;i++){
    const r=.67+i*.06,x=-.12+i*.08,y=.025*i,z=-.72+i*.48,t=.085;
    boxes.push(solid([x-r,y,z],[t,r+t,t]),solid([x+r,y,z],[t,r+t,t]),solid([x,y-r,z],[r-t,t,t]),solid([x,y+r,z],[r-t,t,t]));
  }
  return boxes;
}
function steps(){
  // Rise away from the camera so the risers remain visible, not a rear wall.
  return pad(Array.from({length:5},(_,i)=>{
    const top=-.65+i*.38,bottom=-.88;
    return solid([.72-i*.36,(top+bottom)/2,0],[.18,(top-bottom)/2,.67]);
  }));
}
function slabs(){
  return pad(Array.from({length:3},(_,i)=>solid([-.1+i*.1,-.68+i*.68,-.06+i*.06],[.86,.105,.72])));
}
function tiers(){
  return pad(Array.from({length:3},(_,i)=>solid([-.09+i*.09,-.68+i*.68,0],[.9-i*.08,.12,.9-i*.08],1)));
}
export const SHAPES={frames:frames(),steps:steps(),slabs:slabs(),tiers:tiers()};

// No interpolated solids: the old silhouette persists until the commit instant.
export function switchState(from,to,elapsed){
  const t=Math.max(0,elapsed),transitioning=t<TRANSITION;
  const flash=t<SWITCH_AT?smooth(0,SWITCH_AT,t):1-smooth(SWITCH_AT,TRANSITION,t);
  const focus=t<SWITCH_AT?from:to;
  return {from,to,focus,flash:transitioning?flash:0,transitioning,phase:transitioning?(t<SWITCH_AT?'flare':'settle'):'hold'};
}
export function stateAt(time,mode='auto'){
  if(FORMS.includes(mode))return {from:mode,to:mode,focus:mode,flash:0,transitioning:false,phase:'hold'};
  const clock=((time%PERIOD)+PERIOD)%PERIOD,index=Math.floor(clock/STEP),elapsed=clock-index*STEP,from=FORMS[index];
  if(elapsed<HOLD)return {from,to:from,focus:from,flash:0,transitioning:false,phase:'hold'};
  return switchState(from,FORMS[(index+1)%FORMS.length],elapsed-HOLD);
}
export function boxesAt(time,mode='auto'){
  const state=stateAt(time,mode);return {state,boxes:SHAPES[state.focus]};
}
export function revealAt(time,seed,rim=0){
  const t=clamp(time/BOOT),delay=seed*.55+(1-rim)*.12;
  const filled=smooth(delay,delay+.3,t);
  return Math.max(filled,seed>.982?.12*rim:0);
}
export function highlightFlare(light,flash){return light+flash*.8*smooth(.48,.85,light);}
export function paletteRamp(hex){
  const base=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
  return {base,shadow:base.map(v=>v*.24),highlight:base.map((v,i)=>v+(1-v)*[.68,.68,.28][i])};
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
export function traceBoxes(screenX,screenY,boxes,turn=0,tilt=0){
  const x=screenX/1.7320508;
  const origin=cameraRotate([x+8,-screenY+8,-x+8],turn,tilt),direction=cameraRotate([-.57735027,-.57735027,-.57735027],turn,tilt);
  let nearest=1000,hit=null;
  for(const box of boxes){
    if(box.half.some(v=>v<.001))continue;
    const inverse=[-box.rotation[0],-box.rotation[1],-box.rotation[2],box.rotation[3]];
    const o=rotate(inverse,origin.map((v,k)=>v-box.center[k])),d=rotate(inverse,direction),near=[],far=[];
    if(box.kind===1){
      const [rx,h,rz]=box.half,A=(d[0]/rx)**2+(d[2]/rz)**2,B=2*(o[0]*d[0]/rx**2+o[2]*d[2]/rz**2),C=(o[0]/rx)**2+(o[2]/rz)**2-1;
      const discriminant=B*B-4*A*C;
      if(discriminant<0)continue;
      const radial=[(-B-Math.sqrt(discriminant))/(2*A),(-B+Math.sqrt(discriminant))/(2*A)],caps=[(-h-o[1])/d[1],(h-o[1])/d[1]].sort((a,b)=>a-b);
      const entry=Math.max(radial[0],caps[0]),exit=Math.min(radial[1],caps[1]);
      if(entry<=exit&&exit>0&&entry<nearest){
        nearest=entry;const p=o.map((v,k)=>v+d[k]*entry),cap=entry===caps[0];
        const localNormal=cap?[0,-Math.sign(d[1]),0]:normalize([p[0]/rx**2,0,p[2]/rz**2]),normal=rotate(box.rotation,localNormal);
        const edge=cap?Math.abs(1-Math.hypot(p[0]/rx,p[2]/rz))*Math.min(rx,rz):h-Math.abs(p[1]);
        const rim=Math.exp(-Math.pow(edge/.1,2)),diffuse=Math.max(0,dot(normal,normalize([-.45,.8,.45])));
        hit={rim,normal,light:.16+diffuse*.72+rim*.25,depth:entry};
      }
      continue;
    }
    for(let k=0;k<3;k++){const inv=1/(Math.abs(d[k])<1e-6?1e-6:d[k]),a=(-box.half[k]-o[k])*inv,b=(box.half[k]-o[k])*inv;near[k]=Math.min(a,b);far[k]=Math.max(a,b);}
    const entry=Math.max(...near),exit=Math.min(...far);
    if(entry<=exit&&exit>0&&entry<nearest){
      nearest=entry;const position=o.map((v,k)=>v+d[k]*entry),margins=position.map((v,k)=>Math.max(0,box.half[k]-Math.abs(v))).sort((a,b)=>a-b);
      const axis=near.indexOf(entry),normal=[0,0,0];normal[axis]=-Math.sign(d[axis]);
      const worldNormal=rotate(box.rotation,normal),diffuse=Math.max(0,dot(worldNormal,normalize([-.45,.8,.45])));
      const rim=Math.exp(-Math.pow(margins[1]/.1,2));
      hit={rim,normal:worldNormal,light:.16+diffuse*.72+rim*.25,depth:entry};
    }
  }
  return hit;
}
