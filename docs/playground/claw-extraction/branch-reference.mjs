import {BOOT,smooth} from './engine/geometry.mjs?v=claw-20261103-1';

export const PART_COUNT=40;
export const DIRECTIONS=['blocks','branches','frames'];
export const POSES=['locked','open','offset'];
export const HOLD=4.5,EVENT=.5,STEP=HOLD+EVENT,PERIOD=STEP*POSES.length;
const solid=(center,half)=>({center,half,rotation:[0,0,0,1],kind:0});
const pad=parts=>{
  if(parts.length>PART_COUNT)throw Error('Formation exceeds the renderer capacity');
  return [...parts,...Array.from({length:PART_COUNT-parts.length},()=>solid([0,0,0],[0,0,0]))];
};

// Six notched beams run in three orthogonal directions. The thin central
// bridges leave keyways between the full-depth ends of neighboring modules.
function blocks(pose){
  const parts=[];
  for(let axis=0;axis<3;axis++)for(const sign of [-1,1]){
    const lateral=(axis+1)%3,depth=(axis+2)%3;
    const shift=pose==='offset'?sign*.12:0,spread=pose==='open'?.14:0;
    for(const [a,b] of [[-1.12,-.38],[-.38,.38],[.38,1.12]]){
      const center=[0,0,0],half=[.22,.22,.22],bridge=a===-.38;
      center[axis]=(a+b)/2+shift;half[axis]=(b-a)/2;
      center[lateral]=sign*(.34+spread);
      if(bridge){center[depth]=sign*.12;half[depth]=.1;}
      parts.push(solid(center,half));
    }
  }
  return pad(parts);
}

export const PROOF_EDGES=[[0,1],[1,2],[1,3],[1,4],[2,5],[2,6],[3,7],[3,8],[4,9]];
export function proofNodes(pose='locked'){
  // Arrange the five conclusions distinctly in the accepted isometric view,
  // then lift them onto different depth planes instead of overlapping leaves.
  const projected=[[0,1.3,0],[0,.55,0],[-.62,-.08,-.2],[.62,-.08,.2],[0,-.45,-.5],[-1.25,-1.12,-.1],[-.52,-1.28,.25],[1.25,-1.12,.1],[.52,-1.28,-.25],[0,-1.7,-.5]];
  const nodes=projected.map(([x,y,depth])=>[(depth+x/.8660254)/2,depth/2-y,(depth-x/.8660254)/2]);
  return nodes.map((p,i)=>p.map((v,k)=>{
    if(i<2)return v;
    if(pose==='open')return v*(k===1?.96:1.12);
    if(pose==='offset'&&k===2)return v+(i%2?.08:-.08);
    return v;
  }));
}
function branches(pose){
  const nodes=proofNodes(pose),parts=nodes.map((p,i)=>solid(p,Array(3).fill(i<2?.145:.125)));
  // Every edge keeps the same three slots in every pose, including zero-length
  // segments. This preserves continuity when a branch changes its depth.
  for(const [from,to] of PROOF_EDGES){
    const cursor=[...nodes[from]],target=nodes[to];
    for(const axis of [1,0,2]){
      const next=[...cursor];next[axis]=target[axis];
      const center=cursor.map((v,k)=>(v+next[k])/2),half=[.062,.062,.062];
      half[axis]=Math.abs(next[axis]-cursor[axis])/2;
      parts.push(solid(center,half));cursor[axis]=next[axis];
    }
  }
  return pad(parts);
}

function frame(size,thickness,offset){
  const parts=[];
  for(let axis=0;axis<3;axis++)for(const a of [-1,1])for(const b of [-1,1]){
    const center=[...offset],half=Array(3).fill(thickness);
    center[(axis+1)%3]+=a*(size-thickness);center[(axis+2)%3]+=b*(size-thickness);half[axis]=size;
    parts.push(solid(center,half));
  }
  return parts;
}
function frames(pose){
  const centers=pose==='open'?[[0,0,0],[.12,.14,-.12],[.02,.04,-.02]]:pose==='offset'?[[0,0,0],[-.1,.08,.1],[.04,-.04,-.04]]:[[0,0,0],[0,0,0],[0,0,0]];
  return pad([...[1.06,.69,.32].flatMap((size,i)=>frame(size,[.095,.075,.055][i],centers[i]))]);
}
export const FORMATIONS=Object.fromEntries(DIRECTIONS.map(id=>[id,Object.fromEntries(POSES.map(pose=>[pose,({blocks,branches,frames}[id])(pose)]))]));

export function transition(from,to,elapsed){
  const t=Math.max(0,elapsed),blend=smooth(.2,.4,t),active=t<EVENT;
  return {from,to,focus:blend<.5?from:to,blend,flash:active?(t<.15?smooth(0,.15,t):1-smooth(.15,EVENT,t)):0,transitioning:active};
}
export function stateAt(clock,mode='auto'){
  if(POSES.includes(mode))return {from:mode,to:mode,focus:mode,blend:0,flash:0,transitioning:false};
  const t=((clock%PERIOD)+PERIOD)%PERIOD,i=Math.floor(t/STEP),elapsed=t-i*STEP,from=POSES[i];
  return elapsed<HOLD?{from,to:from,focus:from,blend:0,flash:0,transitioning:false}:transition(from,POSES[(i+1)%POSES.length],elapsed-HOLD);
}
export function blendParts(from,to,t){
  if(t<=0)return from;if(t>=1)return to;
  return from.map((p,i)=>solid(p.center.map((v,k)=>v+(to[i].center[k]-v)*t),p.half.map((v,k)=>v+(to[i].half[k]-v)*t)));
}
export function formationAt(id,time,mode='auto',offset=0){
  const state=stateAt(Math.max(0,time-BOOT)+offset,mode);
  return {state,boxes:blendParts(FORMATIONS[id][state.from],FORMATIONS[id][state.to],state.blend)};
}
export function layoutFor(width,height){
  const unit=Math.min(96,width*.195,height*.18);
  return {unit,center:[width/2,height*.5],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};
}
