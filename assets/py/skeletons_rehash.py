import argparse
import random
import shutil
import textwrap

SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

OPEN_PITCHES = [40, 45, 50, 55, 59, 64]  # E A D G B e in semitones (low E = 40)
BASE_NOTES = [p % 12 for p in OPEN_PITCHES]  # the same, as pitch classes
STRING_NAMES = ["E", "A", "D", "g", "b", "e"]  # low to high, matching BASE_NOTES
FOURTH = 5  # the spacing the skeleton's windows assume
OCTAVE = 12

NUM_FRETS = 21
MAX_FRET = NUM_FRETS - 4  # highest starting fret
STRETCH = 5  # widest allowed gap between fretted notes, in frets (a fourth)
# Kinds with their own stretch rule (None: no limit). The zealot lies along one
# string, so a wide skeleton is a change of position, not a stretch of the hand.
STRETCHES = {"zealot": None}
MAX_TRIES = 500  # skeletons drawn for one setting before giving up on it
MAX_ATTEMPTS = 50  # settings tried when some are left on random
MIN_WIDTH = 40  # narrowest frame around a printed skeleton
ZEALOT_CEILING = OCTAVE  # the zealot spans at most an octave (offsets 0 to 12)
ZEALOT_MAX_LENGTH = 12  # longest zealot drawn when the length is left on random

KINDS = ("reprobate", "flagellant", "penitent", "zealot", "pietist", "schismatic")
# Kinds whose modes are not defined yet: only mode I is possible.
NO_MODES = ("pietist", "schismatic")
# Kinds with no string grouping: their pattern is not tied to one.
NO_GROUPING = ("zealot", "pietist")
# Kinds whose tab does not depend on the grouping: it only sets their ceiling.
GROUPING_IGNORED = ("penitent",)
# Kinds that are melodies, not sorted patterns: the other kinds cannot place them,
# and they cannot be compared. Their "grouping" is the string the melody starts on.
MELODIC = ("schismatic",)
DEFAULT_INTERVAL = 4  # the schismatic's maximum step when none is given: a major third
MAX_INTERVAL = 12  # the widest maximum step it accepts: an octave
MELODY_LENGTHS = (2, 32)  # shortest and longest schismatic melody
MELODY_RANDOM_LENGTHS = (6, 12)  # the range drawn when the length is left on random
PIETIST_MAX_GAP = 2  # widest step between neighbouring notes: a major second

# grouping -> (min length, max length). Ceiling is 5 * grouping - 1 (4, 9, 14).
LENGTH_RANGES = {1: (2, 4), 2: (2, 8), 3: (3, 12)}


def ceiling_for(grouping):
    return FOURTH * grouping - 1


def reach(start_fret):
    """The lowest and highest fret the hand covers from a start fret.

    That is the stretch, and at fret 0 one more, since the open string is free.
    """
    top = start_fret + STRETCH + (1 if start_fret == 0 else 0)
    return start_fret, min(top, NUM_FRETS)


def ceiling_of(kind, grouping, start_fret):
    """Highest offset a skeleton of this kind may reach.

    The zealot spans at most an octave, and still has to stay on the neck. The b
    and e strings sit one fret higher than the others, so that is the fret to
    keep on the neck.
    """
    if kind == "zealot":
        return min(ZEALOT_CEILING, NUM_FRETS - 1 - start_fret)
    if kind == "pietist":
        _, top_fret = reach(start_fret)
        return OPEN_PITCHES[-1] + top_fret - (OPEN_PITCHES[0] + start_fret)
    return ceiling_for(grouping)


def window_for(kind, grouping, skeleton):
    """The distance a note moves up when a mode rotates it to the end.

    Most kinds use one string group (5 semitones per string). The zealot uses
    one more than its ceiling (13), like the others, so a rotated pattern always
    stays within the octave.
    """
    if kind == "zealot":
        return ZEALOT_CEILING + 1
    return FOURTH * grouping


def unearth_skeleton(length, ceiling):
    """Sorted unique offsets that always include 0 and stay within the ceiling."""
    if length < 2:
        raise ValueError("Length must be at least 2.")
    if length - 1 > ceiling:
        raise ValueError("Length can be at most ceiling + 1.")
    return [0] + sorted(random.sample(range(1, ceiling + 1), k=length - 1))


