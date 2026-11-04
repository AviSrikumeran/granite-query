import {BOOT,traceBoxes,smooth,rotate} from './geometry.mjs?v=claw-20261103-1';
import {KEY,FILL,mineralColors,TIER_GLYPHS,materialColors,materialProfile,ghostOffsets,sideClearance,ghostWeight,introCell,litSurface,softenedNormal,occlusionAt,viewDirection} from './material.mjs?v=claw-20261103-1';

// One scene Ã¢â€ â€™ luminance tiers Ã¢â€ â€™ glyphs Ã¢â€ â€™ camera-projected peripheral views Ã¢â€ â€™
// highlight bloom. Peripheral samples share the finished scene, not a new trace.
const vertex=`
precision highp float;
attribute vec2 a_cell;
uniform vec2 u_resolution,u_center;
uniform vec4 u_centers[40],u_rotations[40];
uniform vec3 u_halves[40],u_colors[16],u_mineralColors[16],u_key,u_fill;
uniform float u_unit,u_turn,u_tilt,u_reveal,u_flash,u_hover,u_ratio,u_footprint,u_aa;
varying vec3 v_color;
varying float v_glyph,v_reveal,v_size;
float noise(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
vec3 camera(vec3 p){float c=cos(u_turn),s=sin(u_turn),ct=cos(u_tilt),st=sin(u_tilt);vec3 q=vec3(p.x*c-p.z*s,p.y,p.x*s+p.z*c);return vec3(q.x,q.y*ct-q.z*st,q.y*st+q.z*ct);}
vec3 qRotate(vec4 q,vec3 v){return v+2.*cross(q.xyz,cross(q.xyz,v)+q.w*v);}
vec2 interval(vec3 o,vec3 d,vec3 h){vec3 inv=1./d,a=(-h-o)*inv,b=(h-o)*inv,lo=min(a,b),hi=max(a,b);return vec2(max(lo.x,max(lo.y,lo.z)),min(hi.x,min(hi.y,hi.z)));}
float distanceToScene(vec3 p){
  float distance=100.;
  for(int i=0;i<40;i++){vec3 h=u_halves[i];if(min(h.x,min(h.y,h.z))<.001)continue;vec4 r=u_rotations[i];vec3 q=abs(qRotate(vec4(-r.xyz,r.w),p-u_centers[i].xyz))-h;distance=min(distance,length(max(q,0.))+min(max(q.x,max(q.y,q.z)),0.));}
  return distance;
}
float glyphFor(float t){
  if(t<.5)return 4.;if(t<1.5)return 2.;if(t<2.5)return 6.;if(t<3.5)return 4.;
  if(t<4.5)return 2.;if(t<5.5)return 8.;if(t<6.5)return 9.;if(t<7.5)return 8.;
  if(t<8.5)return 9.;if(t<9.5)return 4.;if(t<10.5)return 2.;if(t<11.5)return 6.;
  if(t<12.5)return 4.;if(t<13.5)return 2.;if(t<14.5)return 8.;return 9.;
}
void main(){
  vec2 local=(a_cell-u_center)/u_unit,cell=floor(local/(6.4/95.)+.01);
  float seed=noise(cell+vec2(17.,53.)),nearest=1000.,coverage=0.,materialPower=1.;
  vec3 origin=camera(vec3(local.x/1.7320508,-local.y,-local.x/1.7320508)+8.);
  vec3 ray=camera(vec3(-.57735027)),normal=vec3(0.),point=vec3(0.);
  for(int i=0;i<40;i++){
    vec3 h=u_halves[i];if(min(h.x,min(h.y,h.z))<.001)continue;
    vec4 rotation=u_rotations[i],inverse=vec4(-rotation.xyz,rotation.w);
    vec3 o=qRotate(inverse,origin-u_centers[i].xyz),d=qRotate(inverse,ray);vec2 hit=interval(o,d,h);
    if(hit.x<=hit.y+u_aa&&hit.y>0.&&hit.x<nearest){
      nearest=hit.x;materialPower=u_centers[i].w;vec3 p=o+d*hit.x;
      normal=qRotate(rotation,normalize(sign(p)*(1.-smoothstep(vec3(0.),vec3(.075),max(h-abs(p),0.)))));
      point=origin+ray*hit.x;coverage=1.-smoothstep(-u_aa,u_aa,hit.x-hit.y);
    }
  }
  if(nearest>999.){v_color=vec3(0.);v_glyph=0.;v_reveal=0.;v_size=1.;gl_Position=vec4(2.,2.,0.,1.);gl_PointSize=1.;return;}
  float ao=0.,weight=1.;
  for(int i=1;i<=4;i++){float d=float(i)*.09;ao+=(d-distanceToScene(point+normal*d))*weight;weight*=.7;}
  ao=clamp(1.-ao*2.55,0.,1.);
  float key=max(dot(normal,u_key),0.),fill=max(dot(normal,u_fill),0.);
  float spec=pow(max(dot(normal,normalize(u_key-ray)),0.),20.);
  float rim=pow(1.-max(dot(normal,-ray),0.),2.5);
  float light=(.33+key*1.11+fill*.79)*ao+rim*.83+u_hover*.25*(.2+rim);
  vec3 shaded=vec3(0.,.9,.46)*light+vec3(.78,1.,.86)*spec*.95;
  shaded=shaded/(1.+shaded);
  float luminance=clamp(dot(shaded,vec3(.299,.587,.114))*1.6,0.,1.);
  float tier=clamp(floor(luminance*16.+(noise(cell+7.)-.5)*.5),0.,15.);
  vec3 color=vec3(0.);for(int i=0;i<16;i++)if(abs(tier-float(i))<.1)color=mix(u_mineralColors[i],u_colors[i],clamp(materialPower,0.,1.))*max(1.,materialPower);
  float variant=noise(cell+vec2(83.,19.));
  v_glyph=glyphFor(variant<.34?floor(noise(cell+91.)*16.):tier);
  float start=clamp(length(local)/2.4+seed*.18,0.,1.)/1.18*.75;
  float reveal=clamp((smoothstep(.92,1.35,u_reveal)*1.1-start)/.35,0.,1.);
  if(u_reveal>=1.55)reveal=1.;
  float sparse=step(.982,seed)*.4;
  v_reveal=max(smoothstep(0.,.7,reveal),sparse)*coverage;
  v_size=mix(.1,1.,reveal*(2.-reveal));if(reveal<.001)v_size=.8;
  float ignition=1.+2.2*4.*reveal*(1.-reveal);
  float flare=1.+u_flash*1.25*smoothstep(.43,.76,luminance);
  v_color=color*ignition*flare;
  if(u_reveal<.93)v_color=vec3(.37,.42,.35);
  gl_Position=vec4(a_cell.x/u_resolution.x*2.-1.,1.-a_cell.y/u_resolution.y*2.,0.,1.);
  gl_PointSize=u_footprint*u_ratio;
}`;
const fragment=`
precision highp float;
uniform sampler2D u_atlas;
uniform float u_footprint,u_glyphSize;
varying vec3 v_color;
varying float v_glyph,v_reveal,v_size;
void main(){
  if(v_reveal<.002)discard;
  vec2 uv=(gl_PointCoord-.5)*u_footprint/(u_glyphSize*v_size)+.5;
  if(min(uv.x,uv.y)<0.||max(uv.x,uv.y)>1.)discard;
  float mask=texture2D(u_atlas,vec2((v_glyph+uv.x)/16.,uv.y)).a*v_reveal;
  gl_FragColor=vec4(v_color*mask,mask);
}`;
const quadVertex=`attribute vec2 a_position;varying vec2 v_uv;void main(){v_uv=a_position*.5+.5;gl_Position=vec4(a_position,0.,1.);}`;
const blurFragment=`
precision highp float;
uniform sampler2D u_image;
uniform vec2 u_pixel,u_range;
uniform float u_extract;
varying vec2 v_uv;
void main(){
  vec3 c=texture2D(u_image,v_uv).rgb*4.;
  c+=texture2D(u_image,v_uv+u_pixel).rgb+texture2D(u_image,v_uv-u_pixel).rgb;
  c+=texture2D(u_image,v_uv+vec2(u_pixel.x,-u_pixel.y)).rgb+texture2D(u_image,v_uv+vec2(-u_pixel.x,u_pixel.y)).rgb;
  c/=8.;
  float l=dot(c,vec3(.2126,.7152,.0722));
  c*=mix(1.,smoothstep(u_range.x,u_range.y,l)*1.2,u_extract);
  gl_FragColor=vec4(c,1.);
}`;
const compositeFragment=`
precision highp float;
uniform sampler2D u_image,u_bloom;
uniform vec2 u_resolution,u_center,u_offsets[3];
uniform vec4 u_region;
uniform vec3 u_background,u_ghostTint,u_energyA,u_energyB;
uniform float u_bloomStrength,u_rolloff;
uniform float u_unit,u_time,u_reveal,u_ghostStrength;
varying vec2 v_uv;
vec4 sampleScene(vec2 uv){if(min(uv.x,uv.y)<0.||max(uv.x,uv.y)>1.)return vec4(0.);return texture2D(u_image,uv);}
void main(){
  vec4 main=sampleScene(v_uv);
  vec2 pixel=vec2(v_uv.x,1.-v_uv.y)*u_resolution,local=(pixel-u_center)/u_unit;
  float fade=clamp(1.-(length(local/4.05)-.49)/.68,0.,1.);
  float weight=.51*pow(fade,2.4)*u_ghostStrength;
  vec3 ghosts=vec3(0.);
  for(int i=0;i<3;i++){
    vec2 offset=u_offsets[i]*u_unit/u_resolution;offset.y=-offset.y;
    vec4 source=sampleScene(v_uv-offset);
    float l=dot(source.rgb,vec3(.2126,.7152,.0722));
    ghosts+=u_ghostTint*l*weight;
  }
  vec3 bloom=texture2D(u_bloom,v_uv).rgb*u_bloomStrength;
  vec3 color=main.rgb+ghosts*(1.-min(main.a,1.))+bloom;
  // Smooth, sparse energy behind the marks, not a halo around every cell.
  vec3 energy=vec3(0.);
  for(int i=0;i<8;i++){
    float n=float(i),phase=n*2.39996+u_time*(.11+mod(n,3.)*.025);
    vec2 center=vec2(cos(phase)*(.35+mod(n,4.)*.32),sin(phase*1.17)*(.55+mod(n+1.,3.)*.28));
    vec2 p=local-center;
    float glow=exp(-dot(p,p)/(i==0?.5:.18))*(.45+.55*pow(.5+.5*sin(u_time*1.2+n),2.));
    energy+=mix(u_energyA,u_energyB,mod(n,2.))*glow;
  }
  energy*=smoothstep(.94,1.2,u_reveal);
  color+=energy;
  float peak=max(color.r,max(color.g,color.b)),knee=u_rolloff;
  float rolled=peak<=knee?peak:knee+(1.-knee)*(1.-exp(-(peak-knee)/(1.-knee)));
  color*=rolled/max(peak,.0001);
  float envelope=1.-smoothstep(3.55,4.1,length(local/vec2(1.05,1.)));
  float edge=smoothstep(u_region.y,u_region.y+u_unit*.4,pixel.y)*(1.-smoothstep(u_region.w-u_unit*.4,u_region.w,pixel.y));
  edge*=smoothstep(u_region.x,u_region.x+u_unit*.4,pixel.x)*(1.-smoothstep(u_region.z-u_unit*.4,u_region.z,pixel.x));
  gl_FragColor=vec4(u_background+color*envelope*edge,1.);
}`;

