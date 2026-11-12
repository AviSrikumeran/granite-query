import {makeAtlas} from '../playground/purple/engine/atlas.mjs?v=magenta-20261103-2';

// The approved navigation-size preview: the same 37 glyphs, faces and colors.
const G=['01111','11000','11011','11001','01111'];
const Q=['01110','11011','11011','11011','01110'];
const points=[];
function letter(rows,offset){rows.forEach((row,y)=>[...row].forEach((cell,x)=>{if(cell==='1')points.push({x:10+(x+offset)*12,y:14+y*12})}));}
letter(G,0);letter(Q,6);
points.push({x:82+4.1*12,y:14+4.1*12},{x:82+4.75*12,y:14+5*12});
const vocabulary=[9,9,8,0,9,4,9,13,9,0,9,2];
points.forEach((point,i)=>point.kind=vocabulary[(i*5+3)%vocabulary.length]);
export const GLYPH_COUNT=points.length;
const darkRamp=['#c22ec9','#df3cdd','#f447e9','#ff58ef','#ff6cf4','#ff88f7','#ffa2fa','#ffbdfc','#ffd5fd','#ffeaff','#fff5ff'];
const paperRamp=['#8d1686','#a21a98','#b91fa9','#c628b6','#d537c4','#df54cd'];
const atlasCache=new Map();
function coloredAtlas(color){if(!atlasCache.has(color))atlasCache.set(color,makeAtlas(color));return atlasCache.get(color)}

export function createNavigationMaterial(canvas,{get}){
 const ctx=canvas.getContext('2d');if(!ctx)return null;
 const layer=document.createElement('canvas'),ink=layer.getContext('2d');if(!ink)return null;
 return {
  resize(){layer.width=canvas.width;layer.height=canvas.height},
  draw(clock){
   const {width,height,ratio,lightSurface}=get(),tone=lightSurface?'paper':'dark',s=width/154;
   ink.setTransform(ratio,0,0,ratio,0,0);ink.clearRect(0,0,width,height);
   ink.beginPath();for(const point of points){const x=point.x*s,y=point.y*(height/88),body=14*s;if(ink.roundRect)ink.roundRect(x-body/2,y-body/2,body,body,2*s);else ink.rect(x-body/2,y-body/2,body,body)}
   const faceTone=ink.createLinearGradient(0,0,0,height);
   faceTone.addColorStop(0,tone==='dark'?'#ff9af3':'#ad169b');faceTone.addColorStop(1,tone==='dark'?'#a52aa8':'#8e167d');
   ink.fillStyle=faceTone;ink.globalAlpha=tone==='dark'?.18:.10;ink.fill();ink.globalAlpha=1;
   for(const point of points){
    const x=point.x*s,y=point.y*(height/88),size=14.6*s;
    const wave=Math.pow(.5+.5*Math.cos((point.x+point.y*.25)*.030-clock*.82),6);
    const face=.5+.5*Math.sin(point.x*.04-point.y*.045),colors=tone==='dark'?darkRamp:paperRamp;
    const base=tone==='dark'?3+Math.floor(face*2):1+Math.floor(face*2);
    const tier=Math.min(colors.length-1,Math.round(base+wave*(tone==='dark'?5:1.8)));
    const depth=coloredAtlas(tone==='dark'?'#8f168f':'#7d166f');
    ink.globalAlpha=.68;ink.drawImage(depth,point.kind*64,0,64,64,x-size/2+.55*s,y-size/2+.8*s,size,size);
    ink.globalAlpha=1;ink.drawImage(coloredAtlas(colors[tier]),point.kind*64,0,64,64,x-size/2,y-size/2,size,size);
   }
   ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);
   ctx.save();ctx.filter=`blur(${tone==='dark'?2.2:1.1}px)`;ctx.globalAlpha=tone==='dark'?.48:.12;ctx.drawImage(layer,0,0,width,height);ctx.restore();
   ctx.drawImage(layer,0,0,width,height);
  },
  destroy(){layer.width=0;layer.height=0},
 };
}
