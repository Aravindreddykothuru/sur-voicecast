"""The Alembic revision graph must actually resolve.

0002_segment_detected_language shipped with `down_revision =
"0001_initial_schema"` while 0001 declares `revision = "0001"`. Alembic
builds its revision map lazily, so nothing complained until the first real
`alembic upgrade head` -- which is the Docker `migrate` service and the CI
`migrate` job. The dev SQLite DB is built by Base.metadata.create_all(), not
migrations, so the whole test suite stayed green while `upgrade head` was
broken. This walks the graph the same way Alembic does, with no database.
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_revision_graph_resolves_to_a_single_head():
    script = _script_dir()
    # .get_revisions("heads") forces _revision_map to build -- this is the
    # exact call that raised KeyError: '0001_initial_schema'.
    heads = script.get_revisions("heads")
    assert len(heads) == 1, f"expected one migration head, found {[h.revision for h in heads]}"


def test_every_down_revision_points_at_a_real_revision():
    script = _script_dir()
    known = {rev.revision for rev in script.walk_revisions()}
    for rev in script.walk_revisions():
        for parent in rev._all_down_revisions:
            assert parent in known, (
                f"{rev.revision} lists down_revision {parent!r}, which is not a "
                f"known revision id. Known: {sorted(known)}"
            )


def test_full_chain_walks_from_head_to_base():
    script = _script_dir()
    head = script.get_current_head()
    assert head is not None, "no head revision"
    walked = list(script.walk_revisions("base", head))
    assert walked, "no revisions walked head->base"
    # The oldest revision in the walk must be the root (down_revision is None);
    # anything else means the chain doesn't actually reach base.
    assert walked[-1].down_revision is None, (
        f"chain bottoms out at {walked[-1].revision} whose down_revision is "
        f"{walked[-1].down_revision!r}, not the base"
    )
