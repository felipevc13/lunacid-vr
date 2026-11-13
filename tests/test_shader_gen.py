#!/usr/bin/env python3
"""Tests for tools/shader_gen. The decompiled shader here is written by hand in USCSandbox's output
format; it is not taken from any game."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "shader_gen"))
import generate  # noqa: E402
import uscs  # noqa: E402


def vert_block(cond, extra=""):
    return """
            {cond}
            struct appdata
            {{
                float4 vertex : POSITION;
            }};
            struct v2f
            {{
                float4 position : SV_POSITION;
                float4 texcoord : TEXCOORD;
            }};

            // CBs for DX11VertexSM40
            float4 _MainTex_ST; // 32 (starting at cb0[2].x)
            // Textures for DX11VertexSM40

            v2f vert(appdata v)
            {{
                v2f o;
                o.position = mul(unity_MatrixVP, mul(unity_ObjectToWorld, v.vertex));
                o.texcoord = v.vertex{extra};
                return o;
            }}
""".format(cond=cond, extra=extra)


def frag_block(cond, body):
    return """
            {cond}
            struct fout
            {{
                float4 sv_target : SV_Target;
            }};

            // CBs for DX11PixelSM40
            float4 _MainTex_ST; // 32 (starting at cb0[2].x)
            float4 _Color; // 48 (starting at cb0[3].x)
            // Textures for DX11PixelSM40
            sampler2D _MainTex; // 0

            fout frag(v2f inp)
            {{
                fout o;
                float4 tmp0;
{body}
                return o;
            }}
