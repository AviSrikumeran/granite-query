import {smooth} from './engine/geometry.mjs?v=results-20261103-1';

export const PART_COUNT=40;
export const STAGES=[
  {id:'query',label:'Query',progress:0},
  {id:'sources',label:'Sources',progress:.36},
  {id:'evidence',label:'Evidence',progress:.72},
  {id:'answer',label:'Answer',progress:1}
];
// Geometry stays fixed while validated published records supply the content.
export const NODES=[{"id":"query","tag":"Query","stage":0,"at":0,"point":[0,-1.65,0]},{"id":"retrieve","tag":"Connect","stage":1,"at":0.1,"point":[0,-1.02,0.05]},{"id":"evaluation","tag":"Protocol","stage":1,"at":0.22,"point":[-1.5,-0.32,-0.12]},{"id":"results","tag":"Results","stage":1,"at":0.27,"point":[0,-0.32,0.14]},{"id":"run","tag":"Receipts","stage":1,"at":0.32,"point":[1.5,-0.32,-0.06]},{"id":"matched","tag":"E1","stage":2,"at":0.46,"point":[-2.02,0.75,-0.12]},{"id":"scope","tag":"E2","stage":2,"at":0.51,"point":[-1.01,0.75,0.08]},{"id":"comparison","tag":"E3","stage":2,"at":0.56,"point":[0,0.75,0.18]},{"id":"uncertainty","tag":"E4","stage":2,"at":0.61,"point":[1.01,0.75,-0.06]},{"id":"settings","tag":"E5","stage":2,"at":0.66,"point":[2.02,0.75,-0.12]},{"id":"answer","tag":"Finding","stage":3,"at":0.94,"point":[0,1.83,0.06]}].map(node=>({...node,label:'Loading published evidence',kind:'Loading',title:'Loading published evidence',text:'Reading the public study snapshot. No result is inferred while evidence is unavailable.',links:[]}));
export function bindContent(content){
  for(const node of NODES){const item=content[node.id];if(!item)throw Error('Missing node content: '+node.id);for(const key of ['label','kind','title','text','source','links','pointer'])node[key]=item[key];node.label=item.label??item.title;}
}
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
