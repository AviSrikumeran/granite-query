// Original Granite Query structures. Local X follows each ribbon or beam.
export const FORMS=['loop','frames','weave','helix'];
export const FORM_LABELS={loop:'Folded loop',frames:'Nested frames',weave:'Weave',helix:'Double helix'};
export const BOX_COUNT=16,HOLD=2.4,TRANSITION=3.2,STEP=HOLD+TRANSITION,PERIOD=STEP*FORMS.length;
export const easeProgress=t=>{t=Math.max(0,Math.min(1,t));return t*t*t*(t*(t*6-15)+10);};
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const normalize=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
const copy=b=>({center:[...b.center],half:[...b.half],rotation:[...b.rotation]});

function basisQuaternion(x,y,z){
  const m00=x[0],m01=y[0],m02=z[0],m10=x[1],m11=y[1],m12=z[1],m20=x[2],m21=y[2],m22=z[2];
  const trace=m00+m11+m22;let q;
  if(trace>0){const s=Math.sqrt(trace+1)*2;q=[(m21-m12)/s,(m02-m20)/s,(m10-m01)/s,s/4];}
  else if(m00>m11&&m00>m22){const s=Math.sqrt(1+m00-m11-m22)*2;q=[s/4,(m01+m10)/s,(m02+m20)/s,(m21-m12)/s];}
  else if(m11>m22){const s=Math.sqrt(1+m11-m00-m22)*2;q=[(m01+m10)/s,s/4,(m12+m21)/s,(m02-m20)/s];}
  else{const s=Math.sqrt(1+m22-m00-m11)*2;q=[(m02+m20)/s,(m12+m21)/s,s/4,(m10-m01)/s];}
  return normalize(q);
}
function beam(a,b,width=.12,depth=.055,twist=0){
  const direction=b.map((v,i)=>v-a[i]),x=normalize(direction);
  const up=Math.abs(x[1])>.94?[0,0,1]:[0,1,0];
  const baseZ=normalize(cross(x,up)),baseY=cross(baseZ,x);
  const y=baseY.map((v,i)=>v*Math.cos(twist)+baseZ[i]*Math.sin(twist));
  const z=cross(x,y);
  return {center:a.map((v,i)=>(v+b[i])/2),half:[Math.hypot(...direction)/2+.025,width,depth],rotation:basisQuaternion(x,y,z)};
}
function loop(){
  const point=a=>[.84*Math.cos(a),.23*Math.sin(2*a),.84*Math.sin(a)];
  return Array.from({length:16},(_,i)=>{const a=i/16*Math.PI*2,b=(i+1)/16*Math.PI*2;return beam(point(a),point(b),.26,.055,(a+b)/4);});
}
function frames(){
  const boxes=[];
  for(let i=0;i<4;i++){
    const r=.56+i*.135,x=-.2+i*.13,y=.08*Math.sin(i),z=-.78+i*.52;
    const corners=[[x-r,y-r,z],[x-r,y+r,z],[x+r,y+r,z],[x+r,y-r,z]];
    for(let j=0;j<4;j++)boxes.push(beam(corners[j],corners[(j+1)%4],.065,.065));
  }
  return boxes;
}
function weave(){
  const boxes=[];
  for(let i=0;i<8;i++){
    const p=-.98+i*.28,y=i%2?.09:-.09;
    boxes.push(beam([-1.04,y,p],[1.04,y,p],.065,.08));
  }
  for(let i=0;i<8;i++){
    const p=-.98+i*.28,y=i%2?-.09:.09;
    boxes.push(beam([p,y,-1.04],[p,y,1.04],.065,.08));
  }
  return boxes;
}
function helix(){
  const boxes=[];
  for(let strand=0;strand<2;strand++)for(let i=0;i<8;i++){
    const point=t=>{const a=t*Math.PI*2+strand*Math.PI;return [.65*Math.cos(a),-.92+t*1.84,.65*Math.sin(a)];};
    boxes.push(beam(point(i/8),point((i+1)/8),.18,.055,i/8*Math.PI*.6));
  }
  return boxes;
}
export const SHAPES={loop:loop(),frames:frames(),weave:weave(),helix:helix()};

