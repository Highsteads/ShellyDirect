#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_config_xml.py
# Description: Generic guards on the plugin's XML files (Devices, Actions,
#              Events, MenuItems, PluginConfig). Indigo only reads most of this
#              XML when a person opens a dialog or runs a menu item, so a broken
#              file, a duplicate field id or a callback name that does not exist
#              in plugin.py is invisible until someone clicks on it. Ported from
#              the ApplianceMonitor suite and extended with the "every callback
#              named in the XML exists in plugin.py" check.
# Author:      CliveS & Claude Opus 5.5
# Date:        01-11-2026
# Version:     1.0

from __future__ import annotations

import collections
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SERVER_DIR = (Path(__file__).resolve().parent.parent
              / "ShellyDirect.indigoPlugin" / "Contents" / "Server Plugin")
XML_FILES  = sorted(SERVER_DIR.glob("*.xml"))
XML_IDS    = [p.name for p in XML_FILES]

# Indigo right-aligns every <Label> and puts the control beside it, so the
# widest label sets the control column, and a <Description> never wraps. Same
# limits as ApplianceMonitor's test_config_xml.py.
MAX_CONTROL_LABEL_CHARS = 100
MAX_DESCRIPTION_CHARS   = 100


def _root(path):
    return ET.parse(path).getroot()


def _dialog_scopes(root, path):
    """Field ids only have to be unique within one dialog: the whole file for
    PluginConfig.xml, each <ConfigUI> block everywhere else."""
    if path.name == "PluginConfig.xml":
        return [("<root>", root)]
    scopes = [(f"ConfigUI[{i}]", cfg) for i, cfg in enumerate(root.iter("ConfigUI"))]
    return scopes or [("<root>", root)]


def test_the_expected_xml_files_are_there():
    """A glob that matched nothing would let every test below pass."""
    names = set(XML_IDS)
    for wanted in ("Devices.xml", "Actions.xml", "Events.xml",
                   "MenuItems.xml", "PluginConfig.xml"):
        assert wanted in names, f"{wanted} not found in {SERVER_DIR}"


@pytest.mark.parametrize("path", XML_FILES, ids=XML_IDS)
def test_every_xml_file_parses(path):
    ET.parse(path)


@pytest.mark.parametrize("path", XML_FILES, ids=XML_IDS)
def test_every_field_has_an_id(path):
    missing = [i for i, f in enumerate(_root(path).iter("Field")) if not f.get("id")]
    assert missing == [], f"{path.name}: Field number(s) {missing} have no id"


@pytest.mark.parametrize("path", XML_FILES, ids=XML_IDS)
def test_field_ids_are_unique_within_each_dialog(path):
    """A duplicate id stops the Indigo client building the dialog at all."""
    for name, scope in _dialog_scopes(_root(path), path):
        ids   = [f.get("id") for f in scope.iter("Field") if f.get("id")]
        dupes = [i for i, n in collections.Counter(ids).items() if n > 1]
        assert dupes == [], f"{path.name} {name}: duplicate Field ids {dupes}"


@pytest.mark.parametrize("path", XML_FILES, ids=XML_IDS)
def test_visible_bindings_point_at_a_field_in_the_same_dialog(path):
    """A visibleBindingId naming a missing field hides that row for good."""
    for name, scope in _dialog_scopes(_root(path), path):
        ids = {f.get("id") for f in scope.iter("Field")}
        for field in scope.iter("Field"):
            binding = field.get("visibleBindingId")
            if binding:
                assert binding in ids, (
                    f"{path.name} {name}: {field.get('id')} binds to '{binding}', "
                    f"which is not a field in this dialog")


@pytest.mark.parametrize("path", XML_FILES, ids=XML_IDS)
def test_top_level_item_ids_are_unique(path):
    """Two <Device>, <Action>, <Event> or <MenuItem> entries with the same id:
    Indigo keeps one and the other silently disappears."""
    root = _root(path)
    ids = [el.get("id") for el in root
           if el.tag in ("Device", "Action", "Event", "MenuItem") and el.get("id")]
    dupes = [i for i, n in collections.Counter(ids).items() if n > 1]
    assert dupes == [], f"{path.name}: duplicate ids {dupes}"


# ── every callback named in the XML exists in plugin.py ──────────────────────

def _callbacks():
    """(file, kind, name) for every method the XML asks Indigo to call."""
    found = []
    for path in XML_FILES:
        root = _root(path)
        for el in root.iter("CallbackMethod"):
            name = (el.text or "").strip()
            if name:
                found.append((path.name, "CallbackMethod", name))
        for el in root.iter("List"):
            if el.get("class") == "self" and el.get("method"):
                found.append((path.name, "List method", el.get("method")))
    return found


def test_the_callback_scan_finds_something():
    """MenuItems and Actions both name callbacks, so an empty scan is a broken scan."""
    assert len(_callbacks()) >= 10


def test_every_callback_named_in_the_xml_exists_in_plugin_py(plugin_mod):
    """A misspelt CallbackMethod is only found when someone picks that menu
    item or action, and Indigo then logs that the method does not exist."""
    missing = [(f, kind, name) for f, kind, name in _callbacks()
               if not callable(getattr(plugin_mod.Plugin, name, None))]
    assert missing == [], "named in the XML but not defined on Plugin: " + repr(missing)


def test_the_callback_check_can_fail(plugin_mod):
    """Guard against the check above passing vacuously."""
    assert getattr(plugin_mod.Plugin, "menuThisDoesNotExist", None) is None


def test_every_device_type_in_devices_xml_has_a_poll_route_or_is_push_only(plugin_mod):
    """A device type with no poller and not marked push-only/BLU would sit
    showing whatever state it was created with, looking live."""
    root  = _root(SERVER_DIR / "Devices.xml")
    types_in_xml = {d.get("id") for d in root.iter("Device")}
    src = (SERVER_DIR / "plugin.py").read_text(encoding="utf-8")
    push_only = set(getattr(plugin_mod, "PUSH_ONLY_TYPES", ()))
    blu       = set(getattr(plugin_mod, "BLU_TYPES", ()))
    unhandled = sorted(t for t in types_in_xml
                       if t not in push_only and t not in blu
                       and f'"{t}":' not in src.split("def _poll_device", 1)[1][:1200])
    assert unhandled == [], f"device types with no poll route: {unhandled}"


# ── dialog width ─────────────────────────────────────────────────────────────

def test_no_control_label_is_a_paragraph():
    too_long = []
    for path in XML_FILES:
        for field in _root(path).iter("Field"):
            if field.get("type") in ("label", "separator"):
                continue
            label = field.find("Label")
            text  = (label.text or "").strip() if label is not None else ""
            if len(text) > MAX_CONTROL_LABEL_CHARS:
                too_long.append((path.name, field.get("id"), len(text)))
    assert too_long == [], f"control labels too long for the dialog: {too_long}"


def test_no_description_is_a_paragraph():
    too_long = []
    for path in XML_FILES:
        for field in _root(path).iter("Field"):
            desc = field.find("Description")
            text = (desc.text or "").strip() if desc is not None else ""
            if len(text) > MAX_DESCRIPTION_CHARS:
                too_long.append((path.name, field.get("id"), len(text)))
    assert too_long == [], f"<Description> text too long (it never wraps): {too_long}"
