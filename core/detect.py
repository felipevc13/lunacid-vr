#!/usr/bin/env python3
"""
Lunacid VR Porting Pipeline - Game Triage & Detection Tool
----------------------------------------------------------
Performs read-only inspection of a PC game install directory (e.g. Steam download)
to identify engine, Unity version, scripting backend, render pipeline, packages,
third-party middleware, scene structure, and potential porting risks.

Output: Markdown report (stdout) and JSON report (--json <path>).
"""

import os
import sys
import re
import glob
import json
import argparse

KNOWN_DRM_SIGNATURES = {
    "EasyAntiCheat": ["EasyAntiCheat", "EasyAntiCheat_Setup.exe", "easyanticheat_x64.dll"],
    "BattlEye": ["BattlEye", "BEService.exe", "BEService_x64.exe"],
    "Denuvo": ["dbdata.dll"],
    "Steamworks / Steam DRM": ["steam_api64.dll", "steam_api.dll", "steam_appid.txt", "appmanifest_*.acf"]
}

KNOWN_PACKAGES = {
    "TextMeshPro": ["Unity.TextMeshPro.dll"],
    "Input System (New)": ["Unity.InputSystem.dll", "Unity.InputSystem.RebindingUI.dll"],
    "PostProcessing v2": ["Unity.Postprocessing.Runtime.dll"],
    "Addressables": ["Unity.Addressables.dll"],
    "ProBuilder": ["Unity.ProBuilder.dll"],
    "Cinemachine": ["Cinemachine.dll"]
}

KNOWN_THIRD_PARTY = {
    "I2 Localization": ["I2.Localization.dll", "I2"],
    "RetroLookPro": ["RetroLookPro", "RLPro"],
    "Steamworks.NET": ["Steamworks.NET.dll", "Steamworks.NET.txt"],
    "FMOD Audio": ["fmod.dll", "fmodstudio.dll"]
}

def extract_unity_version(data_dir):
    candidates = ["globalgamemanagers", "data.unity3d"]
    version_regex = re.compile(rb"(\d{4}\.\d+\.\d+[a-z]\d+)")

    for c in candidates:
        p = os.path.join(data_dir, c)
        if os.path.exists(p):
            try:
                with open(p, "rb") as fh:
                    # Scan header first
                    chunk = fh.read(8192)
                    m = version_regex.search(chunk)
                    if m:
                        return m.group(1).decode("ascii")
                    # Scan full file up to 10MB
                    fh.seek(0)
                    full = fh.read(10 * 1024 * 1024)
                    m = version_regex.search(full)
                    if m:
                        return m.group(1).decode("ascii")
            except Exception:
                pass
    return "desconhecida"

