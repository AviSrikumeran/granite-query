// Independently authored rendering model, informed by the recording and public
// renderer architecture. Geometry and layout remain in geometry.mjs unchanged.
import {cameraRotate,smooth,rotate} from './geometry.mjs?v=results-20261103-1';
const clamp=t=>Math.max(0,Math.min(1,t));
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const norm=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
const direction=(az,el)=>{const a=az*Math.PI/180,e=el*Math.PI/180;return [Math.sin(a)*Math.cos(e),Math.sin(e),Math.cos(a)*Math.cos(e)];};
export const KEY=direction(73,-1),FILL=direction(180,-32);
export const TIER_COLORS=['#151b16','#203023','#213922','#24462a','#28552b','#286633','#317a3a','#378c40','#46a549','#68b650','#86c459','#a0ce60','#b2d366','#c5da6b','#d2e16e','#e0e97b'];
export const TIER_GLYPHS=[4,2,6,4,2,8,9,8,9,4,2,6,4,2,8,9];
export const rgbOf=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
const MAGENTA=['#13051c','#2a0a3f','#4a1163','#781b90','#a92cbf','#d63add','#ed4bea','#fa58f3','#ff67f8','#ff7dfc','#ff93fd','#ffabff','#ffc0ff','#ffd6ff','#ffeaff','#fff5ff'];
const HOT_VIOLET=['#10051e','#21083e','#3a106c','#5a189e','#8227d0','#a43ae9','#bf4df5','#d45cff','#e06cff','#eb80ff','#f092ff','#f5aaff','#f9c0ff','#fcd5ff','#ffebff','#fff5ff'];
const materialKey=material=>material==='orchid'?'magenta':material==='violet'?'hotviolet':material;
export function materialColors(material='green'){
  const key=materialKey(material),colors=key==='magenta'?MAGENTA:key==='hotviolet'?HOT_VIOLET:TIER_COLORS;
  return colors.map(rgbOf).flatMap(color=>{const boosted=color.map(v=>v*1.6),peak=Math.max(1,...boosted);return boosted.map(v=>v/peak);});
}
export function materialProfile(material='green'){
  const key=materialKey(material);
  if(key==='green')return {background:[4/255,8/255,4/255],ghost:[.957,1,.8],energyA:[.04,.055,.025],energyB:[.045,.045,.038],bloomRange:[.39,1.03],bloom:.5,rolloff:.22};
  return {background:[8/255,3/255,14/255],ghost:key==='magenta'?[1,.55,.95]:[.85,.55,1],energyA:[.06,.008,.085],energyB:[.09,.012,.055],bloomRange:[.16,.72],bloom:.62,rolloff:key==='magenta'?.78:.72};
}
// Projection of three adjacent lattice cells, rather than three differently
// scaled sculptures. The inverse camera keeps the fragments attached on hover.
// Retain a small separation from the peripheral samples for all new forms.
export function sideClearance(){return .08;}
export function ghostOffsets(turn=0,tilt=0,clearance=0){
  const c=Math.cos(turn),s=Math.sin(turn),ct=Math.cos(tilt),st=Math.sin(tilt);
  const inverse=p=>{const y=p[1]*ct+p[2]*st,z=-p[1]*st+p[2]*ct;return [p[0]*c+z*s,y,-p[0]*s+z*c];};
  return [[-2,0,2],[0,2,-2],[2,-2,0]].map(p=>{
    const q=inverse(p),offset=[.8660254*(q[0]-q[2]),.5*q[0]-q[1]+.5*q[2]];
    const scale=1+clearance/Math.hypot(...offset);return offset.map(v=>v*scale);
  });
}
export function ghostWeight(x,y){return .51*Math.pow(clamp(1-(Math.hypot(x/4.05,y/4.05)-.49)/.68),2.4);}
export function introCell(time,radius,seed){
  if(time>=1.55)return {alpha:1,scale:1,flash:1};
  const progress=smooth(.92,1.35,time),start=clamp(radius/2.4+seed*.18)/1.18*.75;
  const reveal=clamp((progress*1.1-start)/.35),ease=reveal*(2-reveal);
  return {alpha:smooth(0,.7,reveal),scale:.1+.9*ease,flash:1+2.2*4*reveal*(1-reveal)};
}
export function litSurface(normal,point,view,occlusion=1,hover=0){
  const key=Math.max(0,dot(normal,KEY)),fill=Math.max(0,dot(normal,FILL));
  const spec=Math.pow(Math.max(0,dot(normal,norm(KEY.map((v,k)=>v+view[k])))),20);
  const rim=Math.pow(1-Math.max(0,dot(normal,view)),2.5);
  const light=(.33+1.11*key+.79*fill)*occlusion+.83*rim+.25*hover*(.2+rim);
  const color=[0,.9,.46].map((v,k)=>{const n=v*light+[.78,1,.86][k]*spec*.95;return n/(1+n);});
  return clamp(dot(color,[.299,.587,.114])*1.6);
}
export function softenedNormal(point,box){
  return norm(point.map((v,k)=>Math.sign(v)*(1-smooth(0,.075,box.half[k]-Math.abs(v)))));
}
export function occlusionAt(point,normal,boxes){
  let occlusion=0,weight=1;
  for(let i=1;i<=4;i++){
    const distance=i*.09,p=point.map((v,k)=>v+normal[k]*distance);
    const nearest=Math.min(...boxes.filter(b=>b.half.every(v=>v>.001)).map(b=>{
      const local=rotate([-b.rotation[0],-b.rotation[1],-b.rotation[2],b.rotation[3]],p.map((v,k)=>v-b.center[k]));
      const q=local.map((v,k)=>Math.abs(v)-b.half[k]);
      return Math.hypot(...q.map(v=>Math.max(0,v)))+Math.min(Math.max(...q),0);
    }));
    occlusion+=(distance-nearest)*weight;weight*=.7;
  }
  return clamp(1-occlusion*2.55);
}
export function viewDirection(turn=0,tilt=0){return norm(cameraRotate([1,1,1],turn,tilt));}

// Mineral shell uses the same light tiers, with a subdued stone treatment.
export const mineralColors=()=>['#06060c','#0c0c17','#131421','#1b1d2c','#252537','#303044','#3b3a51','#4b465e','#5a526f','#6a5c80','#796c91','#8b7da4','#9f91b5','#b0a3c4','#c2b7d4','#d7cfe3'].map(rgbOf).flat();
