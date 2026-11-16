"""One entry point for every inversion variation.

A *source* builds a Collection (an ordered, cyclic list of notes), a *mode*
starts it on any of its notes, a *transform* maps the chosen positions to their
inverted positions, and a *renderer* prints the result. A variation's *actions*
are what the user can do with the collection once it exists. Register new
combinations in VARIATIONS at the bottom.
"""
import random
import re
import shutil
from itertools import combinations
from dataclasses import dataclass, field
from typing import Callable

import skeletons_rehash as sk
import tonal_inversion_2_0 as ti


def roman(n):
    out = ""
    for value, numeral in [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]:
        while n >= value:
            out += numeral
            n -= value
    return out


# --- Shared data structure -----------------------------------------------------

@dataclass
class Collection:
    names: list                                # spelled note names, in order
    pcs: list                                  # pitch classes, same order
    labels: list | None = None                 # names for positions, e.g. 'A6'
    data: list | None = None                   # anything per position, e.g. (string, fret)
    ids: dict = field(default_factory=dict)    # extra accepted position ids -> index
    meta: dict = field(default_factory=dict)   # anything a renderer needs
    mode: int = 1                              # which mode this is
    layout: Callable | None = None             # (collection, n) -> mode n, or None
    mode_count: int | None = None              # number of modes (default: one per note)

    def __len__(self):
        return len(self.names)

    @property
    def n_modes(self):
        return self.mode_count or len(self)

    def label(self, i):
        return self.labels[i] if self.labels else f"#{i + 1}"

    def rotated(self, n):
        """The same notes, starting on the nth."""
        k = n - 1

        def turn(items):
            return None if items is None else items[k:] + items[:k]

        return Collection(
            names=turn(self.names),
            pcs=turn(self.pcs),
            labels=turn(self.labels),
            data=turn(self.data),
            ids={ident: (i - k) % len(self) for ident, i in self.ids.items()},
            meta=self.meta,
            mode=n,
        )

    def mode_of(self, n):
        """Mode n (1 is the collection as built), or None if it doesn't fit.

        A plain rotation, unless the source supplied its own `layout`.
        """
        if not 1 <= n <= self.n_modes:
            raise SystemExit(f"Mode: 1 to {self.n_modes}, or 'r' for random.")
        return self.layout(self, n) if self.layout else self.rotated(n)


# --- Input: notes by name, with a follow-up only when a name repeats ------------

ID = r"[A-Za-z]\d{1,2}"
ITEM = rf"(?:{ID}|{ti.NOTE})"
ITEM_LIST = re.compile(rf"{ITEM}(?:\s*,?\s*{ITEM})*")
TOKEN = re.compile(rf"({ID})|({ti.NOTE})")