export function slerp(a,b,t){
  let end=[...b],cosine=dot(a,end);
  if(cosine<0){end=end.map(v=>-v);cosine=-cosine;}
  if(cosine>.9995)return normalize(a.map((v,i)=>v+(end[i]-v)*t));
  const angle=Math.acos(Math.max(-1,Math.min(1,cosine))),denominator=Math.sin(angle);
  return a.map((v,i)=>(v*Math.sin((1-t)*angle)+end[i]*Math.sin(t*angle))/denominator);
}
export function rotate(q,v){
  const uv=cross(q,v),uuv=cross(q,uv);
  return v.map((n,i)=>n+2*(q[3]*uv[i]+uuv[i]));
}
export function mixBoxes(from,to,progress){
  if(progress<=0)return from.map(copy);if(progress>=1)return to.map(copy);
  return from.map((a,i)=>{
    const b=to[i],delay=(i%4)*.018,t=easeProgress((progress-delay)/(1-delay));
    return {center:a.center.map((v,k)=>v+(b.center[k]-v)*t),half:a.half.map((v,k)=>v+(b.half[k]-v)*t),rotation:slerp(a.rotation,b.rotation,t)};
  });
}
export function stateAt(time,mode='auto'){
  if(FORMS.includes(mode))return {from:mode,to:mode,progress:0,blend:0,focus:mode,transitioning:false};
  const clock=((time%PERIOD)+PERIOD)%PERIOD,index=Math.floor(clock/STEP),elapsed=clock-index*STEP;
  const progress=Math.max(0,Math.min(1,(elapsed-HOLD)/TRANSITION)),blend=easeProgress(progress);
  const from=FORMS[index],to=FORMS[(index+1)%FORMS.length];
  return {from,to,progress,blend,focus:blend<.5?from:to,transitioning:elapsed>HOLD};
}
export function boxesAt(time,mode='auto'){
  const state=stateAt(time,mode);return {state,boxes:mixBoxes(SHAPES[state.from],SHAPES[state.to],state.progress)};
}
export function traceBoxes(screenX,screenY,boxes,turn=0){
  const c=Math.cos(turn),s=Math.sin(turn),x=screenX/1.7320508;
  const raw=[x+8,-screenY+8,-x+8],ray=[-.57735027,-.57735027,-.57735027];
  const origin=[raw[0]*c-raw[2]*s,raw[1],raw[0]*s+raw[2]*c],direction=[ray[0]*c-ray[2]*s,ray[1],ray[0]*s+ray[2]*c];
  let nearest=1000,hit=null;
  for(const box of boxes){
    const inverse=[-box.rotation[0],-box.rotation[1],-box.rotation[2],box.rotation[3]];
    const o=rotate(inverse,origin.map((v,k)=>v-box.center[k])),d=rotate(inverse,direction),near=[],far=[];
    for(let k=0;k<3;k++){const inv=1/(Math.abs(d[k])<1e-6?1e-6:d[k]),a=(-box.half[k]-o[k])*inv,b=(box.half[k]-o[k])*inv;near[k]=Math.min(a,b);far[k]=Math.max(a,b);}
    const entry=Math.max(...near),exit=Math.min(...far);
    if(entry<=exit&&exit>0&&entry<nearest){
      nearest=entry;const position=o.map((v,k)=>v+d[k]*entry),margins=position.map((v,k)=>Math.max(0,box.half[k]-Math.abs(v))).sort((a,b)=>a-b);
      const world=origin.map((v,k)=>v+direction[k]*entry);
      hit={rim:Math.exp(-Math.pow(margins[1]/.1,2)),hue:Math.max(0,Math.min(1,.5+world[0]*.3+world[1]*.2+world[2]*.22)),depth:entry};
    }
  }
  return hit;
}
