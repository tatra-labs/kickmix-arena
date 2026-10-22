"""python -m kickmix.record TASK CANDIDATE.py: print the operations the candidate's circuit performs."""

import sys

from .evaluate import _record

if __name__ == "__main__":
    _record(sys.argv[1], sys.argv[2])
