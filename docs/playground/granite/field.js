import {FORMS,FORM_LABELS,BOX_COUNT,TRANSITION,STEP,SHAPES,boxesAt,mixBoxes,easeProgress,traceBoxes} from './geometry.mjs';

// Independent Granite Query motion study. The Modal reference remains separate.
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
let canvas=document.querySelector('#glyph-field');
const pauseButton=document.querySelector('#pause-motion'),formControl=document.querySelector('#form-mode');
const formName=document.querySelector('#form-name'),status=document.querySelector('#motion-status');
const DEFAULTS={blue:'#81d9fa',pink:'#ff79bd'};
const palette={...DEFAULTS};
const parseHex=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
let width=0,height=0,ratio=1,time=0,previous=0,request=0,frames=0;
let paused=reducedMotion.matches,visible=!document.hidden,inView=true,mode='auto',sequenceOffset=0,morph=null;
let renderer,layout;
const pointer={x:-2000,y:-2000,strength:0,turn:0};
const centers=new Float32Array(BOX_COUNT*3),halves=new Float32Array(BOX_COUNT*3),rotations=new Float32Array(BOX_COUNT*4);
const PITCH=5.6,GLYPH_SIZE=7.8,POINT_SIZE=12;

function makeAtlas(color='#fff'){
  const image=document.createElement('canvas');image.width=1024;image.height=64;
  const ctx=image.getContext('2d');ctx.fillStyle=color;ctx.strokeStyle=color;
  for(let kind=0;kind<16;kind++){
    ctx.save();ctx.translate(kind*64+32,32);ctx.lineWidth=7;ctx.lineCap='round';ctx.lineJoin='round';
    if(kind===0||kind===8||kind===13){ctx.beginPath();ctx.arc(0,0,22,0,Math.PI*2);kind===0?ctx.fill():ctx.stroke();if(kind===13){ctx.beginPath();ctx.arc(0,0,6,0,Math.PI*2);ctx.fill();}}
    if(kind===1){ctx.beginPath();for(let k=0;k<6;k++){const a=k*Math.PI/3;ctx[k?'lineTo':'moveTo'](21*Math.cos(a),21*Math.sin(a));}ctx.closePath();ctx.stroke();}
    if(kind===2||kind===7||kind===12){ctx.beginPath();const n=kind===2?6:kind===12?4:5;for(let k=0;k<n*2;k++){const a=k*Math.PI/n-Math.PI/2,r=k%2?11:24;ctx[k?'lineTo':'moveTo'](r*Math.cos(a),r*Math.sin(a));}ctx.closePath();kind===12?ctx.stroke():ctx.fill();}
    if(kind===3){ctx.fillRect(-3,-22,6,44);ctx.fillRect(-22,-3,44,6);}
    if(kind===4){ctx.beginPath();ctx.moveTo(-19,-19);ctx.lineTo(0,0);ctx.lineTo(19,-19);ctx.moveTo(0,0);ctx.lineTo(0,22);ctx.stroke();}
    if(kind===5||kind===11){const sign=kind===5?1:-1;ctx.beginPath();ctx.moveTo(0,-22*sign);ctx.lineTo(23,19*sign);ctx.lineTo(-23,19*sign);ctx.closePath();ctx.fill();}
    if(kind===6){ctx.beginPath();ctx.moveTo(0,-23);ctx.lineTo(22,0);ctx.lineTo(0,23);ctx.lineTo(-22,0);ctx.closePath();ctx.stroke();}
    if(kind===9)ctx.fillRect(-18,-18,36,36);
    if(kind===10){ctx.beginPath();ctx.moveTo(-17,-17);ctx.lineTo(17,17);ctx.moveTo(-17,17);ctx.lineTo(17,-17);ctx.stroke();}
    if(kind===14)for(const y of [-14,0,14])ctx.fillRect(-20,y-2,40,4);
    if(kind===15){ctx.beginPath();ctx.moveTo(-20,8);ctx.lineTo(0,-12);ctx.lineTo(20,8);ctx.stroke();}
    ctx.restore();
  }
  return image;
}

