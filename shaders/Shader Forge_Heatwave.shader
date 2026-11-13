// Protected override for Shader Forge/Heatwave (HEAT1: the hot air over the CAVE lava). The original
// (tools/shader_disasm/dxbc_dump.py) is a GrabPass distortion with no colour of its own:
//   o = _DistTex(TRANSFORM_TEX(uv + _Time.y * (0.1, -0.2))).r * _DIST_POWER * _MainTex(uv).r
//       * depth fade (_Fade.z, _Fade.w) * height fade (_Fade.x, _Fade.y) - vertex red * _DIST_POWER
//   colour = _GrabTexture(screen uv + o), opaque
// A stereo GrabPass costs the Quest a full-screen resolve every frame for a faint shimmer, so this
// draws nothing; the generic stub painted the texture: a red band across the cave.
Shader "Shader Forge/Heatwave" {
    Properties {
        _DistTex ("DistTex", 2D) = "white" {}
        _DIST_POWER ("DIST_POWER", Float) = 0.05
        _MainTex ("MainTex", 2D) = "white" {}
        _Fade ("Fade", Vector) = (0,1,0,1)
    }
    SubShader {
        Tags { "Queue"="Transparent" "IgnoreProjector"="True" "RenderType"="Transparent" }
        ColorMask 0
        ZWrite Off
        Cull Off

        Pass {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            struct appdata {
                float4 vertex : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f {
                float4 pos : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            v2f vert(appdata v) {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target {
                return 0;
            }
            ENDCG
        }
    }
}
