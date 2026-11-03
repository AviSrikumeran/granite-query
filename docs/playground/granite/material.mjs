// Independently authored rendering model, informed by the recording and public
// renderer architecture. Geometry and layout remain in geometry.mjs unchanged.
import {cameraRotate,smooth} from './geometry.mjs?v=spacing-20261103-6';
const clamp=t=>Math.max(0,Math.min(1,t));
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const norm=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
const direction=(az,el)=>{const a=az*Math.PI/180,e=el*Math.PI/180;return [Math.sin(a)*Math.cos(e),Math.sin(e),Math.cos(a)*Math.cos(e)];};
export const KEY=direction(73,-1),FILL=direction(180,-32);
export const TIER_COLORS=['#151b16','#203023','#213922','#24462a','#28552b','#286633','#317a3a','#378c40','#46a549','#68b650','#86c459','#a0ce60','#b2d366','#c5da6b','#d2e16e','#e0e97b'];
export const TIER_GLYPHS=[4,2,6,4,2,8,9,8,9,4,2,6,4,2,8,9];
export const rgbOf=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
export function materialColors(hex='#7fee64'){
  const base=rgbOf(hex),reference=rgbOf('#7fee64');
  return TIER_COLORS.map(rgbOf).flatMap(color=>{
    const boosted=color.map((v,k)=>v*1.6*(base[k]+.07)/(reference[k]+.07));
    const peak=Math.max(1,...boosted);return boosted.map(v=>clamp(v/peak));
  });
}
// Projection of three adjacent lattice cells, rather than three differently
// scaled sculptures. The inverse camera keeps the fragments attached on hover.
export function sideClearance(state){
  const blend=state.blend??0;
  return .08*((state.from==='box'?1-blend:0)+(state.to==='box'?blend:0));
}
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
      const q=p.map((v,k)=>Math.abs(v-b.center[k])-b.half[k]);
      return Math.hypot(...q.map(v=>Math.max(0,v)))+Math.min(Math.max(...q),0);
    }));
    occlusion+=(distance-nearest)*weight;weight*=.7;
  }
  return clamp(1-occlusion*2.55);
}
export function viewDirection(turn=0,tilt=0){return norm(cameraRotate([1,1,1],turn,tilt));}
