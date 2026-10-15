"""BN254 (alt_bn128) in pure Python: the fields, G1, G2 and the optimal ate pairing.

Enough to check a Groth16 proof off chain with no dependency (about a second): the same curve and the same byte layout
as Solana's alt_bn128 syscalls (big-endian; a G2 point is x.c1, x.c0, y.c1, y.c0 as in EIP-197). It is a checker,
not a prover: nothing here is constant-time and nothing here handles secrets.

Towers: Fp2 = Fp[u]/(u^2 + 1), Fp6 = Fp2[v]/(v^3 - xi) with xi = 9 + u, Fp12 = Fp6[w]/(w^2 - v).
G2 lives on the D-type twist y^2 = x^3 + 3/xi over Fp2; psi(x, y) = (x w^2, y w^3) maps it into E(Fp12).
"""

from __future__ import annotations

P = 21888242871839275222246405745257275088696311157297823662689037894645226208583
R = 21888242871839275222246405745257275088548364400416034343698204186575808495617
ATE_LOOP = 29793968203157093288  # 6x + 2, x = 4965661367192848881

# ---- Fp2: (a0, a1) = a0 + a1 u ----
F2_ZERO = (0, 0)
F2_ONE = (1, 0)


def f2_add(a, b):
    return ((a[0] + b[0]) % P, (a[1] + b[1]) % P)


def f2_sub(a, b):
    return ((a[0] - b[0]) % P, (a[1] - b[1]) % P)


def f2_neg(a):
    return ((-a[0]) % P, (-a[1]) % P)


def f2_mul(a, b):
    return ((a[0] * b[0] - a[1] * b[1]) % P, (a[0] * b[1] + a[1] * b[0]) % P)


def f2_scale(a, k):
    return ((a[0] * k) % P, (a[1] * k) % P)


def f2_sq(a):
    return f2_mul(a, a)


def f2_inv(a):
    t = pow((a[0] * a[0] + a[1] * a[1]) % P, -1, P)
    return ((a[0] * t) % P, (-a[1] * t) % P)


def f2_conj(a):
    return (a[0], (-a[1]) % P)


def f2_mul_xi(a):  # a * (9 + u)
    return ((9 * a[0] - a[1]) % P, (a[0] + 9 * a[1]) % P)


def f2_pow(a, e):
    out = F2_ONE
    while e:
        if e & 1:
            out = f2_mul(out, a)
        a = f2_sq(a)
        e >>= 1
    return out


XI = (9, 1)
B2 = f2_mul((3, 0), f2_inv(XI))  # the twist's b = 3 / xi

# ---- Fp6: (c0, c1, c2) = c0 + c1 v + c2 v^2 ----
F6_ZERO = (F2_ZERO, F2_ZERO, F2_ZERO)
F6_ONE = (F2_ONE, F2_ZERO, F2_ZERO)


def f6_add(a, b):
    return (f2_add(a[0], b[0]), f2_add(a[1], b[1]), f2_add(a[2], b[2]))


def f6_sub(a, b):
    return (f2_sub(a[0], b[0]), f2_sub(a[1], b[1]), f2_sub(a[2], b[2]))


def f6_neg(a):
    return (f2_neg(a[0]), f2_neg(a[1]), f2_neg(a[2]))


def f6_mul(a, b):
    a0, a1, a2 = a
    b0, b1, b2 = b
    t0, t1, t2 = f2_mul(a0, b0), f2_mul(a1, b1), f2_mul(a2, b2)
    c0 = f2_add(t0, f2_mul_xi(f2_add(f2_mul(a1, b2), f2_mul(a2, b1))))
    c1 = f2_add(f2_add(f2_mul(a0, b1), f2_mul(a1, b0)), f2_mul_xi(t2))
    c2 = f2_add(f2_add(f2_mul(a0, b2), t1), f2_mul(a2, b0))
    return (c0, c1, c2)


def f6_mul_v(a):  # a * v
    return (f2_mul_xi(a[2]), a[0], a[1])


