// GQ glyph material, derived from the preserved homepage renderer.
// Homepage-only adapter of the accepted Electric Magenta renderer.
// Study source stays unchanged; ghostDistance only adjusts the three peripheral samples.
import {BOOT,traceBoxes,smooth} from '../playground/purple/engine/geometry.mjs?v=magenta-20261103-2';
import {KEY,FILL,TIER_GLYPHS,materialColors,materialProfile,ghostOffsets,sideClearance,ghostWeight,introCell,litSurface,softenedNormal,occlusionAt,viewDirection} from '../playground/purple/engine/material.mjs?v=magenta-20261103-2';

// One scene → luminance tiers → glyphs → camera-projected peripheral views →
// highlight bloom. Peripheral samples share the finished scene, not a new trace.
const vertex=`
precision highp float;
attribute vec2 a_cell;
uniform vec2 u_resolution,u_center;
uniform vec3 u_centers[40],u_halves[40],u_colors[16],u_key,u_fill;
uniform float u_unit,u_turn,u_tilt,u_reveal,u_flash,u_hover,u_ratio,u_footprint,u_aa,u_shineTime,u_shineStrength,u_shineStyle;
varying vec3 v_color;
varying float v_glyph,v_reveal,v_size;
float noise(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
vec3 camera(vec3 p){float c=cos(u_turn),s=sin(u_turn),ct=cos(u_tilt),st=sin(u_tilt);vec3 q=vec3(p.x*c-p.z*s,p.y,p.x*s+p.z*c);return vec3(q.x,q.y*ct-q.z*st,q.y*st+q.z*ct);}
vec2 interval(vec3 o,vec3 d,vec3 h){vec3 inv=1./d,a=(-h-o)*inv,b=(h-o)*inv,lo=min(a,b),hi=max(a,b);return vec2(max(lo.x,max(lo.y,lo.z)),min(hi.x,min(hi.y,hi.z)));}

float roundedRect(vec2 p,vec2 b,float r){vec2 q=abs(p)-b+r;return min(max(q.x,q.y),0.)+length(max(q,0.))-r;}
float ring(vec2 p){return max(roundedRect(p,vec2(.91,1.12),.31),-roundedRect(p,vec2(.49,.70),.15));}
float lettering(vec2 p){
  vec2 g=p-vec2(-1.12,0.);
  float gd=ring(g);
  float mouth=roundedRect(g-vec2(.85,.375),vec2(.65,.285),.025);
  gd=max(gd,-mouth);
  float crossbar=roundedRect(g-vec2(.43,-.12),vec2(.48,.20),.035);
  gd=min(gd,crossbar);
  vec2 q=p-vec2(1.12,0.);
  float qd=ring(q);
  vec2 tail=q-vec2(.58,-.92);
  tail=mat2(.70710678,.70710678,-.70710678,.70710678)*tail;
  qd=min(qd,roundedRect(tail,vec2(.64,.19),.055));
  return min(gd,qd);
}
float distanceToScene(vec3 p){
  float d=lettering(p.xy);
  // A genuine extruded solid, with a softly bevelled perimeter.
  vec2 q=vec2(d+.085,abs(p.z)-.40);
  float solid=min(max(q.x,q.y),0.)+length(max(q,0.))-.085;
  // Two recessed construction seams keep the strokes from reading as a flat mask.
  float gSeam=max(abs(p.x+1.55)-.023,abs(p.y-.99)-.25);
  float qSeam=max(abs(p.x-1.56)-.023,abs(p.y+.99)-.25);
  float groove=min(gSeam,qSeam);
  // Keep both letter caps uninterrupted in this study.
  return solid;
}
float glyphFor(float t){
  if(t<.5)return 4.;if(t<1.5)return 2.;if(t<2.5)return 6.;if(t<3.5)return 4.;
  if(t<4.5)return 2.;if(t<5.5)return 8.;if(t<6.5)return 9.;if(t<7.5)return 8.;
  if(t<8.5)return 9.;if(t<9.5)return 4.;if(t<10.5)return 2.;if(t<11.5)return 6.;
  if(t<12.5)return 4.;if(t<13.5)return 2.;if(t<14.5)return 8.;return 9.;
}
void main(){
  vec2 local=(a_cell-u_center)/u_unit,cell=floor(local/(4.3/95.)+.01);
  float seed=noise(cell+vec2(17.,53.)),nearest=1000.,coverage=0.;
  vec3 origin=camera(vec3(local.x,-local.y,8.));
  vec3 ray=camera(vec3(0.,0.,-1.)),normal=vec3(0.),point=vec3(0.);

  float travel=4.8;
  for(int step=0;step<72;step++){
    point=origin+ray*travel;
    float d=distanceToScene(point);
    if(d<.0025){
      nearest=travel;coverage=1.;
      vec2 e=vec2(.012,0.);
      normal=normalize(vec3(distanceToScene(point+e.xyy)-distanceToScene(point-e.xyy),distanceToScene(point+e.yxy)-distanceToScene(point-e.yxy),distanceToScene(point+e.yyx)-distanceToScene(point-e.yyx)));
      break;
    }
    travel+=max(d,.003);
    if(travel>12.)break;
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
  vec3 color=vec3(0.);for(int i=0;i<16;i++)if(abs(tier-float(i))<.1)color=u_colors[i];
  float variant=noise(cell+vec2(83.,19.));
  
  float choice=floor(noise(cell+91.)*6.);
  float selected=choice<.5?4.:choice<1.5?2.:choice<2.5?13.:choice<3.5?0.:choice<4.5?8.:9.;
  v_glyph=variant<.55?selected:glyphFor(tier);
  float start=clamp(length(local)/2.4+seed*.18,0.,1.)/1.18*.75;
  float reveal=clamp((smoothstep(.92,1.35,u_reveal)*1.1-start)/.35,0.,1.);
  if(u_reveal>=1.55)reveal=1.;
  float sparse=step(.982,seed)*.4;
  v_reveal=max(smoothstep(0.,.7,reveal),sparse)*coverage;
  v_size=mix(.1,1.,reveal*(2.-reveal));if(reveal<.001)v_size=.8;
  float ignition=1.+2.2*4.*reveal*(1.-reveal);
  float flare=1.+u_flash*1.25*smoothstep(.43,.76,luminance);
  
  // RGB only: the accepted geometry, atlas cell and glyph size remain unchanged.
  float band=pow(.5+.5*cos((point.x+.28*point.y)*.95-u_shineTime*.82),6.);
  float crest=pow(band,2.);
  float drift=.5+.5*sin(point.y*1.7-point.x*.45+u_shineTime*.63);
  float surfaceWeight=.55+.45*smoothstep(.28,.72,luminance);
  float sheen=u_shineStrength*((.10+.28*band+.40*crest)*surfaceWeight+.045*drift);
  vec3 radiant=max(color,mix(color,vec3(1.,.52,1.),.24*surfaceWeight));
  vec3 illuminated=mix(radiant,vec3(1.,.96,1.),clamp(sheen,0.,.85));
  
  if(u_shineStyle>.5&&u_shineStyle<1.5){
    float pulse=pow(.5+.5*sin(u_shineTime*.90-1.2),1.6);
    float shoulder=smoothstep(.1,.8,rim);
    float breathing=(.08+.48*pulse*(.25+.75*shoulder))*u_shineStrength;
    illuminated=mix(radiant,vec3(1.,.85,1.),min(breathing,.68));
    illuminated*=.94+.17*pulse;
  }
  v_color=illuminated*ignition*flare;
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
  vec3 ink=color*envelope*edge;float alpha=clamp(max(ink.r,max(ink.g,ink.b))*2.,0.,1.);gl_FragColor=vec4(ink,alpha);
}`;

