"""A kickmix circuit builder that simulates, counts and records as you build.

kickmix circuits (classical reversible gates, sign gates, and X-basis measurements used for
uncomputation) map computational-basis states to computational-basis states with a sign. So a
circuit's action on any input is a bit string plus one sign bit, and many inputs can be simulated
at once: every qubit here is a Python int whose bit k is that qubit's value in trajectory k.

Every X-basis measurement draws an independent uniformly random outcome per trajectory, kicks the
phase (-1)^(r * value) and returns the qubit to |0>. Outcomes are classical Bits; they may control
sign gates (to cancel the kick) but never gates that change the stored bits.

Every operation is also appended to `ops` as plain data, so a circuit built in an untrusted process
can be replayed and scored by a fresh Circuit elsewhere (see `replay`).
"""

from __future__ import annotations

import random


class CircuitError(Exception):
    """A rule of the circuit model was broken: the candidate is invalid."""


class Bit:
    """A classical measurement record, one bit per trajectory: the XOR of some measurement outcomes."""

    __slots__ = ("v", "ids")

    def __init__(self, v: int, ids: frozenset):
        self.v, self.ids = v, ids

    def __xor__(self, other: Bit) -> Bit:
        return Bit(self.v ^ other.v, self.ids ^ other.ids)


class Reg(list):
    """A register: a list of qubit ids, least significant bit first."""

    def __init__(self, qubits, name: str = ""):
        super().__init__(qubits)
        self.name = name

    def __getitem__(self, i):
        out = super().__getitem__(i)
        return Reg(out, self.name) if isinstance(i, slice) else out


