import {makeAtlas} from '../playground/purple/engine/atlas.mjs?v=magenta-20261103-2';

// Exact six-row lettering and 259 symbols from the approved taller preview.
const letters={
 G:['01111','11000','11000','11011','11001','01111'],
 R:['11110','11011','11011','11110','11100','11011'],
 A:['01110','11011','11011','11111','11011','11011'],
 N:['110011','111011','111011','111111','110111','110011'],
 I:['1111','0110','0110','0110','0110','1111'],
 T:['111111','111111','001100','001100','001100','001100'],
 E:['11111','11000','11110','11000','11000','11111'],
 Q:['01110','11011','11011','11011','11011','01110'],
 U:['11011','11011','11011','11011','11011','01110'],
 Y:['110011','110011','011110','001100','001100','001100'],
};
const vocabulary=[9,9,8,0,9,4,9,13,9,0,9,2],words=[];
let symbolIndex=0;
for(const word of ['GRANITE','QUERY']){
 const points=[];let cursor=0;
 for(const char of word){
  let local=0;const start=char==='G'?0:char==='Q'?19:symbolIndex;
  letters[char].forEach((row,y)=>[...row].forEach((cell,x)=>{if(cell==='1'){points.push({x:cursor+x,y,kind:vocabulary[((start+local)*5+3)%vocabulary.length]});local++;symbolIndex++;}}));
  if(char==='Q'){for(const [x,y]of [[4.1,5.1],[4.75,6]]){points.push({x:cursor+x,y,kind:vocabulary[((start+local)*5+3)%vocabulary.length]});local++;symbolIndex++;}}
  cursor+=letters[char][0].length+1;
 }
 words.push({points,columns:cursor-1});
}
export const GLYPH_COUNT=symbolIndex;
const darkRamp=['#c22ec9','#df3cdd','#f447e9','#ff58ef','#ff6cf4','#ff88f7','#ffa2fa','#ffbdfc','#ffd5fd','#ffeaff','#fff5ff'];
const paperRamp=['#8d1686','#a21a98','#b91fa9','#c628b6','#d537c4','#df54cd'];
const atlasCache=new Map();
function atlas(color){if(!atlasCache.has(color))atlasCache.set(color,makeAtlas(color));return atlasCache.get(color)}

export function createNavigationMaterial(canvas,{get}){
 const ctx=canvas.getContext('2d');if(!ctx)return null;
 const layer=document.createElement('canvas'),ink=layer.getContext('2d');if(!ink)return null;
 return {
  resize(){layer.width=canvas.width;layer.height=canvas.height},
  draw(clock){
   const {width,height,ratio,lightSurface,stacked}=get();
   const columns=stacked?Math.max(...words.map(w=>w.columns)):words[0].columns+1+words[1].columns;
   const pitch=Math.min(12,(width-16)/(columns+.2)),s=pitch/12,body=14*s,size=14.6*s;
   const x0=9+(width-18-(columns-1)*pitch)/2,y0=stacked?14:Math.max(13,(height-6*pitch)/2);
   const points=[];let offset=0;
   words.forEach((word,i)=>{for(const p of word.points)points.push({...p,x:x0+(p.x+(stacked?0:offset))*pitch,y:y0+p.y*pitch+(stacked?i*8*pitch:0)});offset+=word.columns+1;});
   ink.setTransform(ratio,0,0,ratio,0,0);ink.clearRect(0,0,width,height);
   ink.beginPath();for(const p of points){if(ink.roundRect)ink.roundRect(p.x-body/2,p.y-body/2,body,body,2*s);else ink.rect(p.x-body/2,p.y-body/2,body,body)}
   const face=ink.createLinearGradient(0,0,0,height);face.addColorStop(0,lightSurface?'#ad169b':'#ff9af3');face.addColorStop(1,lightSurface?'#8e167d':'#a52aa8');ink.fillStyle=face;ink.globalAlpha=lightSurface?.10:.18;ink.fill();ink.globalAlpha=1;
   for(const p of points){
    const mx=(p.x-x0)/s+10,my=(p.y-y0)/s+14;
    const wave=Math.pow(.5+.5*Math.cos((mx+my*.25)*.030-clock*.82),6);
    const light=.5+.5*Math.sin(mx*.04-my*.045),colors=lightSurface?paperRamp:darkRamp;
    const base=lightSurface?1+Math.floor(light*2):3+Math.floor(light*2);
    const tier=Math.min(colors.length-1,Math.round(base+wave*(lightSurface?1.8:5)));
    ink.globalAlpha=.68;ink.drawImage(atlas(lightSurface?'#7d166f':'#8f168f'),p.kind*64,0,64,64,p.x-size/2+.55*s,p.y-size/2+.8*s,size,size);
    ink.globalAlpha=1;ink.drawImage(atlas(colors[tier]),p.kind*64,0,64,64,p.x-size/2,p.y-size/2,size,size);
   }
   ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);ctx.save();ctx.filter=`blur(${lightSurface?1.1:2.2}px)`;ctx.globalAlpha=lightSurface?.12:.48;ctx.drawImage(layer,0,0,width,height);ctx.restore();ctx.drawImage(layer,0,0,width,height);
  },
  destroy(){layer.width=0;layer.height=0},
 };
}
