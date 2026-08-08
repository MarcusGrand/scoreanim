"""The glow's scope on real scene items, offscreen: only notes light,
attached ink shares its note's halo, and a tied chain glows as one note.

The policy itself is core and lives in tests/test_glow_scope.py; the
sprite is tests/test_glow_render.py. This file is the applier obeying
both — through the driver (render/glow_driver.py) and the gate on the
item (render/properties.py).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (GLOWING_KINDS,  # noqa: E402
                                      StyleRules, build_reveal_tracks,
                                      build_trigger_schedule, glow_scope,
                                      resolve_durations)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

TEMPO = TempoMap([TempoEvent(0.0, 120.0)])
# Glow alone, stretched to each note's own value — which is the default,
# and the only setting under which "the chain burns longer" means
# anything. Attack 0 and release 1 make the light plain arithmetic: full
# at the onset, straight down to nothing at the span's end.
GLOW_RULES = StyleRules(default_effect="glow",
                        effect_params={"glow": {"attack": 0.0,
                                                "sustain": 1.0,
                                                "release": 1.0}})


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def parts(engraved, join_mapping, score_model):
    """Everything the applier needs derived once: the durations, the
    schedule, the reveal tracks and the glow scope."""
    durations = resolve_durations(engraved.layout, join_mapping,
                                  engraved.note_durations,
                                  score_model.measures)
    schedule = build_trigger_schedule(engraved.layout, join_mapping,
                                      score_model.measures, durations)
    score_end = max(m.start + m.quarter_length for m in score_model.measures)
    tracks = build_reveal_tracks(engraved.layout, schedule, score_end)
    scope = glow_scope(engraved.layout, join_mapping, durations)
    return durations, schedule, tuple(tracks), scope


@pytest.fixture()
def scene(qapp, engraved, parts):
    durations, schedule, tracks, scope = parts
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    scenes = ScoreScenes(engraved.layout, stage)
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES,
                               tracks, scenes.system_groups.values(), scope)
    return scenes, applier, schedule, scope, durations


def _lit_kinds(scenes) -> set:
    return {item.identity.kind for item in scenes.items.values()
            if item.identity is not None and item.glow_strength > 0.0}


def _sweep(scenes, applier, end: float, step: float = 0.05) -> set:
    """Every kind that lights at any point up to `end` seconds."""
    kinds: set = set()
    t = 0.0
    while t < end:
        applier.apply_at(t)
        kinds |= _lit_kinds(scenes)
        t += step
    return kinds


# -- the gate -------------------------------------------------------------

def test_only_note_ink_ever_lights_over_a_whole_playthrough(scene) -> None:
    scenes, applier, _schedule, _scope, _durations = scene
    kinds = _sweep(scenes, applier, 40.0)
    assert ElementKind.NOTEHEAD in kinds
    assert kinds <= GLOWING_KINDS, sorted(k.name for k in kinds
                                          - GLOWING_KINDS)


def test_a_rest_a_dynamic_and_a_signature_stay_dark(scene) -> None:
    scenes, applier, _schedule, _scope, _durations = scene
    dark = (ElementKind.REST, ElementKind.MREST, ElementKind.DYNAMIC,
            ElementKind.METER_SIG, ElementKind.KEY_SIG, ElementKind.CLEF,
            ElementKind.TEXT, ElementKind.CHORD_SYMBOL, ElementKind.SLUR,
            ElementKind.BARLINE, ElementKind.STAFF_LINES)
    present = {item.identity.kind for item in scenes.items.values()
               if item.identity is not None}
    assert set(dark) & present, "the fixture should carry some of these"
    assert not (_sweep(scenes, applier, 40.0) & set(dark))


def test_ink_that_cannot_glow_never_builds_a_sprite(scene) -> None:
    """Half the reason the scope is worth having: a page of rests and
    signatures costs nothing to blur."""
    scenes, applier, _schedule, _scope, _durations = scene
    _sweep(scenes, applier, 40.0)
    for eid, item in scenes.items.items():
        if item.identity is not None \
                and item.identity.kind not in GLOWING_KINDS:
            assert not item.can_glow, eid
            assert item._glow._sprite is None, eid


def test_the_gate_is_on_the_item_not_in_the_applier(scene) -> None:
    """A caller writing a glow straight onto ink that cannot carry one
    is refused at the property applier, wherever the value came from."""
    from scoreanim.render.properties import PROPERTY_APPLIERS
    from scoreanim.core.animation import GLOW
    scenes, _applier, _schedule, _scope, _durations = scene
    rest = next(item for item in scenes.items.values()
                if item.identity is not None
                and item.identity.kind is ElementKind.REST)
    PROPERTY_APPLIERS[GLOW](rest, 1.0)
    assert rest.glow_strength == 0.0


# -- the shared halo ------------------------------------------------------

def test_a_tie_glows_although_no_trigger_ever_reaches_it(scene) -> None:
    """Ties are clip-revealed, so they left the trigger schedule long
    ago. Their light comes from the note they belong to instead."""
    scenes, applier, schedule, scope, _durations = scene
    ties = [eid for eid, item in scenes.items.items()
            if item.identity is not None
            and item.identity.kind is ElementKind.TIE]
    assert ties
    assert not any(eid in schedule.beats_by_element for eid in ties)
    assert ElementKind.TIE in _sweep(scenes, applier, 40.0)


def test_a_chain_holds_one_light_across_all_of_its_ink(scene) -> None:
    scenes, applier, schedule, scope, durations = scene
    leader = max(scope.span, key=lambda eid: scope.span[eid])
    crew = [leader, *scope.followers()[leader]]
    assert any(scenes.items[e].identity.kind is ElementKind.NOTEHEAD
               for e in crew[1:]), "want a chain with a second notehead"

    start = TEMPO.seconds_at(schedule.beats_by_element[leader])
    span = TEMPO.seconds_at(schedule.beats_by_element[leader]
                            + scope.span[leader]) - start
    seen_lit = False
    for frac in (0.01, 0.25, 0.5, 0.75, 0.99):
        applier.apply_at(start + frac * span)
        values = {round(scenes.items[e].glow_strength, 9) for e in crew}
        assert len(values) == 1, (frac, values)
        seen_lit |= values.pop() > 0.0
    assert seen_lit


def test_a_chain_outlives_the_first_notehead_and_lands_on_nothing(
        scene) -> None:
    """The whole point of the longer burn: a held note is still lit
    where its own engraved value ran out, and dark exactly where the
    last of the chain stops."""
    scenes, applier, schedule, scope, durations = scene
    leader = max(scope.span, key=lambda eid: scope.span[eid])
    beats = schedule.beats_by_element[leader]
    own_end = TEMPO.seconds_at(beats + durations[leader])
    chain_end = TEMPO.seconds_at(beats + scope.span[leader])
    assert chain_end > own_end

    applier.apply_at(own_end)
    assert scenes.items[leader].glow_strength > 0.0
    applier.apply_at(chain_end)
    assert scenes.items[leader].glow_strength == pytest.approx(0.0)


def test_a_follower_is_never_lit_by_its_own_clock(scene) -> None:
    """A continuation notehead has a trigger of its own — it appears at
    its own barline. Its HALO is its leader's, so the gate is off."""
    scenes, _applier, schedule, scope, _durations = scene
    heads = [eid for eid in scope.owner
             if scenes.items[eid].identity.kind is ElementKind.NOTEHEAD]
    assert heads
    for eid in heads:
        assert eid in schedule.beats_by_element   # it still appears
        assert not scenes.items[eid].can_glow     # but it does not light