def f6_inv(a):
    a0, a1, a2 = a
    t0 = f2_sub(f2_sq(a0), f2_mul_xi(f2_mul(a1, a2)))
    t1 = f2_sub(f2_mul_xi(f2_sq(a2)), f2_mul(a0, a1))
    t2 = f2_sub(f2_sq(a1), f2_mul(a0, a2))
    f = f2_add(f2_mul(a0, t0), f2_mul_xi(f2_add(f2_mul(a2, t1), f2_mul(a1, t2))))
    fi = f2_inv(f)
    return (f2_mul(t0, fi), f2_mul(t1, fi), f2_mul(t2, fi))


# ---- Fp12: (c0, c1) = c0 + c1 w ----
F12_ONE = (F6_ONE, F6_ZERO)


def f12_mul(a, b):
    t0 = f6_mul(a[0], b[0])
    t1 = f6_mul(a[1], b[1])
    c1 = f6_sub(f6_sub(f6_mul(f6_add(a[0], a[1]), f6_add(b[0], b[1])), t0), t1)
    return (f6_add(t0, f6_mul_v(t1)), c1)


def f12_sq(a):
    return f12_mul(a, a)


def f12_conj(a):
    return (a[0], f6_neg(a[1]))


def f12_inv(a):
    d = f6_inv(f6_sub(f6_mul(a[0], a[0]), f6_mul_v(f6_mul(a[1], a[1]))))
    return (f6_mul(a[0], d), f6_neg(f6_mul(a[1], d)))


def f12_pow(a, e):
    out = F12_ONE
    while e:
        if e & 1:
            out = f12_mul(out, a)
        a = f12_sq(a)
        e >>= 1
    return out


# ---- G1 over Fp, affine; None is the point at infinity ----

def g1_on_curve(pt) -> bool:
    if pt is None:
        return True
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - x * x * x - 3) % P == 0


def g1_neg(pt):
    return None if pt is None else (pt[0], (-pt[1]) % P)


def g1_add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0]:
        if (a[1] + b[1]) % P == 0:
            return None
        lam = 3 * a[0] * a[0] * pow(2 * a[1], -1, P) % P
    else:
        lam = (b[1] - a[1]) * pow(b[0] - a[0], -1, P) % P
    x = (lam * lam - a[0] - b[0]) % P
    return (x, (lam * (a[0] - x) - a[1]) % P)


def g1_mul(pt, k: int):
    out = None
    while k:
        if k & 1:
            out = g1_add(out, pt)
        pt = g1_add(pt, pt)
        k >>= 1
    return out


# ---- G2 over Fp2 (the twist), affine ----

def g2_on_curve(pt) -> bool:
    if pt is None:
        return True
    x, y = pt
    if not all(0 <= c < P for c in (*x, *y)):
        return False
    return f2_sub(f2_sq(y), f2_add(f2_mul(f2_sq(x), x), B2)) == F2_ZERO


def g2_neg(pt):
    return None if pt is None else (pt[0], f2_neg(pt[1]))


def g2_add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0]:
        if f2_add(a[1], b[1]) == F2_ZERO:
            return None
        lam = f2_mul(f2_scale(f2_sq(a[0]), 3), f2_inv(f2_scale(a[1], 2)))
    else:
        lam = f2_mul(f2_sub(b[1], a[1]), f2_inv(f2_sub(b[0], a[0])))
    x = f2_sub(f2_sub(f2_sq(lam), a[0]), b[0])
    return (x, f2_sub(f2_mul(lam, f2_sub(a[0], x)), a[1]))


def g2_mul(pt, k: int):
    out = None
    while k:
        if k & 1:
            out = g2_add(out, pt)
        pt = g2_add(pt, pt)
        k >>= 1
    return out


def g2_in_subgroup(pt) -> bool:
    return g2_mul(pt, R) is None


