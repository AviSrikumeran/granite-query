import {smooth} from './engine/geometry.mjs?v=reveal-20261103-1';

export const PART_COUNT=40,PERIOD=13.6;
export const STAGES=[
  {id:'joined',label:'Joined',progress:0,description:'Two keyed mineral pieces hold a luminous core.'},
  {id:'unlocked',label:'Unlocked',progress:.37,description:'The two pieces slide apart along their keyed seam.'},
  {id:'revealed',label:'Revealed',progress:.61,description:'The selected core floats forward, clear of both pieces.'}
];
const ease=(a,b,t)=>{const x=Math.max(0,Math.min(1,(t-a)/(b-a)));return x*x*x*(x*(x*6-15)+10);};
const box=(center,half,group,emission)=>({center,half,group,emission,rotation:[0,0,0,1],kind:0});

// Each bracket is a single rigid piece. These touching volumes describe its
// keyed profile, not separate moving cubes. The .08-wide joint is intentional.
const LEFT=[
  [[-.32,-.91,.44],[.80,.28,.38]],
  [[0,-.91,-.44],[1.12,.28,.38]],
  [[-.84,0,0],[.28,.63,.82]],
  [[-.56,.91,-.40],[.56,.28,.42]],
  [[-.84,.91,.44],[.28,.28,.38]]
];
const RIGHT=[
  [[.84,-.91,.44],[.28,.28,.38]],
  [[.84,.04,0],[.28,.59,.82]],
  [[.32,.91,.44],[.80,.28,.38]],
  [[.60,.91,-.40],[.52,.28,.42]]
];
export function revealAt(value){
  const progress=Math.max(0,Math.min(1,value));
  const selected=ease(.10,.20,progress)*(1-ease(.91,.99,progress));
  const opening=ease(.20,.37,progress)*(1-ease(.83,.96,progress));
  const settle=progress>.96?.018*Math.sin((progress-.96)/.04*Math.PI*2)**2*(1-ease(.96,1,progress)):0;
  const separation=opening+settle;
  const extraction=ease(.39,.55,progress)*(1-ease(.68,.83,progress));
  // Clear the rear key before lifting. The same path in reverse seats the
  // core first, so the shell never sweeps through it on the return.
  const offsets={left:[-.30*separation,-.18*separation,0],right:[.30*separation,.46*separation,0],core:[.30*extraction,.56*ease(.40,1,extraction),1.20*extraction]};
  const surface=.12+.11*selected;
  const pieces=[...LEFT.map(([p,h])=>box(p.map((v,k)=>v+offsets.left[k]),h,'left',surface)),...RIGHT.map(([p,h])=>box(p.map((v,k)=>v+offsets.right[k]),h,'right',surface)),box(offsets.core,[.42,.42,.42],'core',.67+.51*selected)];
  const boxes=[...pieces,...Array.from({length:PART_COUNT-pieces.length},()=>box([0,0,0],[0,0,0],'unused',0))];
  let stage=STAGES[0];
  if(progress>=.1&&progress<.2)stage={id:'selecting',label:'Selecting',description:'Light gathers around the selected core.'};
  else if(progress>=.2&&progress<.37)stage={id:'unlocking',label:'Unlocking',description:'The keyed pieces counter-slide to clear the core.'};
  else if(progress>=.37&&progress<.39)stage=STAGES[1];
  else if(progress>=.39&&progress<.55)stage={id:'revealing',label:'Revealing',description:'The core moves forward through the cleared opening.'};
  else if(progress>=.55&&progress<.68)stage=STAGES[2];
  else if(progress>=.68&&progress<.83)stage={id:'returning',label:'Returning',description:'The core returns before the pieces close.'};
  else if(progress>=.83&&progress<.96)stage={id:'locking',label:'Locking',description:'The two pieces slide back into their keyed joint.'};
  const flash=.10*Math.sin(Math.PI*smooth(.10,.20,progress))*(progress<.2?1:0)+.045*Math.sin(Math.PI*smooth(.95,1,progress));
  return {boxes,progress,stage,selected,opening,extraction,offsets,state:{flash}};
}
export const sequenceAt=seconds=>(((seconds%PERIOD)+PERIOD)%PERIOD)/PERIOD;
export function layoutFor(width,height){
  const unit=Math.min(width/4.8,height/5.15);
  return {unit,center:[width*.5,height*.5],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};
}
