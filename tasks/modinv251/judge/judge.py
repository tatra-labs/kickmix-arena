"""Scores circuit.py for lethe (or any harness): one JSON line, lower TQ is better."""

import json
import random

from kickmix import TASKS, evaluate_file

result = evaluate_file(TASKS["modinv251"], "circuit.py", seed=random.randrange(2**31))
print(json.dumps({"score": result.tq if result.valid else None, "feedback": result.summary()}))
