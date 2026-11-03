import {FORMS,FORM_LABELS,BOX_COUNT,BOOT,STEP,TRANSITION,MORPH_START,MORPH_END,SHAPES,REFLECTIONS,layoutFor,sceneBounds,boxesAt,switchState,mixBoxes,traceBoxes,revealAt,startupFlare,pointerPose,lightDirection,highlightFlare,paletteRamp,smooth} from './geometry.mjs?v=replica-20261103-3';

// Reconstruct the supplied reference's formations, scale and reflected fragments.
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
let canvas=document.querySelector('#glyph-field');
const hero=document.querySelector('.hero'),pauseButton=document.querySelector('#pause-motion'),formControl=document.querySelector('#form-mode');
const formName=document.querySelector('#form-name'),status=document.querySelector('#motion-status');
const DEFAULT_COLOR='#7fee64';
let color=DEFAULT_COLOR,ramp=paletteRamp(color);
let width=0,height=0,ratio=1,time=0,previous=0,request=0,frames=0;
let paused=reducedMotion.matches,visible=!document.hidden,inView=true,mode='auto',sequenceOffset=0,manual=null,bootSkipped=reducedMotion.matches;
let renderer,layout;
const pointer={x:-2000,y:-2000,strength:0,turn:0,tilt:0};
const centers=new Float32Array(BOX_COUNT*3),halves=new Float32Array(BOX_COUNT*3);
const echoPose=new Float32Array(REFLECTIONS.flatMap(r=>[...r.offset,r.scale,r.strength]));
const echoMirror=new Float32Array(REFLECTIONS.flatMap(r=>r.mirror));
const echoFade=new Float32Array(REFLECTIONS.flatMap(r=>r.fade));
const echoAspect=new Float32Array(REFLECTIONS.map(r=>r.aspect));
const rgb=values=>'rgb('+values.map(v=>Math.round(v*255)).join(',')+')';
const hash=(x,y)=>{const n=Math.sin(x*127.1+y*311.7)*43758.5453;return n-Math.floor(n);};
function makeCells(pitch){
  const cells=[],[cx,cy]=layout.center,firstRow=Math.ceil((layout.top-cy)/pitch);
  for(let row=firstRow,y=cy+row*pitch;y<layout.bottom;row++,y=cy+row*pitch){
    const offset=row%2?.75:.25,firstCol=Math.ceil((layout.left-cx)/pitch-offset);
    for(let col=firstCol,x=cx+(col+offset)*pitch;x<layout.right;col++,x=cx+(col+offset)*pitch)cells.push(x,y);
  }
  return new Float32Array(cells);
}

