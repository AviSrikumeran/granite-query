import {navigationVertex as vertex} from './gq-symbols.mjs?v=20261111-2';
// GQ glyph material, derived from the preserved homepage renderer.
// Homepage-only adapter of the accepted Electric Magenta renderer.
// Study source stays unchanged; ghostDistance only adjusts the three peripheral samples.
import {BOOT,traceBoxes,smooth} from '../playground/purple/engine/geometry.mjs?v=magenta-20261103-2';
import {KEY,FILL,TIER_GLYPHS,materialColors,materialProfile,ghostOffsets,sideClearance,ghostWeight,introCell,litSurface,softenedNormal,occlusionAt,viewDirection} from '../playground/purple/engine/material.mjs?v=magenta-20261103-2';

// One scene → luminance tiers → glyphs → camera-projected peripheral views →
// highlight bloom. Peripheral samples share the finished scene, not a new trace.
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
  float glowEdge=smoothstep(0.,.06,v_uv.x)*(1.-smoothstep(.94,1.,v_uv.x))*smoothstep(0.,.06,v_uv.y)*(1.-smoothstep(.94,1.,v_uv.y));
  vec3 bloom=texture2D(u_bloom,v_uv).rgb*u_bloomStrength*glowEdge;
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
  // No ambient background layer: only glyphs and their bloom are composited.
  float peak=max(color.r,max(color.g,color.b)),knee=u_rolloff;
  float rolled=peak<=knee?peak:knee+(1.-knee)*(1.-exp(-(peak-knee)/(1.-knee)));
  color*=rolled/max(peak,.0001);
  float envelope=1.-smoothstep(3.55,4.1,length(local/vec2(1.05,1.)));
  float edge=smoothstep(u_region.y,u_region.y+u_unit*.4,pixel.y)*(1.-smoothstep(u_region.w-u_unit*.4,u_region.w,pixel.y));
  edge*=smoothstep(u_region.x,u_region.x+u_unit*.4,pixel.x)*(1.-smoothstep(u_region.z-u_unit*.4,u_region.z,pixel.x));
  vec3 ink=color;float alpha=clamp(max(ink.r,max(ink.g,ink.b))*2.,0.,1.);gl_FragColor=vec4(ink,alpha);
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
  const main=program(vertex,fragment,['resolution','center','unit','turn','tilt','reveal','flash','hover','ratio','footprint','glyphSize','centers[0]','halves[0]','colors[0]','key','fill','aa','atlas','shineTime','shineStrength','shineStyle','lightSurface']);
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
    canvas.dataset.glyphCount=String(count);canvas.dataset.glyphPitch=layout.pitch.toFixed(3);canvas.dataset.pipeline='scene-glyphs-ghosts-bloom';canvas.dataset.bloomLevels='2';
    gl.bindBuffer(gl.ARRAY_BUFFER,cellsBuffer);gl.bufferData(gl.ARRAY_BUFFER,cells,gl.STATIC_DRAW);
    for(const t of [target,...mips])if(t){gl.deleteTexture(t.texture);gl.deleteFramebuffer(t.f);}
    target=targetAt(canvas.width,canvas.height);mips=Array.from({length:2},(_,i)=>targetAt(Math.max(1,Math.floor(canvas.width/2**(i+1))),Math.max(1,Math.floor(canvas.height/2**(i+1)))));
  },draw(scene){
    const {width,height,layout,ratio,time,pointer,bootSkipped,color,ghosts=true,ghostDistance=1,material='green'}=get(),reveal=bootSkipped?BOOT:time;
    scene.boxes.forEach((b,i)=>{centers.set(b.center,i*3);halves.set(b.half,i*3);});
    gl.disable(gl.BLEND);screen(target);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);use(main,cellsBuffer,'a_cell',2);bind(atlas);
    const u=main.u;gl.uniform1i(u.atlas,0);gl.uniform2f(u.resolution,width,height);gl.uniform2fv(u.center,layout.center);gl.uniform3fv(u['centers[0]'],centers);gl.uniform3fv(u['halves[0]'],halves);gl.uniform3fv(u['colors[0]'],materialColors(material));gl.uniform3fv(u.key,KEY);gl.uniform3fv(u.fill,FILL);
    for(const [k,v] of Object.entries({lightSurface:scene.lightSurface??0,shineStyle:scene.shineStyle??0,shineTime:scene.shineTime??0,shineStrength:scene.shineStrength??0,unit:layout.unit,turn:scene.turn,tilt:scene.tilt,reveal,flash:scene.state.flash,hover:pointer.strength,ratio,footprint:layout.footprint,glyphSize:layout.glyphSize,aa:layout.pitch/layout.unit*.25}))gl.uniform1f(u[k],v);
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.drawArrays(gl.POINTS,0,count);gl.disable(gl.BLEND);
    const profile=materialProfile(material);gl.useProgram(blur.p);gl.uniform2fv(blur.u.range,profile.bloomRange);
    for(let i=0;i<mips.length;i++)blurTo(i?mips[i-1]:target,mips[i],i?0:1);
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);for(let i=mips.length-1;i>0;i--)blurTo(mips[i],mips[i-1],0);gl.disable(gl.BLEND);
    screen(null);use(composite,quadBuffer,'a_position',2);bind(target.texture);bind(mips[0].texture,1);
    const c=composite.u;gl.uniform1i(c.image,0);gl.uniform1i(c.bloom,1);gl.uniform2f(c.resolution,width,height);gl.uniform2fv(c.center,layout.center);gl.uniform2fv(c['offsets[0]'],ghostOffsets(scene.turn,scene.tilt,sideClearance(scene.state)).map(offset=>offset.map(value=>value*ghostDistance)).flat());gl.uniform4f(c.region,layout.left,layout.top,layout.right,layout.bottom);gl.uniform1f(c.unit,layout.unit);gl.uniform1f(c.time,time);gl.uniform1f(c.reveal,reveal);gl.uniform1f(c.ghostStrength,ghosts?1:0);gl.uniform3fv(c.background,profile.background);gl.uniform3fv(c.ghostTint,profile.ghost);gl.uniform3fv(c.energyA,profile.energyA);gl.uniform3fv(c.energyB,profile.energyB);gl.uniform1f(c.bloomStrength,profile.bloom*.65*(1.+(scene.energy??0)*.25));gl.uniform1f(c.rolloff,profile.rolloff);gl.drawArrays(gl.TRIANGLES,0,6);
  }};
}

