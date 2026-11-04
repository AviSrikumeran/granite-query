export const GROUPS=[{id:'A',name:'Method examples',color:'#b747a0'},{id:'B',name:'Measurement examples',color:'#dc6ac5'},{id:'C',name:'Scope examples',color:'#9d438f'}];
export const RECORDS=Array.from({length:24},(_,index)=>({index,id:'DEMO-'+String(index+1).padStart(2,'0'),group:Math.floor(index/8),column:index%2,row:Math.floor(index%8/2),title:'Example source '+String(index+1).padStart(2,'0')}));
export const clamp=(value,min=0,max=1)=>Math.max(min,Math.min(max,value));
export const ease=value=>{const t=clamp(value);return t*t*t*(t*(t*6-15)+10);};
const mix=(a,b,t)=>a+(b-a)*t;
export function groupPose(index,progress){const p=ease(progress),shared=[(index-1)*2,0,0],split=[[-2.7,.5,2.7],[0,1.25,-.65],[2.7,.7,-2.7]][index];return {center:shared.map((v,i)=>mix(v,split[i],p)),angle:[-.08,.025,.08][index]*p};}
function transform(point,pose){const [x,y,z]=point,c=Math.cos(pose.angle),s=Math.sin(pose.angle);return [x*c-z*s+pose.center[0],y+pose.center[1],x*s+z*c+pose.center[2]];}
export function sceneAt(progress,{selected=0,focus=-1}={}){const p=clamp(progress),poses=GROUPS.map((_,i)=>groupPose(i,p));const bases=poses.map((pose,group)=>({id:'base-'+group,group,center:transform([0,-.13,0],pose),half:[.99,.15,1.99],angle:pose.angle,base:true}));const records=RECORDS.map(record=>{const local=[record.column-.5,.13,record.row-1.5],pose=poses[record.group];return {...record,center:transform([local[0],local[1]+(record.index===selected?.10:0),local[2]],pose),half:[.445,.10,.445],angle:pose.angle,base:false,active:record.index===selected,dim:focus>=0&&record.group!==focus,origin:[(record.group-1)*2+local[0],-.48,local[2]]};});return {progress:p,poses,bases,records};}
export function layoutFor(width,height){return {width,height,unit:Math.min((width-42)/12.5,(height-100)/6.7),center:[width*.5,height*.55]};}
export function project(point,layout,pointer={turn:0,tilt:0}){const [x,y,z]=point,c=Math.cos(pointer.turn),s=Math.sin(pointer.turn),rx=x*c-z*s,rz=x*s+z*c;return [layout.center[0]+(rx-rz)*.76*layout.unit,layout.center[1]+((rx+rz)*(.28+pointer.tilt)-y)*layout.unit];}
export function corners(box){const pose={center:box.center,angle:box.angle};return [[-1,-1,-1],[1,-1,-1],[1,-1,1],[-1,-1,1],[-1,1,-1],[1,1,-1],[1,1,1],[-1,1,1]].map(v=>transform(v.map((n,i)=>n*box.half[i]),pose));}
export function faces(box,layout,pointer){const p=corners(box).map(v=>project(v,layout,pointer));return [[p[1],p[2],p[6],p[5]],[p[2],p[3],p[7],p[6]],[p[4],p[5],p[6],p[7]]];}
export function sequenceAt(seconds){const t=clamp(seconds/8);return t<.1?0:t>.8?1:ease((t-.1)/.7);}
