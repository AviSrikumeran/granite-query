import {smooth} from './engine/geometry.mjs?v=claw-20261103-1';
import {FORMATIONS} from './baseline.mjs?v=claw-20261103-1';

export const PART_COUNT=40;
export const STAGES=[
  {id:'closed',label:'Closed',progress:0,description:'A mineral shell holds the selected volume.'},
  {id:'selected',label:'Selected',progress:.22,description:'Magenta light identifies the core through the seams.'},
  {id:'open',label:'Open',progress:.52,description:'The lid and one side move clear of the extraction path.'},
  {id:'extracted',label:'Extracted',progress:1,description:'The core lifts free; small gaps reveal its eight modules.'}
];
const solid=(center,half,role='shell',emission=0)=>({center,half,rotation:[0,0,0,1],kind:0,role,emission});
const pad=parts=>[...parts,...Array.from({length:PART_COUNT-parts.length},()=>solid([0,0,0],[0,0,0],'unused'))];
export function extractionAt(value){
  const progress=Math.max(0,Math.min(1,value)),selected=smooth(.08,.22,progress),opening=smooth(.24,.50,progress),lift=smooth(.53,.87,progress),spread=smooth(.86,1,progress)*.035;
  const boxes=[
    solid([-1.75*opening,1.03,-.10*opening],[.93,.12,.93],'lid'),
    solid([0,-.93,0],[.93,.12,.93],'base'),
    solid([.93+1.12*opening,-.22*opening,0],[.12,.77,.77],'sliding-face'),
    solid([-.93,0,0],[.12,.77,.77]),
    solid([0,0,.93],[.77,.77,.12]),
    solid([0,0,-.93],[.77,.77,.12])
  ];
  for(const x of [-1,1])for(const y of [-1,1])for(const z of [-1,1]){
    boxes.push(solid([x*(.205+spread)+.28*lift,y*(.205+spread)+1.78*lift,z*(.205+spread)],[.185,.185,.185],'core',.05+selected*1.07));
  }
  const stage=progress<.08?STAGES[0]:progress<.24?STAGES[1]:progress<.53?STAGES[2]:progress<.999?{id:'extracting',label:'Extracting',description:'The core rises through the cleared opening.'}:STAGES[3];
  return {boxes:pad(boxes),progress,selected,opening,lift,stage,state:{focus:stage.id,flash:Math.sin(Math.PI*smooth(.08,.24,progress))*.22}};
}
export const BASELINE=FORMATIONS.clear.locked;
export function sequenceAt(seconds){
  const t=((seconds%12)+12)%12;
  if(t<8)return t/8;
  if(t<10)return 1;
  return 1-smooth(10,12,t);
}
export function layoutFor(width,height){
  // Reserve room for the opened lid and lowered side at the full pointer range.
  const unit=Math.min(110,width/7.4,height/6.6);
  return {unit,center:[width/2,height*.55],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};
}