def detect_game(game_path):
    game_path = os.path.abspath(game_path)
    if not os.path.exists(game_path):
        raise FileNotFoundError(f"Path does not exist: {game_path}")

    report = {
        "path": game_path,
        "is_unity": False,
        "engine": "Unknown",
        "unity_version": "desconhecida",
        "scripting_backend": "desconhecido",
        "render_pipeline": "desconhecido",
        "packages": [],
        "native_plugins": [],
        "third_party_assets": [],
        "structure": {
            "levels_count": 0,
            "sharedassets_count": 0,
            "resources_count": 0,
            "has_addressables": False
        },
        "drm_and_protections": {
            "detected": [],
            "checked": list(KNOWN_DRM_SIGNATURES.keys()),
            "disclaimer": "A ausência de assinaturas conhecidas não comprova ausência de proteção proprietária ou customizada."
        },
        "risk_assessment": {},
        "undetermined": []
    }

    # 1. Engine Detection
    has_unity_player = os.path.exists(os.path.join(game_path, "UnityPlayer.dll"))
    data_dirs = [d for d in os.listdir(game_path) if d.endswith("_Data") and os.path.isdir(os.path.join(game_path, d))]

    if has_unity_player or data_dirs:
        report["is_unity"] = True
        report["engine"] = "Unity"
    else:
        report["undetermined"].append("Não foi possível confirmar o motor como Unity (ausência de UnityPlayer.dll e pasta *_Data).")
        return report

    data_dir = os.path.join(game_path, data_dirs[0]) if data_dirs else None
    if not data_dir:
        report["undetermined"].append("Pasta *_Data não encontrada.")
        return report

    # 2. Unity Version
    report["unity_version"] = extract_unity_version(data_dir)

    # 3. Scripting Backend
    managed_dir = os.path.join(data_dir, "Managed")
    mono_bleeding = os.path.exists(os.path.join(game_path, "MonoBleedingEdge"))
    game_assembly = os.path.exists(os.path.join(game_path, "GameAssembly.dll"))
    metadata_file = os.path.join(data_dir, "il2cpp_data", "Metadata", "global-metadata.dat")

    if game_assembly or os.path.exists(metadata_file):
        report["scripting_backend"] = "IL2CPP"
    elif mono_bleeding or (managed_dir and os.path.exists(os.path.join(managed_dir, "Assembly-CSharp.dll"))):
        report["scripting_backend"] = "Mono"
    else:
        report["scripting_backend"] = "desconhecido"
        report["undetermined"].append("Backend de script não pôde ser determinado.")

    # 4. Managed Assemblies Analysis
    managed_files = []
    if managed_dir and os.path.exists(managed_dir):
        managed_files = [f for f in os.listdir(managed_dir) if not f.startswith("._") and f.endswith(".dll")]

    # Render Pipeline
    if any("Universal.Runtime" in f for f in managed_files):
        report["render_pipeline"] = "Universal Render Pipeline (URP)"
    elif any("HighDefinition.Runtime" in f for f in managed_files):
        report["render_pipeline"] = "High Definition Render Pipeline (HDRP)"
    elif report["is_unity"]:
        report["render_pipeline"] = "Built-in Render Pipeline"
    else:
        report["render_pipeline"] = "desconhecido"

    # Known Packages
    for pkg_name, dll_patterns in KNOWN_PACKAGES.items():
        if any(any(pat.lower() == mf.lower() for pat in dll_patterns) for mf in managed_files):
            report["packages"].append(pkg_name)

    # Third Party Assets (check managed DLLs, Assembly-CSharp strings, and assets)
    ac_dll = os.path.join(managed_dir, "Assembly-CSharp.dll") if managed_dir else None
    ac_bytes = b""
    if ac_dll and os.path.exists(ac_dll):
        try:
            with open(ac_dll, "rb") as fh:
                ac_bytes = fh.read()
        except Exception:
            pass

    for tp_name, sigs in KNOWN_THIRD_PARTY.items():
        found = False
        # Check managed DLL filenames
        for sig in sigs:
            if any(sig.lower() in mf.lower() for mf in managed_files):
                found = True
                break
        # Check inside Assembly-CSharp.dll strings
        if not found and ac_bytes:
            for sig in sigs:
                if sig.encode("ascii", errors="ignore") in ac_bytes:
                    found = True
                    break
        # Check plugins directory
        if not found and data_dir:
            plugins_dir = os.path.join(data_dir, "Plugins")
            if os.path.exists(plugins_dir):
                for root, _, pfiles in os.walk(plugins_dir):
                    if any(sig.lower() in pf.lower() for pf in pfiles for sig in sigs):
                        found = True
                        break
        if found:
            report["third_party_assets"].append(tp_name)

    # Check for Shader Forge signatures in resources, sharedassets, or strings
    sf_found = False
    for mf in managed_files:
        if "shaderforge" in mf.lower():
            sf_found = True
            break
    if not sf_found and ac_bytes and b"Shader Forge" in ac_bytes:
        sf_found = True
    if not sf_found and data_dir:
        for rf in glob.glob(os.path.join(data_dir, "*assets*")):
            if os.path.isfile(rf):
                try:
                    with open(rf, "rb") as fh:
                        sample = fh.read(1024 * 1024)
                        if b"Shader Forge" in sample:
                            sf_found = True
                            break
                except Exception:
                    pass
    if sf_found:
        report["third_party_assets"].append("Shader Forge")

    # Native Plugins
    plugins_dir = os.path.join(data_dir, "Plugins")
    if os.path.exists(plugins_dir):
        for root, _, pfiles in os.walk(plugins_dir):
            for pf in pfiles:
                if not pf.startswith("._") and pf.endswith(".dll"):
                    report["native_plugins"].append(pf)

    # 5. Structure Counts
    levels = [f for f in os.listdir(data_dir) if f.startswith("level") and not f.startswith("._")]
    sharedassets = [f for f in os.listdir(data_dir) if f.startswith("sharedassets") and not f.startswith("._")]
    ress_files = [f for f in os.listdir(data_dir) if f.endswith(".resS") or f.endswith(".resource")]

    report["structure"]["levels_count"] = len(levels)
    report["structure"]["sharedassets_count"] = len(sharedassets)
    report["structure"]["resources_count"] = len(ress_files)

    streaming_aa = os.path.join(data_dir, "StreamingAssets", "aa")
    report["structure"]["has_addressables"] = os.path.exists(streaming_aa)

    # 6. Protections / DRM
    for drm_name, patterns in KNOWN_DRM_SIGNATURES.items():
        matched = False
        for pat in patterns:
            if "*" in pat:
                for root, dirs, files in os.walk(game_path):
                    if glob.glob(os.path.join(root, pat)):
                        matched = True
                        break
            else:
                for root, dirs, files in os.walk(game_path):
                    if pat.lower() in [f.lower() for f in files] or pat.lower() in [d.lower() for d in dirs]:
                        matched = True
                        break
            if matched:
                break
        if matched:
            report["drm_and_protections"]["detected"].append(drm_name)

    # 7. Risk Assessment
    risks = {}

    # Code / Runtime Risk
    if report["scripting_backend"] == "Mono":
        risks["Código / Runtime"] = {
            "nivel": "Baixo a Médio",
            "motivo": "Backend Mono facilita descompilação limpa (AssetRipper Level 2), mas exige descarte de DLLs legadas (InputSystem, TextMeshPro, uGUI) que conflitam com Unity 6."
        }
    elif report["scripting_backend"] == "IL2CPP":
        risks["Código / Runtime"] = {
            "nivel": "Médio a Alto",
            "motivo": "Backend IL2CPP requer desofuscação via Il2CppDumper/Cpp2IL e reconstrução de tipos de dados, com maior risco de perda de assinaturas e nomes."
        }
    else:
        risks["Código / Runtime"] = {
            "nivel": "Alto",
            "motivo": "Backend não identificado com precisão."
        }

    # Shaders / Renderização
    shader_risk_motivo = []
    if "Shader Forge" in report["third_party_assets"]:
        shader_risk_motivo.append("Shaders customizados Shader Forge geram dummy stubs no export; exigem substituição por passes ForwardBase + ForwardAdd para iluminação pontual.")
    if "PostProcessing v2" in report["packages"] or "RetroLookPro" in report["third_party_assets"]:
        shader_risk_motivo.append("Efeitos fullscreen de tela (PostProcessing/RetroLookPro) quebram em VR standalone e exigem desativação sistemática.")
    if not shader_risk_motivo:
        shader_risk_motivo.append("Pipeline Built-in padrão com materiais comuns.")

    risks["Shaders / Renderização"] = {
        "nivel": "Médio" if "Shader Forge" in report["third_party_assets"] else "Baixo",
        "motivo": " ".join(shader_risk_motivo)
    }

    # Carregamento / Estrutura de Cenas
    if report["structure"]["levels_count"] > 10:
        risks["Carregamento / Estrutura"] = {
            "nivel": "Médio",
            "motivo": f"Projeto com {report['structure']['levels_count']} arquivos de cenas/níveis. Alto risco de referências cruzadas de assets para objetos de cena ('type: 2') que travam o standalone player (ReadObjectThreaded)."
        }
    else:
        risks["Carregamento / Estrutura"] = {
            "nivel": "Baixo",
            "motivo": f"Poucas cenas ({report['structure']['levels_count']})."
        }

    # Interface / Input
    if "Input System (New)" in report["packages"]:
        risks["Interface / Input"] = {
            "nivel": "Baixo",
            "motivo": "Usa Unity Input System moderno, simplificando remapeamento para controladores OpenXR do Meta Quest."
        }
    else:
        risks["Interface / Input"] = {
            "nivel": "Médio",
            "motivo": "Input clássico (InputManager / KeyCodes hardcoded); exigirá hooking ou reescrita para eixos de VR."
        }

    report["risk_assessment"] = risks

    # Undetermined items
    report["undetermined"].append("Chamadas de script por reflexão ou carregamento dinâmico de assemblies em tempo de execução.")
    report["undetermined"].append("Comportamentos de shaders específicos que dependem de render texturas customizadas.")

    return report

