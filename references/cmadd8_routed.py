"""Conditional routing, the first design principle of Gu et al. (2026).

Instead of two controlled multiply-adds, swap y and z when s = 1, do one *uncontrolled*
multiply-add with y, and swap back: the branch only decides which data goes through the
expensive arithmetic.
"""


def add(c, x, y):
    """y <- y + x (mod 2^len(y)), len(x) == len(y); ripple carry, Toffoli uncomputation."""
    n = len(y)
    if n == 1:
        c.cx(x[0], y[0])
        return
    carry = c.alloc(n - 1)
    for i in range(n - 1):
        if i:
            c.cx(carry[i - 1], x[i])
            c.cx(carry[i - 1], y[i])
        c.ccx(x[i], y[i], carry[i])
        if i:
            c.cx(carry[i - 1], carry[i])
    c.cx(x[n - 1], y[n - 1])
    c.cx(carry[n - 2], y[n - 1])
    for i in reversed(range(n - 1)):
        if i:
            c.cx(carry[i - 1], carry[i])
        c.ccx(x[i], y[i], carry[i])
        if i:
            c.cx(carry[i - 1], x[i])
        c.cx(x[i], y[i])
    c.free(carry)


def multiply_add(c, m, v, x):
    """x <- x + m*v (mod 2^n), uncontrolled: each bit of m gates one addition."""
    n = len(x)
    for i in range(n):
        tmp = c.alloc(n - i)
        for j in range(n - i):
            c.ccx(m[i], v[j], tmp[j])
        add(c, tmp, x[i:])
        for j in range(n - i):
            c.ccx(m[i], v[j], tmp[j])
        c.free(tmp)


def build(c, s, k, x, y, z):
    (sel,) = s
    for a, b in zip(y, z):
        c.cswap(sel, a, b)
    multiply_add(c, k, y, x)
    for a, b in zip(y, z):
        c.cswap(sel, a, b)
