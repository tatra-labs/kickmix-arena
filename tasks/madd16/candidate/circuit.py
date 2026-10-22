"""Starting candidate: schoolbook multiply-accumulate, one controlled addition per bit of b."""


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


def build(c, a, b, p):
    n = len(a)
    for i in range(n):
        width = len(p) - i
        tmp = c.alloc(width)  # tmp = a if b_i else 0, zero-extended to the width of p[i:]
        for j in range(min(n, width)):
            c.ccx(b[i], a[j], tmp[j])
        add(c, tmp, p[i:])
        for j in range(min(n, width)):
            c.ccx(b[i], a[j], tmp[j])
        c.free(tmp)