def test_a_notes_own_ink_lights_exactly_as_its_head_does(scene) -> None:
    """One note, one light. A stem, a beam, a flag, a dot, an
    articulation and a ledger dash all take the head's value, so no part
    of a note is ever brighter or dimmer than the rest of it — and on a
    tied note they hold for the whole chain, not for the notehead's own
    engraved value."""
    scenes, applier, schedule, scope, _durations = scene
    attached = (ElementKind.STEM, ElementKind.BEAM, ElementKind.FLAG,
                ElementKind.ARTICULATION, ElementKind.LEDGER_LINES,
                ElementKind.OTHER)
    leader = max(scope.span, key=lambda eid: scope.span[eid])
    crew = {eid: scenes.items[eid] for eid in scope.followers()[leader]}
    assert any(it.identity.kind in attached for it in crew.values()), \
        "want a tied note with some ink hanging off it"

    start = TEMPO.seconds_at(schedule.beats_by_element[leader])
    span = TEMPO.seconds_at(schedule.beats_by_element[leader]
                            + scope.span[leader]) - start
    lit = False
    for frac in (0.01, 0.4, 0.8, 0.99):
        applier.apply_at(start + frac * span)
        head = scenes.items[leader].glow_strength
        for eid, item in crew.items():
            assert item.glow_strength == pytest.approx(head, abs=1e-9), eid
        lit |= head > 0.0
    assert lit