export function makeGPU(canvas,{get,makeCells,makeAtlas}){
  // Keep the last composed frame available while paused, including captures
  // after a focus/scroll repaint. All intermediate targets are still reused.
  const gl=canvas.getContext('webgl',{alpha:false,antialias:false,preserveDrawingBuffer:true,powerPreference:'low-power'});if(!gl)return null;
  function program(v,f,names){
    const p=gl.createProgram();
    for(const [type,source] of [[gl.VERTEX_SHADER,v],[gl.FRAGMENT_SHADER,f]]){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));gl.attachShader(p,s);gl.deleteShader(s);}
    gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));
    return {p,u:Object.fromEntries(names.map(n=>[n,gl.getUniformLocation(p,'u_'+n)]))};
  }
  const main=program(vertex,fragment,['resolution','center','unit','turn','tilt','reveal','flash','hover','ratio','footprint','glyphSize','centers[0]','halves[0]','rotations[0]','colors[0]','mineralColors[0]','key','fill','aa','atlas']);
  const blur=program(quadVertex,blurFragment,['image','pixel','extract','range']);
  const composite=program(quadVertex,compositeFragment,['image','bloom','resolution','center','offsets[0]','unit','time','reveal','region','ghostStrength','background','ghostTint','energyA','energyB','bloomStrength','rolloff']);
  const cellsBuffer=gl.createBuffer(),quadBuffer=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,quadBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
  const atlas=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,atlas);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,makeAtlas());gl.generateMipmap(gl.TEXTURE_2D);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  const centers=new Float32Array(160),halves=new Float32Array(120),rotations=new Float32Array(160);let target,mips=[],count=0;
  const bind=(texture,slot=0)=>{gl.activeTexture(gl.TEXTURE0+slot);gl.bindTexture(gl.TEXTURE_2D,texture);};
  function targetAt(w,h){
    const texture=gl.createTexture();bind(texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,null);for(const k of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,k,gl.LINEAR);for(const k of [gl.TEXTURE_WRAP_S,gl.TEXTURE_WRAP_T])gl.texParameteri(gl.TEXTURE_2D,k,gl.CLAMP_TO_EDGE);
    const f=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,f);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,texture,0);if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw Error('Incomplete field framebuffer');return {texture,f,w,h};
  }
  function use(p,buffer,name,size){gl.useProgram(p.p);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);const a=gl.getAttribLocation(p.p,name);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,size,gl.FLOAT,false,0,0);}
  function screen(t){gl.bindFramebuffer(gl.FRAMEBUFFER,t?.f??null);gl.viewport(0,0,t?.w??canvas.width,t?.h??canvas.height);}
  function blurTo(from,to,extract){screen(to);use(blur,quadBuffer,'a_position',2);bind(from.texture);gl.uniform1i(blur.u.image,0);gl.uniform2f(blur.u.pixel,1.65/from.w,1.65/from.h);gl.uniform1f(blur.u.extract,extract);gl.drawArrays(gl.TRIANGLES,0,6);}
  return {type:'WebGL',resize(){
    const {layout}=get(),cells=makeCells(layout.pitch);count=cells.length/2;
    canvas.dataset.glyphCount=String(count);canvas.dataset.glyphPitch=layout.pitch.toFixed(3);canvas.dataset.pipeline='scene-glyphs-ghosts-bloom';canvas.dataset.bloomLevels='6';
    gl.bindBuffer(gl.ARRAY_BUFFER,cellsBuffer);gl.bufferData(gl.ARRAY_BUFFER,cells,gl.STATIC_DRAW);
    for(const t of [target,...mips])if(t){gl.deleteTexture(t.texture);gl.deleteFramebuffer(t.f);}
    target=targetAt(canvas.width,canvas.height);mips=Array.from({length:6},(_,i)=>targetAt(Math.max(1,Math.floor(canvas.width/2**(i+1))),Math.max(1,Math.floor(canvas.height/2**(i+1)))));
  },draw(scene){
    const {width,height,layout,ratio,time,pointer,bootSkipped,color,ghosts=true,material='green'}=get(),reveal=bootSkipped?BOOT:time;
    scene.boxes.forEach((b,i)=>{centers.set([...b.center,b.emission??1],i*4);halves.set(b.half,i*3);rotations.set(b.rotation,i*4);});
    gl.disable(gl.BLEND);screen(target);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);use(main,cellsBuffer,'a_cell',2);bind(atlas);
    const u=main.u;gl.uniform1i(u.atlas,0);gl.uniform2f(u.resolution,width,height);gl.uniform2fv(u.center,layout.center);gl.uniform4fv(u['centers[0]'],centers);gl.uniform3fv(u['halves[0]'],halves);gl.uniform4fv(u['rotations[0]'],rotations);gl.uniform3fv(u['colors[0]'],materialColors(material));gl.uniform3fv(u['mineralColors[0]'],mineralColors());gl.uniform3fv(u.key,KEY);gl.uniform3fv(u.fill,FILL);
    for(const [k,v] of Object.entries({unit:layout.unit,turn:scene.turn,tilt:scene.tilt,reveal,flash:scene.state.flash,hover:pointer.strength,ratio,footprint:layout.footprint,glyphSize:layout.glyphSize,aa:layout.pitch/layout.unit*.25}))gl.uniform1f(u[k],v);
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.drawArrays(gl.POINTS,0,count);gl.disable(gl.BLEND);
    const profile=materialProfile(material);gl.useProgram(blur.p);gl.uniform2fv(blur.u.range,profile.bloomRange);
    for(let i=0;i<mips.length;i++)blurTo(i?mips[i-1]:target,mips[i],i?0:1);
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);for(let i=mips.length-1;i>0;i--)blurTo(mips[i],mips[i-1],0);gl.disable(gl.BLEND);
    screen(null);use(composite,quadBuffer,'a_position',2);bind(target.texture);bind(mips[0].texture,1);
    const c=composite.u;gl.uniform1i(c.image,0);gl.uniform1i(c.bloom,1);gl.uniform2f(c.resolution,width,height);gl.uniform2fv(c.center,layout.center);gl.uniform2fv(c['offsets[0]'],ghostOffsets(scene.turn,scene.tilt,sideClearance(scene.state)).flat());gl.uniform4f(c.region,layout.left,layout.top,layout.right,layout.bottom);gl.uniform1f(c.unit,layout.unit);gl.uniform1f(c.time,time);gl.uniform1f(c.reveal,reveal);gl.uniform1f(c.ghostStrength,ghosts?1:0);gl.uniform3fv(c.background,profile.background);gl.uniform3fv(c.ghostTint,profile.ghost);gl.uniform3fv(c.energyA,profile.energyA);gl.uniform3fv(c.energyB,profile.energyB);gl.uniform1f(c.bloomStrength,profile.bloom);gl.uniform1f(c.rolloff,profile.rolloff);gl.drawArrays(gl.TRIANGLES,0,6);
  }};
}