export function makeGPU(canvas,{get,makeCells,makeAtlas}){
  // Keep the last composed frame available while paused, including captures
  // after a focus/scroll repaint. All intermediate targets are still reused.
  const gl=canvas.getContext('webgl',{alpha:true,antialias:false,preserveDrawingBuffer:true,powerPreference:'low-power'});if(!gl)return null;
  function program(v,f,names){
    const p=gl.createProgram();
    for(const [type,source] of [[gl.VERTEX_SHADER,v],[gl.FRAGMENT_SHADER,f]]){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));gl.attachShader(p,s);gl.deleteShader(s);}
    gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));
    return {p,u:Object.fromEntries(names.map(n=>[n,gl.getUniformLocation(p,'u_'+n)]))};
  }
  const main=program(vertex,fragment,['resolution','center','unit','turn','tilt','reveal','flash','hover','ratio','footprint','glyphSize','centers[0]','halves[0]','colors[0]','key','fill','aa','atlas','shineTime','shineStrength','shineStyle']);
  const blur=program(quadVertex,blurFragment,['image','pixel','extract','range']);
  const composite=program(quadVertex,compositeFragment,['image','bloom','resolution','center','offsets[0]','unit','time','reveal','region','ghostStrength','background','ghostTint','energyA','energyB','bloomStrength','rolloff']);
  const cellsBuffer=gl.createBuffer(),quadBuffer=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,quadBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
  const atlas=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,atlas);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,makeAtlas());gl.generateMipmap(gl.TEXTURE_2D);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  const centers=new Float32Array(120),halves=new Float32Array(120);let target,mips=[],count=0;
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
    const {width,height,layout,ratio,time,pointer,bootSkipped,color,ghosts=true,ghostDistance=1,material='green'}=get(),reveal=bootSkipped?BOOT:time;
    scene.boxes.forEach((b,i)=>{centers.set(b.center,i*3);halves.set(b.half,i*3);});
    gl.disable(gl.BLEND);screen(target);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);use(main,cellsBuffer,'a_cell',2);bind(atlas);
    const u=main.u;gl.uniform1i(u.atlas,0);gl.uniform2f(u.resolution,width,height);gl.uniform2fv(u.center,layout.center);gl.uniform3fv(u['centers[0]'],centers);gl.uniform3fv(u['halves[0]'],halves);gl.uniform3fv(u['colors[0]'],materialColors(material));gl.uniform3fv(u.key,KEY);gl.uniform3fv(u.fill,FILL);
    for(const [k,v] of Object.entries({shineStyle:scene.shineStyle??0,shineTime:scene.shineTime??0,shineStrength:scene.shineStrength??0,unit:layout.unit,turn:scene.turn,tilt:scene.tilt,reveal,flash:scene.state.flash,hover:pointer.strength,ratio,footprint:layout.footprint,glyphSize:layout.glyphSize,aa:layout.pitch/layout.unit*.25}))gl.uniform1f(u[k],v);
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.drawArrays(gl.POINTS,0,count);gl.disable(gl.BLEND);
    const profile=materialProfile(material);gl.useProgram(blur.p);gl.uniform2fv(blur.u.range,profile.bloomRange);
    for(let i=0;i<mips.length;i++)blurTo(i?mips[i-1]:target,mips[i],i?0:1);
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);for(let i=mips.length-1;i>0;i--)blurTo(mips[i],mips[i-1],0);gl.disable(gl.BLEND);
    screen(null);use(composite,quadBuffer,'a_position',2);bind(target.texture);bind(mips[0].texture,1);
    const c=composite.u;gl.uniform1i(c.image,0);gl.uniform1i(c.bloom,1);gl.uniform2f(c.resolution,width,height);gl.uniform2fv(c.center,layout.center);gl.uniform2fv(c['offsets[0]'],ghostOffsets(scene.turn,scene.tilt,sideClearance(scene.state)).map(offset=>offset.map(value=>value*ghostDistance)).flat());gl.uniform4f(c.region,layout.left,layout.top,layout.right,layout.bottom);gl.uniform1f(c.unit,layout.unit);gl.uniform1f(c.time,time);gl.uniform1f(c.reveal,reveal);gl.uniform1f(c.ghostStrength,ghosts?1:0);gl.uniform3fv(c.background,profile.background);gl.uniform3fv(c.ghostTint,profile.ghost);gl.uniform3fv(c.energyA,profile.energyA);gl.uniform3fv(c.energyB,profile.energyB);gl.uniform1f(c.bloomStrength,profile.bloom*1.28*(1.+(scene.energy??0)*.25));gl.uniform1f(c.rolloff,profile.rolloff);gl.drawArrays(gl.TRIANGLES,0,6);
  }};
}