const vertex=`
precision highp float;
attribute vec2 a_cell;
uniform vec2 u_resolution,u_center,u_pointer;
uniform vec3 u_centers[16],u_halves[16];
uniform vec4 u_rotations[16];
uniform float u_time,u_ratio,u_unit,u_turn,u_pointerStrength,u_aa,u_footprint,u_mobile;
varying float v_energy,v_glyph,v_hue,v_tint;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+1.),f.x),f.y);}
vec3 yaw(vec3 p){float c=cos(u_turn),s=sin(u_turn);return vec3(p.x*c-p.z*s,p.y,p.x*s+p.z*c);}
vec3 rotate(vec4 q,vec3 p){return p+2.*cross(q.xyz,cross(q.xyz,p)+q.w*p);}
vec3 trace(vec2 screen){
  vec2 local=(screen-u_center)/u_unit;
  vec3 origin=yaw(vec3(local.x/1.7320508,-local.y,-local.x/1.7320508)+8.);
  vec3 direction=yaw(vec3(-.57735027));
  float nearest=1000.,energy=0.,hue=.5;
  for(int i=0;i<16;i++){
    vec4 q=u_rotations[i],inverse=vec4(-q.xyz,q.w);
    vec3 o=rotate(inverse,origin-u_centers[i]),d=rotate(inverse,direction);
    vec3 safe=mix(vec3(.00001),d,step(vec3(.00001),abs(d))),inv=1./safe;
    vec3 a=(-u_halves[i]-o)*inv,b=(u_halves[i]-o)*inv;
    vec3 low=min(a,b),high=max(a,b);
    float entry=max(low.x,max(low.y,low.z)),exit=min(high.x,min(high.y,high.z));
    if(entry<=exit+u_aa&&exit>0.&&entry<nearest){
      nearest=entry;
      vec3 point=o+d*entry,world=origin+direction*entry;
      vec3 margin=max(vec3(0.),u_halves[i]-abs(point));
      float second=min(max(margin.x,margin.y),max(min(margin.x,margin.y),margin.z));
      float rim=exp(-pow(second/.11,2.));
      vec3 normal=entry==low.y?vec3(0.,-sign(d.y),0.):(entry==low.x?vec3(-sign(d.x),0.,0.):vec3(0.,0.,-sign(d.z)));
      vec3 worldNormal=rotate(q,normal);
      float diffuse=.48+.52*max(0.,dot(worldNormal,normalize(vec3(-.2,1.,.7))));
      float coverage=1.-smoothstep(-u_aa,u_aa,entry-exit);
      energy=(.44*diffuse+.47*rim)*coverage;
      hue=clamp(.5+world.x*.3+world.y*.2+world.z*.22,0.,1.);
    }
  }
  return vec3(energy,hue,nearest);
}
void main(){
  vec2 p=a_cell;
  vec3 coreSample=trace(p);
  vec3 left=trace((p-u_center+vec2(1.7,-.12)*u_unit)/.76+u_center);
  vec3 right=trace((p-u_center-vec2(1.18,-.86)*u_unit)/.66+u_center);
  float echo=max(left.x,right.x)*.15;
  float grain=.87+.13*noise(p*.035+vec2(u_time*.02,-u_time*.015));
  vec2 ellipse=(p-u_center)/vec2(u_unit*3.1,u_unit*2.4);
  float envelope=exp(-pow(length(ellipse),4.)*.45);
  float edge=(1.-smoothstep(u_resolution.y*.88,u_resolution.y*.98,p.y));
  edge*=mix(smoothstep(u_resolution.x*.37,u_resolution.x*.49,p.x),1.,u_mobile);
  float lamp=exp(-dot(p-u_pointer,p-u_pointer)/13500.)*u_pointerStrength;
  v_energy=clamp(max(coreSample.x*1.3,echo)*grain*envelope*edge+lamp*.17*step(.01,coreSample.x),0.,1.);
  v_tint=step(echo,coreSample.x)*step(.01,coreSample.x);
  v_hue=mix(clamp((p.x-u_center.x)/u_unit*.23+.5,0.,1.),coreSample.y,v_tint);
  v_hue=clamp(v_hue+.07*sin(u_time*.16+p.y*.005),0.,1.);
  float choice=floor(hash(a_cell+vec2(17.,53.))*24.);
  v_glyph=choice<16.?choice:(choice<19.?0.:(choice<21.?2.:(choice<23.?4.:7.)));
  gl_Position=vec4(p.x/u_resolution.x*2.-1.,1.-p.y/u_resolution.y*2.,0.,1.);
  gl_PointSize=u_footprint*u_ratio;
}`;
const fragment=`
precision highp float;
uniform sampler2D u_atlas;
uniform float u_footprint,u_glyphSize;
uniform vec3 u_blue,u_pink;
varying float v_energy,v_glyph,v_hue,v_tint;
void main(){
  if(v_energy<.005)discard;
  vec3 color=mix(u_blue,u_pink,smoothstep(.12,.88,v_hue));
  color=mix(color*.56,color,v_tint);
  color=mix(color,vec3(.96,.97,1.),smoothstep(.64,1.,v_energy)*.18*v_tint);
  vec2 uv=(gl_PointCoord-.5)*(u_footprint/u_glyphSize)+.5;
  float inside=step(0.,uv.x)*step(uv.x,1.)*step(0.,uv.y)*step(uv.y,1.);
  float mask=texture2D(u_atlas,vec2((v_glyph+clamp(uv.x,0.,1.))/16.,clamp(uv.y,0.,1.))).a*inside;
  float opacity=mix(pow(v_energy,.72),pow(v_energy,.48)*.9,v_tint);
  float halo=exp(-dot(gl_PointCoord-.5,gl_PointCoord-.5)*14.)*pow(v_energy,1.5)*.046;
  gl_FragColor=vec4(color,min(.94,mask*opacity+halo));
}`;

