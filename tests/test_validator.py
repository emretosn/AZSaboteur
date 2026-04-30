"""Tests for FlagValidator."""

from saboteur.scenario.validator import FlagValidator, VALIDATION_DIR


FLAGS = {0: "AZS_F{aaa}", 1: "AZS_F{bbb}", 2: "AZS_F{ccc}"}


def _make_validator() -> FlagValidator:
    return FlagValidator(FLAGS)


def _cleanup_state(scenario_id: str) -> None:
    FlagValidator.clear_state(scenario_id)


def test_correct_flag_first_step():
    v = _make_validator()
    r = v.validate("AZS_F{aaa}")
    assert r.correct
    assert r.step == 0
    assert not r.already_solved
    assert r.solved_count == 1
    assert r.total == 3


def test_correct_flag_out_of_order():
    v = _make_validator()
    r = v.validate("AZS_F{ccc}")
    assert r.correct
    assert r.step == 2
    assert r.solved_count == 1
    assert r.total == 3
    assert "Step 3 solved" in r.message


def test_incorrect_flag():
    v = _make_validator()
    r = v.validate("AZS_F{wrong}")
    assert not r.correct
    assert r.step is None
    assert r.solved_count == 0


def test_duplicate_submission():
    v = _make_validator()
    v.validate("AZS_F{aaa}")
    r = v.validate("AZS_F{aaa}")
    assert r.correct
    assert r.already_solved
    assert r.solved_count == 1
    assert "already solved" in r.message


def test_all_flags_solved():
    v = _make_validator()
    v.validate("AZS_F{bbb}")
    v.validate("AZS_F{aaa}")
    r = v.validate("AZS_F{ccc}")
    assert r.correct
    assert r.solved_count == 3
    assert v.is_complete
    assert "All 3 flags captured" in r.message


def test_progress_string():
    v = _make_validator()
    assert v.progress == "0/3 flags captured"
    v.validate("AZS_F{bbb}")
    assert v.progress == "1/3 flags captured"


def test_whitespace_stripped():
    v = _make_validator()
    r = v.validate("  AZS_F{aaa}  ")
    assert r.correct


def test_empty_flags():
    v = FlagValidator({})
    assert v.is_complete
    assert v.progress == "0/0 flags captured"


def test_state_persistence():
    """Solved flags are restored when creating a new validator with same scenario_id."""
    sid = "test-persist-001"
    try:
        v1 = FlagValidator(FLAGS, scenario_id=sid)
        v1.validate("AZS_F{bbb}")
        assert v1.solved == {1}

        v2 = FlagValidator(FLAGS, scenario_id=sid)
        assert v2.solved == {1}
        assert v2.progress == "1/3 flags captured"
    finally:
        _cleanup_state(sid)


def test_state_clear():
    """clear_state removes the persisted file."""
    sid = "test-clear-001"
    try:
        v = FlagValidator(FLAGS, scenario_id=sid)
        v.validate("AZS_F{aaa}")
        assert (VALIDATION_DIR / f"{sid}.json").exists()

        FlagValidator.clear_state(sid)
        assert not (VALIDATION_DIR / f"{sid}.json").exists()

        v2 = FlagValidator(FLAGS, scenario_id=sid)
        assert v2.solved == set()
    finally:
        _cleanup_state(sid)


def test_state_ignores_stale_steps():
    """Persisted steps that no longer match current flags are ignored."""
    sid = "test-stale-001"
    try:
        v1 = FlagValidator(FLAGS, scenario_id=sid)
        v1.validate("AZS_F{aaa}")
        v1.validate("AZS_F{bbb}")

        # New deployment with different flags
        new_flags = {0: "AZS_F{xxx}", 1: "AZS_F{yyy}"}
        v2 = FlagValidator(new_flags, scenario_id=sid)
        assert v2.solved == set()
    finally:
        _cleanup_state(sid)
