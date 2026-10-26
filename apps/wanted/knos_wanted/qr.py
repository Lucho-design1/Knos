"""A QR code for a result page's address, with the standard library alone (ISO/IEC 18004: byte mode, error correction
level M, versions 1 to 6, so up to 106 bytes and no version block). svg() draws it; read() takes a module grid back to
its text, so a test can check what a drawn code says."""
from __future__ import annotations

# version -> (error correction codewords per block, [(blocks, data codewords per block), ...]) at level M
BLOCKS = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]), 6: (16, [(4, 27)])}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
LEVEL_M = 0                       # the two format bits of level M
MASKS = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
         lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
         lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]


def _mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(degree: int) -> list[int]:
    out, root = [0] * (degree - 1) + [1], 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _mul(root, 2)
    return out


def _ecc(data: list[int], degree: int) -> list[int]:
    div, out = _divisor(degree), [0] * degree
    for b in data:
        f = b ^ out.pop(0)
        out.append(0)
        for i, c in enumerate(div):
            out[i] ^= _mul(c, f)
    return out


def _capacity(v: int) -> int:
    return sum(n * k for n, k in BLOCKS[v][1])


def _format_bits(mask: int) -> int:
    data = LEVEL_M << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


class _Grid:
    def __init__(self, v: int):
        self.v, self.n = v, 17 + 4 * v
        self.dark = [[False] * self.n for _ in range(self.n)]
        self.fixed = [[False] * self.n for _ in range(self.n)]
        n = self.n
        for i in range(n):
            self.put(6, i, i % 2 == 0)
            self.put(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        a = ALIGN[v]
        for i, ax in enumerate(a):
            for j, ay in enumerate(a):
                if (i, j) in ((0, 0), (0, len(a) - 1), (len(a) - 1, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.format(0)                                  # reserves the format modules; drawn again with the mask

    def put(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x], self.fixed[y][x] = dark, True

    def format(self, mask: int) -> None:
        bits, n = _format_bits(mask), self.n
        b = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        for i in range(6):
            self.put(8, i, b(i))
        self.put(8, 7, b(6))
        self.put(8, 8, b(7))
        self.put(7, 8, b(8))
        for i in range(9, 15):
            self.put(14 - i, 8, b(i))
        for i in range(8):
            self.put(n - 1 - i, 8, b(i))
        for i in range(8, 15):
            self.put(8, n - 15 + i, b(i))
        self.put(8, n - 8, True)

    def cells(self):
        """The data modules in placement order: up and down two columns at a time, from the right."""
        n, right = self.n, self.n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                    if not self.fixed[y][x]:
                        yield x, y
            right -= 2


def _penalty(d: list[list[bool]]) -> int:
    n, p = len(d), 0
    for rows in (d, [list(c) for c in zip(*d)]):
        for row in rows:
            run = 1
            for i in range(1, n + 1):
                if i < n and row[i] == row[i - 1]:
                    run += 1
                else:
                    p += run - 2 if run >= 5 else 0
                    run = 1
            s = "".join("1" if c else "0" for c in row)
            p += 40 * (s.count("10111010000") + s.count("00001011101"))
    p += 3 * sum(1 for y in range(n - 1) for x in range(n - 1) if d[y][x] == d[y][x + 1] == d[y + 1][x] == d[y + 1][x + 1])
    dark = sum(map(sum, d))
    return p + 10 * (abs(dark * 20 - n * n * 10) // (n * n))


def encode(text: str) -> list[list[bool]]:
    """The module grid (rows of dark or light) for text, at the smallest version that holds it."""
    data = text.encode("utf-8")
    v = next((v for v in BLOCKS if 12 + 8 * len(data) <= 8 * _capacity(v)), None)
    if v is None:
        raise ValueError(f"{len(data)} bytes: more than a version 6 code holds at level M (106)")
    cap = _capacity(v)
    bits = [0, 1, 0, 0] + [(len(data) >> i) & 1 for i in range(7, -1, -1)] + [(b >> i) & 1 for b in data for i in range(7, -1, -1)]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    words += [(0xEC, 0x11)[i % 2] for i in range(cap - len(words))]
    ec, groups = BLOCKS[v]
    blocks, k = [], 0
    for count, size in groups:
        for _ in range(count):
            blocks.append(words[k:k + size])
            k += size
    eccs = [_ecc(b, ec) for b in blocks]
    out = [b[i] for i in range(max(map(len, blocks))) for b in blocks if i < len(b)] + [e[i] for i in range(ec) for e in eccs]
    best = None
    for mask in range(8):
        g = _Grid(v)
        stream = [(w >> i) & 1 for w in out for i in range(7, -1, -1)]
        for i, (x, y) in enumerate(g.cells()):
            g.dark[y][x] = (i < len(stream) and stream[i] == 1) ^ MASKS[mask](x, y)
        g.format(mask)
        score = _penalty(g.dark)
        if best is None or score < best[0]:
            best = (score, g.dark)
    return best[1]


def read(d: list[list[bool]]) -> str:
    """The text a module grid holds (byte mode, level M, versions 1 to 6): the format bits name the mask."""
    n = len(d)
    v = (n - 17) // 4
    if v not in BLOCKS or 17 + 4 * v != n:
        raise ValueError(f"a {n}x{n} grid is not a version 1 to 6 code")
    got = sum(1 << i for i in range(6) if d[i][8]) | (d[7][8] << 6) | (d[8][8] << 7) | (d[8][7] << 8) | \
        sum(1 << i for i in range(9, 15) if d[8][14 - i])
    mask = next((m for m in range(8) if _format_bits(m) == got), None)
    if mask is None:
        raise ValueError("format bits are not level M with a known mask")
    g = _Grid(v)
    stream = [int(d[y][x] ^ MASKS[mask](x, y)) for x, y in g.cells()]
    words = [int("".join(map(str, stream[i:i + 8])), 2) for i in range(0, len(stream) - 7, 8)]
    ec, groups = BLOCKS[v]
    sizes = [size for count, size in groups for _ in range(count)]
    blocks: list[list[int]] = [[] for _ in sizes]
    k = 0
    for i in range(max(sizes)):
        for b, size in enumerate(sizes):
            if i < size:
                blocks[b].append(words[k])
                k += 1
    for b, blk in enumerate(blocks):                  # each block's correction codewords must be its data's
        if [words[k + i * len(blocks) + b] for i in range(ec)] != _ecc(blk, ec):
            raise ValueError("a block's error correction does not match its data")
    bits = "".join(f"{w:08b}" for blk in blocks for w in blk)
    if bits[:4] != "0100":
        raise ValueError("not byte mode")
    count = int(bits[4:12], 2)
    return bytes(int(bits[12 + 8 * i:20 + 8 * i], 2) for i in range(count)).decode("utf-8")


def svg(text: str, px: int = 4, quiet: int = 4) -> str:
    """The code as an SVG: one path of dark modules on a light ground with the standard 4-module quiet zone."""
    d = encode(text)
    n, side = len(d), (len(d) + 2 * quiet) * px
    path = "".join(f"M{(x + quiet) * px},{(y + quiet) * px}h{px}v{px}h-{px}z" for y in range(n) for x in range(n) if d[y][x])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" width="{side}" height="{side}" role="img" '
            f'aria-label="QR code for {text}" data-modules="{n}" data-px="{px}" data-quiet="{quiet}">'
            f'<rect width="{side}" height="{side}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