function makeWebGL(){
  const gl=canvas.getContext('webgl',{alpha:false,antialias:false,powerPreference:'low-power'});if(!gl)return null;
  const compile=(type,source)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;};
  const program=gl.createProgram(),shaders=[compile(gl.VERTEX_SHADER,vertex),compile(gl.FRAGMENT_SHADER,fragment)];
  shaders.forEach(s=>gl.attachShader(program,s));gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);shaders.forEach(s=>gl.deleteShader(s));
  const locations=Object.fromEntries(['resolution','center','pointer','centers[0]','halves[0]','rotations[0]','time','ratio','unit','turn','pointerStrength','aa','footprint','glyphSize','mobile','blue','pink','atlas'].map(name=>[name,gl.getUniformLocation(program,`u_${name}`)]));
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  const attribute=gl.getAttribLocation(program,'a_cell');gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,0,0);
  const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,makeAtlas());gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.uniform1i(locations.atlas,0);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);
  let count=0;
  return {type:'WebGL',resize(){
    const cells=[];let row=0;
    for(let y=layout.top;y<height*.98;y+=PITCH,row++)for(let x=layout.left+PITCH*(row%2?.75:.25);x<width;x+=PITCH)cells.push(x,y);
    count=cells.length/2;canvas.dataset.glyphCount=String(count);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(cells),gl.STATIC_DRAW);gl.viewport(0,0,canvas.width,canvas.height);
  },draw(scene){
    scene.boxes.forEach((box,i)=>{centers.set(box.center,i*3);halves.set(box.half,i*3);rotations.set(box.rotation,i*4);});
    gl.clearColor(8/255,12/255,24/255,1);gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(locations.resolution,width,height);gl.uniform2fv(locations.center,layout.center);gl.uniform2f(locations.pointer,pointer.x,pointer.y);
    gl.uniform3fv(locations['centers[0]'],centers);gl.uniform3fv(locations['halves[0]'],halves);gl.uniform4fv(locations['rotations[0]'],rotations);
    gl.uniform3fv(locations.blue,parseHex(palette.blue));gl.uniform3fv(locations.pink,parseHex(palette.pink));
    for(const [key,value] of Object.entries({time,ratio,unit:layout.unit,turn:scene.turn,pointerStrength:pointer.strength,aa:PITCH/layout.unit*.55,footprint:POINT_SIZE,glyphSize:GLYPH_SIZE,mobile:layout.mobile?1:0}))gl.uniform1f(locations[key],value);
    gl.drawArrays(gl.POINTS,0,count);
  }};
}

