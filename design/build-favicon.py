"""Export the approved square-ended, maximum-contrast asterisk. No dependencies."""
from pathlib import Path
import math
import struct
import zlib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'docs'

def outline(radius, half):
    points = []
    for k in range(6):
        a = k * math.pi / 3
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        b = a + math.pi / 6
        points.extend([(radius*ux-half*nx, radius*uy-half*ny),
                       (radius*ux+half*nx, radius*uy+half*ny),
                       (2*half*math.cos(b), 2*half*math.sin(b))])
    return points

outer = outline(6.8, 2)
inner = outline(5.9, 1.1)
dx, dy = .65, .8
layers = [([(x+dx, y+dy) for x,y in outer], '#0d001b', None)]
for i, p in enumerate(outer):
    q = outer[(i+1) % len(outer)]
    vx, vy = q[0]-p[0], q[1]-p[1]
    length = math.hypot(vx, vy)
    nx, ny = vy/length, -vx/length
    if nx*dx + ny*dy > 0:
        color = '#0a0017' if ny > .6 else '#7000bf' if nx > .6 else '#230035'
        layers.append(([p, q, (q[0]+dx,q[1]+dy), (p[0]+dx,p[1]+dy)], color, None))
layers.append((outer, '#b500ff', None))
for i, p in enumerate(outer):
    j = (i+1) % len(outer)
    q = outer[j]
    vx, vy = q[0]-p[0], q[1]-p[1]
    length = math.hypot(vx, vy)
    light = -(vy/length)*.65 + (vx/length)*.76
    color = '#ffffff' if light > .65 else '#ffc2ff' if light > .1 else '#9a19ff' if light > -.45 else '#21003e'
    layers.append(([p,q,inner[j],inner[i]], color, None))
layers += [(inner, '#dc1eff', None),
           ([(-9,-9),(9,-9),(9,-5),(-9,3)], '#ff9dff', inner),
           ([(-9,7),(9,-1),(9,9),(-9,9)], '#6900d4', inner)]

def path(points):
    return 'M' + 'L'.join(f'{x:.6f},{y:.6f}' for x,y in points) + 'Z'

svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">',
       '<title>GraniteQuery</title>',
       '<g transform="translate(7.6 7.4)">',
       f'<defs><clipPath id="front"><path d="{path(inner)}"/></clipPath></defs>']
for points, color, clip in layers:
    clip_attr = ' clip-path="url(#front)"' if clip is not None else ''
    svg.append(f'<path fill="{color}" d="{path(points)}"{clip_attr}/>')
svg += ['</g>', '</svg>']
svg_text = '\n'.join(svg) + '\n'
ET.fromstring(svg_text)
(DEST / 'favicon.svg').write_text(svg_text, encoding='utf-8')

def inside(x, y, points):
    hit = False
    xj,yj = points[-1]
    for xi,yi in points:
        if ((yi > y) != (yj > y)) and x < (xj-xi)*(y-yi)/(yj-yi)+xi:
            hit = not hit
        xj,yj = xi,yi
    return hit

def prepared(points):
    return (points, min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))

def contains(poly, x, y):
    points,x0,y0,x1,y1 = poly
    return x0 <= x <= x1 and y0 <= y <= y1 and inside(x,y,points)

render_layers = [(prepared(points), tuple(bytes.fromhex(color[1:])), prepared(clip) if clip is not None else None)
                 for points,color,clip in layers]

def chunk(kind, data):
    return struct.pack('>I',len(data)) + kind + data + struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)

def png(size):
    ss = 8 if size == 16 else 4
    raw = bytearray()
    for py in range(size):
        raw.append(0)
        for px in range(size):
            sums = [0,0,0]
            covered = 0
            for sy in range(ss):
                y = (py+(sy+.5)/ss)*16/size - 7.4
                for sx in range(ss):
                    x = (px+(sx+.5)/ss)*16/size - 7.6
                    color = None
                    for poly, ink, clip in render_layers:
                        if contains(poly,x,y) and (clip is None or contains(clip,x,y)):
                            color = ink
                    if color is not None:
                        covered += 1
                        for c in range(3): sums[c] += color[c]
            raw.extend([round(v/covered) if covered else 0 for v in sums])
            raw.append(round(covered*255/(ss*ss)))
    header = struct.pack('>IIBBBBB',size,size,8,6,0,0,0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',header) + chunk(b'IDAT',zlib.compress(bytes(raw),9)) + chunk(b'IEND',b'')

images = []
for size in (16,32,48):
    image = png(size)
    (DEST / f'favicon-{size}.png').write_bytes(image)
    images.append((size,image))
offset = 6 + 16*len(images)
directory = bytearray(struct.pack('<HHH',0,1,len(images)))
for size,image in images:
    directory.extend(struct.pack('<BBBBHHII',size,size,0,0,1,32,len(image),offset))
    offset += len(image)
(DEST / 'favicon.ico').write_bytes(bytes(directory) + b''.join(image for _,image in images))

all_points = outer + [(x+dx,y+dy) for x,y in outer]
bounds = (min(x+7.6 for x,y in all_points), min(y+7.4 for x,y in all_points),
          max(x+7.6 for x,y in all_points), max(y+7.4 for x,y in all_points))
assert min(bounds[:2]) > 0 and max(bounds[2:]) < 16, bounds
assert len(outer) == 18
for size,image in images:
    assert image.startswith(b'\x89PNG\r\n\x1a\n')
    assert struct.unpack('>II',image[16:24]) == (size,size)
print(f'Exported SVG, PNG16/32/48 and ICO; 16px bounds={tuple(round(v,3) for v in bounds)}')
