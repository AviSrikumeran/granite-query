import {FORMS,FORM_LABELS,BOX_COUNT,BOOT,STEP,TRANSITION,MORPH_START,MORPH_END,SHAPES,boxesAt,switchState,mixBoxes,traceBoxes,revealAt,startupFlare,pointerPose,lightDirection,highlightFlare,paletteRamp,smooth} from './geometry.mjs?v=recording-20261103-2';

// Independent scene tuned from the supplied mouse-only recording.
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
let canvas=document.querySelector('#glyph-field');
const hero=document.querySelector('.hero'),pauseButton=document.querySelector('#pause-motion'),formControl=document.querySelector('#form-mode');
const formName=document.querySelector('#form-name'),status=document.querySelector('#motion-status');
const DEFAULT_COLOR='#78e865';
let color=DEFAULT_COLOR,ramp=paletteRamp(color);
let width=0,height=0,ratio=1,time=0,previous=0,request=0,frames=0;
let paused=reducedMotion.matches,visible=!document.hidden,inView=true,mode='auto',sequenceOffset=0,manual=null,bootSkipped=reducedMotion.matches;
let renderer,layout;
const pointer={x:-2000,y:-2000,strength:0,turn:0,tilt:0};
const centers=new Float32Array(BOX_COUNT*3),halves=new Float32Array(BOX_COUNT*3),rotations=new Float32Array(BOX_COUNT*4),kinds=new Float32Array(BOX_COUNT);
const PITCH=5.4,GLYPH_SIZE=6.8,POINT_SIZE=13;
const ECHOES=[[-1.94,.05,.74,.24],[1.02,-1.19,.65,.21],[1.1,1.28,.67,.16]];
const rgb=values=>'rgb('+values.map(v=>Math.round(v*255)).join(',')+')';
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};

function makeAtlas(fill='#fff'){
  const image=document.createElement('canvas');image.width=1024;image.height=64;
  const ctx=image.getContext('2d');ctx.fillStyle=fill;ctx.strokeStyle=fill;
  for(let kind=0;kind<16;kind++){
    ctx.save();ctx.translate(kind*64+32,32);ctx.lineWidth=7;ctx.lineCap='round';ctx.lineJoin='round';
    const arc=(r,a=0,b=Math.PI*2)=>{ctx.beginPath();ctx.arc(0,0,r,a,b);};
    if(kind===0){arc(19);ctx.fill();}
    if(kind===1){arc(20);ctx.stroke();}
    if(kind===2){arc(21,-Math.PI*.8,Math.PI*.8);ctx.stroke();}
    if(kind===3){ctx.beginPath();ctx.moveTo(-17,11);ctx.quadraticCurveTo(0,-28,17,11);ctx.stroke();}
    if(kind===4){arc(21);ctx.fill();ctx.globalCompositeOperation='destination-out';ctx.fillRect(-3,-26,6,52);}
    if(kind===5){ctx.beginPath();ctx.moveTo(0,-19);ctx.lineTo(0,19);ctx.moveTo(-19,0);ctx.lineTo(19,0);ctx.stroke();}
    if(kind===6){ctx.beginPath();ctx.ellipse(0,0,23,12,-Math.PI/4,0,Math.PI*2);ctx.fill();}
    if(kind===7){ctx.beginPath();ctx.moveTo(-17,-15);ctx.lineTo(0,0);ctx.lineTo(17,-15);ctx.moveTo(0,0);ctx.lineTo(0,20);ctx.stroke();}
    if(kind===8){ctx.beginPath();ctx.moveTo(-17,-17);ctx.lineTo(17,17);ctx.moveTo(-17,17);ctx.lineTo(17,-17);ctx.stroke();}
    if(kind===9){ctx.beginPath();ctx.moveTo(-16,13);ctx.lineTo(0,-17);ctx.lineTo(16,13);ctx.closePath();ctx.fill();}
    if(kind===10){for(let i=0;i<3;i++){const a=i*Math.PI*2/3;ctx.beginPath();ctx.arc(13*Math.cos(a),13*Math.sin(a),8,0,Math.PI*2);ctx.fill();}}
    if(kind===11){ctx.beginPath();ctx.moveTo(-18,8);ctx.quadraticCurveTo(-2,-22,18,8);ctx.moveTo(-18,18);ctx.quadraticCurveTo(-2,-12,18,18);ctx.stroke();}
    if(kind===12){arc(21,0,Math.PI);ctx.stroke();arc(21,Math.PI,Math.PI*2);ctx.setLineDash([5,9]);ctx.stroke();}
    if(kind===13){ctx.beginPath();ctx.moveTo(0,-22);ctx.bezierCurveTo(22,-4,24,16,0,23);ctx.bezierCurveTo(-24,16,-22,-4,0,-22);ctx.fill();}
    if(kind===14){ctx.beginPath();ctx.moveTo(-17,0);ctx.lineTo(17,0);ctx.lineWidth=13;ctx.stroke();}
    if(kind===15){ctx.beginPath();ctx.moveTo(-19,13);ctx.quadraticCurveTo(-10,-21,0,-1);ctx.quadraticCurveTo(11,19,19,-13);ctx.stroke();}
    ctx.restore();
  }
  return image;
}

