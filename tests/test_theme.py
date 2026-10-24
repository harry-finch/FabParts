"""Contrast requirements across the shared interactive palette."""

import pytest

from kipartmanager.ui.theme import COLORS


def luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return sum(
        value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
    )


@pytest.mark.parametrize("surface", ["PRIMARY", "PRIMARY_HOVER", "PRIMARY_PRESSED"])
def test_primary_label_contrast(surface: str) -> None:
    bright, dark = sorted(
        (luminance(COLORS[surface]), luminance(COLORS["PRIMARY_TEXT"])), reverse=True
    )
    assert (bright + 0.05) / (dark + 0.05) >= 4.5


@pytest.mark.parametrize("surface", ["BG", "PANEL", "CONTROL", "SELECTION"])
def test_selection_text_and_focus_contrast(surface: str) -> None:
    background = luminance(COLORS[surface])
    assert (luminance(COLORS["TEXT"]) + 0.05) / (background + 0.05) >= 4.5
    assert (luminance(COLORS["ACCENT"]) + 0.05) / (background + 0.05) >= 3
