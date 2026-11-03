import {BOOT,smooth} from './engine/geometry.mjs?v=magenta-20261103-2';
export const PART_COUNT=40,DIRECTIONS=['green','purple'],POSES=['locked','open','offset'];
export const HOLD=4.5,EVENT=.5,STEP=HOLD+EVENT,PERIOD=STEP*POSES.length;
const solid=(center,half)=>({center,half,rotation:[0,0,0,1],kind:0});
function blocks(pose,spacing){
  const clear=spacing==='clear',parts=[],thickness=clear?.19:.22;
  for(let axis=0;axis<3;axis++)for(const sign of [-1,1]){
    const lateral=(axis+1)%3,depth=(axis+2)%3;
    const shift=pose==='offset'?sign*.12:0,spread=pose==='open'?.14:0;
    for(const [a,b] of [[-1.12,-.38],[-.38,.38],[.38,1.12]]){
      const center=[0,0,0],half=Array(3).fill(thickness),bridge=a===-.38;
      center[axis]=(a+b)/2+shift;half[axis]=(b-a)/2;
      center[lateral]=sign*((clear?.42:.34)+spread);
      if(bridge){half[depth]=clear?.075:.1;center[depth]=sign*(thickness-half[depth]);}
      parts.push(solid(center,half));
    }
  }
  return [...parts,...Array.from({length:PART_COUNT-parts.length},()=>solid([0,0,0],[0,0,0]))];
}
export const FORMATIONS=Object.fromEntries(['reference','clear'].map(spacing=>[spacing,Object.fromEntries(POSES.map(pose=>[pose,blocks(pose,spacing)]))]));
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
export function formationAt(id,time,mode='auto',offset=0,spacing='clear'){
  const state=stateAt(Math.max(0,time-BOOT)+offset,mode),forms=FORMATIONS[spacing];
  return {state,boxes:blendParts(forms[state.from],forms[state.to],state.blend)};
}
export function layoutFor(width,height){
  const unit=Math.min(132,width*.205,height*.255);
  return {unit,center:[width/2,height*.5],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};
}