def unearth_steps(top):
    """A stepwise skeleton from 0 up towards `top`.

    Every step is 1 or 2 semitones, and never two 1s in a row. It climbs until
    no step fits any more under `top`, so its length is decided by the climb.
    """
    skeleton, last_gap = [0], PIETIST_MAX_GAP
    while True:
        gaps = [g for g in (1, 2) if not (g == 1 and last_gap == 1)]
        gaps = [g for g in gaps if skeleton[-1] + g <= top]
        if not gaps:
            return skeleton
        last_gap = random.choice(gaps)
        skeleton.append(skeleton[-1] + last_gap)


def has_chromatic_run(skeleton, run=4):
    """True if `run` consecutive semitones occur, e.g. [0, 1, 2, 3]."""
    return any(
        skeleton[i + run - 1] - skeleton[i] == run - 1
        for i in range(len(skeleton) - run + 1)
    )


def has_cluster_at_both_ends(skeleton, ceiling):
    """Starts with 0, 1 and ends with ceiling-2, ceiling-1, ceiling."""
    return skeleton[1] == 1 and skeleton[-3:] == [ceiling - 2, ceiling - 1, ceiling]


def has_melodic_chromatic_run(melody, run=4):
    """True if `run` notes in a row move by single semitones in one direction."""
    steps = [b - a for a, b in zip(melody, melody[1:])]
    return any(
        abs(steps[i]) == 1 and steps[i:i + run - 1] == [steps[i]] * (run - 1)
        for i in range(len(steps) - run + 2)
    )


def reachable_offsets(start_string, start_fret):
    """Offsets from the first note that the hand can play in one position."""
    low, high = reach(start_fret)
    root = OPEN_PITCHES[start_string] + start_fret
    return {
        OPEN_PITCHES[string] + fret - root
        for string in range(len(OPEN_PITCHES))
        for fret in range(low, high + 1)
    }


def unearth_melody(length, start_string, start_fret, interval):
    """A random melody: offsets from 0 where each note lies within `interval`
    semitones, above or below, of the one before. A note never repeats straight
    away, never leaves the hand's reach, and four notes never run by semitones in
    one direction. None if it paints itself into a corner.
    """
    reachable = reachable_offsets(start_string, start_fret)
    melody, steps = [0], []
    while len(melody) < length:
        options = [
            step
            for step in range(-interval, interval + 1)
            if step
            and melody[-1] + step in reachable
            and not (abs(step) == 1 and steps[-2:] == [step, step])
        ]
        if not options:
            return None
        steps.append(random.choice(options))
        melody.append(melody[-1] + steps[-1])
    return melody


def rotate_skeleton(skeleton, n, window):
    """Mode n of a skeleton (1 is the skeleton itself), as a new pattern.

    Mode n starts on the nth offset: the offsets before it move up one window and
    follow the rest, and everything is re-based so the new first note is 0. The
    window is one more than the ceiling (or, for the zealot, clears the last
    offset), so the offsets stay unique and sorted.
    """
    root = skeleton[n - 1]
    rotated = skeleton[n - 1:] + [offset + window for offset in skeleton[: n - 1]]
    return [offset - root for offset in rotated]


