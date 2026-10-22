"""Starting candidate: a ripple-carry adder whose carries are uncomputed with Toffolis."""


def build(c, a, b):
    n = len(a)
    carry = c.alloc(n - 1, "carry")  # carry[i] is the carry into bit i + 1
    for i in range(n - 1):
        if i:
            c.cx(carry[i - 1], a[i])
            c.cx(carry[i - 1], b[i])
        c.ccx(a[i], b[i], carry[i])  # with a, b xored by the incoming carry: carry = maj(a, b, cin)
        if i:
            c.cx(carry[i - 1], carry[i])
    c.cx(a[n - 1], b[n - 1])  # top sum bit; the carry out of it is dropped (mod 2^n)
    if n > 1:
        c.cx(carry[n - 2], b[n - 1])
    for i in reversed(range(n - 1)):
        if i:
            c.cx(carry[i - 1], carry[i])
        c.ccx(a[i], b[i], carry[i])  # uncompute the carry
        if i:
            c.cx(carry[i - 1], a[i])
        c.cx(a[i], b[i])  # b_i ^ cin_i ^ a_i: the sum bit
    c.free(carry)
