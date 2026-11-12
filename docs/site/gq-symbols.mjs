// Authored at navigation scale: 19 glyphs in G and 22 in Q.
export const SYMBOL_ROWS=[
 '011110  011110',
 '100001  100001',
 '100000  100001',
 '100111  100001',
 '100001  100101',
 '100001  100011',
 '011110  011111',
 '000000  000001',
];
export const GLYPH_COUNT=SYMBOL_ROWS.reduce((sum,row)=>sum+[...row].filter(c=>c==='1').length,0);

export const navigationVertex=`
precision highp float;
attribute vec2 a_cell;
uniform vec2 u_resolution,u_center;
uniform vec3 u_colors[16];
uniform float u_unit,u_ratio,u_footprint,u_shineTime,u_shineStrength,u_lightSurface;
varying vec3 v_color;
varying float v_glyph,v_reveal,v_size;
void main(){
 vec2 local=(a_cell-u_center)/u_unit;
 float choice=mod(floor(a_cell.x/20.)+3.*floor(a_cell.y/20.),6.);
 v_glyph=choice<.5?4.:choice<1.5?13.:choice<2.5?2.:choice<3.5?9.:choice<4.5?8.:0.;
 float face=.5+.5*sin(local.x*.9-local.y*1.2);
 vec3 base=mix(u_colors[8],u_colors[11],face*.35);
 float band=pow(.5+.5*cos((local.x-local.y*.28)*.95-u_shineTime*.82),6.);
 vec3 lit=mix(base,vec3(1.,.92,1.),min(.72,band*.55*u_shineStrength));
 if(u_lightSurface>.5){
   base=mix(vec3(.53,.025,.49),vec3(.79,.055,.70),face*.55);
   lit=mix(base,vec3(.89,.14,.77),min(.65,band*.5*u_shineStrength));
 }
 v_color=lit;v_reveal=1.;v_size=1.;
 gl_Position=vec4(a_cell.x/u_resolution.x*2.-1.,1.-a_cell.y/u_resolution.y*2.,0.,1.);
 gl_PointSize=u_footprint*u_ratio;
}`;
