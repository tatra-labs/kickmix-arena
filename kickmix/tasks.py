"""Arena tasks: reversible arithmetic primitives that dominate the cost of quantum algorithms.

A task names its registers (allocated by the evaluator, in order, and passed to `build`), gives the
required final value of every register as a function of the initial values, and samples inputs.
Output registers start from random values, so a circuit must truly compute (y XOR f(x), or an
in-place update), not assume they start at zero.
"""

from __future__ import annotations

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

    @property
    def signature(self) -> str:
        return f"build(c, {', '.join(name for name, _ in self.registers)})"


def _uniform(rng: random.Random, registers) -> dict[str, int]:
    return {name: rng.getrandbits(width) for name, width in registers}


def add(n: int = 32) -> Task:
    regs = (("a", n), ("b", n))
    return Task(
        f"add{n}", f"In-place addition: b <- (a + b) mod 2^{n}, a unchanged.", regs,
        lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % 2 ** n},
        lambda rng: _uniform(rng, regs),
        {"Cuccaro et al. 2004 ripple-carry": (2 * n, 2 * n + 1),
         "Gidney 2018 (measurement-based uncomputation)": (n - 1, 3 * n - 1)},
    )


def compare(n: int = 32) -> Task:
    regs = (("a", n), ("b", n), ("t", 1))
    return Task(
        f"compare{n}", f"Comparison: t <- t XOR [a < b] for {n}-bit unsigned a, b, both unchanged.", regs,
        lambda v: {"a": v["a"], "b": v["b"], "t": v["t"] ^ int(v["a"] < v["b"])},
        lambda rng: _uniform(rng, regs),
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
    )


TASKS: dict[str, Task] = {t.name: t for t in (add(), compare(), multiply_add(), conditional_multiply_add(),
                                              modular_inverse())}
