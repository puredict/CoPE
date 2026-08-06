import pytest

from experiments.task7_occurrence_canary import terminal_expected


def test_task7_terminal_expectations_are_mode_specific():
    assert terminal_expected("cancel") == {
        "done": True, "original": False, "intermediate": False,
    }
    assert terminal_expected("restore") == {
        "done": True, "original": True, "intermediate": False,
    }
    with pytest.raises(ValueError):
        terminal_expected("unknown")
