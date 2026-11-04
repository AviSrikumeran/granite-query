import {smooth} from './engine/geometry.mjs?v=proof-20261103-1';

export const PART_COUNT=40;
export const STAGES=[
  {id:'query',label:'Query',progress:0},
  {id:'sources',label:'Sources',progress:.36},
  {id:'evidence',label:'Evidence',progress:.72},
  {id:'answer',label:'Answer',progress:1}
];
// Illustrative records and passages. This module never reads training state.
export const NODES=[
  {id:'query',tag:'Query',label:'The question',kind:'Query',stage:0,at:0,point:[0,-1.65,0],title:'What would verify a reported gain?',text:'Follow the records needed to assess a claimed improvement. This example specifies the evidence to look for; it does not report a model result.'},
  {id:'retrieve',tag:'Connect',label:'Find the relevant records',kind:'Retrieval',stage:1,at:.10,point:[0,-1.02,.05],title:'Three records, one question',text:'Connect the question to an evaluation protocol, paired results and a run record. Each record answers a different part of the claim.'},
  {id:'evaluation',tag:'Evaluation',label:'Evaluation protocol',kind:'Source record',stage:1,at:.22,point:[-1.50,-.32,-.12],title:'Evaluation protocol',text:'A protocol should identify the held-out queries, evaluation measure, scope and exclusions. It gives a result its context.'},
  {id:'results',tag:'Results',label:'Paired results',kind:'Source record',stage:1,at:.27,point:[0,-.32,.14],title:'Paired results',text:'Compare the base and adapted models on the same evaluation. A headline gain needs its baseline, comparison conditions and uncertainty.'},
  {id:'run',tag:'Run record',label:'Run record',kind:'Source record',stage:1,at:.32,point:[1.50,-.32,-.06],title:'Run record',text:'A run record should identify the model, configuration and reproducible artifact. It connects the reported result to the run that produced it.'},
  {id:'matched',tag:'E1',label:'Same held-out queries',kind:'Evidence requirement',stage:2,at:.46,point:[-2.02,.75,-.12],title:'E1 · Same held-out queries',text:'Use the same held-out query set for both models. Otherwise a score change may reflect different examples rather than the adaptation.',source:'Evaluation protocol'},
  {id:'scope',tag:'E2',label:'Scope and exclusions',kind:'Evidence requirement',stage:2,at:.51,point:[-1.01,.75,.08],title:'E2 · Scope and exclusions',text:'Keep the dataset scope and excluded cases beside the result. A finding on this evaluation does not establish performance on every query.',source:'Evaluation protocol'},
  {id:'comparison',tag:'E3',label:'Matched comparison',kind:'Evidence requirement',stage:2,at:.56,point:[0,.75,.18],title:'E3 · Matched comparison',text:'Show the base and adapted results under matched evaluation settings. Keep negative and inconclusive comparisons visible too.',source:'Paired results'},
  {id:'uncertainty',tag:'E4',label:'Uncertainty remains visible',kind:'Evidence requirement',stage:2,at:.61,point:[1.01,.75,-.06],title:'E4 · Uncertainty remains visible',text:'Report variability and unresolved checks with the comparison. An unverified or missing estimate remains an open question, not a positive result.',source:'Paired results'},
  {id:'settings',tag:'E5',label:'Reproducible settings',kind:'Evidence requirement',stage:2,at:.66,point:[2.02,.75,-.12],title:'E5 · Reproducible settings',text:'Link the reported comparison to the model revision, configuration and run artifact so someone can inspect or repeat the evaluation.',source:'Run record'},
  {id:'answer',tag:'Qualified answer',label:'The answer with its conditions',kind:'Qualified answer',stage:3,at:.94,point:[0,1.83,.06],title:'A claim with its conditions attached',text:'Assess a reported gain using the matched comparison, held-out scope, uncertainty and reproducible settings together. This map identifies what is needed; it does not establish that a gain occurred.'}
];
export const EDGES=[[0,1],[1,2],[1,3],[1,4],[2,5],[2,6],[3,7],[3,8],[4,9],[5,10],[6,10],[7,10],[8,10],[9,10]];
export const toWorld=([x,y,depth])=>[(depth+x/.8660254)/2,depth/2-y,(depth-x/.8660254)/2];
const mix=(a,b,t)=>a.map((v,k)=>v+(b[k]-v)*t);
const solid=(center,half,role,emission=1,rotation=[0,0,0,1])=>({center,half,role,emission,rotation,kind:0});
export function beam(from,to,role){
  const delta=to.map((v,k)=>v-from[k]),length=Math.hypot(...delta);
  if(length<1e-6)return solid(from,[0,0,0],role);
  const d=delta.map(v=>v/length),q=[d[2],0,-d[0],1+d[1]],norm=Math.hypot(...q);
  return solid(mix(from,to,.5),[.055,length/2,.055],role,.92,norm<1e-7?[1,0,0,0]:q.map(v=>v/norm));
}
export function edgeTiming(from,to){
  const end=NODES[to].at;
  // All incoming passages must be ready before a merged answer grows.
  const ready=to===10?Math.max(...NODES.slice(5,10).map(n=>n.at+.025)):NODES[from].at+.025;
  return [Math.max(ready,end-(to===10?.19:.105)),end];
}
export function nodeVisibility(node,progress){return node.id==='query'?1:smooth(node.at,node.at+.025,progress);}
export function graphAt(value,selected='query'){
  const progress=Math.max(0,Math.min(1,value)),points=NODES.map(n=>toWorld(n.point));
  const nodes=NODES.map((n,i)=>{
    const visibility=nodeVisibility(n,progress),size=i===0||i===10?.16:i<5?.13:.095;
    return solid(points[i],Array(3).fill(size*visibility),`node:${n.id}`,n.id===selected?1.26:1.02);
  });
  const paths=EDGES.flatMap(([from,to],index)=>{
    const a=NODES[from].point,b=NODES[to].point;
    // Two legs keep the same slots in either scroll direction. Offset the
    // merge elbows so five requirements remain traceable into one answer.
    const merge=to===10,bend=[a[0],merge?1.29+(from-5)*.09:b[1]-.18,(a[2]+b[2])/2];
    const worldBend=toWorld(bend),ends=[points[from],worldBend,points[to]],lengths=[Math.hypot(...ends[1].map((v,k)=>v-ends[0][k])),Math.hypot(...ends[2].map((v,k)=>v-ends[1][k]))];
    const [start,end]=edgeTiming(from,to),growth=smooth(start,end,progress),distance=growth*(lengths[0]+lengths[1]);
    return lengths.map((length,leg)=>{
      const t=length<1e-6?0:Math.max(0,Math.min(1,(distance-(leg?lengths[0]:0))/length));
      const part=beam(ends[leg],mix(ends[leg],ends[leg+1],t),`edge:${index}:${leg}`);
      part.emission=(NODES[from].id===selected||NODES[to].id===selected)?1.15:.92;
      return part;
    });
  });
  return {boxes:[...nodes,...paths,...Array.from({length:PART_COUNT-nodes.length-paths.length},()=>solid([0,0,0],[0,0,0],'unused'))],progress,state:{flash:0}};
}
export function layoutFor(width,height){
  const unit=Math.min(width/5.3,(height-56)/4.35);
  return {unit,center:[width*.5,height*.47],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};
}
export function project(point,layout,turn=0,tilt=0){
  const v=toWorld(point),c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt);
  const y=v[1]*ct+v[2]*st,z=-v[1]*st+v[2]*ct,q=[v[0]*c+z*s,y,-v[0]*s+z*c];
  return [layout.center[0]+.8660254*(q[0]-q[2])*layout.unit,layout.center[1]+(.5*q[0]-q[1]+.5*q[2])*layout.unit];
}
export function progressFromScroll(scroll,anchors){
  if(anchors.length!==STAGES.length||anchors.some((v,i)=>!Number.isFinite(v)||(i>0&&v<=anchors[i-1])))throw Error('Four ordered scroll anchors are required');
  if(scroll<=anchors[0])return 0;if(scroll>=anchors.at(-1))return 1;
  const i=anchors.findIndex((v,j)=>j<anchors.length-1&&scroll>=v&&scroll<anchors[j+1]);
  return STAGES[i].progress+(STAGES[i+1].progress-STAGES[i].progress)*(scroll-anchors[i])/(anchors[i+1]-anchors[i]);
}
export function stageAt(progress){return progress<.18?0:progress<.40?1:progress<.80?2:3;}
