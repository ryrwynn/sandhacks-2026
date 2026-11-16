"""Sprint step 0: the prefill table is one shared constant; the TS copy must match the Python one."""
import importlib.util
from pathlib import Path

import pytest

from contracts.prefill import PREFILL, form_url

ROOT = Path(__file__).resolve().parents[2]


def _gen():
    spec = importlib.util.spec_from_file_location("gen_prefill", ROOT / "scripts" / "gen-prefill.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_ts_copy_is_current():
    assert (ROOT / "frontend/src/lib/prefill.ts").read_text() == _gen().render()


def test_form_url_builds_only_known_params():
    assert form_url("listing", zip="92104", beds=1, asking=2400.0) == "/renter?tab=listing&zip=92104&beds=1&asking=2400"
    assert form_url("renter", corp=True, notice=None) == "/renter?corp=yes"
    with pytest.raises(ValueError):
        form_url("gouging", rent=1)


def test_every_form_has_a_path():
    assert {f["path"] for f in PREFILL.values()} >= {"/renter", "/gouging", "/owner", "/owner/reach", "/buyer", "/find", "/advisor"}
