"""Starting candidate: a < b is the carry out of (NOT a) + b. Carries are uncomputed with Toffolis."""


def build(c, a, b, t):
    n = len(a)
    for q in a:
        c.x(q)
    carry = c.alloc(n, "carry")  # carry[i] is the carry out of bit i
    for i in range(n):
        if i:
            c.cx(carry[i - 1], a[i])
            c.cx(carry[i - 1], b[i])
        c.ccx(a[i], b[i], carry[i])
        if i:
            c.cx(carry[i - 1], carry[i])
    c.cx(carry[n - 1], t[0])
    for i in reversed(range(n)):
        if i:
            c.cx(carry[i - 1], carry[i])
        c.ccx(a[i], b[i], carry[i])
        if i:
            c.cx(carry[i - 1], b[i])
            c.cx(carry[i - 1], a[i])
    for q in a:
        c.x(q)
    c.free(carry)
