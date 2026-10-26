<h1 align="center">kickmix-arena</h1>

<p align="center">
  <a href="https://github.com/tatra-labs/kickmix-arena/actions/workflows/tests.yml"><img src="https://github.com/tatra-labs/kickmix-arena/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <a href="https://arxiv.org/abs/2610.22367"><img src="https://img.shields.io/badge/arXiv-2610.22367-b31b1b.svg" alt="arXiv"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

<p align="center"><b>An open arena where AI agents discover cheaper quantum circuits.</b><br>
Write a Python program that builds a reversible circuit; the arena proves it correct on thousands of
random inputs and scores it by Toffolis × qubits. No quantum computer, no dependencies.</p>

[*Discovering state-of-the-art quantum circuits with large language models*](https://arxiv.org/abs/2610.22367)
(Gu, Kemeny, Yelin and Lukin; Harvard, Anthropic, QuEra; October 2026) let an LLM evolve circuit-building
programs against an exact evaluator. In seven of eight tasks the discovered circuits beat the state of the
art in **both** Toffoli count and qubit count, by up to 39× in Toffolis × qubits, and the search found a new
reversible architecture for modular inversion. The evaluator was not released.

**kickmix-arena** is an open, dependency-free version of that loop's missing half: a verifier and scorer
for the same circuit model, a set of arithmetic tasks with checked baselines, and task folders that plug
straight into an agent harness such as [lethe](https://github.com/tatra-labs/lethe).

## The scoreboard

| task | what the circuit computes | starting circuit | best reference here |
|---|---|---:|---:|
| `add32` | b ← a + b mod 2³² | 5,890 | **2,945** Gidney 2018 · 4,160 Cuccaro 2004 |
| `compare32` | t ← t ⊕ [a < b] | 6,208 | |
| `madd16` | p ← p + a·b mod 2³² | 160,528 | |
| `cmadd8` | x ← x + k·y if s = 0, else x + k·z | 14,112 | **6,912** conditional routing (the paper's first principle) |
| `modinv251` | y ← y ⊕ x⁻¹ mod 251 | 80,500 | |

<sub>Toffoli count × peak qubits, lower is better. Every number is measured by this repository's evaluator
(`kickmix tasks` and `pytest` reproduce them). Starting circuits are deliberately plain: ripple carries uncomputed with
Toffolis, schoolbook products, and a 250-entry lookup table for the inverse.</sub>

The references show the arena rewards exactly what the paper found. Gidney's adder replaces each carry's
uncomputation with an X-basis measurement and halves the Toffolis. On `cmadd8`, swapping *y* and *z* under
control of *s* and running one uncontrolled multiply-add, instead of two controlled ones, halves them too:
288 → 144, the paper's "conditional routing". The empty cells are open: send a pull request.

## Quickstart

```bash
git clone https://github.com/tatra-labs/kickmix-arena && cd kickmix-arena
pip install -e .
kickmix tasks                                        # tasks and starting costs
kickmix eval add32 references/add32_gidney.py        # VALID  T=31  Q=95  TQ=2,945
```

A candidate is a file that defines `build(c, <registers>)`:

```python
def build(c, a, b):                      # add32: b <- a + b
    carry = c.alloc(len(a) - 1)          # ancillas start in 0 ...
    ...
    r = c.mx(carry[i])                   # measurement-based uncomputation: no Toffoli
    c.cz(a[i], b[i], when=r)             # cancel its phase kick
    ...
    c.free(carry)                        # ... and must end in 0
```

**Let an agent search.** Every task folder (`tasks/add32`, ...) holds a `TASK.md` that teaches the
circuit model, a starting `circuit.py`, and a judge, in [lethe](https://github.com/tatra-labs/lethe)'s
task format:

```bash
lethe run tasks/cmadd8 --agent claude -m sonnet --budget 48   # or any OpenAI-compatible model
```

## How a circuit is checked

The arena uses the *kickmix* circuit model ([arXiv:2603.28846](https://arxiv.org/pdf/2603.28846), and the
paper's Methods): classical reversible gates (X, CNOT, Toffoli, SWAP, Fredkin), sign gates (Z, CZ, CCZ,
global −1), and destructive X-basis measurements whose random outcomes may control sign gates only. Such
a circuit sends every computational-basis input to a single basis state with a sign, so its action on a
coherent superposition is fixed by its action on basis states, which a classical computer can simulate.

- **Bit-sliced trajectories.** Each qubit is one Python integer whose bit *k* is that qubit's value in
  trajectory *k*, so 4,096 random inputs, each with its own random measurement outcomes, run in one pass.
- **Exact pass/fail.** On every trajectory, every register must hold the required value, every ancilla
  must be freed back to 0, and the sign must be +1. If all *k* trajectories pass, the candidate's failure
  probability is at most about ln(1/δ)/*k* with confidence 1 − δ (the paper's bound).
- **Edge cases, not just uniform inputs.** Uniform sampling almost never hits a carry that ripples through
  all 32 bits, so every check adds fixed corners (each mix of 0, 1, top bit and all ones; every *x* for
  `modinv251`), plus a quarter as many structured inputs stratified by carry-chain or common-prefix length.
  Judges also keep the inputs that broke earlier candidates in `~/.kickmix/` (or `$KICKMIX_HOME`) and replay
  them for every later one, so a bug found once stays found.
- **Untrusted code is replayed, not trusted.** `kickmix eval` and the task judges build the candidate in
  a separate process that returns only its gate list; the scorer replays it in its own simulator. A
  candidate that edits the counters only fools itself (there is a test for exactly that).
- **Cost.** T counts Toffoli, Fredkin and CCZ gates; Q is the peak number of live qubits, task registers
  included. The score is T × Q, as in the paper.

| call | effect | T |
|---|---|:-:|
| `c.alloc(n)`, `c.free(*qubits)` | n qubits in 0; release qubits that are 0 again | 0 |
| `c.x`, `c.cx`, `c.swap` | NOT, CNOT, SWAP | 0 |
| `c.ccx(a, b, q)`, `c.cswap(ctl, a, b)` | Toffoli, Fredkin | 1 |
| `c.z`, `c.cz`, `c.flip()` | sign gates (take `when=r`) | 0 |
| `c.ccz(a, b, q)` | sign gate (takes `when=r`) | 1 |
| `r = c.mx(q)` | X-basis measurement: random r kicks (−1)^(r·q); q becomes 0 | 0 |

## Add a task

A task is a set of registers, the required final value of each as a function of the initial values, and an
input sampler; see [`kickmix/tasks.py`](kickmix/tasks.py). Output registers start random, so circuits must
truly compute rather than assume zeros. `kickmix init <task> <dir>` writes the folder an agent needs.

## Citation

The search method and the design principles are the authors'; this repository is an independent,
open evaluator for the same circuit model.

```bibtex
@article{gu2026quantum,
  title   = {Discovering state-of-the-art quantum circuits with large language models},
  author  = {Gu, Andi and Kemeny, Alek H. and Yelin, Susanne F. and Lukin, Mikhail D.},
  journal = {arXiv preprint arXiv:2610.22367},
  year    = {2026}
}
```

MIT License.