const vertex=`
precision highp float;
attribute vec2 a_cell;
uniform vec2 u_resolution,u_center,u_pointer;
uniform vec3 u_light;
uniform vec3 u_centers[16],u_halves[16];
uniform vec4 u_rotations[16];
uniform float u_kinds[16];
uniform float u_time,u_reveal,u_flash,u_ratio,u_unit,u_turn,u_tilt,u_pointerStrength,u_aa,u_footprint,u_mobile;
varying float v_energy,v_glyph,v_tint,v_reveal;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
vec3 camera(vec3 p){float c=cos(u_turn),s=sin(u_turn),ct=cos(u_tilt),st=sin(u_tilt);vec3 q=vec3(p.x*c-p.z*s,p.y,p.x*s+p.z*c);return vec3(q.x,q.y*ct-q.z*st,q.y*st+q.z*ct);}
vec3 rotate(vec4 q,vec3 p){return p+2.*cross(q.xyz,cross(q.xyz,p)+q.w*p);}
vec2 interval(vec3 o,vec3 d,vec3 h,float kind){
  if(kind>.5){
    vec2 od=o.xz/h.xz,dd=d.xz/h.xz;
    float a=dot(dd,dd),b=2.*dot(od,dd),c=dot(od,od)-1.,disc=b*b-4.*a*c;
    if(disc<0.)return vec2(1000.,-1000.);
    vec2 radial=vec2(-b-sqrt(disc),-b+sqrt(disc))/(2.*a),caps=(vec2(-h.y,h.y)-o.y)/d.y;
    return vec2(max(radial.x,min(caps.x,caps.y)),min(radial.y,max(caps.x,caps.y)));
  }
  vec3 safe=mix(vec3(.00001),d,step(vec3(.00001),abs(d))),inv=1./safe;
  vec3 a=(-h-o)*inv,b=(h-o)*inv,lo=min(a,b),hi=max(a,b);
  return vec2(max(lo.x,max(lo.y,lo.z)),min(hi.x,min(hi.y,hi.z)));
}
vec3 trace(vec2 screen,bool detailed){
  vec2 local=(screen-u_center)/u_unit;
  vec3 origin=camera(vec3(local.x/1.7320508,-local.y,-local.x/1.7320508)+8.);
  vec3 direction=camera(vec3(-.57735027));
  float nearest=1000.,energy=0.,rim=0.;
  vec3 surface=vec3(0.),surfaceNormal=vec3(0.);
  for(int i=0;i<16;i++){
    vec3 h=u_halves[i];if(min(h.x,min(h.y,h.z))<.001)continue;
    vec4 q=u_rotations[i],inverse=vec4(-q.xyz,q.w);
    vec3 o=rotate(inverse,origin-u_centers[i]),d=rotate(inverse,direction);
    vec2 range=interval(o,d,h,u_kinds[i]);
    float entry=range.x,exit=range.y;
    if(entry<=exit+u_aa&&exit>0.&&entry<nearest){
      nearest=entry;vec3 p=o+d*entry,normal;
      if(u_kinds[i]>.5){
        bool cap=abs(abs(p.y)-h.y)<.003;
        normal=cap?vec3(0.,sign(p.y),0.):normalize(vec3(p.x/(h.x*h.x),0.,p.z/(h.z*h.z)));
        float edge=cap?abs(1.-length(p.xz/h.xz))*min(h.x,h.z):h.y-abs(p.y);
        rim=exp(-pow(edge/.1,2.));
      }else{
        vec3 margin=max(vec3(0.),h-abs(p));
        float second=min(max(margin.x,margin.y),max(min(margin.x,margin.y),margin.z));
        rim=exp(-pow(second/.1,2.));
        vec3 distance=abs(abs(p)-h);
        normal=distance.y<distance.x&&distance.y<distance.z?vec3(0.,sign(p.y),0.):(distance.x<distance.z?vec3(sign(p.x),0.,0.):vec3(0.,0.,sign(p.z)));
      }
      surface=origin+direction*entry;surfaceNormal=rotate(q,normal);
      float diffuse=max(0.,dot(surfaceNormal,u_light));
      float band=pow(.5+.5*sin(dot(surface,vec3(2.4,2.8,-1.4))-u_time*1.45),3.);
      energy=(.17+diffuse*.32+rim*.2+band*(.2+diffuse*.25+rim*.18))*(1.-smoothstep(-u_aa,u_aa,entry-exit));
    }
  }
  if(detailed&&energy>0.){
    vec3 light=u_light,start=surface+surfaceNormal*.015;
    float shade=1.;
    for(int i=0;i<16;i++){
      vec3 h=u_halves[i];if(min(h.x,min(h.y,h.z))<.001)continue;
      vec4 inverse=vec4(-u_rotations[i].xyz,u_rotations[i].w);
      vec2 hit=interval(rotate(inverse,start-u_centers[i]),rotate(inverse,light),h,u_kinds[i]);
      if(hit.y>max(hit.x,.025)&&hit.x>.005)shade=.56;
    }
    energy*=shade;
  }
  return vec3(energy,rim,nearest<999.?1.:0.);
}
float reveal(vec2 local,float seed,float rim){
  float front=smoothstep(.96,1.23,u_reveal)*2.4,delay=length(local)+seed*.09;
  float filled=smoothstep(delay-.1,delay+.16,front)*smoothstep(.92,1.02,u_reveal);
  return max(filled,step(.982,seed)*.55*rim);
}
void main(){
  vec2 p=a_cell;
  vec3 core=trace(p,true);
  vec3 left=trace((p-u_center-vec2(-1.94,.05)*u_unit)/.74+u_center,false);
  vec3 upper=trace((p-u_center-vec2(1.02,-1.19)*u_unit)/.65+u_center,false);
  vec3 lower=trace((p-u_center-vec2(1.1,1.28)*u_unit)/.67+u_center,false);
  float echoes=max(left.x*.24,max(upper.x*.21,lower.x*.16));
  float seed=hash(p+vec2(17.,53.)),grain=.56+.64*hash(p+7.);
  float patch=.88+.12*sin(p.x*.029+p.y*.023);
  vec2 ellipse=(p-u_center)/vec2(u_unit*3.4,u_unit*2.9);
  float envelope=exp(-pow(length(ellipse),4.)*.25);
  float edge=1.-smoothstep(u_resolution.y*.95,u_resolution.y,p.y);
  edge*=mix(smoothstep(u_resolution.x*.37,u_resolution.x*.48,p.x),1.,u_mobile);
  float spark=step(.93,hash(p+vec2(23.,47.)))*.22*smoothstep(.4,.75,core.x);
  float light=core.x*grain*patch+spark;
  float flare=u_flash*.8*smoothstep(.48,.85,light);
  float lamp=exp(-dot(p-u_pointer,p-u_pointer)/19000.)*u_pointerStrength;
  float primary=light+flare+lamp*.055*core.z;
  v_energy=max(primary,echoes*grain)*envelope*edge;
  v_tint=step(echoes,light)*core.z;
  vec2 local=(p-u_center)/u_unit;
  float coreReveal=reveal(local,seed,core.y)*core.z;
  float leftReveal=reveal((local-vec2(-1.94,.05))/.74,seed,left.y)*left.z;
  float upperReveal=reveal((local-vec2(1.02,-1.19))/.65,seed,upper.y)*upper.z;
  float lowerReveal=reveal((local-vec2(1.1,1.28))/.67,seed,lower.y)*lower.z;
  v_reveal=max(coreReveal,max(leftReveal,max(upperReveal,lowerReveal)));
  float choice=floor(hash(p+vec2(83.,19.))*32.);
  v_glyph=choice<16.?choice:(choice<21.?0.:(choice<24.?6.:(choice<27.?9.:(choice<29.?10.:(choice<31.?13.:14.)))));
  gl_Position=vec4(p.x/u_resolution.x*2.-1.,1.-p.y/u_resolution.y*2.,0.,1.);
  gl_PointSize=u_footprint*u_ratio;
}`;
const fragment=`
precision highp float;
uniform sampler2D u_atlas;
uniform float u_footprint,u_glyphSize,u_reveal;
uniform vec3 u_base,u_shadow,u_highlight;
varying float v_energy,v_glyph,v_tint,v_reveal;
void main(){
  if(v_energy*v_reveal<.004)discard;
  vec3 ink=mix(u_shadow,u_base,smoothstep(.12,.68,v_energy));
  ink=mix(ink,u_highlight,smoothstep(.62,1.2,v_energy)*.85);
  vec3 color=mix(vec3(.39,.45,.36),ink,v_tint);
  color=mix(vec3(.5,.55,.46),color,smoothstep(.94,1.03,u_reveal));
  vec2 uv=(gl_PointCoord-.5)*(u_footprint/u_glyphSize)+.5;
  float inside=step(0.,uv.x)*step(uv.x,1.)*step(0.,uv.y)*step(uv.y,1.);
  float mask=texture2D(u_atlas,vec2((v_glyph+clamp(uv.x,0.,1.))/16.,clamp(uv.y,0.,1.))).a*inside;
  float opacity=mix(pow(min(v_energy,1.),.8),.48+.48*sqrt(min(v_energy,1.)),v_tint);
  float halo=exp(-dot(gl_PointCoord-.5,gl_PointCoord-.5)*12.)*pow(v_energy,2.)*.12*v_tint;
  gl_FragColor=vec4(color,min(.98,mask*opacity+halo)*v_reveal);
}`;

