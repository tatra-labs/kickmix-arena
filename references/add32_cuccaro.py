"""Cuccaro, Draper, Kutin and Moulton 2004: the MAJ/UMA ripple-carry adder with one ancilla."""


def build(c, a, b):
    n = len(a)
    (anc,) = c.alloc(1, "anc")

    def maj(x, y, z):
        c.cx(z, y)
        c.cx(z, x)
        c.ccx(x, y, z)

    def uma(x, y, z):
        c.ccx(x, y, z)
        c.cx(z, x)
        c.cx(x, y)

    maj(anc, b[0], a[0])
    for i in range(1, n):
        maj(a[i - 1], b[i], a[i])
    for i in reversed(range(1, n)):
        uma(a[i - 1], b[i], a[i])
    uma(anc, b[0], a[0])
    c.free(anc)
