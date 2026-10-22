from pathlib import Path

import pytest

from kickmix import TASKS, Circuit, CircuitError, evaluate, evaluate_file, load_build

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", TASKS)
def test_every_starting_candidate_is_correct(name):
    assert evaluate(TASKS[name], load_build(ROOT / "tasks" / name / "candidate" / "circuit.py"), 1024).valid


def test_reference_adders_match_their_published_costs():
    task = TASKS["add32"]
    for file, label in (("add32_gidney.py", "Gidney 2018 (measurement-based uncomputation)"),
                        ("add32_cuccaro.py", "Cuccaro et al. 2004 ripple-carry")):
        r = evaluate(task, load_build(ROOT / "references" / file))
        assert r.valid and (r.toffolis, r.qubits) == task.references[label]


def test_conditional_routing_halves_the_toffolis():
    task = TASKS["cmadd8"]
    naive = evaluate(task, load_build(ROOT / "tasks" / "cmadd8" / "candidate" / "circuit.py"))
    routed = evaluate(task, load_build(ROOT / "references" / "cmadd8_routed.py"))
    assert routed.valid and routed.toffolis * 2 == naive.toffolis


def test_an_uncancelled_measurement_kick_is_caught():
    def adder_without_correction(c, a, b):
        n = len(a)
        carry = c.alloc(n - 1)
        for i in range(n - 1):
            if i:
                c.cx(carry[i - 1], a[i])
                c.cx(carry[i - 1], b[i])
            c.ccx(a[i], b[i], carry[i])
            if i:
                c.cx(carry[i - 1], carry[i])
        c.cx(a[n - 1], b[n - 1])
        c.cx(carry[n - 2], b[n - 1])
        for i in reversed(range(n - 1)):
            if i:
                c.cx(carry[i - 1], carry[i])
            c.mx(carry[i])  # no cz: the phase kick stays
            if i:
                c.cx(carry[i - 1], a[i])
            c.cx(a[i], b[i])
        c.free(carry)

    r = evaluate(TASKS["add32"], adder_without_correction)
    assert not r.valid and "sign" in r.message


def test_dirty_or_leaked_ancillas_and_misused_registers_are_rejected():
    def leaks(c, a, b):
        c.alloc(1)

    def dirty(c, a, b):
        (q,) = c.alloc(1)
        c.cx(a[0], q)
        c.free(q)

    def register_as_qubit(c, a, b):
        c.cx(a, b[0])

    for build, words in ((leaks, "never freed"), (dirty, "freed while still 1"), (register_as_qubit, "expects qubits")):
        r = evaluate(TASKS["add32"], build)
        assert not r.valid and words in r.message


def test_isolated_scoring_ignores_a_candidate_that_tampers_with_the_counters(tmp_path):
    cheat = tmp_path / "circuit.py"
    cheat.write_text((ROOT / "references" / "add32_gidney.py").read_text() + "\n\n_honest = build\n\n\n"
                     "def build(c, a, b):\n    _honest(c, a, b)\n    c.toffolis = 0\n    c.phase = 0\n")
    assert evaluate(TASKS["add32"], load_build(cheat)).toffolis == 0  # in-process trusts the code ...
    r = evaluate_file(TASKS["add32"], cheat)
    assert r.valid and r.toffolis == 31  # ... the isolated scorer counts the replayed gates itself


def test_replayed_sign_gates_reference_real_measurements():
    c = Circuit(8)
    (q,) = c.alloc(1)
    with pytest.raises(CircuitError):
        c.replay([("cz", [q, q + 1], [0])])
