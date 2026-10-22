"""What an agent is told: the circuit model, the API, and one task."""

from .tasks import Task

MODEL = """\
## The circuit model

You write Python that builds a *kickmix* circuit: classical reversible gates, sign gates and
X-basis measurements. Such a circuit maps every computational-basis input to one basis state with
a sign, so it is checked exactly by simulating many random inputs at once. Your file defines
`{signature}`. The task's registers arrive already allocated and loaded (lists of qubit ids, least
significant bit first); `c` is the circuit:

| call | effect | Toffoli count |
|---|---|---|
| `c.alloc(n)` / `c.free(*qubits)` | get n qubits in 0 / release qubits, which must be 0 again | 0 |
| `c.x(q)`, `c.cx(ctl, q)`, `c.swap(a, b)` | NOT, CNOT, SWAP | 0 |
| `c.ccx(a, b, q)` | Toffoli | 1 |
| `c.cswap(ctl, a, b)` | Fredkin (controlled swap) | 1 |
| `c.z(q)`, `c.cz(a, b)`, `c.flip()` | sign gates: (-1)^q, (-1)^(ab), global -1 | 0 |
| `c.ccz(a, b, q)` | sign (-1)^(abq) | 1 |
| `r = c.mx(q)` | X-basis measurement: random outcome r kicks the sign (-1)^(r q), and q becomes 0 | 0 |

Sign gates take `when=r` to apply only when the measurement outcome r is 1 (outcomes combine with
`r1 ^ r2`); this is how a measurement's sign kick is cancelled. Outcomes may not control gates
that change bits. Measurement-based uncomputation (Gidney 2018) therefore clears a temporary AND
`q = a AND b` with no Toffoli: `r = c.mx(q); c.cz(a, b, when=r)`.

A trajectory is one random input with its own random measurement outcomes. On every trajectory,
every register must end with the required value, every ancilla you allocated must be freed (back
to 0), and the sign must be +1. Plain Python (loops, functions, classical precomputation) is free.

**Score: Toffoli count x peak number of live qubits (task registers included). Lower is better.**
"""


def task_markdown(task: Task, start: tuple[int, int]) -> str:
    refs = "".join(f"- {name}: T = {t:,}, Q = {q:,}, TQ = {t * q:,}\n" for name, (t, q) in task.references.items())
    return (f"# kickmix arena: {task.name}\n\n{task.summary}\n\nRegisters: "
            + ", ".join(f"`{name}` ({width} qubit{'s' if width > 1 else ''})" for name, width in task.registers)
            + f". The starting candidate has T = {start[0]:,}, Q = {start[1]:,}, TQ = {start[0] * start[1]:,}.\n\n"
            + (f"Known circuits for reference:\n{refs}\n" if refs else "")
            + MODEL.format(signature=task.signature))
