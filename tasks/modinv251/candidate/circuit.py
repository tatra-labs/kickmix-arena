"""Starting candidate: a lookup table. For every x in [1, 250], detect x == v with a chain of
Toffolis and copy v^-1 into y. Correct for any function, and expensive."""

P = 251


def build(c, x, y):
    n = len(x)
    chain = c.alloc(n - 1)
    for v in range(1, P):
        inverse = pow(v, -1, P)
        zeros = [i for i in range(n) if not (v >> i) & 1]
        for i in zeros:
            c.x(x[i])  # now every bit of x is 1 exactly when x == v
        c.ccx(x[0], x[1], chain[0])
        for i in range(2, n):
            c.ccx(chain[i - 2], x[i], chain[i - 1])
        for j in range(n):
            if (inverse >> j) & 1:
                c.cx(chain[-1], y[j])
        for i in reversed(range(2, n)):
            c.ccx(chain[i - 2], x[i], chain[i - 1])
        c.ccx(x[0], x[1], chain[0])
        for i in zeros:
            c.x(x[i])
    c.free(chain)
