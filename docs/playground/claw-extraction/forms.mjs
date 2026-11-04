import {smooth} from './engine/geometry.mjs?v=claw-20261103-1';
import {extractionAt as previousExtractionAt} from './core-reference.mjs?v=claw-20261103-1';
import {proofNodes,PROOF_EDGES} from './branch-reference.mjs?v=claw-20261103-1';

export {PROOF_EDGES};
export const PART_COUNT=40,FORWARD=12,PERIOD=18;
export const STAGES=[
  {id:'branches',label:'Branches',progress:0,description:'The proof branches sit above a closed mineral shell.'},
  {id:'clear',label:'Clear',progress:.32,description:'The branches have become an open claw. The shell clears its path.'},
  {id:'reach',label:'Reach',progress:.55,description:'The open fingers descend around the selected core.'},
  {id:'grip',label:'Grip',progress:.69,description:'The fingers close around the core before it moves.'},
  {id:'lifted',label:'Lifted',progress:1,description:'The claw and core rise together through the cleared shell.'}
];
const solid=(center,half,role,emission=0,rotation=[0,0,0,1])=>({center,half,role,emission,rotation,kind:0});
const mix=(a,b,t)=>a.map((v,k)=>v+(b[k]-v)*t);
const pad=parts=>{
  if(parts.length>PART_COUNT)throw Error('Claw scene exceeds renderer capacity');
  return [...parts,...Array.from({length:PART_COUNT-parts.length},()=>solid([0,0,0],[0,0,0],'unused'))];
};
export function beam(from,to,index){
  const delta=to.map((v,k)=>v-from[k]),length=Math.hypot(...delta);
  if(length<1e-6)return solid(from,[0,0,0],`edge-${index}`,.35);
  const direction=delta.map(v=>v/length),raw=[direction[2],0,-direction[0],1+direction[1]],norm=Math.hypot(...raw);
  const rotation=norm<1e-7?[1,0,0,0]:raw.map(v=>v/norm);
  return solid(mix(from,to,.5),[.055,length/2+.015,.055],`edge-${index}`,.35,rotation);
}
export function gripNodes({approach=0,grip=0,lift=0}){
  const x=.28*lift,y=3-1.72*approach+1.78*lift,radius=.70-(.70-.475)*grip,tipY=y-1.40;
  return [
    [x,y+.45,0],[x,y,0],
    [x+.73,y-.35,0],[x-.365,y-.35,.632],[x-.365,y-.35,-.632],
    [x+radius,tipY,-.13],[x+radius,tipY,.13],
    [x-.315,tipY,radius],[x-.095,tipY,radius],[x-.205,tipY,-radius]
  ];
}
export function clawAt(value){
  const progress=Math.max(0,Math.min(1,value)),selected=smooth(.04,.10,progress),morph=smooth(.06,.26,progress),opening=smooth(.12,.30,progress),approach=smooth(.34,.54,progress),grip=smooth(.56,.68,progress),lift=smooth(.70,.94,progress);
  const source=previousExtractionAt(0),shell=source.boxes.filter(p=>p.role!=='core'&&p.role!=='unused').map(p=>({...p,center:[...p.center],half:[...p.half]}));
  shell.find(p=>p.role==='lid').center=[-1.75*opening,1.03,-.10*opening];
  shell.find(p=>p.role==='sliding-face').center=[.93+1.12*opening,-.22*opening,0];
  const core=source.boxes.filter(p=>p.role==='core').map(p=>({...p,center:[p.center[0]+.28*lift,p.center[1]+1.78*lift,p.center[2]],emission:.05+selected*1.07}));
  const branch=proofNodes().map(p=>[p[0]*.62,-p[1]*.62+3,p[2]*.62]),target=gripNodes({approach,grip,lift}),nodes=branch.map((p,i)=>mix(p,target[i],morph));
  const joints=nodes.map((p,i)=>solid(p,Array(3).fill(i<2?.13:i<5?.105:.085),`joint-${i}`,i<5?.45:.78));
  const edges=PROOF_EDGES.map(([a,b],i)=>beam(nodes[a],nodes[b],i));
  let stage=STAGES[0];
  if(progress>=.06&&progress<.30)stage={id:'forming',label:'Forming claw',description:'The connected branches reshape as the shell opens.'};
  else if(progress>=.30&&progress<.34)stage=STAGES[1];
  else if(progress>=.34&&progress<.54)stage={id:'approaching',label:'Approaching',description:'The open claw lowers through the cleared opening.'};
  else if(progress>=.54&&progress<.56)stage=STAGES[2];
  else if(progress>=.56&&progress<.68)stage={id:'gripping',label:'Gripping',description:'The fingers close while the core remains in place.'};
  else if(progress>=.68&&progress<.70)stage=STAGES[3];
  else if(progress>=.70&&progress<.999)stage={id:'lifting',label:'Lifting',description:'The attached claw and core move as one assembly.'};
  else if(progress>=.999)stage=STAGES[4];
  return {boxes:pad([...shell,...core,...joints,...edges]),progress,stage,nodes,opening,morph,approach,grip,lift,state:{focus:stage.id,flash:Math.sin(Math.PI*morph)*.12}};
}
export function referenceAt(progress){return previousExtractionAt(progress);}
export function sequenceAt(seconds){
  const time=((seconds%PERIOD)+PERIOD)%PERIOD;
  if(time<FORWARD)return time/FORWARD;
  if(time<14.5)return 1;
  return 1-smooth(14.5,PERIOD,time);
}
export function layoutFor(width,height){
  const unit=Math.min(100,width/7.4,height/7.6);
  return {unit,center:[width/2,height*.59],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};
}