export function makeCPU(canvas,{get,makeCells,makeAtlas,hash}){
  const ctx=canvas.getContext('2d');if(!ctx)return {type:'unavailable',resize(){},draw(){}};
  const layer=document.createElement('canvas'),ghost=document.createElement('canvas'),fog=document.createElement('canvas');
  const ink=layer.getContext('2d'),gray=ghost.getContext('2d'),haze=fog.getContext('2d');
  let cells,signature='',atlases=[],mineralAtlases=[],white;
  const makeWhite=()=>white??=makeAtlas();
  return {type:'Canvas 2D',resize(){const {layout}=get();cells=makeCells(layout.pitch*1.25);for(const c of [layer,ghost,fog]){c.width=canvas.width;c.height=canvas.height;}},draw(scene){
    const {layout,width,height,ratio,time,bootSkipped,color,pointer,ghosts=true,material='green'}=get(),revealTime=bootSkipped?BOOT:time;
    const profile=materialProfile(material),colors=materialColors(material),view=viewDirection(scene.turn,scene.tilt);
    if(signature!==material){signature=material;atlases=Array.from({length:16},(_,i)=>makeAtlas('rgb('+colors.slice(i*3,i*3+3).map(v=>Math.round(v*255)).join(',')+')'));mineralAtlases=Array.from({length:16},(_,i)=>makeAtlas('rgb('+mineralColors().slice(i*3,i*3+3).map(v=>Math.round(v*255)).join(',')+')'));}
    for(const c of [ink,gray,haze,ctx]){c.setTransform(ratio,0,0,ratio,0,0);c.clearRect(0,0,width,height);}
    for(let i=0;i<cells.length;i+=2){
      const x=cells[i],y=cells[i+1],local=[(x-layout.center[0])/layout.unit,(y-layout.center[1])/layout.unit];
      const hit=traceBoxes(...local,scene.boxes,scene.turn,scene.tilt);if(!hit)continue;
      const b=scene.boxes[hit.boxIndex];if(!b)continue;
      const inverse=[-b.rotation[0],-b.rotation[1],-b.rotation[2],b.rotation[3]],localPoint=rotate(inverse,hit.world.map((v,k)=>v-b.center[k]));
      const normal=rotate(b.rotation,softenedNormal(localPoint,b)),light=litSurface(normal,hit.world,view,occlusionAt(hit.world,normal,scene.boxes),pointer.strength);
      const cell=local.map(v=>Math.floor(v/(6.4/95)+.01)),seed=hash(cell[0]+17,cell[1]+53);
      const intro=introCell(revealTime,Math.hypot(...local),seed),sparse=seed>.982?.4:0,alpha=Math.max(intro.alpha,sparse);
      if(alpha<.002)continue;
      const tier=Math.max(0,Math.min(15,Math.floor(light*16+(hash(cell[0]+7,cell[1]+7)-.5)*.5)));
      const kind=TIER_GLYPHS[hash(cell[0]+83,cell[1]+19)<.34?Math.floor(hash(cell[0]+91,cell[1]+91)*16):tier],size=layout.glyphSize*(intro.alpha?intro.scale:.8);
      ink.globalAlpha=alpha;ink.drawImage((b.emission??1)<.5?mineralAtlases[tier]:atlases[tier],kind*64,0,64,64,x-size/2,y-size/2,size,size);
      gray.globalAlpha=alpha*colors.slice(tier*3,tier*3+3).reduce((s,v,k)=>s+v*[.2126,.7152,.0722][k],0);gray.drawImage(makeWhite(),kind*64,0,64,64,x-size/2,y-size/2,size,size);
    }
    gray.globalCompositeOperation='source-in';gray.globalAlpha=1;gray.fillStyle='rgb('+profile.ghost.map(v=>Math.round(v*255)).join(',')+')';gray.fillRect(0,0,width,height);gray.globalCompositeOperation='source-over';
    haze.globalAlpha=1;for(const offset of ghostOffsets(scene.turn,scene.tilt,sideClearance(scene.state)))haze.drawImage(ghost,offset[0]*layout.unit,offset[1]*layout.unit,width,height);
    haze.globalCompositeOperation='destination-in';
    const gradient=haze.createRadialGradient(...layout.center,layout.unit*1.8,...layout.center,layout.unit*4.7);gradient.addColorStop(0,'rgba(255,255,255,.51)');gradient.addColorStop(.6,'rgba(255,255,255,.12)');gradient.addColorStop(1,'transparent');haze.fillStyle=gradient;haze.fillRect(0,0,width,height);haze.globalCompositeOperation='source-over';
    ctx.fillStyle='rgb('+profile.background.map(v=>Math.round(v*255)).join(',')+')';ctx.fillRect(0,0,width,height);ctx.globalAlpha=1;
    ctx.save();ctx.beginPath();ctx.rect(layout.left,layout.top,layout.right-layout.left,layout.bottom-layout.top);ctx.clip();
    if(ghosts)ctx.drawImage(fog,0,0,width,height);ctx.drawImage(layer,0,0,width,height);
    ctx.save();ctx.globalCompositeOperation='screen';ctx.globalAlpha=.2;ctx.filter='blur('+layout.unit*.09+'px)';ctx.drawImage(layer,0,0,width,height);ctx.restore();
    ctx.restore();
  }};
}
