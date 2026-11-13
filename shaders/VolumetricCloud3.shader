// Protected override for the VolumetricClouds3 raymarcher (material "Volumetric Clouds HighQ").
// RaymarchedClouds (on the SHOT_ALLEY cinematic camera) puts a full-screen quad in front of the
// camera with this material. The generic stub drew _MainTex (unset -> white), so the town shot of
// the intro was ~6 s of solid white. The original raymarches faint dark clouds that are barely
// visible in that shot; a 48-step raymarch is too heavy for the Quest anyway, so the quad draws
// nothing.
Shader "VolumetricCloud3" {
    Properties {
        _BaseColor ("BaseColor", Color) = (0.25,0.27,0.39,1)
    }
    SubShader {
        Tags { "Queue"="Transparent+500" "IgnoreProjector"="True" "RenderType"="Transparent" }
        Blend Zero One
        ZWrite Off
        ColorMask 0

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
                discard;
                return 0;
            }
            ENDCG
        }
    }
    Fallback Off
}
