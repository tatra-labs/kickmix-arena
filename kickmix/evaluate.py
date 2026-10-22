"""Check a candidate circuit on random trajectories and score it by Toffolis x peak qubits.

`evaluate` runs a build function in-process (fast, for your own code). `evaluate_file` runs an
untrusted candidate file in a separate process that only returns the circuit it built, as plain
data; this process replays and scores it, so candidate code never touches the counters.
"""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .circuit import Circuit, CircuitError
from .tasks import TASKS, Task


@dataclass
class Result:
    valid: bool
    toffolis: int
    qubits: int
    failures: int
    trajectories: int
    message: str

    @property
    def tq(self) -> int:
        return self.toffolis * self.qubits

    def summary(self) -> str:
        return f"T={self.toffolis:,}  Q={self.qubits:,}  TQ={self.tq:,}  ({self.message})"


def evaluate(task: Task, build: Callable, trajectories: int = 4096, seed: int = 0,
             failure_budget: float = 0.0) -> Result:
    """Score `build(c, **registers)` on random trajectories, each with its own measurement outcomes."""
    return _score(task, lambda c, regs: build(c, **regs), trajectories, seed, failure_budget)


def evaluate_file(task: Task, path: str | Path, trajectories: int = 4096, seed: int = 0,
                  failure_budget: float = 0.0, timeout: float = 300) -> Result:
    """Score an untrusted candidate file: build it in a child process, replay its gates here."""
    try:
        proc = subprocess.run([sys.executable, "-P", "-m", "kickmix.record", task.name, str(Path(path).resolve())],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Result(False, 0, 0, trajectories, trajectories, f"building the circuit took over {timeout:.0f}s")
    try:
        ops = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        error = (proc.stderr or proc.stdout).strip().splitlines()
        return Result(False, 0, 0, trajectories, trajectories,
                      "build() failed: " + (error[-1] if error else f"exit code {proc.returncode}"))
    if isinstance(ops, dict):  # the child reports an error as {"error": ...}
        return Result(False, 0, 0, trajectories, trajectories, ops["error"])
    return _score(task, lambda c, regs: c.replay(ops), trajectories, seed, failure_budget)


def _score(task: Task, run: Callable, trajectories: int, seed: int, failure_budget: float) -> Result:
    rng = random.Random(seed)
    inputs = [task.sample(rng) for _ in range(trajectories)]
    c = Circuit(trajectories, seed)
    regs = allocate(c, task)
    for name, reg in regs.items():
        c.load(reg, [inp[name] for inp in inputs])
    io = {q for reg in regs.values() for q in reg}

    def fail(message: str) -> Result:
        return Result(False, c.toffolis, c.peak, trajectories, trajectories, message)

    try:
        run(c, regs)
    except CircuitError as e:
        return fail(f"circuit rule broken: {e}")
    except Exception as e:  # noqa: BLE001 - any crash of the candidate makes it invalid
        frame = traceback.extract_tb(e.__traceback__)[-1]
        return fail(f"build() raised {type(e).__name__}: {e} (line {frame.lineno}: {frame.line})")
    if missing := [q for q in io if q not in c.bits]:
        return fail(f"{len(missing)} input/output qubits were freed")
    if leaked := [q for q in c.bits if q not in io]:
        return fail(f"{len(leaked)} ancilla qubits were never freed (free them once they are back to |0>)")

    actual = {name: c.read(reg) for name, reg in regs.items()}
    failures, example = 0, ""
    for k, inp in enumerate(inputs):
        want = task.target(inp)
        wrong = [name for name in want if actual[name][k] != want[name]]
        flipped = (c.phase >> k) & 1
        if wrong or flipped:
            failures += 1
            if not example:
                expected = {name: want[name] for name in wrong}
                got = {name: actual[name][k] for name in wrong}
                example = (f"for input {inp}: got {got}, expected {expected}" if wrong
                           else f"for input {inp}: the sign of this trajectory is flipped (uncancelled phase kick)")
    allowed = int(failure_budget * trajectories)
    message = (f"{failures} of {trajectories} trajectories fail ({allowed} allowed); e.g. {example}" if failures
               else f"correct on {trajectories} random trajectories")
    return Result(failures <= allowed, c.toffolis, c.peak, failures, trajectories, message)


def allocate(c: Circuit, task: Task) -> dict:
    """The task's registers, allocated first and in order (so their qubit ids are the same everywhere)."""
    return {name: c.alloc(width, name) for name, width in task.registers}


def load_build(path: str | Path) -> Callable:
    """Import `build` from a candidate file."""
    spec = importlib.util.spec_from_file_location("candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build


def _record(task_name: str, path: str) -> None:
    """Child process: build the candidate on a one-trajectory circuit and print its operations."""
    c = Circuit(trajectories=1)
    regs = allocate(c, TASKS[task_name])
    c.ops.clear()  # the scorer allocates the task registers itself; record only what build() does
    try:
        load_build(path)(c, **regs)
        print("\n" + json.dumps(c.ops))
    except Exception as e:  # noqa: BLE001
        frame = traceback.extract_tb(e.__traceback__)[-1]
        print("\n" + json.dumps({"error": f"build() raised {type(e).__name__}: {e} "
                                          f"(line {frame.lineno}: {frame.line})"}))
