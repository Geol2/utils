# make_icon.py — 영향도 분석 아이콘(.ico) 생성기. 의존성 없음(표준 라이브러리만).
# 실행: python make_icon.py   ->  impact.ico
# 도안: 남색 라운드 배경 + 금색 중심 노드에서 3방향으로 퍼지는 영향(파급) 그래프 + 파급 링
import struct, zlib, math

SS   = 4                                   # 픽셀당 4x4 슈퍼샘플 (안티에일리어싱)
GOLD = (0xd9, 0xb4, 0x5a)
SAT  = (0xf2, 0xf6, 0xfc)
EDGE = (0xa9, 0xc6, 0xea)
BG_T = (0x2a, 0x5e, 0xa8)                  # 배경 위쪽
BG_B = (0x15, 0x36, 0x68)                  # 배경 아래쪽

C  = (0.50, 0.50)                          # 중심 노드
SATS = [(0.50 + 0.33 * math.cos(math.radians(a)),
         0.50 + 0.33 * math.sin(math.radians(a))) for a in (-90, 30, 150)]

def rrect(x, y, r):
    """0..1 좌표에서 모서리 반경 r 인 라운드 사각형 내부인지 (여백 m)"""
    m = 0.045
    qx = max(abs(x - .5) - (.5 - m - r), 0.0)
    qy = max(abs(y - .5) - (.5 - m - r), 0.0)
    return math.hypot(qx, qy) <= r

def seg_dist(px, py, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

def over(dst, src, a):
    """src(RGB) 를 알파 a 로 dst(RGB) 위에 올림"""
    return tuple(int(round(s * a + d * (1 - a))) for s, d in zip(src, dst))

def sample(x, y, small):
    """(x, y) 한 점의 (R, G, B, A). small=True 면 16/24px 용으로 선을 굵게"""
    if not rrect(x, y, 0.20): return (0, 0, 0, 0)
    t = (y - .045) / .91
    col = tuple(int(round(a + (b - a) * min(max(t, 0), 1))) for a, b in zip(BG_T, BG_B))
    if not small:                                               # 파급 링 (작은 크기에선 뭉개져서 생략)
        if abs(math.hypot(x - C[0], y - C[1]) - 0.385) <= 0.020: col = over(col, GOLD, 0.45)
    ew = 0.036 if small else 0.028                              # 영향 간선
    if any(seg_dist(x, y, C, s) <= ew for s in SATS): col = over(col, EDGE, 0.95)
    sr = 0.125 if small else 0.110                              # 말단 노드
    if any(math.hypot(x - sx, y - sy) <= sr for sx, sy in SATS): col = SAT
    if math.hypot(x - C[0], y - C[1]) <= (0.185 if small else 0.170): col = GOLD   # 중심(변경 지점)
    return col + (255,)

def render(n):
    """n×n RGBA 바이트열"""
    small, px, inv = n <= 24, bytearray(), 1.0 / (n * SS)
    for py in range(n):
        for pxi in range(n):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    cr, cg, cb, ca = sample((pxi * SS + sx + .5) * inv, (py * SS + sy + .5) * inv, small)
                    w = ca / 255.0
                    r += cr * w; g += cg * w; b += cb * w; a += ca
            k = SS * SS; aa = a / k
            if aa < 0.5: px += b'\x00\x00\x00\x00'
            else:
                s = a / 255.0
                px += bytes((int(round(r / s)), int(round(g / s)), int(round(b / s)), int(round(aa))))
    return bytes(px)

def png(w, rgba, h=None):
    h = h or w
    raw = b''.join(b'\x00' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    def chunk(tag, d): 
        c = tag + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))

def dib(n, rgba):
    """ICO 안에 넣는 BMP(BITMAPINFOHEADER + 32bpp BGRA, 상하반전 + AND 마스크)"""
    hdr = struct.pack('<IiiHHIIiiII', 40, n, n * 2, 1, 32, 0, n * n * 4, 0, 0, 0, 0)
    body = bytearray()
    for y in range(n - 1, -1, -1):
        for x in range(n):
            r, g, b, a = rgba[(y * n + x) * 4:(y * n + x) * 4 + 4]
            body += bytes((b, g, r, a))
    return hdr + bytes(body) + b'\x00' * (((n + 31) // 32) * 4 * n)   # AND 마스크 전부 0

def build(path='impact.ico'):
    SIZES = [16, 24, 32, 48, 64, 128, 256]
    imgs = []
    for n in SIZES:
        rgba = render(n)
        imgs.append((n, png(n, rgba) if n >= 128 else dib(n, rgba)))     # 큰 건 PNG 압축, 작은 건 BMP
        print(f'  {n}x{n} ok')

    off = 6 + 16 * len(imgs)
    out = struct.pack('<HHH', 0, 1, len(imgs))
    for n, d in imgs:
        out += struct.pack('<BBBBHHII', 0 if n == 256 else n, 0 if n == 256 else n, 0, 0, 1, 32, len(d), off); off += len(d)
    out += b''.join(d for _, d in imgs)
    open(path, 'wb').write(out)
    print(f'{path} ({len(out):,} bytes, {len(imgs)} sizes)')

if __name__ == '__main__':
    build()
