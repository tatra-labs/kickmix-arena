"""Arena tasks: reversible arithmetic primitives that dominate the cost of quantum algorithms.

A task names its registers (allocated by the evaluator, in order, and passed to `build`), gives the
required final value of every register as a function of the initial values, and samples inputs.
Output registers start from random values, so a circuit must truly compute (y XOR f(x), or an
in-place update), not assume they start at zero.

Uniform inputs almost never hit the cases that break arithmetic circuits (a carry rippling through
all 32 bits has probability 2^-32), so every task also has fixed corner cases and a sampler of
structured inputs, stratified by the length of the hard part.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Task:
    name: str
    summary: str
    registers: tuple[tuple[str, int], ...]
    target: Callable[[dict[str, int]], dict[str, int]]
    sample: Callable[[random.Random], dict[str, int]]
    references: dict[str, tuple[int, int]] = field(default_factory=dict)  # known circuits: (T, Q)
    edge: Callable[[random.Random], dict[str, int]] | None = None  # structured inputs; default: _edge values
    fixed: tuple[dict[str, int], ...] | None = None  # checked every time; default: all corner combinations

    @property
    def signature(self) -> str:
        return f"build(c, {', '.join(name for name, _ in self.registers)})"

    def corners(self) -> list[dict[str, int]]:
        """Inputs checked on every evaluation: by default every mix of 0, 1, top bit only and all ones."""
        if self.fixed is not None:
            return list(self.fixed)
        names = [name for name, _ in self.registers]
        values = [sorted({0, 1, 1 << (w - 1), 2**w - 1}) for _, w in self.registers]
        return [dict(zip(names, combo)) for combo in itertools.product(*values)]

    def sample_edge(self, rng: random.Random) -> dict[str, int]:
        if self.edge:
            return self.edge(rng)
        return {name: _edge(rng, width) for name, width in self.registers}


def _uniform(rng: random.Random, registers) -> dict[str, int]:
    return {name: rng.getrandbits(width) for name, width in registers}


def _edge(rng: random.Random, width: int) -> int:
    """A structured value that uniform sampling almost never draws."""
    ones, kind = 2**width - 1, rng.randrange(6)
    if kind == 0:
        return rng.choice((0, ones))
    if kind in (1, 2):  # one bit set, or all bits but one
        return (1 << rng.randrange(width)) ^ (ones if kind == 2 else 0)
    if kind == 3:  # a run of ones of random length and position
        length = rng.randint(1, width)
        return (2**length - 1) << rng.randint(0, width - length)
    return rng.getrandbits(width)


def _carry_chain(rng: random.Random, n: int) -> dict[str, int]:
    """a, b whose sum carries through about L bits, with L uniform in [0, n]: b = -a mod 2^L below."""
    a, length = rng.getrandbits(n), rng.randint(0, n)
    return {"a": a, "b": (-a) % 2**length | rng.getrandbits(n - length) << length}


def _common_prefix(rng: random.Random, n: int) -> dict[str, int]:
    """a, b that agree on their top L bits, L uniform in [0, n], so a < b is decided late (or a = b)."""
    a, low = rng.getrandbits(n), n - rng.randint(0, n)
    return {"a": a, "b": a >> low << low | rng.getrandbits(low)}


def _either(sampler, registers):
    """Half from `sampler`, half structured values per register; other registers get structured values."""
    def sample(rng):
        values = {name: _edge(rng, width) for name, width in registers}
        return {**values, **sampler(rng)} if rng.random() < 0.5 else values
    return sample


def add(n: int = 32) -> Task:
    regs = (("a", n), ("b", n))
    return Task(
        f"add{n}", f"In-place addition: b <- (a + b) mod 2^{n}, a unchanged.", regs,
        lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % 2 ** n},
        lambda rng: _uniform(rng, regs),
        {"Cuccaro et al. 2004 ripple-carry": (2 * n, 2 * n + 1),
         "Gidney 2018 (measurement-based uncomputation)": (n - 1, 3 * n - 1)},
        edge=_either(lambda rng: _carry_chain(rng, n), regs),
    )


def compare(n: int = 32) -> Task:
    regs = (("a", n), ("b", n), ("t", 1))
    return Task(
        f"compare{n}", f"Comparison: t <- t XOR [a < b] for {n}-bit unsigned a, b, both unchanged.", regs,
        lambda v: {"a": v["a"], "b": v["b"], "t": v["t"] ^ int(v["a"] < v["b"])},
        lambda rng: _uniform(rng, regs),
        edge=_either(lambda rng: _common_prefix(rng, n), regs),
    )


def multiply_add(n: int = 16) -> Task:
    regs = (("a", n), ("b", n), ("p", 2 * n))
    return Task(
        f"madd{n}", f"Multiply-accumulate: p <- (p + a*b) mod 2^{2 * n}, a and b unchanged.", regs,
        lambda v: {"a": v["a"], "b": v["b"], "p": (v["p"] + v["a"] * v["b"]) % 2 ** (2 * n)},
        lambda rng: _uniform(rng, regs),
    )


def conditional_multiply_add(n: int = 8) -> Task:
    """The paper's example of conditional routing: one multiply-add whose operand depends on s."""
    regs = (("s", 1), ("k", n), ("x", n), ("y", n), ("z", n))
    return Task(
        f"cmadd{n}", f"Conditional multiply-add: x <- x + k*y if s = 0, else x + k*z (mod 2^{n}); "
                     "s, k, y and z unchanged.", regs,
        lambda v: {**v, "x": (v["x"] + v["k"] * (v["z"] if v["s"] else v["y"])) % 2 ** n},
        lambda rng: _uniform(rng, regs),
    )


def modular_inverse(p: int = 251) -> Task:
    n = p.bit_length()
    regs = (("x", n), ("y", n))
    return Task(
        f"modinv{p}", f"Prime-field inversion: y <- y XOR x^-1 mod {p} for x in [1, {p - 1}], x unchanged.", regs,
        lambda v: {"x": v["x"], "y": v["y"] ^ pow(v["x"], -1, p)},
        lambda rng: {"x": rng.randrange(1, p), "y": rng.getrandbits(n)},
        edge=lambda rng: {"x": rng.randrange(1, p), "y": _edge(rng, n)},
        fixed=tuple({"x": x, "y": (0, 2**n - 1)[x % 2]} for x in range(1, p)),  # every x: exhaustive
    )


TASKS: dict[str, Task] = {t.name: t for t in (add(), compare(), multiply_add(), conditional_multiply_add(),
                                              modular_inverse())}
