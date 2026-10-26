"""Check a candidate circuit on random trajectories and score it by Toffolis x peak qubits.

`evaluate` runs a build function in-process (fast, for your own code). `evaluate_file` runs an
untrusted candidate file in a separate process that only returns the circuit it built, as plain
data; this process replays and scores it, so candidate code never touches the counters.

Every evaluation checks `trajectories` uniform random inputs (the statistical guarantee), plus the
task's corner cases, a quarter as many structured inputs, and, with a corpus, inputs that broke
earlier candidates: a bug found once is checked for in every later candidate.
"""

from __future__ import annotations

import importlib.util
import json
import os
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
             failure_budget: float = 0.0, corpus: str | Path | None = None) -> Result:
    """Score `build(c, **registers)` on random trajectories, each with its own measurement outcomes."""
    return _score(task, lambda c, regs: build(c, **regs), trajectories, seed, failure_budget, corpus)


def evaluate_file(task: Task, path: str | Path, trajectories: int = 4096, seed: int = 0,
                  failure_budget: float = 0.0, timeout: float = 300, corpus: str | Path | None = None) -> Result:
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
    return _score(task, lambda c, regs: c.replay(ops), trajectories, seed, failure_budget, corpus)


def corpus_path(task: Task) -> Path:
    """Where the judges keep inputs that broke earlier candidates: $KICKMIX_HOME or ~/.kickmix."""
    return Path(os.environ.get("KICKMIX_HOME", Path.home() / ".kickmix")) / f"{task.name}.jsonl"


def _score(task: Task, run: Callable, trajectories: int, seed: int, failure_budget: float,
           corpus: str | Path | None = None) -> Result:
    rng = random.Random(seed)
    found = _load_corpus(task, corpus)
    edges = task.corners() + found + [task.sample_edge(rng) for _ in range(trajectories // 4)]
    inputs = [task.sample(rng) for _ in range(trajectories)] + edges
    trajectories = len(inputs)
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
    failures, example, broke = 0, "", []
    for k, inp in enumerate(inputs):
        want = task.target(inp)
        wrong = [name for name in want if actual[name][k] != want[name]]
        flipped = (c.phase >> k) & 1
        if wrong or flipped:
            failures += 1
            broke.append(inp)
            if not example:
                expected = {name: want[name] for name in wrong}
                got = {name: actual[name][k] for name in wrong}
                example = (f"for input {inp}: got {got}, expected {expected}" if wrong
                           else f"for input {inp}: the sign of this trajectory is flipped (uncancelled phase kick)")
    _save_corpus(corpus, broke, found)
    allowed = int(failure_budget * trajectories)
    checked = f"{trajectories - len(edges):,} uniform + {len(edges):,} edge-case trajectories"
    message = (f"{failures} of {checked} fail ({allowed} allowed); e.g. {example}" if failures
               else f"correct on {checked}" + (f", {len(found)} of them inputs that broke earlier circuits"
                                               if found else ""))
    return Result(failures <= allowed, c.toffolis, c.peak, failures, trajectories, message)


def _load_corpus(task: Task, corpus: str | Path | None, keep: int = 1024) -> list[dict[str, int]]:
    """The most recent inputs that broke earlier candidates, masked to the task's register widths."""
    if not corpus or not Path(corpus).exists():
        return []
    rows = []
    for line in Path(corpus).read_text(encoding="utf-8").splitlines()[-keep:]:
        try:
            row = json.loads(line)
            row = {name: int(row[name]) % 2**width for name, width in task.registers}
            task.target(row)  # skip inputs outside the task's domain
            rows.append(row)
        except (ValueError, KeyError, TypeError):
            continue
    return rows


def _save_corpus(corpus: str | Path | None, broke: list[dict[str, int]], known: list[dict[str, int]],
                 per_run: int = 8) -> None:
    """Append a few new failing inputs; one line each, so parallel judges can share the file."""
    if not corpus:
        return
    seen = {json.dumps(row, sort_keys=True) for row in known}
    new = [line for line in dict.fromkeys(json.dumps(row, sort_keys=True) for row in broke) if line not in seen]
    if new:
        Path(corpus).parent.mkdir(parents=True, exist_ok=True)
        with open(corpus, "a", encoding="utf-8") as f:
            f.writelines(line + "\n" for line in new[:per_run])


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