class Circuit:
    def __init__(self, trajectories: int = 4096, seed: int = 0):
        self.k = trajectories
        self.ones = (1 << trajectories) - 1
        self.rng = random.Random(seed)
        self.bits: dict[int, int] = {}  # live qubit id -> its value in every trajectory
        self.phase = 0  # sign bit of every trajectory
        self.outcomes: list[int] = []  # every measurement's outcomes
        self.ops: list[tuple] = []
        self.toffolis = 0
        self.peak = 0
        self._next = 0

    # -- qubits ---------------------------------------------------------------------------

    def alloc(self, n: int = 1, name: str = "") -> Reg:
        """n fresh qubits in |0>."""
        reg = Reg(range(self._next, self._next + n), name)
        self.ops.append(("alloc", n))
        self._next += n
        for q in reg:
            self.bits[q] = 0
        self.peak = max(self.peak, len(self.bits))
        return reg

    def free(self, *qubits) -> None:
        """Release qubits; each must be back in |0> on every trajectory."""
        qs = list(_flat(qubits))
        self.ops.append(("free", qs))
        for q in qs:
            v = self._live(q)
            if v:
                raise CircuitError(f"qubit {q} freed while still 1 in {bin(v).count('1')} of {self.k} trajectories")
            del self.bits[q]

    # -- reversible gates (change bits) ---------------------------------------------------

    def x(self, q: int) -> None:
        self.ops.append(("x", q))
        self.bits[q] = self._live(q) ^ self.ones

    def cx(self, control: int, target: int) -> None:
        self._op("cx", control, target)
        self.bits[target] = self._live(target) ^ self._live(control)

    def ccx(self, a: int, b: int, target: int) -> None:
        """Toffoli: counts 1."""
        self._op("ccx", a, b, target)
        self.bits[target] = self._live(target) ^ (self._live(a) & self._live(b))
        self.toffolis += 1

    def swap(self, a: int, b: int) -> None:
        self._op("swap", a, b)
        self.bits[a], self.bits[b] = self._live(b), self._live(a)

    def cswap(self, control: int, a: int, b: int) -> None:
        """Fredkin: counts 1 Toffoli."""
        self._op("cswap", control, a, b)
        va, vb = self._live(a), self._live(b)
        diff = (va ^ vb) & self._live(control)
        self.bits[a], self.bits[b] = va ^ diff, vb ^ diff
        self.toffolis += 1

    # -- sign gates (change only the phase); `when` applies them on trajectories where a Bit is 1 --

    def z(self, q: int, when: Bit | None = None) -> None:
        self._sign("z", (q,), when, self._live(q))

    def cz(self, a: int, b: int, when: Bit | None = None) -> None:
        self._sign("cz", (a, b), when, self._live(a) & self._live(b))

    def ccz(self, a: int, b: int, c: int, when: Bit | None = None) -> None:
        """Counts 1 Toffoli, like a Toffoli."""
        self._sign("ccz", (a, b, c), when, self._live(a) & self._live(b) & self._live(c))
        self.toffolis += 1

    def flip(self, when: Bit | None = None) -> None:
        """A global sign flip (free)."""
        self._sign("flip", (), when, self.ones)

    # -- measurement-based uncomputation ---------------------------------------------------

    def mx(self, q: int) -> Bit:
        """Measure q in the X basis: a random outcome r per trajectory kicks (-1)^(r*q) and q becomes 0."""
        self.ops.append(("mx", q))
        r = self.rng.getrandbits(self.k)
        self.phase ^= r & self._live(q)
        self.bits[q] = 0
        self.outcomes.append(r)
        return Bit(r, frozenset({len(self.outcomes) - 1}))

    # -- helpers ----------------------------------------------------------------------------

    def _op(self, name: str, *qubits: int) -> None:
        self._check(name, qubits)
        if len(set(qubits)) != len(qubits):
            raise CircuitError(f"{name} used the same qubit twice: {qubits}")
        self.ops.append((name, *qubits))

    def _sign(self, name: str, qubits: tuple, when: Bit | None, mask: int) -> None:
        self._check(name, qubits)
        if len(set(qubits)) != len(qubits):
            raise CircuitError(f"{name} used the same qubit twice: {qubits}")
        self.ops.append((name, list(qubits), sorted(when.ids) if when is not None else None))
        self.phase ^= mask if when is None else mask & when.v

    @staticmethod
    def _check(name: str, qubits: tuple) -> None:
        for q in qubits:
            if not isinstance(q, int):
                raise CircuitError(f"{name} expects qubits (ints), got {type(q).__name__} {q!r}; "
                                   "index a register, e.g. reg[0]")

    def _live(self, q: int) -> int:
        try:
            return self.bits[q]
        except (KeyError, TypeError):
            raise CircuitError(f"qubit {q!r} is not allocated") from None

    # -- loading and reading values, and replaying recorded circuits ---------------------------

    def load(self, reg: Reg, values: list[int]) -> None:
        for i, q in enumerate(reg):
            word = 0
            for k, v in enumerate(values):
                word |= ((v >> i) & 1) << k
            self.bits[q] = word

    def read(self, reg: Reg) -> list[int]:
        words = [self._live(q) for q in reg]
        return [sum(((w >> k) & 1) << i for i, w in enumerate(words)) for k in range(self.k)]

    def replay(self, ops: list) -> None:
        """Apply recorded operations (e.g. from an untrusted process) to this circuit."""
        for op in ops:
            name, args = op[0], op[1:]
            if name == "alloc":
                self.alloc(int(args[0]))
            elif name == "free":
                self.free(list(args[0]))
            elif name == "mx":
                self.mx(args[0])
            elif name in ("x", "cx", "ccx", "swap", "cswap"):
                getattr(self, name)(*args)
            elif name in ("z", "cz", "ccz", "flip"):
                qubits, ids = args
                when = None
                if ids is not None:
                    if any(not 0 <= i < len(self.outcomes) for i in ids):
                        raise CircuitError("a sign gate referred to a measurement that has not happened")
                    v = 0
                    for i in ids:
                        v ^= self.outcomes[i]
                    when = Bit(v, frozenset(ids))
                getattr(self, name)(*qubits, when=when)
            else:
                raise CircuitError(f"unknown operation {name!r}")


def _flat(items):
    for item in items:
        if isinstance(item, (list, tuple)):
            yield from item
        else:
            yield item
