"""Scores circuit.py for lethe (or any harness): one JSON line, lower TQ is better."""

import json
import random

from kickmix import TASKS, corpus_path, evaluate_file

task = TASKS["add32"]
result = evaluate_file(task, "circuit.py", seed=random.randrange(2**31), corpus=corpus_path(task))
print(json.dumps({"score": result.tq if result.valid else None, "feedback": result.summary()}))