def test_the_leader_pops_on_its_own_note_not_the_chain(scene) -> None:
    """The longer burn is the GLOW's alone: a scale on the same note is
    still timed to the notehead the user can see."""
    scenes, _applier, schedule, scope, durations = scene
    leader = max(scope.span, key=lambda eid: scope.span[eid])
    rules = StyleRules(default_effect="swell+glow",
                       effect_params=GLOW_RULES.effect_params)
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules,
                               (), scenes.system_groups.values(), scope)
    beats = schedule.beats_by_element[leader]
    own_end = TEMPO.seconds_at(beats + durations[leader])
    chain_end = TEMPO.seconds_at(beats + scope.span[leader])
    applier.apply_at(own_end)
    # the swell has settled back onto the engraved size...
    assert scenes.items[leader].scale() == pytest.approx(1.0, abs=1e-6)
    # ...while the glow is still burning for the rest of the chain
    assert scenes.items[leader].glow_strength > 0.0
    applier.apply_at(chain_end)
    assert scenes.items[leader].glow_strength == pytest.approx(0.0)


# -- the stale-state reset ------------------------------------------------

def test_dropping_the_glow_puts_a_tie_out_too(scene) -> None:
    """A tie receives no trigger, so the applier's own reset loop cannot
    reach it — the driver has to."""
    scenes, applier, schedule, scope, _durations = scene
    tie = next(eid for eid, owner in scope.owner.items()
               if scenes.items[eid].identity.kind is ElementKind.TIE
               and owner in schedule.beats_by_element)
    applier.apply_at(TEMPO.seconds_at(
        schedule.beats_by_element[scope.owner[tie]]))
    assert scenes.items[tie].glow_strength > 0.0

    applier.set_style(StyleRules(default_effect="pop"))
    assert scenes.items[tie].glow_strength == 0.0


# -- the halo never runs ahead of the ink ---------------------------------

def test_a_ties_halo_is_cut_where_its_ink_is(scene) -> None:
    """A tie grows left-to-right against the reveal edge. Its light has
    to stop in the same place, or a held note's glow runs a bar ahead of
    the playhead.

    Compared in SCENE coordinates: the halo pixmap and the ink path have
    different local axes, and each maps the one pushed edge through its
    own inverse."""
    from PySide6.QtCore import QPointF
    scenes, applier, _schedule, _scope, _durations = scene
    ties = [item for item in scenes.items.values()
            if item.identity is not None
            and item.identity.kind is ElementKind.TIE and item.reveal_children]
    assert ties

    caught = 0
    t = 0.0
    while t < 20.0:
        applier.apply_at(t)
        for item in ties:
            sprite = item._glow._sprite
            if sprite is None or item.glow_strength <= 0.0:
                continue
            child = item.reveal_children[0]
            edge = child.clip_right
            if edge is None:
                continue                            # fully shown
            # the halo's box is the ink's plus the blur's margin, so ink
            # still cut means halo still cut — never a light standing
            # over ink that is not there
            assert sprite._clip_right is not None
            if edge <= child.boundingRect().left():
                continue                            # nothing shown yet
            ink_x = child.sceneTransform().map(QPointF(edge, 0.0)).x()
            halo_x = sprite.sceneTransform().map(
                QPointF(sprite._clip_right, 0.0)).x()
            assert halo_x == pytest.approx(ink_x, abs=1e-6)
            caught += 1
        t += 0.05
    assert caught, "no tie was caught mid-reveal while lit"