def format_markdown_report(report):
    md = []
    md.append(f"# Relatório de Triagem Pré-Porte: {os.path.basename(report['path'])}\n")
    md.append(f"**Caminho Analisado:** `{report['path']}`\n")

    md.append("## 1. Resumo do Motor e Arquitetura\n")
    md.append(f"- **Motor:** {report['engine']}")
    md.append(f"- **Versão do Unity:** `{report['unity_version']}`")
    md.append(f"- **Scripting Backend:** `{report['scripting_backend']}`")
    md.append(f"- **Render Pipeline:** `{report['render_pipeline']}`\n")

    md.append("## 2. Pacotes e Plugins Detectados\n")
    if report["packages"]:
        md.append("**Pacotes Unity:** " + ", ".join(f"`{p}`" for p in report["packages"]))
    else:
        md.append("**Pacotes Unity:** Nenhum pacote oficial reconhecido nas DLLs.")

    if report["native_plugins"]:
        md.append("**Plugins Nativos:** " + ", ".join(f"`{p}`" for p in sorted(set(report["native_plugins"]))))
    else:
        md.append("**Plugins Nativos:** Nenhum plugin nativo encontrado em `Plugins/`.")

    if report["third_party_assets"]:
        md.append("**Assets de Terceiros / Shaders:** " + ", ".join(f"`{t}`" for t in report["third_party_assets"]))
    else:
        md.append("**Assets de Terceiros:** Nenhum framework reconhecido.")
    md.append("")

    md.append("## 3. Estrutura de Arquivos e Assets\n")
    s = report["structure"]
    md.append(f"- **Arquivos de Níveis (`level*`):** {s['levels_count']}")
    md.append(f"- **Arquivos de Shared Assets (`sharedassets*`):** {s['sharedassets_count']}")
    md.append(f"- **Arquivos de Recursos (`.resS` / `.resource`):** {s['resources_count']}")
    md.append(f"- **Addressables em StreamingAssets:** {'Sim' if s['has_addressables'] else 'Não'}\n")

    md.append("## 4. Proteções e DRM\n")
    if report["drm_and_protections"]["detected"]:
        md.append("**Sinais de DRM Encontrados:** " + ", ".join(f"`{d}`" for d in report["drm_and_protections"]["detected"]))
    else:
        md.append("**Sinais de DRM Encontrados:** Nenhuma assinatura detectada.")
    md.append(f"**Assinaturas verificadas:** {', '.join(report['drm_and_protections']['checked'])}.")
    md.append(f"> [!NOTE] {report['drm_and_protections']['disclaimer']}\n")

    md.append("## 5. Avaliação de Risco para Porte VR Standalone\n")
    md.append("| Categoria | Nível de Risco | Motivo Técnico |")
    md.append("|---|---|---|")
    for cat, r in report["risk_assessment"].items():
        md.append(f"| **{cat}** | `{r['nivel']}` | {r['motivo']} |")
    md.append("")

    if report["undetermined"]:
        md.append("## 6. O Que Não Foi Possível Determinar Estaticamente\n")
        for u in report["undetermined"]:
            md.append(f"- {u}")
        md.append("")

    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(description="Triage tool to detect Unity game features before porting.")
    parser.add_argument("game_path", help="Path to the PC game install directory.")
    parser.add_argument("--json", dest="json_out", help="Optional path to write JSON report.")

    args = parser.parse_args()
    report = detect_game(args.game_path)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)

    print(format_markdown_report(report))

if __name__ == "__main__":
    main()
