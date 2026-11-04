import {rotate,smooth} from './engine/geometry.mjs?v=constellation-20261103-2';
export const PERIOD=17,PART_COUNT=40;
export const RECORDS=[
  {id:'evaluation',tag:'Setup',parent:-1,scatter:[-2.35,-1.05,-.35],resolved:[-1.65,-1.05,-.2],angles:[.55,-.25,-.60]},
  {id:'results',tag:'Scores',parent:-1,scatter:[1.35,-1.65,-.15],resolved:[0,-1.15,.25],angles:[.95,.35,.45]},
  {id:'run',tag:'Run record',parent:-1,scatter:[2.60,-.25,.40],resolved:[1.65,-1.05,-.2],angles:[.30,-.45,-.75]},
  {id:'matched',tag:'1. Same questions',parent:0,scatter:[-3.00,.75,.35],resolved:[-2.05,.55,.1],angles:[.80,.10,-.35]},
  {id:'scope',tag:'2. Training budget',parent:0,scatter:[-1.70,1.50,-.20],resolved:[-1.05,.80,-.2],angles:[.65,-.65,.85]},
  {id:'comparison',tag:'3. Score difference',parent:1,scatter:[.15,1.75,.60],resolved:[0,.95,.15],angles:[.40,.80,-.45]},
  {id:'uncertainty',tag:'4. Uncertainty',parent:1,scatter:[2.00,1.25,-.50],resolved:[1.05,.80,-.2],angles:[1.15,-.20,.50]},
  {id:'settings',tag:'5. Saved settings',parent:2,scatter:[-.75,-1.75,.55],resolved:[2.05,.55,.1],angles:[.75,.50,.65]}
];
export const POSES=[{id:'archive',label:'Archive',progress:.04},{id:'scatter',label:'Scatter',progress:.28},{id:'trace',label:'Trace',progress:.52},{id:'resolve',label:'Resolve',progress:.78}];
const clamp=t=>Math.max(0,Math.min(1,t));
const mix=(a,b,t)=>a.map((v,k)=>v+(b[k]-v)*t);
export function toWorld([x,y,d]){return [(d+x/.8660254)/2,d/2-y,(d-x/.8660254)/2];}
const mul=(a,b)=>[a[3]*b[0]+a[0]*b[3]+a[1]*b[2]-a[2]*b[1],a[3]*b[1]-a[0]*b[2]+a[1]*b[3]+a[2]*b[0],a[3]*b[2]+a[0]*b[1]-a[1]*b[0]+a[2]*b[3],a[3]*b[3]-a[0]*b[0]-a[1]*b[1]-a[2]*b[2]];
export function quaternion(x,y,z){return mul(mul([Math.sin(x/2),0,0,Math.cos(x/2)],[0,Math.sin(y/2),0,Math.cos(y/2)]),[0,0,Math.sin(z/2),Math.cos(z/2)]);}
function slerp(a,b,t){let dot=a.reduce((s,v,i)=>s+v*b[i],0);if(dot<0){b=b.map(v=>-v);dot=-dot;}let q;if(dot>.9995)q=mix(a,b,t);else{const angle=Math.acos(Math.min(1,dot)),sin=Math.sin(angle);q=a.map((v,k)=>(v*Math.sin((1-t)*angle)+b[k]*Math.sin(t*angle))/sin);}const n=Math.hypot(...q);return q.map(v=>v/n);}
export function phaseAt(value){
  const p=clamp(value),open=smooth(.105,.15,p)*(1-smooth(.90,.98,p)),resolve=smooth(.61,.66,p)*(1-smooth(.87,.91,p));
  const flash=.12*Math.sin(Math.PI*smooth(.095,.12,p))*(p<.12?1:0)+.09*Math.sin(Math.PI*smooth(.60,.63,p))*(p<.63?1:0);
  return {progress:p,open,resolve,trace:smooth(.34,.40,p)*(1-smooth(.60,.66,p)),stage:p<.105||p>=.98?'archive':p<.34?'scatter':p<.61?'trace':p<.90?'resolve':'return',flash};
}
export const sequenceAt=time=>(((time%PERIOD)+PERIOD)%PERIOD)/PERIOD;
export function routeFor(selected=-1){
  if(selected<0)return new Set(RECORDS.map((_,i)=>i));
  const route=new Set([selected]);let parent=RECORDS[selected].parent;
  while(parent>=0){route.add(parent);parent=RECORDS[parent].parent;}
  RECORDS.forEach((r,i)=>{if(r.parent===selected)route.add(i);});return route;
}
const solid=(center,half,rotation,emission,role)=>({center,half,rotation,emission,role,kind:0});
export function sceneAt(value,{time=0,selected=-1,pointer=null,offsets=[],spreadX=1.6}={}){
  const phase=phaseAt(value),route=routeFor(selected),boxes=[],panels=[];
  const coreProjected=mix([0,0,0],[0,1.92,.30],phase.resolve),core=toWorld(coreProjected);
  const spin=quaternion(.13*Math.sin(time*.33)*phase.open,.22*Math.sin(time*.21)*phase.open,0);
  for(const x of [-.21,.21])for(const y of [-.21,.21])for(const z of [-.21,.21]){
    const d=rotate(spin,[x,y,z]);boxes.push(solid(core.map((v,k)=>v+d[k]),[.16,.16,.16],spin,selected<0?1.28:1.02,'core'));
  }
  RECORDS.forEach((record,i)=>{
    const side=i%2?1:-1,row=Math.floor(i/2),packed=[side*.62,-1.44+row*.96,0],packedQ=quaternion(0,0,-side*Math.PI/2);
    const scatter=[record.scatter[0]*spreadX,record.scatter[1]*.80,record.scatter[2]],resolved=[record.resolved[0]*spreadX,record.resolved[1],record.resolved[2]];
    let center=mix(packed,toWorld(scatter),phase.open),rotation=slerp(packedQ,quaternion(...record.angles),phase.open);
    center=mix(center,toWorld(resolved),phase.resolve);rotation=slerp(rotation,quaternion(.7,.1,(i%2?1:-1)*.12),phase.resolve);
    const drift=phase.open*(1-phase.resolve);
    const projected=scatter;
    let dx=0,dy=0;
    if(pointer?.strength){const x=projected[0]-pointer.x,y=projected[1]-pointer.y,d=Math.hypot(x,y),force=Math.max(0,1-d/1.2)*.16*drift;dx=x/(d||1)*force;dy=y/(d||1)*force;}
    const offset=offsets[i]??{x:0,y:0},hover=toWorld([dx+offset.x,dy+offset.y,0]);
    center=center.map((v,k)=>v+hover[k]+drift*[.025,.04,.025][k]*Math.sin(time*.6+i*1.7+k));
    const light=selected<0?1.10:route.has(i)?i===selected?1.30:1.10:.22;
    const parts=[[[0,0,0],[.44,.055,.36]], [[-.48,.045,0],[.04,.10,.36]], [[.15,.11,-.30],[.28,.045,.055]]];
    parts.forEach(([point,half],part)=>{const v=rotate(rotation,point);boxes.push(solid(center.map((n,k)=>n+v[k]),half,rotation,light+(part===1?.08:0),'record:'+i));});
    panels.push({center,rotation,id:record.id,index:i,highlight:route.has(i)});
  });
  while(boxes.length<PART_COUNT)boxes.push(solid([0,0,0],[0,0,0],[0,0,0,1],0,'unused'));
  return {boxes,panels,core,phase,route,state:{flash:phase.flash}};
}
export function layoutFor(width,height){const unit=Math.min(width/(width<700?8.6:12.8),height/6.7);return {unit,center:[width*.5,height*.49],pitch:unit*6.4/95,glyphSize:unit*7.4/95,footprint:unit*11/95,left:0,right:width,top:0,bottom:height};}
export function projectWorld(v,layout,turn=0,tilt=0){
  const c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt),y=v[1]*ct+v[2]*st,z=-v[1]*st+v[2]*ct,q=[v[0]*c+z*s,y,-v[0]*s+z*c];
  return [layout.center[0]+.8660254*(q[0]-q[2])*layout.unit,layout.center[1]+(.5*q[0]-q[1]+.5*q[2])*layout.unit];
}
export function hull(points){
  const p=[...points].sort((a,b)=>a[0]-b[0]||a[1]-b[1]),cross=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]),lower=[],upper=[];
  for(const point of p){while(lower.length>1&&cross(lower.at(-2),lower.at(-1),point)<=0)lower.pop();lower.push(point);}
  for(const point of p.toReversed()){while(upper.length>1&&cross(upper.at(-2),upper.at(-1),point)<=0)upper.pop();upper.push(point);}
  return lower.slice(0,-1).concat(upper.slice(0,-1));
}
export function boxHull(box,layout,turn,tilt){
  const points=[];for(const x of [-1,1])for(const y of [-1,1])for(const z of [-1,1]){const d=rotate(box.rotation,box.half.map((v,k)=>v*[x,y,z][k]));points.push(projectWorld(box.center.map((v,k)=>v+d[k]),layout,turn,tilt));}return hull(points);
}
export function springStep(offset,dt){const step=Math.min(.033,Math.max(0,dt));offset.vx+=(-95*offset.x-16*offset.vx)*step;offset.vy+=(-95*offset.y-16*offset.vy)*step;offset.x+=offset.vx*step;offset.y+=offset.vy*step;if(Math.hypot(offset.x,offset.y,offset.vx,offset.vy)<.0001)Object.assign(offset,{x:0,y:0,vx:0,vy:0});return offset;}
export function bezier(points,t){const s=1-t;return points[0].map((v,k)=>s*s*s*v+3*s*s*t*points[1][k]+3*s*t*t*points[2][k]+t*t*t*points[3][k]);}
export function connections(scene,time=0){
  const paths=[];
  scene.panels.forEach((panel,i)=>{
    const record=RECORDS[i],from=record.parent<0?scene.core:scene.panels[record.parent].center,to=panel.center;
    const center=mix(from,to,.5),bend=toWorld([(i%2?1:-1)*.35,0,.5]);
    const controls=[from,mix(from,center,.7).map((v,k)=>v+bend[k]),mix(center,to,.3).map((v,k)=>v+bend[k]),to];
    paths.push({controls,record:i,highlight:scene.route.has(i),alpha:scene.phase.open*(record.parent<0?1-scene.phase.resolve:1)});
    if(i>=3){const target=scene.core;paths.push({controls:[to,mix(to,target,.35).map((v,k)=>v+[0,-.28,.15][k]),mix(to,target,.75).map((v,k)=>v+[0,-.22,.10][k]),target],record:i,highlight:scene.route.has(i),alpha:scene.phase.resolve});}
  });
  const energy=Math.min(1,.16+.84*scene.phase.trace+.8*scene.phase.resolve);
  return paths.map(path=>({...path,alpha:path.alpha*energy}));
}
