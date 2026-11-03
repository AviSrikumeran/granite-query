export function makeAtlas(color='#fff'){
  const image=document.createElement('canvas');image.width=1024;image.height=64;
  const ctx=image.getContext('2d');ctx.fillStyle=color;ctx.strokeStyle=color;
  for(let kind=0;kind<16;kind++){
    ctx.save();ctx.translate(kind*64+32,32);ctx.lineWidth=7;ctx.lineCap='round';ctx.lineJoin='round';
    if(kind===0||kind===13){ctx.beginPath();ctx.arc(0,0,22,0,Math.PI*2);kind===0?ctx.fill():ctx.stroke();if(kind===13){ctx.beginPath();ctx.arc(0,0,6,0,Math.PI*2);ctx.fill();}}
    if(kind===1){ctx.beginPath();ctx.moveTo(0,22);ctx.bezierCurveTo(-36,-1,-19,-31,0,-12);ctx.bezierCurveTo(19,-31,36,-1,0,22);ctx.fill();}
    if(kind===7||kind===12){ctx.beginPath();const n=kind===2?6:kind===12?4:5;for(let k=0;k<n*2;k++){const a=k*Math.PI/n-Math.PI/2,r=k%2?11:24;ctx[k?'lineTo':'moveTo'](r*Math.cos(a),r*Math.sin(a));}ctx.closePath();kind===12?ctx.stroke():ctx.fill();}
    if(kind===3){ctx.fillRect(-3,-22,6,44);ctx.fillRect(-22,-3,44,6);}
    if(kind===4){ctx.beginPath();ctx.moveTo(-19,-19);ctx.lineTo(0,0);ctx.lineTo(19,-19);ctx.moveTo(0,0);ctx.lineTo(0,22);ctx.stroke();}
    if(kind===5||kind===11){const sign=kind===5?1:-1;ctx.beginPath();ctx.moveTo(0,-22*sign);ctx.lineTo(23,19*sign);ctx.lineTo(-23,19*sign);ctx.closePath();ctx.fill();}
    if(kind===2){ctx.beginPath();for(let k=0;k<3;k++){const a=k*Math.PI/3;ctx.moveTo(-23*Math.cos(a),-23*Math.sin(a));ctx.lineTo(23*Math.cos(a),23*Math.sin(a));}ctx.stroke();}
    if(kind===6){ctx.beginPath();for(let k=0;k<3;k++){const a=k*2*Math.PI/3-Math.PI/2,b=a+Math.PI/3,c=a-Math.PI/3;ctx.moveTo(22*Math.cos(b),22*Math.sin(b));ctx.lineTo(25*Math.cos(a),25*Math.sin(a));ctx.lineTo(22*Math.cos(c),22*Math.sin(c));}ctx.stroke();}
    if(kind===8){ctx.beginPath();for(let k=0;k<6;k++){const a=k*Math.PI/3-Math.PI/2;ctx[k?'lineTo':'moveTo'](24*Math.cos(a),24*Math.sin(a));}ctx.closePath();ctx.fill();ctx.globalCompositeOperation='destination-out';ctx.beginPath();for(let k=0;k<3;k++){const a=k*2*Math.PI/3+Math.PI/2;ctx.moveTo(0,0);ctx.lineTo(26*Math.cos(a),26*Math.sin(a));}ctx.lineWidth=5;ctx.stroke();ctx.globalCompositeOperation='source-over';}
    if(kind===9){ctx.beginPath();for(let k=0;k<6;k++){const a=k*Math.PI/3-Math.PI/2;ctx[k?'lineTo':'moveTo'](24*Math.cos(a),24*Math.sin(a));}ctx.closePath();ctx.fill();}
    if(kind===10){ctx.beginPath();ctx.moveTo(-17,-17);ctx.lineTo(17,17);ctx.moveTo(-17,17);ctx.lineTo(17,-17);ctx.stroke();}
    if(kind===14)for(const y of [-14,0,14])ctx.fillRect(-20,y-2,40,4);
    if(kind===15){ctx.beginPath();ctx.moveTo(-20,8);ctx.lineTo(0,-12);ctx.lineTo(20,8);ctx.stroke();}
    ctx.restore();
  }
  return image;
}

