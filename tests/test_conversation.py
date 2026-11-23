"""Navigation and platform constraints, independent of HTTP and Meta."""

import pytest

from univio.conversation import SCREENS, choose_screen


@pytest.mark.parametrize("command", ["hi", " MENU ", "back", "cancel", "stop"])
def test_escape_commands_always_reach_menu(command):
    assert choose_screen(command) is SCREENS["menu"]


def test_all_choices_are_reachable_and_fit_whatsapp_buttons():
    reached = {"menu"}
    pending = ["menu"]
    while pending:
        key = pending.pop()
        screen = SCREENS[key]
        assert 1 <= len(screen.options) <= 3
        assert len(screen.render()) <= 4096
        for option in screen.options:
            assert len(option.label) <= 20
            assert len(option.command.encode()) <= 256
            assert option.command in SCREENS
            assert option.command in screen.render()
            if option.command not in reached:
                reached.add(option.command)
                pending.append(option.command)
    assert reached == set(SCREENS)


def test_unknown_input_does_not_echo_private_text():
    screen = choose_screen("my-private-id")
    assert "my-private-id" not in screen.render()
    assert screen.options == SCREENS["menu"].options


def test_unsupported_media_offers_safe_recovery():
    assert choose_screen(None, "unsupported").options == SCREENS["menu"].options


def test_career_quiz_requires_seven_choices_and_ranks_interests():
    assert choose_screen("quiz rrrrrrr") is SCREENS["career"]
    result = choose_screen("QUIZ iiiassc")
    assert "Investigative" in result.text
    assert "Social" in result.text
    assert "accounting" not in result.text
    assert len(SCREENS["career"].render()) <= 1024
