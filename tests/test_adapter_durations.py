"""M4.1: per-element engraved durations (EngravedScore.note_durations).

The timemap's off/restsOff arrays are symmetric to on/restsOn, so every
note and rest element carries an exact duration — off − on, on the same
performance axis as every onset (rule 12: one axis, no next-onset
inference). A tied notehead's entry is its OWN segment length, not the
chain end; pickup-bar durations are the engraved (short) ones, never
music21's nominal padding.
"""

from scoreanim.core.score.identity import ElementKind

_REST_KINDS = {ElementKind.REST, ElementKind.MREST}


def test_every_note_and_rest_has_a_positive_duration(engraved):
    missing = [r.element_id for r in engraved.note_records
               if r.element_id not in engraved.note_durations]
    assert not missing
    rest_ids = [el.identity.element_id for el in engraved.layout.elements
                if el.identity.kind in _REST_KINDS]
    assert rest_ids
    assert all(i in engraved.note_durations for i in rest_ids)
    assert all(d > 0 for d in engraved.note_durations.values())


def test_durations_cover_only_notes_and_rests(engraved):
    # Absent id → no entry: nothing outside the timemap-class elements
    # (no stem/flag/spanner ever mints a duration off a colliding id).
    note_ids = {r.element_id for r in engraved.note_records}
    rest_ids = {el.identity.element_id for el in engraved.layout.elements
                if el.identity.kind in _REST_KINDS}
    assert set(engraved.note_durations) == note_ids | rest_ids


def test_plain_quarter_is_one_beat(engraved):
    quarters = [r.element_id for r in engraved.note_records
                if not r.grace
                and engraved.note_durations[r.element_id] == 1.0]
    assert quarters


def test_grace_duration_is_fractional(engraved):
    graces = [r for r in engraved.note_records if r.grace]
    assert graces
    for r in graces:
        assert 0.0 < engraved.note_durations[r.element_id] < 0.1


def test_tied_notehead_carries_its_own_segment(engraved):
    # For every tie with a resolved extent: the start notehead's duration
    # is exactly the tie's span (its own notated segment, NOT the chain
    # end), and the continuation notehead carries its own positive entry.
    by_pos: dict[tuple, list] = {}
    for r in engraved.note_records:
        by_pos.setdefault((r.part, r.staff, r.voice, r.onset), []).append(r)
    checked = 0
    for el in engraved.layout.elements:
        idn = el.identity
        if idn.kind is not ElementKind.TIE:
            continue
        if ":seg" in str(idn.element_id):
            continue                     # continuation ink, same identity
        if idn.extent is None or idn.extent[1] <= idn.extent[0]:
            continue                     # unresolved end: no span to pin
        start, end = idn.extent
        span = end - start
        starts = by_pos.get((idn.part, idn.staff, idn.voice, start), [])
        conts = by_pos.get((idn.part, idn.staff, idn.voice, end), [])
        if not starts or not conts:
            continue
        for r in starts:
            assert engraved.note_durations[r.element_id] == span
        for r in conts:
            assert engraved.note_durations[r.element_id] > 0.0
        checked += 1
    assert checked >= 10                 # testscore has 59 tie sources


def test_pickup_bar_durations_are_engraved_not_nominal(engraved_pickup):
    tl = engraved_pickup.timeline
    # The "X0" pickup bar is ordinal 1 and engraved SHORT of a full bar.
    assert tl.durations[1] < tl.durations[2]
    m1 = [r for r in engraved_pickup.note_records if r.measure == 1]
    assert m1
    for r in m1:
        dur = engraved_pickup.note_durations[r.element_id]
        # nominal padding would push the note past the engraved bar
        assert r.onset + dur <= tl.starts[2]
    # the pickup voice fills its short bar exactly to the next downbeat
    assert max(r.onset + engraved_pickup.note_durations[r.element_id]
               for r in m1) == tl.starts[2]
