"""Starting candidate: two controlled multiply-adds, one per value of s (the naive translation)."""


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


def controlled_multiply_add(c, ctl, m, v, x):
    """x <- x + m*v (mod 2^n) when ctl is 1."""
    n = len(x)
    for i in range(n):
        (g,) = c.alloc(1)
        c.ccx(ctl, m[i], g)  # g = ctl AND m_i
        tmp = c.alloc(n - i)  # tmp = v if g else 0, truncated to the width of x[i:]
        for j in range(n - i):
            c.ccx(g, v[j], tmp[j])
        add(c, tmp, x[i:])
        for j in range(n - i):
            c.ccx(g, v[j], tmp[j])
        c.free(tmp)
        c.ccx(ctl, m[i], g)
        c.free(g)


def build(c, s, k, x, y, z):
    (sel,) = s
    c.x(sel)
    controlled_multiply_add(c, sel, k, y, x)  # s = 0: x += k*y
    c.x(sel)
    controlled_multiply_add(c, sel, k, z, x)  # s = 1: x += k*z
