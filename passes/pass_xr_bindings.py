#!/usr/bin/env python3
"""
Pass: Touch Controller Bindings
-------------------------------
The game reads its controls through an Input System asset (MIDNIGHT_TEST: Move, Fire, Jump, ...)
with keyboard, mouse and gamepad bindings, and an empty "XR" control scheme. This adds Quest
Touch controller bindings to the Player map, by usage so any OpenXR controller profile matches:

  left stick  Move          right trigger  Fire        left trigger  Magic1     right grip  Magic2
  left grip   Block         A              Jump        B             Activate   X           UseITEM
  Y           NextITEM      left stick click  Sprint   left menu     INV

Looking up and down is the head; turning is a snap turn done by the VR runtime, so Look gets no
binding. The UI map (pause menu, inventory, dialogs) gets gamepad-style navigation: left stick
Navigate, A or right trigger Submit, B Cancel, left menu closes the inventory.

The asset also carries Unity's template XR bindings for any controller ("<XRController>/{Primary2DAxis}"
Move, "{PrimaryAction}" Fire, "/trigger" UI Click): with them the right stick walked too, and the UI
Click (a pass-through action) fired on every change of the analog trigger, typing a letter many
times on the name screen. They are removed. The XR scheme
required a single "<XRController>", so only one controller got paired (the left one did nothing);
it now requires the left and the right hand.
"""

import os
import re
import uuid

TARGET = "Assets/MonoBehaviour/MIDNIGHT_TEST.asset"
MARK = "LUNAPORT_XR"   # m_Name of the bindings this pass adds

# Template bindings that react to either controller.
GENERIC = ["<XRController>/{Primary2DAxis}", "<XRController>/{PrimaryAction}", "<XRController>/trigger"]
SCHEME_OLD = "    m_DeviceRequirements:\n    - m_ControlPath: '<XRController>'\n      m_Flags: 0\n"
SCHEME_NEW = ("    m_DeviceRequirements:\n    - m_ControlPath: '<XRController>{LeftHand}'\n      m_Flags: 0\n"
              "    - m_ControlPath: '<XRController>{RightHand}'\n      m_Flags: 0\n")

UI_BINDINGS = [
    ("Navigate", "<XRController>{LeftHand}/{Primary2DAxis}", "StickDeadzone"),
    ("Submit", "<XRController>{RightHand}/{PrimaryButton}", ""),
    ("Submit", "<XRController>{RightHand}/{TriggerButton}", ""),
    ("Cancel", "<XRController>{RightHand}/{SecondaryButton}", ""),
    ("INV", "<XRController>{LeftHand}/{MenuButton}", ""),
]

BINDINGS = [
    ("Move", "<XRController>{LeftHand}/{Primary2DAxis}", "StickDeadzone"),
    ("Fire", "<XRController>{RightHand}/{Trigger}", ""),
    ("Magic1", "<XRController>{LeftHand}/{TriggerButton}", ""),
    ("Magic2", "<XRController>{RightHand}/{GripButton}", ""),
    ("Block", "<XRController>{LeftHand}/{GripButton}", ""),
    ("Jump", "<XRController>{RightHand}/{PrimaryButton}", ""),
    ("Activate", "<XRController>{RightHand}/{SecondaryButton}", ""),
    ("UseITEM", "<XRController>{LeftHand}/{PrimaryButton}", ""),
    ("NextITEM", "<XRController>{LeftHand}/{SecondaryButton}", ""),
    ("Sprint", "<XRController>{LeftHand}/{Primary2DAxisClick}", ""),
    ("INV", "<XRController>{LeftHand}/{MenuButton}", ""),
]

def _entry(action, path, processors):
    return (f"    - m_Name: {MARK}\n"
            f"      m_Id: {uuid.uuid5(uuid.NAMESPACE_URL, MARK + action + path)}\n"
            f"      m_Path: '{path}'\n"
            f"      m_Interactions:\n"
            f"      m_Processors: {processors}\n"
            f"      m_Groups: XR\n"
            f"      m_Action: {action}\n"
            f"      m_Flags: 0\n")

def _map_bindings_end(text, name):
    """Offset just after the named map's last binding (before the next action map or the schemes).

    Control schemes are list entries with the same indent as action maps, so the search for the
    next map stops at m_ControlSchemes; otherwise the last map's bindings land among the schemes.
    """
    start = text.find(f"  - m_Name: {name}\n")
    schemes = text.find("\n  m_ControlSchemes:")
    if start < 0 or schemes < 0 or start > schemes:
        return None
    b = text.find("    m_Bindings:\n", start)
    nxt = text.find("\n  - m_Name: ", b, schemes)
    if nxt < 0:
        nxt = schemes
    return nxt + 1

def detect(export_dir, profile=None):
    path = os.path.join(export_dir, TARGET)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    findings = []
    have = len(re.findall(rf"m_Name: {MARK}\n", text))
    want = len(BINDINGS) + len(UI_BINDINGS)
    if have != want:
        findings.append(f"{TARGET}: {want - have} Touch controller bindings missing")
    if f"m_Name: {MARK}\n" in text[text.find("\n  m_ControlSchemes:"):]:
        findings.append(f"{TARGET}: Touch controller bindings among the control schemes")
    for generic in GENERIC:
        if f"m_Path: '{generic}'" in text:
            findings.append(f"{TARGET}: template binding {generic} still active")
    if "m_BindingGroup: XR\n" + SCHEME_OLD in text:
        findings.append(f"{TARGET}: XR scheme pairs a single controller")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    if not detect(export_dir, profile):
        return {"changes_applied": 0, "details": []}
    path = os.path.join(export_dir, TARGET)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # Drop earlier copies and the any-controller template bindings, pair both hands, then add the
    # current set at the end of the Player and UI maps.
    text = re.sub(rf"    - m_Name: {MARK}\n(?:      .*\n){{7}}", "", text)
    for generic in GENERIC:
        text = re.sub(r"    - m_Name: ?\n      m_Id: [\w-]+\n      m_Path: '" + re.escape(generic) + r"'\n(?:      .*\n){5}", "", text)
    text = text.replace("m_BindingGroup: XR\n" + SCHEME_OLD, "m_BindingGroup: XR\n" + SCHEME_NEW)
    for name, bindings in (("Player", BINDINGS), ("UI", UI_BINDINGS)):
        end = _map_bindings_end(text, name)
        if end is None:
            return {"changes_applied": 0, "details": [f"{name} action map not found"]}
        text = text[:end] + "".join(_entry(*b) for b in bindings) + text[end:]
    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    every = BINDINGS + UI_BINDINGS
    return {"changes_applied": len(every), "details": [f"Bind {a} to {p}" for a, p, _ in every]}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
