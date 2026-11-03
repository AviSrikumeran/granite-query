/* Independent reference reconstruction. No Modal application or shader code. */
(() => {
  'use strict';
  let canvas = document.querySelector('#glyph-field');
  const localPause = document.querySelector('#local-pause');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const embedded = window.parent !== window;
  document.body.classList.toggle('embedded', embedded);
  let paused = reducedMotion.matches, visible = !document.hidden, inView = true;
  let time = 0, previous = 0, request = 0, frame = 0, width = 0, height = 0, ratio = 1;
  const pointer = {x: -2000, y: -2000, strength: 0};
  const pulse = {x: 0, y: 0, start: -10};
  const edges = new Float32Array(48);
  const corners = [[-1,-1,-1],[1,-1,-1],[-1,1,-1],[1,1,-1],[-1,-1,1],[1,-1,1],[-1,1,1],[1,1,1]];
  const connections = [[0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],[3,7],[4,5],[4,6],[5,7],[6,7]];
  const glyphs = ['●', '⬡', '✦', '+', 'Y', '▲', '◆', '✳'];
  let renderer;

  function geometry() {
    const scale = Math.min(1.12, Math.max(.62, width / 1265));
    const centerY = 620;
    // A small rotation changes depth without losing the reference's frontal cube silhouette.
    const angle = Math.sin(time * .12) * .085;
    const points = corners.map(([x,y,z]) => {
      const rx = x * Math.cos(angle) - z * Math.sin(angle);
      const rz = x * Math.sin(angle) + z * Math.cos(angle);
      return [width * .5 + (rx - rz) * .8660254 * 112 * scale,
        centerY + ((rx + rz) * .5 - y) * 112 * scale];
    });
    connections.forEach(([a,b], i) => edges.set([...points[a], ...points[b]], i * 4));
    return scale;
  }

  function atlas() {
    const image = document.createElement('canvas'); image.width = 512; image.height = 64;
    const ctx = image.getContext('2d'); ctx.fillStyle = '#fff'; ctx.strokeStyle = '#fff';
    for(let kind = 0; kind < 8; kind++) {
      ctx.save(); ctx.translate(kind * 64 + 32, 32); ctx.lineWidth = 5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      if(kind === 0) { ctx.beginPath(); ctx.arc(0,0,19,0,Math.PI*2); ctx.fill(); }
      if(kind === 1) { ctx.beginPath(); for(let k=0;k<6;k++) { const a=k*Math.PI/3; ctx[k?'lineTo':'moveTo'](21*Math.cos(a),21*Math.sin(a)); } ctx.closePath(); ctx.stroke(); }
      if(kind === 2 || kind === 7) { ctx.beginPath(); const n=kind===2?6:5; for(let k=0;k<n*2;k++) { const a=k*Math.PI/n-Math.PI/2,r=k%2?8:24; ctx[k?'lineTo':'moveTo'](r*Math.cos(a),r*Math.sin(a)); } ctx.closePath(); ctx.fill(); }
      if(kind === 3) { ctx.fillRect(-3,-22,6,44); ctx.fillRect(-22,-3,44,6); }
      if(kind === 4) { ctx.beginPath(); ctx.moveTo(-19,-19);ctx.lineTo(0,0);ctx.lineTo(19,-19);ctx.moveTo(0,0);ctx.lineTo(0,22);ctx.stroke(); }
      if(kind === 5) { ctx.beginPath();ctx.moveTo(0,-22);ctx.lineTo(23,19);ctx.lineTo(-23,19);ctx.closePath();ctx.fill(); }
      if(kind === 6) { ctx.beginPath();ctx.moveTo(0,-23);ctx.lineTo(22,0);ctx.lineTo(0,23);ctx.lineTo(-22,0);ctx.closePath();ctx.stroke(); }
      ctx.restore();
    }
    return image;
  }

  const vertex = `
  precision highp float;
  attribute vec2 a_cell;
  uniform vec2 u_resolution, u_pointer;
  uniform vec3 u_pulse;
  uniform vec2 u_edges[24];
  uniform float u_time, u_ratio, u_scale, u_pointerStrength, u_glow;
  varying float v_energy, v_glyph, v_hue;
  float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+1.),f.x),f.y);}
  float segment(vec2 p,vec2 a,vec2 b){vec2 ab=b-a;return length(p-a-ab*clamp(dot(p-a,ab)/dot(ab,ab),0.,1.));}
  void main(){
    vec2 p=a_cell;
    vec2 flow=vec2(sin(p.y*.018+u_time*.29),cos(p.x*.017-u_time*.23));
    vec2 q=p+flow*3.*u_scale;
    vec2 center=vec2(u_resolution.x*.5,620.);
    vec2 leftEcho=(q-center+vec2(300.,8.)*u_scale)/.72+center;
    vec2 rightEcho=(q-center-vec2(230.,-140.)*u_scale)/.67+center;
    float d=10000., dl=10000., dr=10000.;
    for(int i=0;i<12;i++){
      vec2 a=u_edges[i*2],b=u_edges[i*2+1];
      d=min(d,segment(q,a,b));
      dl=min(dl,segment(leftEcho,a,b));
      dr=min(dr,segment(rightEcho,a,b));
    }
    float grain=noise(q*.027+vec2(u_time*.055,-u_time*.08));
    float fine=noise(q*.075+u_time*.04);
    float lane=exp(-pow(d/(19.*u_scale),2.));
    float halo=exp(-pow(d/(45.*u_scale),2.));
    float ghosts=max(exp(-pow(dl/(19.*u_scale),2.)),exp(-pow(dr/(20.*u_scale),2.)));
    vec2 ellipse=(p-center)/vec2(485.*u_scale,350.*u_scale);
    float envelope=exp(-pow(length(ellipse),4.)*.8);
    float vertical=smoothstep(326.,405.,p.y)*(1.-smoothstep(890.,1040.,p.y));
    float textureLight=.66+grain*.52;
    float flicker=.88+.12*sin(u_time*.45+q.x*.014+q.y*.01);
    float energy=(lane*textureLight*1.38+halo*.035+ghosts*.29+fine*.003)*envelope*vertical*flicker;
    vec2 delta=p-u_pointer;
    float pointerLight=exp(-dot(delta,delta)/10500.)*u_pointerStrength;
    float age=u_pulse.z;
    float ring=exp(-pow((length(p-u_pulse.xy)-age*145.)/17.,2.))*exp(-age*.8)*step(0.,age);
    energy+=pointerLight*.42*vertical+ring*.64*vertical;
    p+=normalize(delta+vec2(.001))*pointerLight*13.;
    p+=normalize(p-u_pulse.xy+vec2(.001))*ring*7.;
    v_energy=clamp(energy,0.,1.);
    v_hue=noise(q*.012+vec2(u_time*.025,0.));
    v_glyph=floor(hash(floor((a_cell+vec2(grain*19.,fine*13.))/vec2(23.,28.))+floor(u_time*.055))*8.);
    gl_Position=vec4(p.x/u_resolution.x*2.-1.,1.-p.y/u_resolution.y*2.,0.,1.);
    gl_PointSize=(u_glow>.5?25.:8.8)*u_ratio;
  }`;
  const fragment = `
  precision highp float;
  uniform sampler2D u_atlas;
  uniform float u_glow;
  varying float v_energy,v_glyph,v_hue;
  void main(){
    if(v_energy<.006)discard;
    vec3 green=mix(vec3(.10,.59,.32),vec3(.53,.99,.37),smoothstep(.3,.76,v_hue));
    green=mix(green,vec3(.79,.96,.36),smoothstep(.69,.87,v_hue)*.7);
    vec3 color=mix(vec3(.21,.25,.21),green,smoothstep(.06,.31,v_energy));
    float alpha;
    if(u_glow>.5){alpha=exp(-dot(gl_PointCoord-.5,gl_PointCoord-.5)*18.)*v_energy*.043;}
    else {alpha=texture2D(u_atlas,vec2((v_glyph+gl_PointCoord.x)/8.,gl_PointCoord.y)).a*pow(v_energy,.79);}
    gl_FragColor=vec4(color,alpha);
  }`;

  function makeWebGL() {
    const gl = canvas.getContext('webgl', {alpha:false, antialias:false, powerPreference:'low-power'});
    if(!gl) return null;
    function compile(type, source) {
      const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
      return shader;
    }
    const program=gl.createProgram();
    const shaders=[compile(gl.VERTEX_SHADER,vertex),compile(gl.FRAGMENT_SHADER,fragment)];
    shaders.forEach(shader=>gl.attachShader(program,shader));gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);shaders.forEach(shader=>gl.deleteShader(shader));
    const locations=Object.fromEntries(['resolution','pointer','pulse','edges[0]','time','ratio','scale','pointerStrength','glow','atlas'].map(name=>[name,gl.getUniformLocation(program,`u_${name}`)]));
    const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    const attribute=gl.getAttribLocation(program,'a_cell');gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,0,0);
    const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,atlas());
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    gl.uniform1i(locations.atlas,0);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);
    let count=0;
    return {type:'WebGL', resize(){
      const cells=[];
      for(let y=326;y<height;y+=7.2) for(let x=3.6;x<width;x+=7.2)cells.push(x,y);
      count=cells.length/2;gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(cells),gl.STATIC_DRAW);gl.viewport(0,0,canvas.width,canvas.height);
    },draw(scale){
      gl.clearColor(4/255,8/255,4/255,1);gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(locations.resolution,width,height);gl.uniform1f(locations.time,time);
      gl.uniform1f(locations.ratio,ratio);gl.uniform1f(locations.scale,scale);
      gl.uniform2f(locations.pointer,pointer.x,pointer.y);gl.uniform1f(locations.pointerStrength,pointer.strength);
      gl.uniform3f(locations.pulse,pulse.x,pulse.y,time-pulse.start);
      gl.uniform2fv(locations['edges[0]'],edges);
      gl.uniform1f(locations.glow,1);gl.drawArrays(gl.POINTS,0,count);
      gl.uniform1f(locations.glow,0);gl.drawArrays(gl.POINTS,0,count);
    },destroy(){gl.deleteBuffer(buffer);gl.deleteTexture(texture);gl.deleteProgram(program);}};
  }

  function makeFallback() {
    // A usable, lower-density field remains available without WebGL.
    const ctx=canvas.getContext('2d');
    if(!ctx) return {type:'unavailable',resize(){},draw(){}};
    const distance=(x,y,a,b,c,d)=>{const dx=c-a,dy=d-b,t=Math.max(0,Math.min(1,((x-a)*dx+(y-b)*dy)/(dx*dx+dy*dy)));return Math.hypot(x-a-dx*t,y-b-dy*t);};
    return {type:'Canvas 2D',resize(){},draw(scale){
      ctx.setTransform(ratio,0,0,ratio,0,0);ctx.fillStyle='#040804';ctx.fillRect(0,0,width,height);ctx.font='7px Arial';ctx.textAlign='center';ctx.textBaseline='middle';
      for(let y=340;y<Math.min(height,1010);y+=8) for(let x=4;x<width;x+=8){
        let d=9999;for(let i=0;i<48;i+=4)d=Math.min(d,distance(x,y,...edges.slice(i,i+4)));
        const envelope=Math.exp(-Math.pow(Math.hypot((x-width/2)/(480*scale),(y-630)/(350*scale)),4));
        const age=time-pulse.start,ring=Math.exp(-Math.pow((Math.hypot(x-pulse.x,y-pulse.y)-age*145)/17,2))*Math.exp(-age*.8);
        const energy=Math.exp(-Math.pow(d/(21*scale),2))*envelope*(.52+.28*Math.sin(x*.025+y*.035+time*.3))+ring*.6;
        if(energy<.025)continue;
        const delta=Math.hypot(x-pointer.x,y-pointer.y),offset=Math.exp(-delta*delta/10500)*pointer.strength*12;
        ctx.fillStyle=`rgba(117,238,100,${Math.min(1,energy)})`;
        ctx.fillText(glyphs[Math.abs(Math.floor(x/28)*17+Math.floor(y/32)*7)%8],x+(x-pointer.x)/(delta||1)*offset,y+(y-pointer.y)/(delta||1)*offset);
      }
    }};
  }

  function draw() {
    const scale=geometry();renderer.draw(scale);frame++;
    canvas.dataset.frame=String(frame);canvas.dataset.time=time.toFixed(3);
  }
  function tick(now) {
    request=0;
    if(paused||!visible||!inView){previous=0;return;}
    if(previous)time+=Math.min(.05,(now-previous)/1000);
    previous=now;
    pointer.strength+=(pointer.x>-1000?1-pointer.strength:-pointer.strength)*.09;
    draw();request=requestAnimationFrame(tick);
  }
  function schedule() { if(!request&&!paused&&visible&&inView)request=requestAnimationFrame(tick); }
  function setPaused(value) {
    paused=value;previous=0;
    if(request){cancelAnimationFrame(request);request=0;}
    canvas.dataset.paused=String(paused);localPause.setAttribute('aria-pressed',String(paused));
    localPause.textContent=paused?'Resume animation':'Pause animation';schedule();
    if(embedded)window.parent.postMessage({type:'modal-hero-motion',paused},location.origin);
  }
  function resize() {
    const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;ratio=Math.min(devicePixelRatio||1,1.5);
    if(width>760){document.querySelector('#mobile-menu').hidden=true;document.querySelector('#menu-toggle').setAttribute('aria-expanded','false');document.querySelector('#menu-toggle').setAttribute('aria-label','Open navigation');}
    canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);renderer.resize();draw();schedule();
  }
  try { if(new URLSearchParams(location.search).get('renderer')!=='canvas')renderer=makeWebGL(); } catch(error) {
    console.warn('WebGL field unavailable:',error.message);
    // A fresh canvas is needed if a WebGL context was created before shader failure.
  }
  if(!renderer) {
    const replacement=canvas.cloneNode();canvas.replaceWith(replacement);canvas=replacement;
    renderer=makeFallback();
  }
  canvas.dataset.renderer=renderer.type;
  canvas.addEventListener('pointermove',event=>{if(event.pointerType==='touch')return;const r=canvas.getBoundingClientRect();pointer.x=event.clientX-r.left;pointer.y=event.clientY-r.top;canvas.dataset.interaction='pointer';});
  canvas.addEventListener('pointerleave',()=>{pointer.x=-2000;pointer.y=-2000;});
  canvas.addEventListener('pointerdown',event=>{const r=canvas.getBoundingClientRect();pulse.x=event.clientX-r.left;pulse.y=event.clientY-r.top;pulse.start=time;canvas.dataset.interaction='pulse';});
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();if(request)cancelAnimationFrame(request);request=0;canvas.dataset.renderer='context lost';});
  canvas.addEventListener('webglcontextrestored',()=>{renderer=makeWebGL();canvas.dataset.renderer=renderer.type;resize();});
  localPause.addEventListener('click',()=>setPaused(!paused));
  document.addEventListener('keydown',event=>{if(event.key==='Escape')setPaused(true);});
  document.addEventListener('visibilitychange',()=>{visible=!document.hidden;previous=0;schedule();});
  new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;previous=0;schedule();}).observe(canvas);
  new ResizeObserver(resize).observe(canvas);
  reducedMotion.addEventListener('change',event=>{if(event.matches)setPaused(true);});
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==window.parent||event.data?.type!=='modal-hero-study')return;
    if(event.data.action==='motion')setPaused(Boolean(event.data.paused));
    if(event.data.action==='reset'){time=0;previous=0;pulse.start=-10;pointer.x=-2000;pointer.y=-2000;pointer.strength=0;draw();}
  });
  const menu=document.querySelector('#menu-toggle'),menuPanel=document.querySelector('#mobile-menu');
  menu.addEventListener('click',()=>{const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Close navigation':'Open navigation');menuPanel.hidden=!open;});
  resize();setPaused(paused);
  if(embedded)window.parent.postMessage({type:'modal-hero-ready'},location.origin);
})();