function makeFallback(){
  const ctx=canvas.getContext('2d');if(!ctx)return {type:'unavailable',resize(){},draw(){}};
  let signature='',atlases=[];
  return {type:'Canvas 2D',resize(){},draw(scene){
    const next=palette.blue+palette.pink;
    if(signature!==next){signature=next;const a=parseHex(palette.blue),b=parseHex(palette.pink);atlases=Array.from({length:8},(_,i)=>makeAtlas(`rgb(${a.map((v,k)=>Math.round((v+(b[k]-v)*i/7)*255)).join(',')})`));}
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.globalAlpha=1;ctx.fillStyle='#080c18';ctx.fillRect(0,0,width,height);ctx.imageSmoothingEnabled=true;
    const pitch=8.8;let row=0;
    for(let y=layout.top;y<height*.95;y+=pitch,row++)for(let x=layout.left+pitch*(row%2?.75:.25);x<width;x+=pitch){
      const hit=traceBoxes((x-layout.center[0])/layout.unit,(y-layout.center[1])/layout.unit,scene.boxes,scene.turn);if(!hit)continue;
      const kind=Math.abs(Math.floor(x/21)*17+Math.floor(y/23)*7)%16;
      ctx.globalAlpha=Math.pow(Math.min(1,.33+hit.rim*.45),.48)*.86;
      ctx.drawImage(atlases[Math.round(hit.hue*7)],kind*64,0,64,64,x-GLYPH_SIZE/2,y-GLYPH_SIZE/2,GLYPH_SIZE,GLYPH_SIZE);
    }
  }};
}
function sceneAtClock(){
  if(morph){const progress=Math.max(0,Math.min(1,(time-morph.started)/TRANSITION));
    if(progress<1){const blend=easeProgress(progress);return {boxes:mixBoxes(morph.boxes,SHAPES[morph.target],progress),state:{from:morph.from,to:morph.target,focus:blend<.5?morph.from:morph.target,transitioning:true}};}
    morph=null;
  }
  return boxesAt(time+sequenceOffset,mode);
}
function draw(){
  const scene=sceneAtClock();scene.turn=Math.sin(time*.13)*.045+pointer.turn;renderer.draw(scene);frames++;
  const name=FORM_LABELS[scene.state.focus];formName.textContent=name;
  canvas.dataset.form=scene.state.focus;canvas.dataset.time=time.toFixed(3);canvas.dataset.frame=String(frames);canvas.dataset.transitioning=String(scene.state.transitioning);canvas.dataset.turn=scene.turn.toFixed(4);
}
function tick(now){
  request=0;if(paused||!visible||!inView){previous=0;return;}
  const delta=previous?Math.min(.1,Math.max(0,(now-previous)/1000)):0;time+=delta;previous=now;
  const response=1-Math.exp(-delta*5),target=pointer.x>-1000?(pointer.x/width-.5)*.22:0;
  pointer.strength+=(pointer.x>-1000?1-pointer.strength:-pointer.strength)*response;pointer.turn+=(target-pointer.turn)*response;
  draw();request=requestAnimationFrame(tick);
}
function schedule(){if(!request&&!paused&&visible&&inView)request=requestAnimationFrame(tick);}
function setPaused(value){paused=value;previous=0;if(request)cancelAnimationFrame(request);request=0;canvas.dataset.paused=String(paused);pauseButton.setAttribute('aria-pressed',String(paused));pauseButton.textContent=paused?'Resume':'Pause';status.textContent=paused?'Animation paused. Choose a form to inspect it.':'Animation playing.';schedule();}
function resize(){
  const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;ratio=Math.min(2,Math.max(1.5,devicePixelRatio||1));
  const mobile=width<=900;
  layout={mobile,center:[width*(mobile?.5:.7),height*(mobile?.68:.54)],unit:mobile?Math.min(155,width*.24):Math.min(195,width*.14),left:mobile?0:width*.37,top:height*(mobile?.43:.07)};
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);renderer.resize();draw();schedule();
}
function changeForm(requested,targetForm){
  const source=sceneAtClock(),target=targetForm||(requested==='auto'?source.state.focus:requested);mode=requested;formControl.value=mode;
  if(paused||(!source.state.transitioning&&source.state.focus===target)){morph=null;if(mode==='auto')sequenceOffset=FORMS.indexOf(target)*STEP-time;}
  else{morph={boxes:source.boxes,from:source.state.focus,target,started:time};if(mode==='auto')sequenceOffset=FORMS.indexOf(target)*STEP-time-TRANSITION;}
  draw();schedule();
}
function nextForm(){const current=sceneAtClock().state.focus,next=FORMS[(FORMS.indexOf(current)+1)%FORMS.length];changeForm(mode==='auto'?'auto':next,next);canvas.dataset.interaction='next form';}
function setColor(key,value){
  if(!/^#[0-9a-f]{6}$/i.test(value))return false;
  palette[key]=value.toLowerCase();document.documentElement.style.setProperty(`--${key}`,value);
  document.querySelector(`#${key}-color`).value=value;document.querySelector(`#${key}-hex`).value=value.toUpperCase();document.querySelector(`#${key}-hex`).removeAttribute('aria-invalid');
  canvas.dataset[key]=palette[key];draw();return true;
}
try{if(new URLSearchParams(location.search).get('renderer')!=='canvas')renderer=makeWebGL();}catch(error){console.warn('WebGL unavailable; using Canvas 2D:',error.message);}
if(!renderer){const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=makeFallback();}
canvas.dataset.renderer=renderer.type;canvas.dataset.blue=palette.blue;canvas.dataset.pink=palette.pink;
canvas.addEventListener('pointermove',event=>{if(event.pointerType==='touch')return;const rect=canvas.getBoundingClientRect();pointer.x=event.clientX-rect.left;pointer.y=event.clientY-rect.top;canvas.dataset.interaction='pointer';});
canvas.addEventListener('pointerleave',()=>{pointer.x=-2000;pointer.y=-2000;});
let down;
canvas.addEventListener('pointerdown',event=>{down={x:event.clientX,y:event.clientY};});
canvas.addEventListener('pointerup',event=>{if(down&&Math.hypot(event.clientX-down.x,event.clientY-down.y)<8)nextForm();down=null;});
canvas.addEventListener('pointercancel',()=>{down=null;});
canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();if(request)cancelAnimationFrame(request);request=0;canvas.dataset.renderer='context lost';});
canvas.addEventListener('webglcontextrestored',()=>{renderer=makeWebGL();canvas.dataset.renderer=renderer.type;resize();});
pauseButton.addEventListener('click',()=>setPaused(!paused));
formControl.addEventListener('change',()=>changeForm(formControl.value));
document.querySelector('#reset-motion').addEventListener('click',()=>{time=0;previous=0;sequenceOffset=0;morph=null;mode='auto';formControl.value='auto';pointer.x=-2000;pointer.y=-2000;pointer.strength=0;pointer.turn=0;draw();});
for(const key of ['blue','pink']){
  const color=document.querySelector(`#${key}-color`),hex=document.querySelector(`#${key}-hex`);
  color.addEventListener('input',()=>setColor(key,color.value));
  hex.addEventListener('input',()=>{if(!setColor(key,hex.value))hex.setAttribute('aria-invalid','true');});
  hex.addEventListener('blur',()=>{if(hex.getAttribute('aria-invalid')==='true'){hex.value=palette[key].toUpperCase();hex.removeAttribute('aria-invalid');}});
}
document.querySelector('#reset-colors').addEventListener('click',()=>{setColor('blue',DEFAULTS.blue);setColor('pink',DEFAULTS.pink);});
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;schedule();});
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;schedule();}).observe(canvas);
new ResizeObserver(resize).observe(canvas);
reducedMotion.addEventListener('change',event=>{if(event.matches)setPaused(true);});
resize();setPaused(paused);