""".format(cond=cond, body=body)


LIGHTMAPPED = """                tmp0 = UNITY_SAMPLE_TEX2D_SAMPLER(unity_Lightmap, unity_Lightmap, inp.texcoord.xy);
                o.sv_target = tmp0 * _Color;"""
PLAIN = """                tmp0 = tex2D(_MainTex, inp.texcoord.xy * _MainTex_ST.xy + _MainTex_ST.zw);
                o.sv_target.xyz = tmp0.xyz * (glstate_lightmodel_ambient.xyz + glstate_lightmodel_ambient.xyz);
                o.sv_target.w = _Color.w;"""

ON = "DIRECTIONAL && DIRLIGHTMAP_OFF && DYNAMICLIGHTMAP_OFF && LIGHTMAP_ON"
DEAD = "DIRECTIONAL && DIRLIGHTMAP_OFF && DYNAMICLIGHTMAP_OFF && LIGHTMAP_OFF && LIGHTMAP_ON"
OFF = "DIRECTIONAL && DIRLIGHTMAP_OFF && DYNAMICLIGHTMAP_OFF && LIGHTMAP_OFF"

DECOMPILED = """Shader "Test/Synthetic" {
    Properties {
        _Color ("Color", Color) = (1, 1, 1, 1)
        _MainTex ("MainTex", 2D) = "white" {}
    }
    SubShader {
        Pass {
            Name "FORWARD"
            Tags {
                "LIGHTMODE"="FORWARDBASE"
            }
            CGPROGRAM

            #pragma vertex vert
            #pragma fragment frag

            #pragma multi_compile DIRECTIONAL
            #pragma shader_feature LIGHTMAP_ON
""" + vert_block("#if %s // FORWARD:DX11VertexSM40" % DEAD) \
    + vert_block("#elif %s // FORWARD:DX11VertexSM40" % ON) \
    + vert_block("#else // %s // FORWARD:DX11VertexSM40" % OFF) + "            #endif\n" \
    + frag_block("#if %s // FORWARD:DX11PixelSM40" % DEAD, "                discard;") \
    + frag_block("#elif %s // FORWARD:DX11PixelSM40" % ON, LIGHTMAPPED) \
    + frag_block("#else // %s // FORWARD:DX11PixelSM40" % OFF, PLAIN) + """            #endif
            ENDCG
        }
        Pass {
            Name "FORWARD_DELTA"
            Tags {
                "LIGHTMODE"="FORWARDADD"
            }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
""" + vert_block("#if POINT && LIGHTMAP_ON // FORWARD_DELTA:DX11VertexSM40") \
    + vert_block("#else // POINT // FORWARD_DELTA:DX11VertexSM40") + "            #endif\n" \
    + frag_block("#if POINT && LIGHTMAP_ON // FORWARD_DELTA:DX11PixelSM40", PLAIN) \
    + frag_block("#else // POINT // FORWARD_DELTA:DX11PixelSM40", PLAIN) + """            #endif
            ENDCG
        }
    }
    Fallback "Diffuse"
}
"""


class TestUscs(unittest.TestCase):
    def test_parse_listing(self):
        text = "Available shaders in assets file:\n  Test/A (path id 13)\n  Test/B b (path id -2)\n"
        self.assertEqual(uscs.parse_listing(text), [("Test/A", 13), ("Test/B b", -2)])

    def test_output_name_matches_repo_shader_names(self):
        self.assertEqual(uscs.output_name("Shader Forge/Object"), "Shader Forge_Object.shader")

    def test_patches_and_pin_exist(self):
        here = os.path.dirname(os.path.abspath(uscs.__file__))
        patches = sorted(f for f in os.listdir(os.path.join(here, "uscs", "patches")) if f.endswith(".patch"))
        self.assertTrue(os.path.exists(os.path.join(here, "uscs", "patches", "LICENSE")))  # GPL-3.0, like USCSandbox
        self.assertEqual(patches, ["0001-sample-texture-from-resource-operand.patch",
                                   "0002-else-keeps-variant-keywords.patch",
                                   "0003-keep-full-swizzle-on-constant-buffer-reads.patch",
                                   "0004-log-is-base-2.patch"])
        import json
        with open(os.path.join(here, "uscs", "UPSTREAM.json")) as f:
            pin = json.load(f)
        self.assertEqual(len(pin["commit"]), 40)

    def test_no_generated_shader_in_repository(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        found = []
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in files:
                if name.endswith(".shader"):
                    with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as f:
                        if f.read(200).startswith(generate.GENERATED_HEADER[:40]):
                            found.append(os.path.relpath(os.path.join(root, name), repo))
        self.assertEqual(found, [], "shaders made from the game's files must not be committed")


class TestNormalise(unittest.TestCase):
    def test_shader_forge_off_keywords_are_removed(self):
        self.assertEqual(generate.normalise(OFF.split(" && ")), ("DIRECTIONAL",))

    def test_unused_combinations_are_dropped(self):
        self.assertIsNone(generate.normalise(DEAD.split(" && ")))
        self.assertIsNone(generate.normalise(["DIRLIGHTMAP_OFF", "DIRLIGHTMAP_COMBINED"]))
        self.assertIsNone(generate.normalise(["DIRLIGHTMAP_SEPARATE"]))

    def test_lightmap_on_survives(self):
        self.assertEqual(generate.normalise(ON.split(" && ")), ("DIRECTIONAL", "LIGHTMAP_ON"))


class TestGenerate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.counts = generate.generate(DECOMPILED)
        base_end = cls.text.index("ENDCG")
        cls.base = cls.text[:base_end]
        cls.add = cls.text[base_end:]

    def test_header_says_not_to_commit(self):
        self.assertTrue(self.text.startswith("// Generated by tools/shader_gen/generate.py"))

    def test_dead_variant_is_gone(self):
        self.assertNotIn("discard;", self.text)
        self.assertEqual(self.counts[0], 2)

    def test_chain_most_keywords_first(self):
        i_on = self.base.index("#if defined(DIRECTIONAL) && defined(LIGHTMAP_ON)")
        i_else = self.base.index("#else // DIRECTIONAL")
        self.assertLess(i_on, i_else)
        self.assertNotIn("LIGHTMAP_OFF", self.text)

    def test_stereo_macros(self):
        for macro in ("UNITY_VERTEX_INPUT_INSTANCE_ID", "UNITY_VERTEX_OUTPUT_STEREO",
                      "UNITY_SETUP_INSTANCE_ID(v);", "UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);",
                      "UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(inp);"):
            self.assertEqual(self.base.count(macro), 2, macro)

    def test_no_duplicate_declaration_in_a_branch(self):
        branch = self.base[self.base.index("#if defined"):self.base.index("#else")]
        self.assertEqual(branch.count("float4 _MainTex_ST;"), 1)
        self.assertEqual(branch.count("float4 _Color;"), 1)

    def test_lightmap_is_decoded(self):
        self.assertIn("tmp0.xyz = DecodeLightmap(tmp0);", self.base)

    def test_ambient_uses_unity_ambient_sky(self):
        self.assertNotIn("glstate_lightmodel_ambient", self.text)
        self.assertIn("(unity_AmbientSky * 0.5).xyz", self.text)

    def test_projection_matrix_is_unity6s(self):
        # Unity 6 rewrites glstate_matrix_projection to UNITY_MATRIX_P in place on import ("Upgrade NOTE"), so the
        # copy in the project never matched the generated file and the pass copied it again on every run (11
        # shaders, Shader Forge_flame_bill first; LESSONS 30). The generator writes Unity 6's name itself.
        out = generate.unity6_rules(["                tmp1 = mul(glstate_matrix_projection, tmp0);"])
        self.assertEqual(out, ["                tmp1 = mul(UNITY_MATRIX_P, tmp0);"])

    def test_pragmas(self):
        self.assertIn("#pragma multi_compile_fwdbase", self.base)
        self.assertIn("#pragma skip_variants DIRLIGHTMAP_COMBINED DYNAMICLIGHTMAP_ON", self.base)
        self.assertIn('#include "UnityCG.cginc"', self.base)
        self.assertNotIn("shader_feature", self.text)

    def test_keyword_that_changes_nothing_is_dropped(self):
        # LIGHTMAP_ON in the ForwardAdd pass: both variants have the same code
        self.assertIn("#pragma multi_compile_fwdadd", self.add)
        self.assertNotIn("multi_compile _ LIGHTMAP_ON", self.add)
        self.assertEqual(self.counts[1], 1)

    def test_probe_volume_declared_only_when_used(self):
        self.assertNotIn("unity_ProbeVolumeParams", self.text)
        text, _ = generate.generate(DECOMPILED.replace(
            "o.sv_target = tmp0 * _Color;", "o.sv_target = tmp0 * _Color * unity_ProbeVolumeParams.x;"))
        base = text[:text.index("ENDCG")]
        self.assertIn("#if !UNITY_LIGHT_PROBE_PROXY_VOLUME", base)
        self.assertIn("float4 unity_ProbeVolumeParams;", base)

    def test_normalize_of_zero_stays_finite(self):
        text, _ = generate.generate(DECOMPILED.replace("o.sv_target = tmp0 * _Color;",
                                                       "tmp0.x = rsqrt(tmp0.x);\n                o.sv_target = tmp0 * _Color;"))
        self.assertIn("tmp0.x = rsqrt(max(tmp0.x, 1e-12));", text)

    def test_front_face_is_a_float(self):
        src = DECOMPILED.replace("fout frag(v2f inp)", "fout frag(v2f inp, uint facing: VFACE)").replace(
            "o.sv_target = tmp0 * _Color;", "tmp0.w = facing.x ? 1.0 : -1.0;\n                o.sv_target = tmp0 * _Color;")
        text, _ = generate.generate(src)
        self.assertIn("float facing : VFACE", text)
        self.assertIn("tmp0.w = facing.x > 0.0 ? 1.0 : -1.0;", text)
        self.assertNotIn("uint facing", text)

    def test_rest_of_shader_kept(self):
        self.assertIn('Shader "Test/Synthetic" {', self.text)
        self.assertIn('_Color ("Color", Color) = (1, 1, 1, 1)', self.text)
        self.assertIn('Fallback "Diffuse"', self.text)


class TestRules(unittest.TestCase):
    RULES = {
        "properties": ['_PortFlag ("Port flag", Float) = 0'],
        "declare": ["float _PortFlag;"],
        "subshader_tags": {"Queue": "Transparent-10", "DisableBatching": "True"},
        "pass_state": {"FORWARDBASE": {"Blend": "[_A] [_B]", "ZWrite": "[_Z]"}},
        "vertex_color": "property:_PortFlag",
        "replace_when": [{"pass": "FORWARDBASE", "keywords": ["LIGHTMAP_ON"],
                          "find": "(?<!float4 )\\b_Color\\b", "replace": "float4(0.0, 0.0, 0.0, 0.0)"}],
        "frag_wrapper": {"FORWARDBASE": ["fout frag(v2f inp)", "{", "    return frag_game(inp);", "}"]},
    }

    @classmethod
    def setUpClass(cls):
        src = DECOMPILED.replace('            Tags {\n                "LIGHTMODE"="FORWARDBASE"',
                                 '            Tags {\n                "LIGHTMODE"="FORWARDBASE"', 1)
        src = src.replace("    SubShader {\n", '    SubShader {\n        Tags {\n            "QUEUE"="Transparent"\n        }\n', 1)
        src = src.replace("o.texcoord = v.vertex", "o.texcoord = v.vertex * v.color")
        cls.text, _ = generate.generate(src, cls.RULES)
        cls.base = cls.text[:cls.text.index("ENDCG")]
        cls.add = cls.text[cls.text.index("ENDCG"):]

    def test_property_added(self):
        props = self.text[self.text.index("Properties"):self.text.index("SubShader")]
        self.assertIn('_PortFlag ("Port flag", Float) = 0', props)

    def test_tags(self):
        self.assertIn('"QUEUE"="Transparent-10"', self.text)
        self.assertIn('"DISABLEBATCHING"="True"', self.text)

    def test_pass_state_replaced_or_added(self):
        self.assertIn("Blend [_A] [_B]", self.base)
        self.assertIn("ZWrite [_Z]", self.base)
        self.assertNotIn("Blend [_A] [_B]", self.add)

    def test_vertex_colour_switch(self):
        self.assertIn("lerp(float4(1.0, 1.0, 1.0, 1.0), v.color, _PortFlag)", self.text)

    def test_replace_only_in_lightmapped_branch(self):
        on = self.base[self.base.index("#if defined(DIRECTIONAL) && defined(LIGHTMAP_ON)"):self.base.index("#else")]
        off = self.base[self.base.index("#else"):]
        self.assertIn("tmp0 * float4(0.0, 0.0, 0.0, 0.0)", on)
        self.assertIn("_Color.w", off)

    def test_frag_wrapper(self):
        self.assertIn("fout frag_game(v2f inp)", self.base)
        self.assertIn("return frag_game(inp);", self.base)
        self.assertIn("float _PortFlag;", self.base)
        self.assertNotIn("frag_game", self.add)

    def test_rule_files_parse_and_name_real_shaders(self):
        d = generate.RULES_DIR
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        known = {"properties", "declare", "subshader_tags", "pass_state", "vertex_color", "replace_when",
                 "frag_wrapper", "use_repo_shader", "why"}
        for f in os.listdir(d):
            r = generate.load_rules(f.replace(".json", ".shader"))
            self.assertTrue(r.get("why"), f)
            self.assertLessEqual(set(r), known, f)
            if "use_repo_shader" in r:
                self.assertTrue(os.path.isfile(os.path.join(repo, r["use_repo_shader"])), f)


class TestPassShaderSource(unittest.TestCase):
    """pass_shader_stubs takes the port's shaders from the generated folder when told to."""

    def setUp(self):
        import json
        import tempfile
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, repo)
        import passes.pass_shader_stubs as stubs
        self.stubs = stubs
        self.tmp = tempfile.mkdtemp()
        with open(stubs.PORT_SHADERS, encoding="utf-8") as fh:
            self.wanted = json.load(fh)["shaders"]
        self.gen = os.path.join(self.tmp, "generated")
        os.makedirs(self.gen)
        for f in self.wanted:
            with open(os.path.join(self.gen, f), "w", encoding="utf-8") as fh:
                fh.write("// generated stand-in for %s\n" % f)
        self.export = os.path.join(self.tmp, "export")
        os.makedirs(os.path.join(self.export, "Assets", "Shader"))
        self.old_env = os.environ.pop("LUNA_SHADER_SOURCE", None)
        self.old_work = os.environ.pop("LUNA_WORK", None)
        # An empty work folder unless a test puts the generated shaders in it.
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        os.environ["LUNA_WORK"] = self.work

    def tearDown(self):
        import shutil
        os.environ.pop("LUNA_SHADER_SOURCE", None)
        os.environ.pop("LUNA_WORK", None)
        if self.old_env is not None:
            os.environ["LUNA_SHADER_SOURCE"] = self.old_env
        if self.old_work is not None:
            os.environ["LUNA_WORK"] = self.old_work
        self.stubs.REPO_ROOT = self.repo_root_was if hasattr(self, "repo_root_was") else self.stubs.REPO_ROOT
        shutil.rmtree(self.tmp)

    def test_default_is_generated_in_work(self):
        # Since Build 91 (approved on the Quest) the generated shaders are the default: in <work>/shader_gen/generated.
        import shutil
        shutil.copytree(self.gen, os.path.join(self.work, "shader_gen", "generated"))
        src = self.stubs.override_sources({})
        for f in self.wanted:
            self.assertEqual(src[f], os.path.join(self.work, "shader_gen", "generated", f))

    def test_repo_keyword_keeps_old_shaders(self):
        os.environ["LUNA_SHADER_SOURCE"] = "repo"
        src = self.stubs.override_sources({})
        self.assertTrue(all(os.path.dirname(p).endswith("shaders") for p in src.values()))

    def test_dev_machine_without_generated_falls_back(self):
        # The development repository still has the transcriptions in shaders/: a machine that never ran make_shaders
        # keeps building. The public one does not (test_public_repo_without_generated_stops covers it).
        if not all(os.path.exists(os.path.join(self.stubs.REPO_ROOT, "shaders", f)) for f in self.wanted):
            self.skipTest("no transcriptions in shaders/ (public repository)")
        src = self.stubs.override_sources({})
        self.assertTrue(all(os.path.dirname(p).endswith("shaders") for p in src.values()))

    def test_public_repo_without_generated_stops(self):
        # The public repository has only our own shaders in shaders/: without the generated ones, stop and say how.
        repo = os.path.join(self.tmp, "public")
        os.makedirs(os.path.join(repo, "shaders"))
        open(os.path.join(repo, "shaders", "Lunacid_VR_Fallback.shader"), "w").close()
        self.repo_root_was = self.stubs.REPO_ROOT
        self.stubs.REPO_ROOT = repo
        with self.assertRaises(FileNotFoundError) as ctx:
            self.stubs.override_sources({})
        self.assertIn("make_shaders.py", str(ctx.exception))

    def test_generated_folder_by_env(self):
        os.environ["LUNA_SHADER_SOURCE"] = self.gen
        src = self.stubs.override_sources({})
        for f in self.wanted:
            self.assertEqual(src[f], os.path.join(self.gen, f))
        own = [f for f, p in src.items() if f not in self.wanted]
        self.assertIn("Lunacid_VR_Fallback.shader", own)       # ours keep coming from shaders/
        self.stubs.apply(self.export, {})
        with open(os.path.join(self.export, "Assets", "Shader", self.wanted[0]), encoding="utf-8") as fh:
            self.assertTrue(fh.read().startswith("// generated stand-in"))
        self.assertTrue(self.stubs.verify(self.export, {})["passed"])

    def test_profile_key_and_missing_file(self):
        os.remove(os.path.join(self.gen, self.wanted[0]))
        with self.assertRaises(FileNotFoundError):
            self.stubs.override_sources({"shader_source": self.gen})
        with self.assertRaises(FileNotFoundError):
            self.stubs.override_sources({"shader_source": os.path.join(self.tmp, "nowhere")})

    def test_port_list_matches_repo_overrides(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        own = {"Lunacid_VR_Fallback.shader", "Lunacid_VR_Fallback_Transparent.shader"}
        game = {f for f in os.listdir(os.path.join(repo, "shaders")) if f.endswith(".shader")} - own
        # every game shader overridden in shaders/ is in the port list (in the public repo shaders/ keeps
        # only ours, so the list is then larger than shaders/)
        self.assertLessEqual(game, set(self.wanted))


class TestQuietOnScreen(unittest.TestCase):
    """2026-11-13 on the notebook: the .NET build printed 27 compiler warnings ('Desreferência de uma referência
    possivelmente nula') and Felipe asked whether that was normal. For a layperson it looks like an error: the
    tools' output goes to a log, the screen gets one line, and the log is shown only when something fails."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_output_goes_to_the_log(self):
        import contextlib
        import io
        log = os.path.join(self.tmp, "build.log")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            uscs.run([sys.executable, "-c", "print('warning CS8602: noisy')"], log=log)
        self.assertNotIn("CS8602", out.getvalue())
        with open(log, encoding="utf-8") as fh:
            self.assertIn("CS8602", fh.read())

    def test_a_failure_shows_the_end_of_the_log(self):
        log = os.path.join(self.tmp, "build.log")
        with self.assertRaises(SystemExit) as ctx:
            uscs.run([sys.executable, "-c", "import sys; print('error CS1002: ; expected'); sys.exit(3)"], log=log)
        self.assertIn("error CS1002", str(ctx.exception))
        self.assertIn(log, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
