"""The bridge between the blog page and the skeleton program.

The page runs this in the browser (Pyodide). It calls the same functions as the
command-line program, and hands the page plain text and JSON. Nothing here asks
for input: every function takes JSON and returns JSON.
"""
import argparse
import contextlib
import io
import json
import os
import sys
import types

# The text blocks are laid out for this many characters per line.
os.environ.setdefault("COLUMNS", "90")

try:
    import tonal_inversion_2_0  # noqa: F401  (your own file, when it is on the page)
except ImportError:
    # Only the skeleton parts are on the page so far: give inversions.py the two
    # things it needs from the tonal file.
    _stub = types.ModuleType("tonal_inversion_2_0")
    _stub.NOTE = r"[A-G](?:[#b])?"
    _letters = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    _accidentals = {"": 0, "#": 1, "b": -1}
    _stub.pc = lambda note: (_letters[note[0]] + _accidentals[note[1:]]) % 12
    sys.modules["tonal_inversion_2_0"] = _stub

import inversions as inv  # noqa: E402
import skeletons_rehash as sk  # noqa: E402

# Which settings each kind takes.
FIELDS = {
    "reprobate": ["fret", "grouping", "length"],
    "flagellant": ["fret", "grouping", "length"],
    "penitent": ["fret", "grouping", "length"],
    "zealot": ["fret", "length"],
    "pietist": ["fret"],
    "schismatic": ["fret", "length", "string", "interval"],
}

# What the length field accepts, for the hint under it.
LENGTH_HINTS = {
    "reprobate": "2-4, 2-8 or 3-12 for groupings 1, 2 or 3",
    "flagellant": "2-4, 2-8 or 3-12 for groupings 1, 2 or 3",
    "penitent": "2-4, 2-8 or 3-12 for groupings 1, 2 or 3",
    "zealot": "2 to 13",
    "schismatic": f"{sk.MELODY_LENGTHS[0]} to {sk.MELODY_LENGTHS[1]}",
}


def _capture(function):
    """What the function prints, as text, without lines made only of '='."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        function()
    lines = [
        line for line in buffer.getvalue().split("\n")
        if not (line.strip() and set(line.strip()) == {"="})
    ]
    return "\n".join(lines).strip("\n")


def _blank(value):
    return None if value in (None, "") else str(value)


def _collections(state, mode):
    """The skeleton as built (mode I) and the mode asked for (None if impossible)."""
    base = inv.skeleton_collection(
        state["skeleton"], state["grouping"], state["start_fret"],
        state["shflat"], state["kind"],
    )
    return base, base.mode_of(mode)


def _describe(state, mode=1):
    base, col = _collections(state, mode)
    if col is None:
        return {"error": f"Mode {inv.roman(mode)} is not possible for this skeleton."}
    variation = inv.VARIATIONS[state["kind"]]
    modes = []
    if variation.list_modes:
        modes = [
            {"n": n, "roman": inv.roman(n), "pattern": inv.mode_summary(m)}
            for n, m in inv.possible_modes(base).items()
        ]
    return {
        "state": state,
        "mode": mode,
        "text": _capture(lambda: inv.show_skeleton(col)),
        "modes": modes if len(modes) > 1 else [],
        "triads": variation.finds_triads,
        "compare": any(label.startswith("Compare") for label, _ in variation.actions),
    }


def kinds_info():
    """The kinds, with their description and the settings each one takes (JSON)."""
    return json.dumps([
        {
            "id": kind,
            "description": inv.VARIATIONS[kind].description,
            "fields": FIELDS[kind],
            "length_hint": LENGTH_HINTS.get(kind, ""),
        }
        for kind in sk.KINDS
    ])


def generate(request):
    """A new skeleton. `request` is JSON: kind, fret, grouping, length, string,
    interval, shflat. A blank setting means random (or the default)."""
    params = json.loads(request)
    kind = params["kind"]
    args = argparse.Namespace(
        fret=_blank(params.get("fret")) or "r",
        grouping=_blank(params.get("grouping")) or "r",
        length=_blank(params.get("length")),
        string=_blank(params.get("string")),
        interval=_blank(params.get("interval")),
        shflat=params.get("shflat") or "#",
        rotation="1",
    )
    try:
        skeleton, grouping, start_fret = sk.generate_skeleton(args, kind)
    except SystemExit as error:
        import re
        names = {"g": "string grouping", "l": "length", "f": "start fret", "i": "largest step"}
        text = re.sub(
            r"(?<![\w-])-([glfi])(?![\w-])",
            lambda match: names[match.group(1)],
            str(error),
        )
        return json.dumps({"error": text})
    state = {
        "kind": kind, "skeleton": skeleton, "grouping": grouping,
        "start_fret": start_fret, "shflat": args.shflat,
    }
    return json.dumps(_describe(state))


def show(request):
    """The skeleton, or one of its modes. `request` is JSON: state, mode."""
    params = json.loads(request)
    return json.dumps(_describe(params["state"], int(params.get("mode", 1))))


def triads(request):
    """The playable triads, each with its voicings as text. `request` is JSON:
    state, mode, adjacent (true for the simple display)."""
    params = json.loads(request)
    _, col = _collections(params["state"], int(params.get("mode", 1)))
    found = inv.find_triads(col, bool(params.get("adjacent")))
    names = sk.FLATS if col.meta.get("shflat") == "b" else sk.SHARPS
    ordered = sorted(found, key=lambda t: (t[0], inv.QUALITY_ORDER.index(t[1])))
    return json.dumps([
        {
            "name": f"{names[root]} {quality}",
            "text": inv.triad_text(col, found[(root, quality)], root, quality, names),
        }
        for root, quality in ordered
    ])


def compare(request):
    """The skeleton's pattern as every kind that accepts it (text, as JSON)."""
    params = json.loads(request)
    _, col = _collections(params["state"], int(params.get("mode", 1)))
    session = types.SimpleNamespace(col=col)
    return json.dumps({"text": _capture(lambda: inv.compare_action(session))})
