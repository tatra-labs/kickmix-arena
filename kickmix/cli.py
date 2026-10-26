"""kickmix tasks | eval TASK FILE | init TASK DIR"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .docs import task_markdown
from .evaluate import corpus_path, evaluate_file
from .tasks import TASKS

ROOT = Path(__file__).resolve().parents[1]

JUDGE = '''"""Scores circuit.py for lethe (or any harness): one JSON line, lower TQ is better."""

import json
import random

from kickmix import TASKS, corpus_path, evaluate_file

task = TASKS["{name}"]
result = evaluate_file(task, "circuit.py", seed=random.randrange(2**31), corpus=corpus_path(task))
print(json.dumps({{"score": result.tq if result.valid else None, "feedback": result.summary()}}))
'''

TOML = '''name = "{name}"
files = ["circuit.py"]
judge = "{{python}} -P judge.py"
direction = "min"
timeout = 600
'''


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="kickmix", description="An arena for cheaper reversible quantum circuits.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("tasks", help="list tasks with their starting and reference costs")
    e = sub.add_parser("eval", help="verify and score a candidate file")
    e.add_argument("task", choices=TASKS)
    e.add_argument("file")
    e.add_argument("--trajectories", type=int, default=4096)
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--no-corpus", action="store_true", help="do not replay or record inputs that broke earlier circuits")
    i = sub.add_parser("init", help="write a lethe-compatible task directory")
    i.add_argument("task", choices=TASKS)
    i.add_argument("dir")
    args = p.parse_args(argv)

    if args.command == "tasks":
        for name, task in TASKS.items():
            r = evaluate_file(task, start_file(name), trajectories=256)
            refs = "; ".join(f"{k}: TQ {t * q:,}" for k, (t, q) in task.references.items())
            print(f"{name:<10} start TQ {r.tq:>9,}  {task.summary}" + (f"  [{refs}]" if refs else ""))
    elif args.command == "eval":
        task = TASKS[args.task]
        r = evaluate_file(task, args.file, args.trajectories, args.seed, corpus=None if args.no_corpus else corpus_path(task))
        print(("VALID   " if r.valid else "INVALID ") + r.summary())
    else:
        write_task(args.task, Path(args.dir))
        print(f"wrote {args.dir}: run it with  lethe run {args.dir} ...")


def start_file(name: str) -> Path:
    return ROOT / "tasks" / name / "candidate" / "circuit.py"


def write_task(name: str, out: Path) -> None:
    """task.toml, TASK.md, candidate/circuit.py and judge/judge.py for one task."""
    task = TASKS[name]
    start = evaluate_file(task, start_file(name), trajectories=256)
    (out / "candidate").mkdir(parents=True, exist_ok=True)
    (out / "judge").mkdir(exist_ok=True)
    if (out / "candidate" / "circuit.py").resolve() != start_file(name).resolve():
        shutil.copy(start_file(name), out / "candidate" / "circuit.py")
    (out / "task.toml").write_text(TOML.format(name=name), encoding="utf-8")
    (out / "TASK.md").write_text(task_markdown(task, (start.toffolis, start.qubits)), encoding="utf-8")
    (out / "judge" / "judge.py").write_text(JUDGE.format(name=name), encoding="utf-8")


if __name__ == "__main__":
    main()
