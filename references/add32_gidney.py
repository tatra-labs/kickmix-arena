"""Gidney 2018, "Halving the cost of quantum addition": carries uncomputed by X-basis measurement.

The uncomputation of each carry's logical AND costs no Toffoli: measuring it kicks a sign that a
classically controlled CZ cancels. n - 1 Toffolis, 3n - 1 qubits.
"""


def build(c, a, b):
    n = len(a)
    carry = c.alloc(n - 1, "carry")
    for i in range(n - 1):
        if i:
            c.cx(carry[i - 1], a[i])
            c.cx(carry[i - 1], b[i])
        c.ccx(a[i], b[i], carry[i])
        if i:
            c.cx(carry[i - 1], carry[i])
    c.cx(a[n - 1], b[n - 1])
    if n > 1:
        c.cx(carry[n - 2], b[n - 1])
    for i in reversed(range(n - 1)):
        if i:
            c.cx(carry[i - 1], carry[i])
        r = c.mx(carry[i])  # carry[i] holds a_i AND b_i here; measuring it costs no Toffoli
        c.cz(a[i], b[i], when=r)  # cancel the phase kick
        if i:
            c.cx(carry[i - 1], a[i])
        c.cx(a[i], b[i])
    c.free(carry)