def choose_position(note, candidates, col):
    """Several positions share this note: ask which one is meant."""
    menu = "  ".join(f"{n}) {col.label(i)}" for n, i in enumerate(candidates, 1))
    while True:
        answer = input(f"{note} is at {menu}. Which one? ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        if col.ids.get(answer) in candidates:
            return col.ids[answer]
        print("ValueError: Pick a number from the list or one of those positions.")


def resolve(items, col):
    """Indices for (id, note) pairs. Returns None after printing an error."""
    chosen = []
    for ident, note in items:
        if ident:
            if ident not in col.ids:
                print(f"ValueError: {ident} is not a position here.")
                return None
            chosen.append(col.ids[ident])
            continue
        candidates = [i for i, p in enumerate(col.pcs) if p == ti.pc(note)]
        if not candidates:
            print(f"ValueError: {note} is not in the set.")
            return None
        if len(candidates) == 1:
            chosen.append(candidates[0])
        else:
            chosen.append(choose_position(note, candidates, col))
    return chosen


def ask_notes(prompt, col, only_one=False):
    """Notes by name (F#, Bb) or position id (A6). Returns indices into `col`."""
    while True:
        raw = input(prompt).strip()
        if not ITEM_LIST.fullmatch(raw):
            print("ValueError: Enter notes (F#, Bb) or position ids (E4, g6).")
            continue
        items = TOKEN.findall(raw)
        if only_one and len(items) != 1:
            print("ValueError: Exactly one note, please.")
            continue
        chosen = resolve(items, col)
        if chosen is not None:
            return chosen


# --- Sources -------------------------------------------------------------------

def tonal_source(args):
    root = ti.ask_note("Root: ")
    scale = ti.ask_scale()
    names = ti.build_tonality(root, scale)
    return Collection(names, [ti.pc(n) for n in names])


def chromatic_source(args):
    names = sk.FLATS if args.shflat == "b" else sk.SHARPS
    return Collection(list(names), list(range(12)))


def frets_by_string(positions):
    """Per-string fret lists (sorted, no repeats) for (string, fret) positions."""
    frets = [[] for _ in sk.BASE_NOTES]
    for string, fret in positions:
        frets[string].append(fret)
    return [sorted(set(f)) for f in frets]


def skeleton_collection(
    skeleton, grouping, start_fret, shflat, kind, mode=1, mode_count=None
):
    """A skeleton (or one of its modes) placed on the neck."""
    frets, names = sk.place_with_notes(skeleton, grouping, start_fret, shflat, kind)
    # Same order as names: low string to high, ascending along each string.
    positions = [
        (string, fret)
        for string, string_frets in enumerate(frets)
        for fret in string_frets
    ]
    labels = [f"{sk.STRING_NAMES[s]}{f}" for s, f in positions]
    pcs = [(sk.BASE_NOTES[s] + f) % 12 for s, f in positions]

    # 'E' is the low string and 'e' the high one. The others work in either case.
    ids = {}
    for i, (string, fret) in enumerate(positions):
        name = sk.STRING_NAMES[string]
        variants = {name} if name in "Ee" else {name.upper(), name.lower()}
        for variant in variants:
            ids[f"{variant}{fret}"] = i

    meta = {
        "start_fret": start_fret,
        "grouping": grouping,
        "skeleton": skeleton,
        "frets": frets,
        "shflat": shflat,
        "kind": kind,
    }
    return Collection(
        names=names,
        pcs=pcs,
        labels=labels,
        data=positions,
        ids=ids,
        meta=meta,
        mode=mode,
        layout=skeleton_layout,
        mode_count=mode_count or len(skeleton),
    )


def skeleton_layout(col, n):
    """Mode n of a skeleton: a new pattern.

    The pattern is rotated to start on its nth offset (see rotate_skeleton) and
    the hand moves up to where that offset sat, dropping an octave if that runs
    off the neck. The new pattern must pass the same rules as a generated
    skeleton of the same kind (ceiling, no empty strings, stretch, no runs of
    four semitones); otherwise None.
    """
    if n == 1:
        return col
    m = col.meta
    if m["kind"] in sk.NO_MODES:
        return None
    window = sk.window_for(m["kind"], m["grouping"], m["skeleton"])
    pattern = sk.rotate_skeleton(m["skeleton"], n, window)
    start_fret = m["start_fret"] + m["skeleton"][n - 1]
    if start_fret > sk.MAX_FRET:
        start_fret -= 12
    if not sk.is_curated(pattern, m["grouping"], start_fret, m["kind"]):
        return None
    return skeleton_collection(
        pattern,
        m["grouping"],
        start_fret,
        m["shflat"],
        m["kind"],
        mode=n,
        mode_count=col.n_modes,
    )


def skeleton_source(args, kind):
    skeleton, grouping, start_fret = sk.generate_skeleton(args, kind)
    return skeleton_collection(skeleton, grouping, start_fret, args.shflat, kind)


# --- Transforms ----------------------------------------------------------------

def reflect(n, axis, chord):
    """Mirror positions about the axis in a cyclic sequence of n positions."""
    return [(2 * axis - k) % n for k in chord]


# --- Renderers -----------------------------------------------------------------

def summary(title, col, indices):
    text = ", ".join(col.names[i] for i in indices)
    if col.labels:
        text += f" ({', '.join(col.label(i) for i in indices)})"
    return f"{title:<12}{text}"


def render_names(col, chord, result):
    return f"\n{summary('Chord:', col, chord)}\n{summary('Inversion:', col, result)}"


def frets_for(col, indices):
    return frets_by_string([col.data[i] for i in indices])


def side_by_side(left, right, gap=6):
    left, right = left.splitlines(), right.splitlines()
    width = max(len(line) for line in left)
    return "\n".join(f"{l:<{width + gap}}{r}".rstrip() for l, r in zip(left, right))


def render_tabs(col, chord, result):
    left = "Chord\n" + sk.tab_print(frets_for(col, chord))
    right = "Inversion\n" + sk.tab_print(frets_for(col, result))
    return f"\n{side_by_side(left, right)}\n{render_names(col, chord, result)}"


def show_tonality(col):
    print(f"Chosen tonality: {', '.join(col.names)}")


def show_skeleton(col):
    m = col.meta
    tab, notes = sk.display_skeleton(
        m["skeleton"], m["grouping"], m["start_fret"], m["shflat"], m["kind"]
    )
    sk.print_skeleton(
        m["start_fret"], sk.setting_line(m["kind"], m["grouping"]), m["skeleton"], tab, notes
    )


# --- Modes ---------------------------------------------------------------------

def fitting_modes(col):
    return [n for n in range(1, col.n_modes + 1) if col.mode_of(n) is not None]


def start_mode(col, wanted):
    """The mode chosen with -m: a number, or None for a random one that fits."""
    if wanted == 1:
        return col
    fits = fitting_modes(col)
    if wanted is None:
        wanted = random.choice(fits)
    elif not 1 <= wanted <= col.n_modes:
        raise SystemExit(f"Mode: 1 to {col.n_modes}, or 'r' for random.")
    elif wanted not in fits:
        others = ", ".join(roman(n) for n in fits)
        raise SystemExit(
            f"Mode {roman(wanted)} doesn't fit the rules for this skeleton. "
            f"Possible modes: {others}."
        )
    return col.mode_of(wanted)


def present(variation, col, label=False):
    if variation.show:
        variation.show(col)
    if label or col.mode != 1:
        print(f"Mode: {roman(col.mode)}")


def mode_summary(mode):
    pattern = mode.meta.get("skeleton")
    if pattern is None:
        return ", ".join(mode.names)
    return f"{', '.join(map(str, pattern))}  (start fret {mode.meta['start_fret']})"


def possible_modes(base):
    """The modes of `base` that fit, as {number: collection}."""
    modes = {n: base.mode_of(n) for n in range(1, base.n_modes + 1)}
    return {n: mode for n, mode in modes.items() if mode is not None}


def print_modes(modes, current):
    """Print the possible modes, marking the current one."""
    if len(modes) < 2:
        print("\nNo other mode is possible.")
        return
    width = max(len(roman(n)) for n in modes) + 2
    print("\nPossible modes:")
    for n, mode in modes.items():
        marker = "  <- current" if n == current.mode else ""
        print(f"  {n:>2}  {roman(n):<{width}}{mode_summary(mode)}{marker}")


# --- Actions: what can be done with a collection ---------------------------------

@dataclass
class Session:
    """What the user is working on while the menu runs."""
    variation: "Variation"
    args: object          # the parsed command-line arguments
    base: Collection      # the collection as built (mode I)
    col: Collection       # the mode currently being worked on


def show_start(session):
    """Show the collection, and its possible modes if the variation lists them."""
    present(session.variation, session.col)
    if session.variation.list_modes:
        print_modes(possible_modes(session.base), session.col)


def modes_action(session):
    """List the possible modes and show the ones asked for."""
    modes = possible_modes(session.base)
    if len(modes) < 2:
        print("\nNo other mode is possible.")
        return
    print_modes(modes, session.col)
    while True:
        answer = input("Mode number (Enter to go back): ").strip()
        if not answer:
            return
        if answer.isdigit() and int(answer) in modes:
            session.col = modes[int(answer)]
            present(session.variation, session.col, label=True)
        else:
            print(f"ValueError: Choose one of {', '.join(map(str, modes))}.")


def invert_action(session):
    """Invert a chord (or set of notes) about an axis within the current collection."""
    variation, col = session.variation, session.col
    print()
    axis = ask_notes("Axis: ", col, only_one=True)[0]
    chord = ask_notes("Chord/notes: ", col)
    result = variation.transform(len(col), axis, chord)
    print(variation.render(col, chord, result))


def generate_action(session):
    """Build a fresh collection from the same source, e.g. a new random skeleton."""
    session.base = session.variation.source(session.args)
    session.col = session.base
    show_start(session)


def ask_action(actions):
    print("\nWhat next?")
    for n, (label, _) in enumerate(actions, 1):
        print(f"  {n}) {label}")
    while True:
        answer = input("Choice (Enter to finish): ").strip()
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(actions):
            return int(answer) - 1
        print(f"ValueError: Enter a number from 1 to {len(actions)}, or press Enter.")


# --- Triads: three notes of a skeleton, each on its own string --------------------

TRIADS = {  # semitones above the root -> quality
    (4, 7): "major",
    (3, 7): "minor",
    (3, 6): "diminished",
    (4, 8): "augmented",
}
QUALITY_ORDER = list(TRIADS.values())
INVERSIONS = ["Root position", "First inversion", "Second inversion"]


def triad_of(pcs):
    """(root, quality) if these three pitch classes form a triad, else None.

    An augmented triad has no single root, so its lowest pitch class is used.
    """
    for root in sorted(pcs):
        steps = tuple(sorted((p - root) % 12 for p in pcs if p != root))
        if steps in TRIADS:
            return root, TRIADS[steps]
    return None


def pitch_of(col, i):
    string, fret = col.data[i]
    return sk.OPEN_PITCHES[string] + fret


def find_triads(col, adjacent=False):
    """Every playable triad in a skeleton, as {(root, quality): [voicings]}.

    A voicing is three positions on three different strings that spell the
    triad (in any order, so any inversion) and sit within the stretch. Open
    strings are free, as everywhere else. With adjacent=True the three strings
    must also be next to each other.
    """
    found = {}
    for trio in combinations(range(len(col)), 3):
        strings = {col.data[i][0] for i in trio}
        if len(strings) < 3:
            continue
        if adjacent and max(strings) - min(strings) > 2:
            continue
        pcs = {col.pcs[i] for i in trio}
        if len(pcs) < 3:
            continue
        fretted = [col.data[i][1] for i in trio if col.data[i][1] > 0]
        if fretted and max(fretted) - min(fretted) > sk.STRETCH:
            continue
        triad = triad_of(pcs)
        if triad:
            found.setdefault(triad, []).append(trio)
    return found


def inversion_of(col, trio, root, quality):
    """0, 1 or 2 for root position and the two inversions (None if augmented)."""
    if quality == "augmented":
        return None
    bass = min(trio, key=lambda i: pitch_of(col, i))
    interval = (col.pcs[bass] - root) % 12
    return 0 if interval == 0 else 1 if interval in (3, 4) else 2


def voicing_block(col, trio, root, quality, names):
    """One voicing as lines of text: inversion, notes low to high, then the tab."""
    inversion = inversion_of(col, trio, root, quality)
    heading = "Voicing" if inversion is None else INVERSIONS[inversion]
    ordered = sorted(trio, key=lambda i: pitch_of(col, i))
    notes = " ".join(names[col.pcs[i]] for i in ordered)
    return "\n".join([heading, notes, sk.tab_print(frets_for(col, trio))])


def in_rows(blocks, gap=4):
    """Blocks of equal height side by side, wrapped to the terminal width."""
    width = max(len(line) for block in blocks for line in block.splitlines()) + gap
    per_row = max(1, shutil.get_terminal_size().columns // width)
    rows = []
    for first in range(0, len(blocks), per_row):
        group = [block.splitlines() for block in blocks[first:first + per_row]]
        rows.append(
            "\n".join(
                "".join(line.ljust(width) for line in lines).rstrip()
                for lines in zip(*group)
            )
        )
    return "\n\n".join(rows)


def in_columns(items):
    """Numbered items, filled down the columns to fit the terminal width."""
    entries = [f"{n:>2}) {item}" for n, item in enumerate(items, 1)]
    width = max(len(entry) for entry in entries) + 3
    n_cols = max(1, shutil.get_terminal_size().columns // width)
    n_rows = -(-len(entries) // n_cols)
    return "\n".join(
        "".join(entry.ljust(width) for entry in entries[r::n_rows]).rstrip()
        for r in range(n_rows)
    )


TRIAD_DISPLAYS = (
    ("Simple: notes on adjacent strings only", True),
    ("Full: notes on any strings", False),
)


def ask_triad_display():
    """Simple (adjacent strings) or full. None if the user is done."""
    print("\nTriad display:")
    for n, (label, _) in enumerate(TRIAD_DISPLAYS, 1):
        print(f"  {n}) {label}")
    while True:
        answer = input("Choice (Enter to go back): ").strip()
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(TRIAD_DISPLAYS):
            return TRIAD_DISPLAYS[int(answer) - 1][1]
        print(f"ValueError: Enter a number from 1 to {len(TRIAD_DISPLAYS)}, or press Enter.")


def triad_text(col, trios, root, quality, names):
    """A triad's name and all its voicings, as tabs side by side."""

    def order(trio):
        inversion = inversion_of(col, trio, root, quality)
        low = min(col.data[i][0] for i in trio)
        return (-1 if inversion is None else inversion, low, sorted(trio))

    blocks = [
        voicing_block(col, trio, root, quality, names) for trio in sorted(trios, key=order)
    ]
    return f"{names[root]} {quality}\n\n{in_rows(blocks)}"


def triads_action(session):
    """Choose a simple or full display, then list the playable triads."""
    while True:
        adjacent = ask_triad_display()
        if adjacent is None:
            return
        show_triads(session.col, adjacent)


def show_triads(col, adjacent, only=None):
    """List the triads; the one picked is shown as tabs, one per voicing.

    `only` limits the list to those (root, quality) triads.
    """
    found = find_triads(col, adjacent)
    if only is not None:
        found = {triad: voicings for triad, voicings in found.items() if triad in only}
    if not found:
        print("\nNo playable triad in this skeleton with that display.")
        return
    names = sk.FLATS if col.meta.get("shflat") == "b" else sk.SHARPS
    triads = sorted(found, key=lambda t: (t[0], QUALITY_ORDER.index(t[1])))
    print("\nPlayable triads in the scale:" if only is not None else "\nPlayable triads:")
    print(in_columns([f"{names[root]} {quality}" for root, quality in triads]))
    while True:
        answer = input("Triad number (Enter to go back): ").strip()
        if not answer:
            return
        if not (answer.isdigit() and 1 <= int(answer) <= len(triads)):
            print(f"ValueError: Enter a number from 1 to {len(triads)}, or press Enter.")
            continue
        root, quality = triads[int(answer) - 1]
        print("\n" + triad_text(col, found[(root, quality)], root, quality, names))


# --- Full circle: a skeleton that plays triads of a scale ----------------------------

MIN_SCALE_TRIADS = 3  # triads of the scale a skeleton must be able to play
MAX_SEARCH = 2000     # skeletons tried before giving up

TRIAD_STEPS = {quality: (0,) + steps for steps, quality in TRIADS.items()}


def scale_triads_in(found, scale_pcs):
    """The found triads whose notes all belong to the scale."""
    return [
        (root, quality)
        for root, quality in found
        if {(root + step) % 12 for step in TRIAD_STEPS[quality]} <= scale_pcs
    ]


def triads_of_scale(scale_pcs):
    """Every (root, quality) triad whose notes all belong to the scale."""
    everything = [(root, quality) for root in range(12) for quality in QUALITY_ORDER]
    return scale_triads_in(everything, scale_pcs)


def ask_skeleton_kind():
    """The skeleton types that can find triads. None if the user is done."""
    kinds = [name for name, variation in VARIATIONS.items() if variation.finds_triads]
    print("\nSkeleton type:")
    for n, name in enumerate(kinds, 1):
        print(f"  {n}) {name:<12}{VARIATIONS[name].description}")
    while True:
        answer = input("Choice (Enter to go back): ").strip()
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(kinds):
            return kinds[int(answer) - 1]
        print(f"ValueError: Enter a number from 1 to {len(kinds)}, or press Enter.")


def search_for_scale(variation, args, scale_pcs, adjacent):
    """Skeletons from this variation until one plays enough triads of the scale.

    Returns (collection, triads, tries), or None after saying why not.
    """
    for tries in range(1, MAX_SEARCH + 1):
        try:
            col = variation.source(args)
        except SystemExit as error:
            print(f"\n{error}")
            return None
        wanted = scale_triads_in(find_triads(col, adjacent), scale_pcs)
        if len(wanted) >= MIN_SCALE_TRIADS:
            return col, wanted, tries
    print(
        f"\nNo skeleton turned up in {MAX_SEARCH} tries. "
        "Try another scale, type, display or settings."
    )
    return None


def scale_runner(args):
    """Choose a scale, then a skeleton type and a display, and search.

    Once a skeleton is found it carries on in that skeleton type's own menu.
    """
    root = ti.ask_note("Root: ")
    scale = ti.ask_scale()
    scale_pcs = {ti.pc(note) for note in ti.build_tonality(root, scale)}
    available = len(triads_of_scale(scale_pcs))
    if available < MIN_SCALE_TRIADS:
        print(
            f"\n{root} {scale} has only {available} triad(s), "
            f"so no skeleton can play {MIN_SCALE_TRIADS} of them."
        )
        return
    kind = ask_skeleton_kind()
    if kind is None:
        return
    adjacent = ask_triad_display()
    if adjacent is None:
        return
    variation = VARIATIONS[kind]
    print(f"\nSearching for a {kind} with at least {MIN_SCALE_TRIADS} {root} {scale} triads...")
    result = search_for_scale(variation, args, scale_pcs, adjacent)
    if result is None:
        return
    col, wanted, tries = result
    session = Session(variation, args, col, col)
    show_start(session)
    print(f"\nFound after {tries} skeletons: {len(wanted)} triads of {root} {scale}.")
    show_triads(col, adjacent, only=set(wanted))
    menu_loop(session)


# --- Compare: one pattern, every kind ------------------------------------------------

def likely_grouping(pattern):
    """The smallest grouping whose ceiling holds the pattern (3 if none does)."""
    for grouping in sorted(sk.LENGTH_RANGES):
        if pattern[-1] <= sk.ceiling_for(grouping):
            return grouping
    return max(sk.LENGTH_RANGES)


def compare_action(session):
    """Show the current pattern as every kind that accepts it, and why not the rest.

    A kind that places the pattern identically under several groupings is shown
    once. The penitent never names a grouping: it only sets its ceiling, and
    leaves the tab unchanged.
    """
    col = session.col
    m = col.meta
    pattern, start_fret = m["skeleton"], m["start_fret"]
    blocks, refused = [], []
    for kind in sk.KINDS:
        if kind in sk.MELODIC:
            continue
        groupings = (None,) if kind in sk.NO_GROUPING else sorted(sk.LENGTH_RANGES)
        placements = {}  # frets -> the groupings that give them
        for grouping in groupings:
            if sk.is_curated(pattern, grouping, start_fret, kind):
                frets = sk.PLACERS[kind](pattern, grouping, start_fret)
                key = tuple(tuple(string) for string in frets)
                placements.setdefault(key, []).append(grouping)
        for key, fitting in placements.items():
            title = kind
            if fitting != [None] and kind not in sk.GROUPING_IGNORED:
                title += ", grouping " + ", ".join(map(str, fitting))
            if kind == m["kind"] and m["grouping"] in fitting:
                title += " (current)"
            blocks.append(title + "\n" + sk.tab_print([list(string) for string in key]))
        if not placements:
            grouping = None if kind in sk.NO_GROUPING else likely_grouping(pattern)
            reason = sk.curation_failure(pattern, grouping, start_fret, kind)
            refused.append(f"  {kind}: {reason}")
    print(f"\nPattern {', '.join(map(str, pattern))} from fret {start_fret}\n")
    print(in_rows(blocks))
    if refused:
        print("\nNot possible:")
        print("\n".join(refused))


# --- Variations ----------------------------------------------------------------

@dataclass
class Variation:
    description: str
    source: Callable
    show: Callable | None = None      # printed once the collection exists
    transform: Callable = reflect
    render: Callable = render_names
    list_modes: bool = False          # print the possible modes straight away
    # (label, action) pairs. With only one, it runs straight away.
    actions: tuple = (("Invert", invert_action),)
    group: str = "Inversions"         # the heading it is listed under in the menu
    finds_triads: bool = False        # can be searched for triads of a scale
    ask_settings: Callable | None = None  # asks for what the command line left out
    runner: Callable | None = None    # runs the whole variation, instead of the menu


def ask_melody_settings(args):
    """Ask for what the command line left out: start string, largest step, length."""
    if args.string is None:
        print("\nStart string:")
        for n, name in enumerate(sk.STRING_NAMES, 1):
            print(f"  {n}) {name}")
        while True:
            answer = input("Choice (Enter for random): ").strip()
            if not answer:
                args.string = "r"
            elif answer.isdigit() and 1 <= int(answer) <= len(sk.STRING_NAMES):
                args.string = sk.STRING_NAMES[int(answer) - 1]
            else:
                print(f"ValueError: Enter a number from 1 to {len(sk.STRING_NAMES)}, or press Enter.")
                continue
            break
    if args.interval is None:
        while True:
            answer = input(
                f"\nLargest step in semitones, 1 to {sk.MAX_INTERVAL} "
                f"(Enter for {sk.DEFAULT_INTERVAL}): "
            ).strip()
            if not answer:
                args.interval = str(sk.DEFAULT_INTERVAL)
            elif answer.isdigit() and 1 <= int(answer) <= sk.MAX_INTERVAL:
                args.interval = answer
            else:
                print(f"ValueError: Enter a number from 1 to {sk.MAX_INTERVAL}, or press Enter.")
                continue
            break
    if args.length is None:
        low, high = sk.MELODY_LENGTHS
        while True:
            answer = input(f"\nLength, {low} to {high} (Enter for random): ").strip()
            if not answer:
                args.length = "r"
            elif answer.isdigit() and low <= int(answer) <= high:
                args.length = answer
            else:
                print(f"ValueError: Enter a number from {low} to {high}, or press Enter.")
                continue
            break


def skeleton_variation(
    kind, description, modes=True, triads=True, compare=True, ask_settings=None
):
    """A skeleton variation: generate, then view modes, triads, invert, or again.

    With modes=False the kind has no modes, so they are neither listed nor offered.
    With triads=False the kind has no triad finder. With compare=False it cannot
    be compared with the other kinds (a melody is not a sorted pattern).
    """
    actions = (
        ("Invert within this skeleton", invert_action),
        ("Generate another skeleton", generate_action),
    )
    if compare:
        actions = (("Compare with the other kinds", compare_action),) + actions
    if triads:
        actions = (("Find playable triads", triads_action),) + actions
    if modes:
        actions = (("Show another mode", modes_action),) + actions
    return Variation(
        description,
        lambda args: skeleton_source(args, kind),
        show=show_skeleton,
        render=render_tabs,
        list_modes=modes,
        actions=actions,
        group="Skeletons",
        finds_triads=triads,
        ask_settings=ask_settings,
    )


# The menu lists them in this order, grouped under their headings: the skeletons,
# the program's main focus, come first.
VARIATIONS = {
    "reprobate": skeleton_variation(
        "reprobate", "Pattern-bound skeleton: modes and inversion"
    ),
    "flagellant": skeleton_variation(
        "flagellant", "Interval-preserving skeleton: modes and inversion"
    ),
    "penitent": skeleton_variation(
        "penitent", "Last-note-chained skeleton: modes and inversion"
    ),
    "zealot": skeleton_variation(
        "zealot",
        "One-string skeleton repeated at fourths: modes and inversion",
        triads=False,
    ),
    "pietist": skeleton_variation(
        "pietist", "Stepwise skeleton across all strings: inversion", modes=False
    ),
    "schismatic": skeleton_variation(
        "schismatic",
        "Non-linear melody: each note within a set interval of the last",
        modes=False,
        triads=False,
        compare=False,
        ask_settings=ask_melody_settings,
    ),
    "scale": Variation(
        "Find a skeleton that plays triads of a scale",
        None,
        runner=scale_runner,
        group="Skeletons",
    ),
    "tonal": Variation(
        "Invert within a scale or mode", tonal_source, show=show_tonality
    ),
    "mirror": Variation("Chromatic (real) inversion", chromatic_source),
}


def menu_loop(session):
    """Offer the variation's actions until the user presses Enter."""
    actions = session.variation.actions
    if len(actions) == 1:
        actions[0][1](session)
        return
    while True:
        choice = ask_action(actions)
        if choice is None:
            return
        actions[choice][1](session)


def run(variation, args):
    if variation.runner:
        variation.runner(args)
        return
    if variation.ask_settings:
        variation.ask_settings(args)
    base = variation.source(args)
    col = start_mode(base, sk.int_or_random(args.rotation, "Mode"))
    session = Session(variation, args, base, col)
    show_start(session)
    menu_loop(session)


def ask_variation():
    names = list(VARIATIONS)
    width = max(len(name) for name in names) + 2
    shown = []
    for group in dict.fromkeys(VARIATIONS[name].group for name in names):
        print(f"{'' if not shown else chr(10)}{group}\n{'-' * len(group)}")
        for name in names:
            if VARIATIONS[name].group == group:
                shown.append(name)
                print(f"  {len(shown)}) {name:<{width}}{VARIATIONS[name].description}")
    while True:
        choice = input("\nVariation: ").strip().lower()
        if choice.isdigit() and 1 <= int(choice) <= len(shown):
            return shown[int(choice) - 1]
        if choice in VARIATIONS:
            return choice
        print(f"ValueError: Enter a number from 1 to {len(shown)}.")


def main():
    parser = sk.make_parser()
    parser.add_argument(
        "-m", "--rotation", default="1",
        help="Mode: 1 (default) is the collection as built, 2 starts on its second "
        "note, and so on; 'r' for a random one that fits.",
    )
    parser.add_argument(
        "variation", nargs="?", choices=list(VARIATIONS),
        help="Which variation to run (asked for if left out). The -f, -l and -g "
        "options apply to the skeleton variations (reprobate, flagellant, "
        "penitent, zealot, pietist; the last two have no grouping) and to the "
        "scale search, and -# to every one but tonal.",
    )
    args = parser.parse_args()
    run(VARIATIONS[args.variation or ask_variation()], args)


if __name__ == "__main__":
    main()