def place_skeleton(skeleton, grouping, start_fret):
    """Reprobate: fret numbers for each string (low to high), as six lists.

    Each skeleton note is played on one string of its group: offsets 0-4 on the
    first, 5-9 on the second, 10-14 on the third. A skeleton no longer than the
    grouping puts one note on each string. The same fret shape is used on every
    group, so the upper strings of the G-B-e group sound a semitone lower.
    """
    frets = []
    for string in range(len(BASE_NOTES)):
        k = string % grouping
        frets.append(
            [
                start_fret + offset - FOURTH * k
                for i, offset in enumerate(skeleton)
                if (i if len(skeleton) <= grouping else offset // FOURTH) == k
            ]
        )
    return frets


def place_flagellant(skeleton, grouping, start_fret):
    """Flagellant: fret numbers for each string (low to high), as six lists.

    The notes go on the same strings as in the reprobate, but the pitch intervals
    are preserved everywhere: the pattern repeats once per string group at a
    constant distance (the group's window, FOURTH * grouping semitones), so the
    gap between the last note of a pattern and the first of its repetition is
    the same each time. The frets follow the actual tuning, which matters where
    the strings are not a fourth apart (G to B).
    """
    window = FOURTH * grouping
    frets = [[] for _ in OPEN_PITCHES]
    for repetition in range(len(OPEN_PITCHES) // grouping):
        root = OPEN_PITCHES[0] + start_fret + repetition * window
        for i, offset in enumerate(skeleton):
            k = i if len(skeleton) <= grouping else offset // FOURTH
            string = repetition * grouping + k
            frets[string].append(root + offset - OPEN_PITCHES[string])
    return frets


def string_for(pitch, start_fret):
    """The string a pitch falls on, or None if it is out of the hand's reach.

    A note belongs on a string if its fret lies within one window of the start
    fret. Where two strings qualify, the higher one (the lower fret) wins.
    """
    for string in reversed(range(len(OPEN_PITCHES))):
        fret = pitch - OPEN_PITCHES[string]
        if start_fret <= fret <= start_fret + ceiling_for(1):
            return string
    return None


def place_penitent(skeleton, grouping, start_fret):
    """Penitent: fret numbers for each string (low to high), as six lists.

    The pattern starts on the low string. Its last note becomes the first note
    of the next repetition, so the chain climbs the neck with no interval
    correction, and the shared note is placed once. The chain stops when the
    next repetition would not fit on the highest string. The grouping only sets
    the pattern's width (through the ceiling).
    """
    frets = [[] for _ in OPEN_PITCHES]
    root = OPEN_PITCHES[0] + start_fret
    while True:
        pitches = [root + offset for offset in skeleton]
        strings = [string_for(pitch, start_fret) for pitch in pitches]
        if None in strings:
            break
        for pitch, string in zip(pitches, strings):
            frets[string].append(pitch - OPEN_PITCHES[string])
        root += skeleton[-1]
    return [sorted(set(string_frets)) for string_frets in frets]


def place_zealot(skeleton, grouping, start_fret):
    """Zealot: fret numbers for each string (low to high), as six lists.

    The whole skeleton lies along one string, and the same skeleton is repeated
    on every string a fourth higher than the last. The intervals are preserved,
    so the frets follow the actual tuning: the b and e strings sit one fret
    higher (G to B is a major third). There is no string grouping.
    """
    frets = []
    for string, open_pitch in enumerate(OPEN_PITCHES):
        root = OPEN_PITCHES[0] + start_fret + FOURTH * string
        frets.append([root + offset - open_pitch for offset in skeleton])
    return frets


def string_within_reach(pitch, start_fret):
    """The string a pitch falls on within the hand's reach, or None.

    Where two strings qualify, the higher one (the lower fret) wins.
    """
    low, high = reach(start_fret)
    for string in reversed(range(len(OPEN_PITCHES))):
        if low <= pitch - OPEN_PITCHES[string] <= high:
            return string
    return None


def place_pietist(skeleton, grouping, start_fret):
    """Pietist: fret numbers for each string (low to high), as six lists.

    One line of notes climbs from the low string to the high one, every note on
    the string where it falls within the stretch. Nothing is repeated, and no
    string grouping is used. A note out of reach goes on the top string beyond
    the stretch, so that curation turns the skeleton down.
    """
    frets = [[] for _ in OPEN_PITCHES]
    root = OPEN_PITCHES[0] + start_fret
    for offset in skeleton:
        string = string_within_reach(root + offset, start_fret)
        if string is None:
            string = len(OPEN_PITCHES) - 1
        frets[string].append(root + offset - OPEN_PITCHES[string])
    return frets


def melody_positions(melody, start_string, start_fret):
    """(string, fret) for each note of a melody, in playing order, or None.

    The hand stays in one position (the start fret and its reach). The first note
    is on the start string; each next note goes on the string that keeps it
    nearest the one before, then the smaller move along the neck, then the lower
    string. None if a note lies outside the hand's reach.
    """
    low, high = reach(start_fret)
    root = OPEN_PITCHES[start_string] + start_fret
    positions = []
    string, fret = start_string, start_fret
    for offset in melody:
        pitch = root + offset
        options = [
            (candidate, pitch - OPEN_PITCHES[candidate])
            for candidate in range(len(OPEN_PITCHES))
            if low <= pitch - OPEN_PITCHES[candidate] <= high
        ]
        if not options:
            return None
        string, fret = min(
            options, key=lambda o: (abs(o[0] - string), abs(o[1] - fret), o[0])
        )
        positions.append((string, fret))
    return positions


def place_schismatic(melody, start_string, start_fret):
    """Schismatic: fret numbers for each string (low to high), as six lists.

    These are the places the melody uses, with no order and no repeats. Use
    melody_positions for the notes in the order they are played.
    """
    frets = [[] for _ in OPEN_PITCHES]
    for string, fret in melody_positions(melody, start_string, start_fret) or []:
        if fret not in frets[string]:
            frets[string].append(fret)
    return [sorted(string_frets) for string_frets in frets]


PLACERS = {
    "reprobate": place_skeleton,
    "flagellant": place_flagellant,
    "penitent": place_penitent,
    "zealot": place_zealot,
    "pietist": place_pietist,
    "schismatic": place_schismatic,
}


def is_playable(frets_by_string, stretch=STRETCH):
    """Frets on the neck, and fretted notes within the stretch (None: no limit)."""
    frets = [f for string in frets_by_string for f in string]
    fretted = [f for f in frets if f > 0]
    return (
        min(frets) >= 0
        and max(frets) <= NUM_FRETS
        and (stretch is None or not fretted or max(fretted) - min(fretted) <= stretch)
    )


def tab_print(frets_by_string, pad=2):
    """The tab, high string on top, with each fret in a column of its own.

    A fret number is in the same column on every string, so the numbers line up
    with their place on the neck. Where a string has no note at that fret, the
    column holds dashes.
    """
    columns = sorted({fret for string in frets_by_string for fret in string})
    lines = []
    for name, frets in zip(STRING_NAMES, frets_by_string):
        cells = [
            str(fret) if fret in frets else "-" * len(str(fret)) for fret in columns
        ]
        lines.append(f"{name:<{pad}}| {'--'.join(cells)}")
    return "\n".join(reversed(lines))


def melody_failure(melody, start_string, start_fret):
    """Why a melody is turned down, or None if it passes.

    The largest step is the user's choice, so it is enforced when a melody is
    generated, not here.
    """
    if any(a == b for a, b in zip(melody, melody[1:])):
        return "repeats a note straight away"
    if has_melodic_chromatic_run(melody):
        return "has a run of four semitones"
    if melody_positions(melody, start_string, start_fret) is None:
        return "goes beyond the hand's reach"
    return None


def curation_failure(skeleton, grouping, start_fret, kind="reprobate"):
    """Why a skeleton is turned down for this kind, or None if it passes.

    It must fit the kind's ceiling, leave no string empty, be playable, and
    pass the rules on the pattern itself. A melody has rules of its own.
    """
    if kind == "schismatic":
        return melody_failure(skeleton, grouping, start_fret)
    ceiling = ceiling_of(kind, grouping, start_fret)
    if skeleton[-1] > ceiling:
        return "reaches past its ceiling"
    frets = PLACERS[kind](skeleton, grouping, start_fret)
    if not all(frets):
        return "leaves a string empty"
    if not is_playable(frets, STRETCHES.get(kind, STRETCH)):
        return "does not fit the neck and the stretch"
    if kind == "pietist":
        steps = zip(skeleton, skeleton[1:])
        if any(b - a > PIETIST_MAX_GAP for a, b in steps):
            return "has a step wider than a major second"
        if has_chromatic_run(skeleton, 3):
            return "has a chromatic run"
        return None
    if has_chromatic_run(skeleton):
        return "has a run of four semitones"
    # The neck can lower the zealot's ceiling, but its end cluster is always
    # measured against the full octave.
    end = ZEALOT_CEILING if kind == "zealot" else ceiling
    if has_cluster_at_both_ends(skeleton, end):
        return "has a cluster at both ends"
    return None


def is_curated(skeleton, grouping, start_fret, kind="reprobate"):
    """A valid skeleton: fits the kind, passes the pattern rules, is playable."""
    return curation_failure(skeleton, grouping, start_fret, kind) is None


def form_skeleton(length, grouping, start_fret, kind="reprobate", interval=None):
    """Generate skeletons until one passes curation (None if none turns up).

    The pietist ignores the length: its length comes from the climb. For the
    schismatic the "grouping" is its start string, and `interval` is its largest
    step.
    """
    if kind == "schismatic":
        def draw():
            return unearth_melody(length, grouping, start_fret, interval)
    elif kind == "pietist":
        ceiling = ceiling_of(kind, grouping, start_fret)

        def draw():
            return unearth_steps(ceiling)
    else:
        ceiling = ceiling_of(kind, grouping, start_fret)
        if length - 1 > ceiling:
            return None

        def draw():
            return unearth_skeleton(length, ceiling)

    for _ in range(MAX_TRIES):
        skeleton = draw()
        if skeleton and is_curated(skeleton, grouping, start_fret, kind):
            return skeleton
    return None


def int_or_random(value, name):
    """None means random, whether it was left out or given as r."""
    if value in (None, "r", ""):
        return None
    if value.isdigit():
        return int(value)
    raise SystemExit(f"{name}: a number or 'r' for random.")


def choose_settings(grouping, length):
    """Resolve random (None) choices into a valid (grouping, length) pair."""
    if grouping is None:
        options = [
            g
            for g, (lo, hi) in LENGTH_RANGES.items()
            if length is None or lo <= length <= hi
        ]
        if not options:
            raise SystemExit("Length must be between 2 and 12.")
        grouping = random.choice(options)
    elif grouping not in LENGTH_RANGES:
        raise SystemExit("Grouping: 1 to 3 or 'r' for random.")

    lo, hi = LENGTH_RANGES[grouping]
    if length is None:
        length = random.randint(lo, hi)
    elif not lo <= length <= hi:
        raise SystemExit(
            f"Length for a grouping of {grouping} must be between {lo} and {hi}."
        )
    return grouping, length


def make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f", "--fret", default="r",
        help="Starting fret: a number or 'r' for random (default). "
        f"Highest allowed fret is {MAX_FRET}.",
    )
    parser.add_argument(
        "-l", "--length", default=None,
        help="Skeleton length: a number or 'r' for random. "
        "Allowed range depends on grouping: 2-4, 2-8, 3-12 for groupings 1, 2, 3. "
        "The zealot has no grouping: any length from 2 to 13 (an octave). "
        "The pietist has no grouping and no length: its climb decides. "
        "The schismatic takes 2 to 32.",
    )
    parser.add_argument(
        "-g", "--grouping", default="r",
        help="Grouping size, 1 to 3, or 'r' for random (default). "
        "Ignored by the zealot, the pietist and the schismatic.",
    )
    parser.add_argument(
        "-t", "--string", default=None,
        help="String the schismatic starts on: E A D g b e (E low, e high), "
        "or 'r' for random.",
    )
    parser.add_argument(
        "-i", "--interval", default=None,
        help=f"Largest step of the schismatic in semitones, 1 to {MAX_INTERVAL} "
        f"(default {DEFAULT_INTERVAL}).",
    )
    parser.add_argument(
        "-#", "--shflat", choices=["#", "b"], default="#",
        help="Show sharps ('#') or flats ('b'). Defaults to sharps.",
    )
    return parser


def parse_args():
    parser = make_parser()
    parser.add_argument(
        "-k", "--kind", choices=KINDS, default="reprobate",
        help="Kind of skeleton (default: reprobate).",
    )
    return parser.parse_args()


def start_string_of(value):
    """The index of the string named (E A D g b e), or a random one."""
    if value in (None, "r", ""):
        return random.randrange(len(STRING_NAMES))
    names = {"E": 0, "a": 1, "A": 1, "d": 2, "D": 2, "g": 3, "G": 3, "b": 4, "B": 4, "e": 5}
    if value not in names:
        raise SystemExit("String: E A D g b e (E low, e high), or 'r' for random.")
    return names[value]


def melody_length(length):
    """The melody's length: as given, or random."""
    low, high = MELODY_LENGTHS
    if length is None:
        return random.randint(*MELODY_RANDOM_LENGTHS)
    if not low <= length <= high:
        raise SystemExit(f"Length for a schismatic must be between {low} and {high}.")
    return length


def melody_interval(args):
    """The largest step of the melody, in semitones."""
    value = args.interval
    if value in (None, ""):
        return DEFAULT_INTERVAL
    if not (value.isdigit() and 1 <= int(value) <= MAX_INTERVAL):
        raise SystemExit(f"Interval: a number from 1 to {MAX_INTERVAL}.")
    return int(value)


def draw_settings(args, kind):
    """Resolve the random choices for one try: (grouping, length, start_fret).

    The zealot and the pietist have no grouping, so theirs is None. The
    pietist's length is None too: its climb decides. For the schismatic the
    "grouping" is the start string.
    """
    start_fret = int_or_random(args.fret, "Fret")
    if start_fret is None:
        start_fret = random.randint(0, MAX_FRET)
    elif start_fret > MAX_FRET:
        raise SystemExit(f"Starting fret too high: the maximum is {MAX_FRET}.")

    length = int_or_random(args.length, "Length")
    if kind == "schismatic":
        return start_string_of(args.string), melody_length(length), start_fret
    if kind == "pietist":
        return None, None, start_fret
    if kind == "zealot":
        if length is None:
            longest = min(ZEALOT_MAX_LENGTH, ceiling_of(kind, None, start_fret) + 1)
            length = random.randint(2, longest)
        elif length < 2:
            raise SystemExit("Length must be at least 2.")
        return None, length, start_fret

    grouping, length = choose_settings(
        int_or_random(args.grouping, "Grouping"), length
    )
    return grouping, length, start_fret


def generate_skeleton(args, kind="reprobate"):
    """Resolve the settings and generate one: (skeleton, grouping, start_fret).

    Settings left on random are redrawn if no skeleton turns up for them.
    """
    interval = melody_interval(args) if kind == "schismatic" else None
    for _ in range(MAX_ATTEMPTS):
        grouping, length, start_fret = draw_settings(args, kind)
        skeleton = form_skeleton(length, grouping, start_fret, kind, interval)
        if skeleton:
            return skeleton, grouping, start_fret
    raise SystemExit(
        "No skeleton turned up for those settings. Try different -g, -l, -f or -i values."
    )


def place_with_notes(skeleton, grouping, start_fret, shflat="#", kind="reprobate"):
    """Per-string frets and note names (low string to high) for a placed skeleton."""
    frets = PLACERS[kind](skeleton, grouping, start_fret)
    names = SHARPS if shflat == "#" else FLATS
    notes = [
        names[(open_string + fret) % 12]
        for open_string, string_frets in zip(BASE_NOTES, frets)
        for fret in string_frets
    ]
    return frets, notes


def setting_line(kind, grouping):
    """The line that names the kind's own setting, or None."""
    if kind in MELODIC:
        return f"Start string: {STRING_NAMES[grouping]}"
    return f"String grouping: {grouping}" if grouping else None


def melody_tab(positions, pad=2):
    """A tab in playing order: one column per note, high string on top.

    A long melody wraps onto further blocks, so that no line is wider than the
    terminal.
    """
    room = shutil.get_terminal_size().columns - 8  # leaves room for the frame
    blocks, row, used = [], [], pad + 2
    for string, fret in positions:
        width = len(str(fret)) + 2
        if row and used + width > room:
            blocks.append(row)
            row, used = [], pad + 2
        row.append((string, fret))
        used += width
    blocks.append(row)

    def block_lines(block):
        lines = []
        for string, name in enumerate(STRING_NAMES):
            cells = [
                str(fret) if note_string == string else "-" * len(str(fret))
                for note_string, fret in block
            ]
            lines.append(f"{name:<{pad}}| {'--'.join(cells)}")
        return "\n".join(reversed(lines))

    return "\n\n".join(block_lines(block) for block in blocks)


def display_skeleton(skeleton, grouping, start_fret, shflat="#", kind="reprobate"):
    """The tab and the note names to print. A melody is shown in playing order."""
    frets, notes = place_with_notes(skeleton, grouping, start_fret, shflat, kind)
    if kind not in MELODIC:
        return tab_print(frets), notes
    names = SHARPS if shflat == "#" else FLATS
    positions = melody_positions(skeleton, grouping, start_fret)
    notes = [names[(BASE_NOTES[string] + fret) % 12] for string, fret in positions]
    return melody_tab(positions), notes


def build_skeleton(args, kind="reprobate"):
    """Returns (start_fret, setting line, skeleton, tab, skel_notes)."""
    skeleton, grouping, start_fret = generate_skeleton(args, kind)
    tab, notes = display_skeleton(skeleton, grouping, start_fret, args.shflat, kind)
    return start_fret, setting_line(kind, grouping), skeleton, tab, notes


def print_skeleton(start_fret, setting, skeleton, tab, skel_notes):
    """`skeleton` may be None to leave the pattern line out; `setting` may be
    None (the kinds with no grouping) to leave that line out.

    Everything is framed in rules, with a thin one between the sections.
    """
    width = max(MIN_WIDTH, max(len(line) for line in tab.splitlines()))
    heavy, thin = "=" * width, "-" * width

    settings = f"Starting fret: {start_fret}"
    if setting:
        settings += f"\n{setting}"
    sections = [tab, settings]
    if skeleton:
        sections.append("Skeleton:\n" + textwrap.fill(", ".join(map(str, skeleton)), width))
    sections.append("Notes:\n" + textwrap.fill(", ".join(skel_notes), width))

    print(f"\n{heavy}\n" + f"\n{thin}\n".join(sections) + f"\n{heavy}")


def main():
    args = parse_args()
    print_skeleton(*build_skeleton(args, args.kind))


if __name__ == "__main__":
    main()
