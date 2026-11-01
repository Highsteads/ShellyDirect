#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_changelog_docs.py
# Description: docs/changelog.md (the "Version history" page of the online
#              guide) must have an entry for the version in Info.plist, and it
#              must be the newest one. test_version_consistency.py already
#              checks the README; this covers the guide's own page.
# Author:      CliveS & Claude Opus 5.5
# Date:        01-11-2026
# Version:     1.0

from __future__ import annotations

import plistlib
import re
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent.parent
INFO_PLIST = REPO_ROOT / "ShellyDirect.indigoPlugin" / "Contents" / "Info.plist"
CHANGELOG  = REPO_ROOT / "docs" / "changelog.md"

# Entries are written "## 4.3.5 — 5 October 2026".
_ENTRY_RE = re.compile(r"^##\s+v?(\d+(?:\.\d+)+)\b", re.M)


def _plist_version():
    with open(INFO_PLIST, "rb") as f:
        return plistlib.load(f)["PluginVersion"]


def _entries():
    return _ENTRY_RE.findall(CHANGELOG.read_text(encoding="utf-8"))


def test_changelog_has_entries():
    assert CHANGELOG.exists(), "docs/changelog.md is missing"
    assert _entries(), "docs/changelog.md has no '## x.y.z' entries"


def test_changelog_documents_the_current_version():
    assert _plist_version() in _entries(), (
        f"docs/changelog.md has no entry for {_plist_version()}")


def test_newest_changelog_entry_is_the_current_version():
    assert _entries()[0] == _plist_version(), (
        f"newest docs/changelog.md entry is {_entries()[0]}, "
        f"Info.plist says {_plist_version()}")


def test_changelog_entries_are_newest_first():
    as_tuples = [tuple(int(p) for p in v.split(".")) for v in _entries()]
    assert as_tuples == sorted(as_tuples, reverse=True), "entries are out of order"