function makeAtlas(color='#fff'){
  const image=document.createElement('canvas');image.width=1024;image.height=64;
  const ctx=image.getContext('2d');ctx.fillStyle=color;ctx.strokeStyle=color;
  for(let kind=0;kind<16;kind++){
    ctx.save();ctx.translate(kind*64+32,32);ctx.lineWidth=7;ctx.lineCap='round';ctx.lineJoin='round';
    if(kind===0||kind===8||kind===13){ctx.beginPath();ctx.arc(0,0,22,0,Math.PI*2);kind===0?ctx.fill():ctx.stroke();if(kind===13){ctx.beginPath();ctx.arc(0,0,6,0,Math.PI*2);ctx.fill();}}
    if(kind===1){ctx.beginPath();ctx.moveTo(0,22);ctx.bezierCurveTo(-36,-1,-19,-31,0,-12);ctx.bezierCurveTo(19,-31,36,-1,0,22);ctx.fill();}
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
uniform vec3 u_light,u_centers[12],u_halves[12],u_boundsCenter,u_boundsHalf;
uniform vec4 u_echoPose[3],u_echoFade[3],u_region;
uniform vec3 u_echoMirror[3];
uniform float u_echoAspect[3];
uniform float u_time,u_reveal,u_flash,u_ratio,u_unit,u_turn,u_tilt,u_pointerStrength,u_aa,u_footprint;
varying float v_energy,v_glyph,v_tint,v_reveal;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
vec3 camera(vec3 p){float c=cos(u_turn),s=sin(u_turn),ct=cos(u_tilt),st=sin(u_tilt);vec3 q=vec3(p.x*c-p.z*s,p.y,p.x*s+p.z*c);return vec3(q.x,q.y*ct-q.z*st,q.y*st+q.z*ct);}
vec2 interval(vec3 o,vec3 d,vec3 h){
  vec3 safe=mix(vec3(.00001),d,step(vec3(.00001),abs(d))),inv=1./safe;
  vec3 a=(-h-o)*inv,b=(h-o)*inv,lo=min(a,b),hi=max(a,b);
  return vec2(max(lo.x,max(lo.y,lo.z)),min(hi.x,min(hi.y,hi.z)));
}
vec3 trace(vec2 local,vec3 mirror,bool detailed){
  vec3 origin=camera(vec3(local.x/1.7320508,-local.y,-local.x/1.7320508)+8.)*mirror;
  vec3 direction=camera(vec3(-.57735027))*mirror;
  float nearest=1000.,energy=0.,rim=0.;vec3 surface=vec3(0.),normal=vec3(0.);
  for(int i=0;i<12;i++){
    vec3 h=u_halves[i];if(min(h.x,min(h.y,h.z))<.001)continue;
    vec3 o=origin-u_centers[i];vec2 range=interval(o,direction,h);
    float entry=range.x,exit=range.y;
    if(entry<=exit+u_aa&&exit>0.&&entry<nearest){
      nearest=entry;vec3 p=o+direction*entry,margin=max(vec3(0.),h-abs(p)),distance=abs(abs(p)-h);
      float second=min(max(margin.x,margin.y),max(min(margin.x,margin.y),margin.z));
      rim=exp(-pow(second/.095,2.));
      normal=(distance.y<distance.x&&distance.y<distance.z?vec3(0.,sign(p.y),0.):(distance.x<distance.z?vec3(sign(p.x),0.,0.):vec3(0.,0.,sign(p.z))))*mirror;
      surface=(origin+direction*entry)*mirror;
      float diffuse=max(0.,dot(normal,u_light)),band=pow(.5+.5*sin(dot(surface,vec3(2.4,2.8,-1.4))-u_time*1.45),3.);
      energy=(.17+diffuse*.32+rim*.2+band*(.2+diffuse*.25+rim*.18))*(1.-smoothstep(-u_aa,u_aa,entry-exit));
    }
  }
  if(detailed&&energy>0.){
    vec3 start=(surface+normal*.015)*mirror,light=u_light*mirror;float shade=1.;
    for(int i=0;i<12;i++){
      vec3 h=u_halves[i];if(min(h.x,min(h.y,h.z))<.001)continue;
      vec2 hit=interval(start-u_centers[i],light,h);
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
float rearVisibility(vec2 local){
  vec3 origin=camera(vec3(local.x/1.7320508,-local.y,-local.x/1.7320508)+8.);
  vec2 hit=interval(origin-u_boundsCenter,camera(vec3(-.57735027)),u_boundsHalf);
  return smoothstep(-u_aa*2.,u_aa*2.,hit.x-hit.y);
}
void main(){
  vec2 p=a_cell,local=(p-u_center)/u_unit;vec3 core=trace(local,vec3(1.),true);
  vec2 cell=floor(local/(6.4/95.)+.01);
  float seed=hash(cell+vec2(17.,53.)),grain=.68+.42*hash(cell+7.);
  float echoes=0.,echoReveal=0.,visibility=rearVisibility(local);
  for(int j=0;j<3;j++){
    vec4 pose=u_echoPose[j];vec2 q=(local-pose.xy)/vec2(pose.z,pose.z*u_echoAspect[j]);vec3 reflected=trace(q,u_echoMirror[j],false);
    vec4 fade=u_echoFade[j];
    float fog=exp(-pow(length(q)/2.9,4.)*.35)*smoothstep(fade.z,fade.w,dot(q,fade.xy));
    float energy=reflected.x*pose.w*visibility*fog;
    if(energy>echoes){echoes=energy;echoReveal=reveal(q,seed,reflected.y);}
  }
  float spark=step(.94,hash(cell+vec2(23.,47.)))*.18*smoothstep(.4,.75,core.x);
  float light=core.x*grain+spark,flare=u_flash*.8*smoothstep(.48,.85,light);
  float lamp=exp(-dot(p-u_pointer,p-u_pointer)/19000.)*u_pointerStrength;
  vec2 ellipse=local/vec2(3.5,3.15);
  float envelope=exp(-pow(length(ellipse),4.)*.32);
  float edge=smoothstep(u_region.x,u_region.x+u_unit*.35,p.x)*(1.-smoothstep(u_region.z-u_unit*.35,u_region.z,p.x));
  edge*=smoothstep(u_region.y,u_region.y+u_unit*.3,p.y)*(1.-smoothstep(u_region.w-u_unit*.35,u_region.w,p.y));
  v_energy=max(light+flare+lamp*.035*core.z,echoes*grain)*envelope*edge;
  v_tint=core.z;
  v_reveal=core.z>.5?reveal(local,seed,core.y):echoReveal;
  float choice=floor(hash(cell+vec2(83.,19.))*24.);
  v_glyph=choice<16.?choice:(choice<19.?0.:(choice<21.?1.:(choice<23.?2.:4.)));
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
  vec3 color=mix(vec3(.36,.41,.32),ink,v_tint);
  color=mix(vec3(.5,.55,.46),color,smoothstep(.94,1.03,u_reveal));
  vec2 uv=(gl_PointCoord-.5)*(u_footprint/u_glyphSize)+.5;
  float inside=step(0.,uv.x)*step(uv.x,1.)*step(0.,uv.y)*step(uv.y,1.);
  float mask=texture2D(u_atlas,vec2((v_glyph+clamp(uv.x,0.,1.))/16.,clamp(uv.y,0.,1.))).a*inside;
  float opacity=mix(pow(min(v_energy,1.),.8),.48+.48*sqrt(min(v_energy,1.)),v_tint);
  float halo=exp(-dot(gl_PointCoord-.5,gl_PointCoord-.5)*12.)*pow(v_energy,2.)*.065*v_tint;
  gl_FragColor=vec4(color,min(.98,mask*opacity+halo)*v_reveal);
}`;
function makeWebGL(){
  const gl=canvas.getContext('webgl',{alpha:false,antialias:false,powerPreference:'low-power'});if(!gl)return null;
  const compile=(type,source)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;};
  const program=gl.createProgram(),shaders=[compile(gl.VERTEX_SHADER,vertex),compile(gl.FRAGMENT_SHADER,fragment)];
  shaders.forEach(s=>gl.attachShader(program,s));gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);shaders.forEach(s=>gl.deleteShader(s));
  const names=['resolution','center','pointer','light','centers[0]','halves[0]','boundsCenter','boundsHalf','echoPose[0]','echoMirror[0]','echoFade[0]','echoAspect[0]','region','time','reveal','flash','ratio','unit','turn','tilt','pointerStrength','aa','footprint','glyphSize','base','shadow','highlight','atlas'];
  const locations=Object.fromEntries(names.map(name=>[name,gl.getUniformLocation(program,'u_'+name)]));
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  const attribute=gl.getAttribLocation(program,'a_cell');gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,0,0);
  const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,makeAtlas());gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.uniform1i(locations.atlas,0);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);
  let count=0;
  return {type:'WebGL',resize(){
    const cells=makeCells(layout.pitch);
    count=cells.length/2;canvas.dataset.glyphCount=String(count);canvas.dataset.glyphPitch=layout.pitch.toFixed(3);
    gl.bufferData(gl.ARRAY_BUFFER,cells,gl.STATIC_DRAW);gl.viewport(0,0,canvas.width,canvas.height);
  },draw(scene){
    scene.boxes.forEach((box,i)=>{centers.set(box.center,i*3);halves.set(box.half,i*3);});
    gl.clearColor(4/255,8/255,4/255,1);gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(locations.resolution,width,height);gl.uniform2fv(locations.center,layout.center);gl.uniform2f(locations.pointer,pointer.x,pointer.y);
    gl.uniform3fv(locations.light,lightDirection(time));
    gl.uniform3fv(locations['centers[0]'],centers);gl.uniform3fv(locations['halves[0]'],halves);gl.uniform3fv(locations.boundsCenter,scene.bounds.center);gl.uniform3fv(locations.boundsHalf,scene.bounds.half);gl.uniform4fv(locations['echoPose[0]'],echoPose);gl.uniform3fv(locations['echoMirror[0]'],echoMirror);gl.uniform4fv(locations['echoFade[0]'],echoFade);gl.uniform1fv(locations['echoAspect[0]'],echoAspect);gl.uniform4f(locations.region,layout.left,layout.top,layout.right,layout.bottom);
    for(const key of ['base','shadow','highlight'])gl.uniform3fv(locations[key],ramp[key]);
    const values={time,reveal:bootSkipped?BOOT:time,flash:Math.max(scene.state.flash,bootSkipped?0:startupFlare(time)),ratio,unit:layout.unit,turn:scene.turn,tilt:scene.tilt,pointerStrength:pointer.strength,aa:layout.pitch/layout.unit*.45,footprint:layout.footprint,glyphSize:layout.glyphSize};
    for(const [key,value] of Object.entries(values))gl.uniform1f(locations[key],value);
    gl.drawArrays(gl.POINTS,0,count);
  }};
}
function makeFallback(){
  const ctx=canvas.getContext('2d');if(!ctx)return {type:'unavailable',resize(){},draw(){}};
  let signature='',atlases=[],echoAtlas,cells=new Float32Array();
  return {type:'Canvas 2D',resize(){cells=makeCells(layout.pitch*7.6/6.4);},draw(scene){
    if(signature!==color){signature=color;atlases=Array.from({length:12},(_,i)=>{const t=i/11,a=t<.65?ramp.shadow:ramp.base,b=t<.65?ramp.base:ramp.highlight,f=t<.65?t/.65:(t-.65)/.35;return makeAtlas(rgb(a.map((v,k)=>v+(b[k]-v)*f)));});echoAtlas=makeAtlas('#5c6952');}
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.globalAlpha=1;ctx.fillStyle='#040804';ctx.fillRect(0,0,width,height);
    const hull={...scene.bounds,rotation:[0,0,0,1],kind:0};
    for(let i=0;i<cells.length;i+=2){
      const x=cells[i],y=cells[i+1],local=[(x-layout.center[0])/layout.unit,(y-layout.center[1])/layout.unit],cell=local.map(v=>Math.floor(v/(6.4/95)+.01)),seed=hash(cell[0]+17,cell[1]+53);
      let hit=traceBoxes(...local,scene.boxes,scene.turn,scene.tilt,time),energy=0,main=!!hit,echo=0,revealRadius=Math.hypot(...local);
      if(hit){const spark=hash(cell[0]+23,cell[1]+47)>.94?.18*smooth(.4,.75,hit.light):0;energy=highlightFlare(hit.light*(.68+.42*hash(cell[0]+7,cell[1]+7))+spark,Math.max(scene.state.flash,bootSkipped?0:startupFlare(time)));}
      if(!traceBoxes(...local,[hull],scene.turn,scene.tilt))for(const r of REFLECTIONS){
        const q=local.map((v,k)=>(v-r.offset[k])/(r.scale*(k?r.aspect:1))),h=traceBoxes(...q,scene.boxes,scene.turn,scene.tilt,time,r.mirror);
        const fog=Math.exp(-Math.pow(Math.hypot(...q)/2.9,4)*.35)*smooth(r.fade[2],r.fade[3],q[0]*r.fade[0]+q[1]*r.fade[1]);
        if(h&&h.light*r.strength*fog>echo){echo=h.light*r.strength*fog;if(!main){hit=h;revealRadius=Math.hypot(...q);}}
      }
      if(!hit)continue;energy=Math.max(energy,echo);
      const envelope=Math.exp(-Math.pow(Math.hypot(local[0]/3.5,local[1]/3.15),4)*.32);
      const edge=smooth(layout.left,layout.left+layout.unit*.35,x)*(1-smooth(layout.right-layout.unit*.35,layout.right,x))*smooth(layout.top,layout.top+layout.unit*.3,y)*(1-smooth(layout.bottom-layout.unit*.35,layout.bottom,y));
      const reveal=revealAt(bootSkipped?BOOT:time,seed,hit.rim,revealRadius);
      ctx.globalAlpha=Math.min(.97,main?.48+.48*Math.sqrt(Math.min(1,energy)):energy**.8)*envelope*edge*reveal;
      const choice=Math.floor(hash(cell[0]+83,cell[1]+19)*24),kind=choice<16?choice:choice<19?0:choice<21?1:choice<23?2:4,atlas=main?atlases[Math.min(11,Math.round(energy*11))]:echoAtlas,size=layout.glyphSize;
      ctx.drawImage(atlas,kind*64,0,64,64,x-size/2,y-size/2,size,size);
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
  const scene=sceneAtClock();scene.turn=pointer.turn;scene.tilt=pointer.tilt;scene.bounds=sceneBounds(scene.boxes);renderer.draw(scene);frames++;
  formName.textContent=FORM_LABELS[scene.state.focus];
  Object.assign(canvas.dataset,{form:scene.state.focus,time:time.toFixed(3),frame:String(frames),transitioning:String(scene.state.transitioning),phase:scene.state.phase,blend:scene.state.blend.toFixed(3),flash:scene.state.flash.toFixed(3),reveal:(bootSkipped?BOOT:Math.min(BOOT,time)).toFixed(3),turn:scene.turn.toFixed(4),tilt:scene.tilt.toFixed(4),echoCount:'3',unit:layout.unit.toFixed(2)});
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
  layout=layoutFor(width,height);
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
