import {FORMS,FORM_LABELS,STEP,TRANSITION,SHAPES,boxesAt,mixBoxes,easeProgress} from './geometry.mjs';

// Independent rendering of the observed sequence. No Modal shader source.
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const embedded = window.parent !== window;
document.body.classList.toggle('embedded',embedded);
let canvas = document.querySelector('#glyph-field');
const pauseButton = document.querySelector('#local-pause');
let width=0,height=0,ratio=1,time=0,previous=0,request=0,frames=0;
let paused=reducedMotion.matches,visible=!document.hidden,inView=true,mode='auto',reported='';
let sequenceOffset=0,morph=null;
let renderer;
const GLYPH_PITCH=5.6,GLYPH_SIZE=7.8,POINT_SIZE=12;
const FACE_LIGHT={box:.26,layers:.8,stairs:.7,cubes:.85};
const pointer={x:-2000,y:-2000,strength:0,turn:0};
const centers=new Float32Array(36),halves=new Float32Array(36);

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
uniform vec2 u_resolution,u_pointer;
uniform vec3 u_centers[12],u_halves[12];
uniform float u_time,u_ratio,u_unit,u_turn,u_pointerStrength,u_face,u_aa,u_footprint;
varying float v_energy,v_glyph,v_hue,v_tint;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+1.),f.x),f.y);}
vec3 turn(vec3 p){float c=cos(u_turn),s=sin(u_turn);return vec3(p.x*c-p.z*s,p.y,p.x*s+p.z*c);}
float trace(vec2 screen){
  vec2 local=(screen-vec2(u_resolution.x*.5,620.))/u_unit;
  vec3 origin=turn(vec3(local.x/1.7320508,-local.y,-local.x/1.7320508)+8.);
  vec3 direction=turn(vec3(-.57735027));
  vec3 inv=1./direction;
  float nearest=1000.,light=0.;
  for(int i=0;i<12;i++){
    vec3 halfBox=u_halves[i];
    if(min(halfBox.x,min(halfBox.y,halfBox.z))<.004)continue;
    vec3 a=(u_centers[i]-halfBox-origin)*inv,b=(u_centers[i]+halfBox-origin)*inv;
    vec3 low=min(a,b),high=max(a,b);
    float entry=max(low.x,max(low.y,low.z)),exit=min(high.x,min(high.y,high.z));
    if(entry<=exit+u_aa&&exit>0.&&entry<nearest){
      nearest=entry;
      vec3 point=origin+direction*entry;
      vec3 margin=max(vec3(0.),halfBox-abs(point-u_centers[i]));
      float second=min(max(margin.x,margin.y),max(min(margin.x,margin.y),margin.z));
      float rim=exp(-pow(second/.095,2.));
      float shade=entry==low.y?.48:(entry==low.x?.7:.86);
      float coverage=1.-smoothstep(-u_aa,u_aa,entry-exit);
      light=(u_face*shade+rim*.56)*coverage;
    }
  }
  return light;
}
void main(){
  vec2 p=a_cell,center=vec2(u_resolution.x*.5,620.);
  float core=trace(p);
  float scale=u_unit/112.;
  float left=trace((p-center+vec2(247.,-4.)*scale)/.78+center);
  float right=trace((p-center-vec2(172.,-143.)*scale)/.7+center);
  float echoes=max(left,right)*.21;
  float grain=noise(p*.038+vec2(u_time*.025,-u_time*.018));
  float sweep=.88+.12*sin(p.x*.011+p.y*.007-u_time*.55);
  vec2 ellipse=(p-center)/vec2(500.*scale,365.*scale);
  float envelope=exp(-pow(length(ellipse),4.)*.48);
  float vertical=smoothstep(326.,390.,p.y)*(1.-smoothstep(930.,1070.,p.y));
  float pointerLight=exp(-dot(p-u_pointer,p-u_pointer)/11500.)*u_pointerStrength;
  v_energy=clamp(max(core*1.22,echoes)*(.74+grain*.33)*sweep*envelope*vertical+pointerLight*.16*step(.01,core),0.,1.);
  v_tint=step(echoes,core)*step(.01,core);
  v_hue=noise(p*.014+vec2(u_time*.018,0.));
  float choice=floor(hash(a_cell+vec2(17.,53.))*24.);
  v_glyph=choice<16.?choice:(choice<19.?0.:(choice<21.?2.:(choice<23.?4.:7.)));
  gl_Position=vec4(p.x/u_resolution.x*2.-1.,1.-p.y/u_resolution.y*2.,0.,1.);
  gl_PointSize=u_footprint*u_ratio;
}`;
const fragment=`
precision highp float;
uniform sampler2D u_atlas;
uniform float u_footprint,u_glyphSize;
varying float v_energy,v_glyph,v_hue,v_tint;
void main(){
  if(v_energy<.007)discard;
  vec3 green=mix(vec3(.18,.83,.36),vec3(.59,.98,.39),smoothstep(.28,.78,v_hue));
  green=mix(green,vec3(.76,.95,.41),smoothstep(.73,.9,v_hue)*.55);
  vec3 color=mix(vec3(.43,.48,.41),green,v_tint);
  vec2 uv=(gl_PointCoord-.5)*(u_footprint/u_glyphSize)+.5;
  float inside=step(0.,uv.x)*step(uv.x,1.)*step(0.,uv.y)*step(uv.y,1.);
  float mask=texture2D(u_atlas,vec2((v_glyph+clamp(uv.x,0.,1.))/16.,clamp(uv.y,0.,1.))).a*inside;
  float opacity=mix(pow(v_energy,.72),pow(v_energy,.48)*.86,v_tint);
  float halo=exp(-dot(gl_PointCoord-.5,gl_PointCoord-.5)*14.)*pow(v_energy,1.5)*.04;
  float alpha=min(.92,mask*opacity+halo);
  gl_FragColor=vec4(color,alpha);
}`;

function makeWebGL(){
  const gl=canvas.getContext('webgl',{alpha:false,antialias:false,powerPreference:'low-power'});
  if(!gl)return null;
  const compile=(type,source)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;};
  const program=gl.createProgram(),shaders=[compile(gl.VERTEX_SHADER,vertex),compile(gl.FRAGMENT_SHADER,fragment)];
  shaders.forEach(s=>gl.attachShader(program,s));gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);shaders.forEach(s=>gl.deleteShader(s));
  const locations=Object.fromEntries(['resolution','pointer','centers[0]','halves[0]','time','ratio','unit','turn','pointerStrength','face','aa','footprint','glyphSize','atlas'].map(name=>[name,gl.getUniformLocation(program,`u_${name}`)]));
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  const attribute=gl.getAttribLocation(program,'a_cell');gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,0,0);
  const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,makeAtlas());
  gl.generateMipmap(gl.TEXTURE_2D);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.uniform1i(locations.atlas,0);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);
  let count=0;
  return {type:'WebGL',resize(){
    const cells=[];let row=0;
    for(let y=326;y<height;y+=GLYPH_PITCH,row++)for(let x=GLYPH_PITCH*(row%2?.75:.25);x<width;x+=GLYPH_PITCH)cells.push(x,y);
    count=cells.length/2;canvas.dataset.glyphCount=String(count);canvas.dataset.glyphPitch=String(GLYPH_PITCH);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(cells),gl.STATIC_DRAW);gl.viewport(0,0,canvas.width,canvas.height);
  },draw(scene){
    scene.boxes.forEach((box,i)=>{centers.set(box.center,i*3);halves.set(box.half,i*3);});
    gl.clearColor(4/255,8/255,4/255,1);gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(locations.resolution,width,height);gl.uniform2f(locations.pointer,pointer.x,pointer.y);
    gl.uniform3fv(locations['centers[0]'],centers);gl.uniform3fv(locations['halves[0]'],halves);
    for(const [name,value] of Object.entries({time,ratio,unit:scene.unit,turn:scene.turn,pointerStrength:pointer.strength,face:scene.face,aa:GLYPH_PITCH/scene.unit*.55,footprint:POINT_SIZE,glyphSize:GLYPH_SIZE}))gl.uniform1f(locations[name],value);
    gl.drawArrays(gl.POINTS,0,count);
  }};
}

// Same scene, fewer samples: no browser gets a blank field for lacking WebGL.
async function makeFallback(){
  const {traceBoxes}=await import('./geometry.mjs');
  const ctx=canvas.getContext('2d');
  if(!ctx)return {type:'unavailable',resize(){},draw(){}};
  const atlas=makeAtlas('#8bed6c'),pitch=6.8;
  return {type:'Canvas 2D',resize(){canvas.dataset.glyphPitch=String(pitch);},draw(scene){
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.globalAlpha=1;ctx.fillStyle='#040804';ctx.fillRect(0,0,width,height);ctx.imageSmoothingEnabled=true;
    let row=0;
    for(let y=340;y<Math.min(height,1040);y+=pitch,row++)for(let x=pitch*(row%2?.75:.25);x<width;x+=pitch){
      const hit=traceBoxes((x-width/2)/scene.unit,(y-620)/scene.unit,scene.boxes,scene.turn);
      if(!hit)continue;
      const grain=.8+.2*Math.sin(x*.038+y*.027+time*.2),energy=Math.min(1,(scene.face*hit.shade+hit.rim*.56)*grain);
      const kind=Math.abs(Math.floor(x/24)*17+Math.floor(y/28)*7)%16;
      ctx.globalAlpha=Math.pow(energy,.48)*.86;ctx.drawImage(atlas,kind*64,0,64,64,x-GLYPH_SIZE/2,y-GLYPH_SIZE/2,GLYPH_SIZE,GLYPH_SIZE);
    }
  }};
}
function notifyState(state){
  const key=`${mode}:${state.focus}`;
  if(key===reported)return;reported=key;
  canvas.dataset.form=state.focus;
  if(embedded)window.parent.postMessage({type:'modal-hero-state',form:state.focus,label:FORM_LABELS[state.focus],mode},location.origin);
}
function sceneAtClock(){
  if(morph){
    const progress=Math.max(0,Math.min(1,(time-morph.started)/TRANSITION));
    if(progress<1){
      const blend=easeProgress(progress);
      return {boxes:mixBoxes(morph.boxes,SHAPES[morph.target],progress),
        state:{from:morph.from,to:morph.target,progress,blend,focus:blend<.5?morph.from:morph.target,transitioning:true},
        face:morph.face+(FACE_LIGHT[morph.target]-morph.face)*blend};
    }
    morph=null;
  }
  const scene=boxesAt(time+sequenceOffset,mode);
  scene.face=FACE_LIGHT[scene.state.from]+(FACE_LIGHT[scene.state.to]-FACE_LIGHT[scene.state.from])*scene.state.blend;
  return scene;
}
function draw(){
  const scene=sceneAtClock();scene.unit=112*Math.min(1.12,Math.max(.62,width/1265));
  scene.turn=Math.sin(time*.14)*.035+pointer.turn;
  renderer.draw(scene);notifyState(scene.state);frames++;
  canvas.dataset.frame=String(frames);canvas.dataset.time=time.toFixed(3);canvas.dataset.transitioning=String(scene.state.transitioning);
  canvas.dataset.turn=scene.turn.toFixed(4);
}
function tick(now){
  request=0;if(paused||!visible||!inView){previous=0;return;}
  const delta=previous?Math.min(.1,Math.max(0,(now-previous)/1000)):0;
  time+=delta;previous=now;
  const response=1.-Math.exp(-delta*6);
  pointer.strength+=(pointer.x>-1000?1-pointer.strength:-pointer.strength)*response;
  const target=pointer.x>-1000?(pointer.x/width-.5)*.13:0;pointer.turn+=(target-pointer.turn)*response;
  draw();request=requestAnimationFrame(tick);
}
function schedule(){if(!request&&!paused&&visible&&inView)request=requestAnimationFrame(tick);}
function setPaused(value){
  paused=value;previous=0;if(request)cancelAnimationFrame(request);request=0;
  canvas.dataset.paused=String(paused);pauseButton.setAttribute('aria-pressed',String(paused));pauseButton.textContent=paused?'Resume animation':'Pause animation';schedule();
  if(embedded)window.parent.postMessage({type:'modal-hero-motion',paused},location.origin);
}
function resize(){
  const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;ratio=Math.min(2,Math.max(1.5,devicePixelRatio||1));
  if(width>760){document.querySelector('#mobile-menu').hidden=true;const menu=document.querySelector('#menu-toggle');menu.setAttribute('aria-expanded','false');menu.setAttribute('aria-label','Open navigation');}
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);renderer.resize();draw();schedule();
}
function changeForm(requested,targetForm){
  const source=sceneAtClock(),target=targetForm||(requested==='auto'?source.state.focus:requested);
  mode=requested;
  if(paused||(!source.state.transitioning&&source.state.focus===target)){
    morph=null;
    if(mode==='auto')sequenceOffset=FORMS.indexOf(target)*STEP-time;
  }else{
    morph={boxes:source.boxes,from:source.state.focus,face:source.face,target,started:time};
    if(mode==='auto')sequenceOffset=FORMS.indexOf(target)*STEP-time-TRANSITION;
  }
  draw();schedule();
}
function nextForm(){
  const current=sceneAtClock().state.focus,next=FORMS[(FORMS.indexOf(current)+1)%FORMS.length];
  changeForm(mode==='auto'?'auto':next,next);canvas.dataset.interaction='next form';
}
try{if(new URLSearchParams(location.search).get('renderer')!=='canvas')renderer=makeWebGL();}catch(error){console.warn('WebGL unavailable; using Canvas 2D:',error.message);}
if(!renderer){const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=await makeFallback();}
canvas.dataset.renderer=renderer.type;
canvas.addEventListener('pointermove',event=>{if(event.pointerType==='touch')return;const rect=canvas.getBoundingClientRect();pointer.x=event.clientX-rect.left;pointer.y=event.clientY-rect.top;canvas.dataset.interaction='pointer';});
canvas.addEventListener('pointerleave',()=>{pointer.x=-2000;pointer.y=-2000;});
let down;
canvas.addEventListener('pointerdown',event=>{down={x:event.clientX,y:event.clientY};});
canvas.addEventListener('pointerup',event=>{if(down&&Math.hypot(event.clientX-down.x,event.clientY-down.y)<8)nextForm();down=null;});
canvas.addEventListener('pointercancel',()=>{down=null;});
canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();if(request)cancelAnimationFrame(request);request=0;canvas.dataset.renderer='context lost';});
canvas.addEventListener('webglcontextrestored',()=>{renderer=makeWebGL();canvas.dataset.renderer=renderer.type;resize();});
pauseButton.addEventListener('click',()=>setPaused(!paused));
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;schedule();});
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;schedule();}).observe(canvas);
new ResizeObserver(resize).observe(canvas);
reducedMotion.addEventListener('change',event=>{if(event.matches)setPaused(true);});
window.addEventListener('message',event=>{
  if(event.origin!==location.origin||event.source!==window.parent||event.data?.type!=='modal-hero-study')return;
  if(['view','form','reset'].includes(event.data.action))window.scrollTo(0,0);
  if(event.data.action==='motion')setPaused(Boolean(event.data.paused));
  if(event.data.action==='form'&&(event.data.form==='auto'||FORMS.includes(event.data.form)))changeForm(event.data.form);
  if(event.data.action==='reset'){mode='auto';time=0;previous=0;sequenceOffset=0;morph=null;pointer.x=-2000;pointer.y=-2000;pointer.strength=0;pointer.turn=0;reported='';draw();}
});
const menu=document.querySelector('#menu-toggle'),menuPanel=document.querySelector('#mobile-menu');
menu.addEventListener('click',()=>{const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Close navigation':'Open navigation');menuPanel.hidden=!open;});
resize();setPaused(paused);
if(embedded)window.parent.postMessage({type:'modal-hero-ready'},location.origin);
