#!/usr/bin/env python3
"""Global material index of the exported project: where every material is used.

For each material (Assets/Material/*.mat): its shader (name and file: the export can hold two shader
files with one name, e.g. "Shader Forge_Additive_Ignore_Fog_0.shader"), the scenes that reference it (directly, or
through a prefab the scene references) and the prefabs that hold it, Resources prefabs marked as
showcase candidates (they can be spawned by the tour). Also a greedy set cover: the fewest scenes
that together hold every scene material, in the order that adds the most new materials first.

Output: JSON with "materials" {name: {shader, scenes, prefabs, resources}} and "scene_order".
Usage: python3 tools/tour/material_index.py <ExportedProject> <out.json>
"""
import json
import os
import re
import sys

GUID = re.compile(rb"guid: ([0-9a-f]{32})")


def meta_guid(path):
    with open(path + ".meta", "rb") as f:
        m = GUID.search(f.read())
    return m.group(1).decode() if m else None


def guids_in(path):
    with open(path, "rb") as f:
        return {g.decode() for g in GUID.findall(f.read())}


def shader_names(assets):
    names = {}
    for root, _, files in os.walk(assets):
        for fn in files:
            if fn.endswith(".shader") and os.path.exists(os.path.join(root, fn + ".meta")):
                p = os.path.join(root, fn)
                with open(p, "rb") as f:
                    m = re.search(rb'Shader\s+"([^"]+)"', f.read())
                names[meta_guid(p)] = (m.group(1).decode() if m else fn, fn)
    return names


def build(project):
    assets = os.path.join(project, "Assets")
    shaders = shader_names(assets)
    mats = {}       # guid -> name
    mat_shader = {}
    mat_shader_file = {}
    for fn in sorted(os.listdir(os.path.join(assets, "Material"))):
        if not fn.endswith(".mat"):
            continue
        p = os.path.join(assets, "Material", fn)
        g = meta_guid(p)
        mats[g] = fn[:-4]
        with open(p, "rb") as f:
            m = re.search(rb"m_Shader: \{fileID: (-?\d+), guid: ([0-9a-f]{32})", f.read())
        if m:
            sg = m.group(2).decode()
            if sg in shaders:
                mat_shader[g], mat_shader_file[g] = shaders[sg]
            else:
                mat_shader[g] = "builtin:" + m.group(1).decode() if sg.startswith("0000000000000000") else sg

    prefabs = {}    # guid -> (relative path, material guids, prefab guids)
    for root, _, files in os.walk(assets):
        for fn in files:
            if fn.endswith(".prefab"):
                p = os.path.join(root, fn)
                g = meta_guid(p)
                refs = guids_in(p)
                prefabs[g] = (os.path.relpath(p, assets), {r for r in refs if r in mats}, refs)
    for g, (rel, m, refs) in prefabs.items():
        prefabs[g] = (rel, m, {r for r in refs if r in prefabs and r != g})

    def prefab_mats(g, seen):
        if g in seen:
            return set()
        seen.add(g)
        rel, m, sub = prefabs[g]
        out = set(m)
        for s in sub:
            out |= prefab_mats(s, seen)
        return out

    scene_mats = {}
    for fn in sorted(os.listdir(os.path.join(assets, "Scenes"))):
        if not fn.endswith(".unity"):
            continue
        refs = guids_in(os.path.join(assets, "Scenes", fn))
        found = {r for r in refs if r in mats}
        for r in refs:
            if r in prefabs:
                found |= prefab_mats(r, set())
        scene_mats[fn[:-6]] = found

    out = {}
    for g, name in mats.items():
        holders = [prefabs[p][0] for p in prefabs if g in prefab_mats(p, set())]
        out[name] = {
            "shader": mat_shader.get(g, "?"),
            "shader_file": mat_shader_file.get(g, ""),
            "scenes": sorted(s for s, ms in scene_mats.items() if g in ms),
            "prefabs": sorted(holders),
            "resources": sorted(h[len("Resources/"):-len(".prefab")] for h in holders if h.startswith("Resources/")),
        }

    # Greedy set cover over the scenes.
    left = {g for ms in scene_mats.values() for g in ms}
    order = []
    while left:
        best = max(scene_mats, key=lambda s: len(scene_mats[s] & left))
        gain = scene_mats[best] & left
        if not gain:
            break
        order.append({"scene": best, "new": len(gain), "total": len(scene_mats[best])})
        left -= gain
    return {"materials": out, "scene_order": order}


if __name__ == "__main__":
    data = build(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    m = data["materials"]
    print(f"{len(m)} materials; in scenes {sum(1 for v in m.values() if v['scenes'])}; "
          f"only in Resources prefabs {sum(1 for v in m.values() if not v['scenes'] and v['resources'])}; "
          f"unused {sum(1 for v in m.values() if not v['scenes'] and not v['prefabs'])}")
    for o in data["scene_order"]:
        print(f"  {o['scene']:22} +{o['new']:4} new  ({o['total']} in scene)")