# Frobenius on the twist: pi(x, y) = (conj(x) g1, conj(y) g2); pi^2(x, y) = (x h1, y h2)
_FX1 = f2_pow(XI, (P - 1) // 3)
_FY1 = f2_pow(XI, (P - 1) // 2)
_FX2 = f2_pow(XI, (P * P - 1) // 3)
_FY2 = f2_pow(XI, (P * P - 1) // 2)


def _frob(q):
    return (f2_mul(f2_conj(q[0]), _FX1), f2_mul(f2_conj(q[1]), _FY1))


def _frob2(q):
    return (f2_mul(q[0], _FX2), f2_mul(q[1], _FY2))


# ---- pairing ----

def _line(lam, t, p):
    """the line of slope lam (twisted) through t, at p in G1, as an element of Fp12 (vertical parts dropped: the
    final exponentiation sends Fp6 to 1)"""
    xp, yp = p
    c0 = ((yp % P, 0), F2_ZERO, F2_ZERO)
    c1 = (f2_scale(lam, -xp % P), f2_sub(f2_mul(lam, t[0]), t[1]), F2_ZERO)
    return (c0, c1)


def _step(t, q, p):
    """(t + q, line through t and q at p); q is t for doubling"""
    if t[0] == q[0] and t[1] == q[1]:
        lam = f2_mul(f2_scale(f2_sq(t[0]), 3), f2_inv(f2_scale(t[1], 2)))
    else:
        lam = f2_mul(f2_sub(q[1], t[1]), f2_inv(f2_sub(q[0], t[0])))
    x = f2_sub(f2_sub(f2_sq(lam), t[0]), q[0])
    nt = (x, f2_sub(f2_mul(lam, f2_sub(t[0], x)), t[1]))
    return nt, _line(lam, t, p)


def miller_loop(q, p):
    if q is None or p is None:
        return F12_ONE
    f = F12_ONE
    t = q
    for bit in bin(ATE_LOOP)[3:]:
        t, ln = _step(t, t, p)
        f = f12_mul(f12_sq(f), ln)
        if bit == "1":
            t, ln = _step(t, q, p)
            f = f12_mul(f, ln)
    q1 = _frob(q)
    nq2 = g2_neg(_frob2(q))
    t, ln = _step(t, q1, p)
    f = f12_mul(f, ln)
    _, ln = _step(t, nq2, p)
    return f12_mul(f, ln)


_HARD = (P**4 - P**2 + 1) // R


def final_exponentiation(f):
    f1 = f12_mul(f12_conj(f), f12_inv(f))  # f^(p^6 - 1)
    f2 = f12_mul(f12_pow(f1, P * P), f1)  # ^(p^2 + 1)
    return f12_pow(f2, _HARD)


def pairing_product_is_one(pairs) -> bool:
    """prod e(p_i, q_i) == 1 for pairs of (G1, G2): the check the alt_bn128 pairing syscall makes"""
    f = F12_ONE
    for p, q in pairs:
        f = f12_mul(f, miller_loop(q, p))
    return final_exponentiation(f) == F12_ONE


def pairing(p, q):
    return final_exponentiation(miller_loop(q, p))


G1_GEN = (1, 2)
G2_GEN = (
    (10857046999023057135944570762232829481370756359578518086990519993285655852781,
     11559732032986387107991004021392285783925812861821192530917403151452391805634),
    (8495653923123431417604973247489272438418190587263600148770280649306958101930,
     4082367875863433681332203403145435568316851327593401208105741076214120093531),
)

# ---- bytes (big-endian, syscall layout) ----


def _int(b: bytes) -> int:
    return int.from_bytes(b, "big")


def g1_from_bytes(b: bytes):
    if len(b) != 64:
        raise ValueError("G1 is 64 bytes")
    if not any(b):
        return None
    pt = (_int(b[:32]), _int(b[32:]))
    if not g1_on_curve(pt):
        raise ValueError("G1 point not on the curve")
    return pt


def g1_to_bytes(pt) -> bytes:
    if pt is None:
        return bytes(64)
    return pt[0].to_bytes(32, "big") + pt[1].to_bytes(32, "big")


def g2_from_bytes(b: bytes):
    if len(b) != 128:
        raise ValueError("G2 is 128 bytes")
    if not any(b):
        return None
    pt = ((_int(b[32:64]), _int(b[:32])), (_int(b[96:]), _int(b[64:96])))
    if not g2_on_curve(pt):
        raise ValueError("G2 point not on the twist")
    if not g2_in_subgroup(pt):
        raise ValueError("G2 point not in the order-r subgroup")
    return pt
