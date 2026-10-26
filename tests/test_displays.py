"""Multi-monitor geometry. Uses made-up monitor layouts (this laptop has one screen);
real Windows calls are covered by a manual check recorded in docs/ULTIMATE_PROGRESS.md."""

from tools.displays import _pick_monitor, fits, number_monitors, placement_rect


def _mon(device, x, y, w, h, primary=False, taskbar=40):
    return {"device": device, "primary": primary, "bounds": (x, y, w, h), "work": (x, y, w, h - taskbar)}


# Laptop primary in the middle, a monitor to its LEFT (negative x) and one to its right.
LAYOUT = number_monitors([
    _mon("RIGHT", 1920, 0, 2560, 1440),
    _mon("LAPTOP", 0, 0, 1920, 1080, primary=True),
    _mon("LEFT", -1280, 0, 1280, 1024),
])


def test_primary_is_screen_one_then_left_to_right():
    assert [(m["number"], m["device"]) for m in LAYOUT] == [(1, "LAPTOP"), (2, "LEFT"), (3, "RIGHT")]


def test_placements_stay_inside_the_target_work_area():
    left_screen = LAYOUT[1]
    assert placement_rect("full", left_screen["work"]) == (-1280, 0, 1280, 984)
    assert placement_rect("right", left_screen["work"]) == (-640, 0, 640, 984)
    assert placement_rect("center", LAYOUT[2]["work"]) == (1920 + 320, 175, 1920, 1050)
    for m in LAYOUT:
        for p in ("full", "left", "right", "top", "bottom", "center"):
            assert fits(placement_rect(p, m["work"]), LAYOUT)


def test_rectangles_off_any_current_screen_are_rejected():
    assert not fits((-3000, 0, 800, 600), LAYOUT)  # a monitor that was unplugged
    assert not fits((1800, 0, 400, 400), LAYOUT)  # straddles two screens
    assert not fits((0, 0, 0, 500), LAYOUT)


def test_screen_selection_handles_numbers_next_and_missing_screens():
    assert _pick_monitor("1", LAYOUT, None)["device"] == "LAPTOP"
    assert _pick_monitor("3", LAYOUT, None)["device"] == "RIGHT"
    assert _pick_monitor("next", LAYOUT, LAYOUT[2])["device"] == "LAPTOP"  # wraps around
    assert _pick_monitor("next", LAYOUT, LAYOUT[0])["device"] == "LEFT"
    assert _pick_monitor("4", LAYOUT, None) is None
    single = number_monitors([_mon("ONLY", 0, 0, 1920, 1080, primary=True)])
    assert _pick_monitor("next", single, single[0]) is None