function makeWebGL(){
  const gl=canvas.getContext('webgl',{alpha:false,antialias:false,powerPreference:'low-power'});if(!gl)return null;
  const compile=(type,source)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;};
  const program=gl.createProgram(),shaders=[compile(gl.VERTEX_SHADER,vertex),compile(gl.FRAGMENT_SHADER,fragment)];
  shaders.forEach(s=>gl.attachShader(program,s));gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);shaders.forEach(s=>gl.deleteShader(s));
  const names=['resolution','center','pointer','light','centers[0]','halves[0]','rotations[0]','kinds[0]','time','reveal','flash','ratio','unit','turn','tilt','pointerStrength','aa','footprint','glyphSize','mobile','base','shadow','highlight','atlas'];
  const locations=Object.fromEntries(names.map(name=>[name,gl.getUniformLocation(program,'u_'+name)]));
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  const attribute=gl.getAttribLocation(program,'a_cell');gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,0,0);
  const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,makeAtlas());gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.uniform1i(locations.atlas,0);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);
  let count=0;
  return {type:'WebGL',resize(){
    const cells=[];let row=0;
    for(let y=layout.top;y<height;y+=PITCH,row++)for(let x=layout.left+PITCH*(row%2?.75:.25);x<width;x+=PITCH)cells.push(x,y);
    count=cells.length/2;canvas.dataset.glyphCount=String(count);canvas.dataset.glyphPitch=String(PITCH);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(cells),gl.STATIC_DRAW);gl.viewport(0,0,canvas.width,canvas.height);
  },draw(scene){
    scene.boxes.forEach((box,i)=>{centers.set(box.center,i*3);halves.set(box.half,i*3);rotations.set(box.rotation,i*4);kinds[i]=box.kind;});
    gl.clearColor(4/255,8/255,4/255,1);gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(locations.resolution,width,height);gl.uniform2fv(locations.center,layout.center);gl.uniform2f(locations.pointer,pointer.x,pointer.y);
    gl.uniform3fv(locations.light,lightDirection(time));
    gl.uniform3fv(locations['centers[0]'],centers);gl.uniform3fv(locations['halves[0]'],halves);gl.uniform4fv(locations['rotations[0]'],rotations);gl.uniform1fv(locations['kinds[0]'],kinds);
    for(const key of ['base','shadow','highlight'])gl.uniform3fv(locations[key],ramp[key]);
    const values={time,reveal:bootSkipped?BOOT:time,flash:Math.max(scene.state.flash,bootSkipped?0:startupFlare(time)),ratio,unit:layout.unit,turn:scene.turn,tilt:scene.tilt,pointerStrength:pointer.strength,aa:PITCH/layout.unit*.45,footprint:POINT_SIZE,glyphSize:GLYPH_SIZE,mobile:layout.mobile?1:0};
    for(const [key,value] of Object.entries(values))gl.uniform1f(locations[key],value);
    gl.drawArrays(gl.POINTS,0,count);
  }};
}
function makeFallback(){
  const ctx=canvas.getContext('2d');if(!ctx)return {type:'unavailable',resize(){},draw(){}};
  let signature='',atlases=[],echoAtlas;
  return {type:'Canvas 2D',resize(){},draw(scene){
    if(signature!==color){signature=color;atlases=Array.from({length:12},(_,i)=>{const t=i/11,a=t<.65?ramp.shadow:ramp.base,b=t<.65?ramp.base:ramp.highlight,f=t<.65?t/.65:(t-.65)/.35;return makeAtlas(rgb(a.map((v,k)=>v+(b[k]-v)*f)));});echoAtlas=makeAtlas('#63735c');}
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.globalAlpha=1;ctx.fillStyle='#040804';ctx.fillRect(0,0,width,height);
    const pitch=8.8;let row=0;
    for(let y=layout.top;y<height;y+=pitch,row++)for(let x=layout.left+pitch*(row%2?.75:.25);x<width;x+=pitch){
      const local=[(x-layout.center[0])/layout.unit,(y-layout.center[1])/layout.unit];
      let hit=traceBoxes(...local,scene.boxes,scene.turn,scene.tilt,time),energy=0,main=!!hit,echo=0,revealRadius=Math.hypot(...local);
      if(hit){const spark=hash(x+23,y+47)>.93?.22*smooth(.4,.75,hit.light):0;energy=highlightFlare(hit.light*(.56+.64*hash(x+7,y+7))+spark,Math.max(scene.state.flash,bootSkipped?0:startupFlare(time)));}
      for(const [dx,dy,scale,strength] of ECHOES){
        const h=traceBoxes((local[0]-dx)/scale,(local[1]-dy)/scale,scene.boxes,scene.turn,scene.tilt,time);
        if(h&&h.light*strength>echo){echo=h.light*strength;if(!main){hit=h;revealRadius=Math.hypot((local[0]-dx)/scale,(local[1]-dy)/scale);}}
      }
      if(!hit)continue;main=energy>=echo;energy=Math.max(energy,echo);
      const envelope=Math.exp(-Math.pow(Math.hypot(local[0]/3.4,local[1]/2.9),4)*.25),edge=(1-smooth(height*.95,height,y))*(layout.mobile?1:smooth(width*.37,width*.48,x));
      const reveal=revealAt(bootSkipped?BOOT:time,hash(x+17,y+53),hit.rim,revealRadius);
      ctx.globalAlpha=Math.min(.97,main?.48+.48*Math.sqrt(Math.min(1,energy)):energy**.8)*envelope*edge*reveal;
      const choice=Math.floor(hash(x+83,y+19)*32),kind=choice<16?choice:choice<21?0:choice<24?6:choice<27?9:choice<29?10:choice<31?13:14,atlas=main?atlases[Math.min(11,Math.round(energy*11))]:echoAtlas;
      ctx.drawImage(atlas,kind*64,0,64,64,x-GLYPH_SIZE/2,y-GLYPH_SIZE/2,GLYPH_SIZE,GLYPH_SIZE);
    }
  }};
}
function sceneAtClock(){
  if(manual){
    const state=switchState(manual.from,manual.target,time-manual.started);
    const blend=smooth(manual.geometryStarted,manual.geometryStarted+MORPH_END-MORPH_START,time);
    if(state.transitioning||blend<1){state.blend=blend;state.focus=blend<.5?manual.from:manual.target;state.transitioning=true;if(time>=manual.geometryStarted&&blend<1)state.phase='reshape';return {state,boxes:mixBoxes(manual.boxes,SHAPES[manual.target],blend)};}
    if(mode==='auto')sequenceOffset=FORMS.indexOf(manual.target)*STEP-Math.max(0,time-BOOT);
    manual=null;
  }
  return boxesAt(Math.max(0,time-BOOT)+sequenceOffset,mode);
}
function draw(){
  const scene=sceneAtClock();scene.turn=pointer.turn;scene.tilt=pointer.tilt;renderer.draw(scene);frames++;
  formName.textContent=FORM_LABELS[scene.state.focus];
  Object.assign(canvas.dataset,{form:scene.state.focus,time:time.toFixed(3),frame:String(frames),transitioning:String(scene.state.transitioning),phase:scene.state.phase,blend:scene.state.blend.toFixed(3),flash:scene.state.flash.toFixed(3),reveal:(bootSkipped?BOOT:Math.min(BOOT,time)).toFixed(3),turn:scene.turn.toFixed(4),tilt:scene.tilt.toFixed(4),echoCount:'3'});
}
function tick(now){
  request=0;if(paused||!visible||!inView){previous=0;return;}
  const delta=previous?Math.min(.06,Math.max(0,(now-previous)/1000)):0;time+=delta;previous=now;
  const response=1-Math.exp(-delta*7.5),active=pointer.x>-1000;
  const {turn,tilt}=pointerPose(pointer.x,pointer.y,width,height,active);
  pointer.strength+=((active?1:0)-pointer.strength)*response;pointer.turn+=(turn-pointer.turn)*response;pointer.tilt+=(tilt-pointer.tilt)*response;
  draw();request=requestAnimationFrame(tick);
}
function schedule(){if(!request&&!paused&&visible&&inView)request=requestAnimationFrame(tick);}
function setPaused(value){paused=value;previous=0;if(request)cancelAnimationFrame(request);request=0;canvas.dataset.paused=String(paused);pauseButton.setAttribute('aria-pressed',String(paused));pauseButton.textContent=paused?'Resume':'Pause';status.textContent=paused?'Animation paused. Choose a form to inspect it.':'Animation playing.';schedule();}
function resize(){
  const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;ratio=Math.min(2,Math.max(1.5,devicePixelRatio||1));
  const mobile=width<=900;
  layout={mobile,center:[width*(mobile?.5:.7),height*(mobile?.68:.52)],unit:mobile?Math.min(155,width*.24):Math.min(195,width*.14),left:mobile?0:width*.37,top:height*(mobile?.43:.07)};
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);renderer.resize();draw();schedule();
}
function changeForm(requested,targetForm){
  const source=sceneAtClock(),target=targetForm||(requested==='auto'?source.state.focus:requested);
  mode=requested;formControl.value=mode;bootSkipped=true;
  if(paused||(!source.state.transitioning&&source.state.focus===target)){manual=null;if(mode==='auto')sequenceOffset=FORMS.indexOf(target)*STEP-Math.max(0,time-BOOT);}
  else if(manual){manual.boxes=source.boxes;manual.from=source.state.focus;manual.target=target;manual.geometryStarted=time;} // Keep the existing flare clock.
  else manual={boxes:source.boxes,from:source.state.focus,target,started:time,geometryStarted:time+MORPH_START};
  draw();schedule();
}
function setColor(value){
  if(!/^#[0-9a-f]{6}$/i.test(value))return false;
  color=value.toLowerCase();ramp=paletteRamp(color);
  document.documentElement.style.setProperty('--accent',color);document.documentElement.style.setProperty('--highlight',rgb(ramp.highlight));
  document.querySelector('#base-color').value=color;document.querySelector('#base-hex').value=color.toUpperCase();document.querySelector('#base-hex').removeAttribute('aria-invalid');
  canvas.dataset.color=color;draw();return true;
}
try{if(new URLSearchParams(location.search).get('renderer')!=='canvas')renderer=makeWebGL();}catch(error){console.warn('WebGL unavailable; using Canvas 2D:',error.message);}
if(!renderer){const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;renderer=makeFallback();}
canvas.dataset.renderer=renderer.type;canvas.dataset.color=color;
hero.addEventListener('pointermove',event=>{if(event.pointerType==='touch')return;const rect=hero.getBoundingClientRect();pointer.x=event.clientX-rect.left;pointer.y=event.clientY-rect.top;canvas.dataset.interaction='pointer';});
hero.addEventListener('pointerleave',()=>{pointer.x=-2000;pointer.y=-2000;});
canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();if(request)cancelAnimationFrame(request);request=0;canvas.dataset.renderer='context lost';});
canvas.addEventListener('webglcontextrestored',()=>{renderer=makeWebGL();canvas.dataset.renderer=renderer.type;resize();});
pauseButton.addEventListener('click',()=>setPaused(!paused));
formControl.addEventListener('change',()=>changeForm(formControl.value));
document.querySelector('#reset-motion').addEventListener('click',()=>{time=0;previous=0;sequenceOffset=0;manual=null;mode='auto';bootSkipped=reducedMotion.matches;formControl.value='auto';Object.assign(pointer,{x:-2000,y:-2000,strength:0,turn:0,tilt:0});setPaused(reducedMotion.matches);draw();});
const colorControl=document.querySelector('#base-color'),hexControl=document.querySelector('#base-hex');
colorControl.addEventListener('input',()=>setColor(colorControl.value));
hexControl.addEventListener('input',()=>{if(!setColor(hexControl.value))hexControl.setAttribute('aria-invalid','true');});
hexControl.addEventListener('blur',()=>{if(hexControl.getAttribute('aria-invalid')==='true'){hexControl.value=color.toUpperCase();hexControl.removeAttribute('aria-invalid');}});
document.querySelector('#reset-colors').addEventListener('click',()=>setColor(DEFAULT_COLOR));
document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;schedule();});
new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;schedule();}).observe(canvas);
new ResizeObserver(resize).observe(canvas);
reducedMotion.addEventListener('change',event=>{if(event.matches){bootSkipped=true;setPaused(true);draw();}});
resize();setPaused(paused);
