Shader "Lunacid/VR_Fallback" {
    Properties {
        _Color ("Main Color", Color) = (1,1,1,1)
        _MainTex ("MainTex", 2D) = "white" {}
        _Emission ("Emission", 2D) = "black" {}
        _EmissionColor ("Emission Color", Color) = (0,0,0,1)
        _Cutoff ("Alpha cutoff", Range(0, 1)) = 0.5
    }

    SubShader {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 150

        Pass {
            Name "ForwardBase"
            Tags { "LightMode"="ForwardBase" }

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile _ LIGHTMAP_ON

            #include "UnityCG.cginc"
            #include "Lighting.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            sampler2D _Emission;
            float4 _Emission_ST;
            fixed4 _Color;
            fixed4 _EmissionColor;
            float _Cutoff;

            struct appdata {
                float4 vertex : POSITION;
                float3 normal : NORMAL;
                float2 uv : TEXCOORD0;
                float2 uv1 : TEXCOORD1;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                float2 uv_em : TEXCOORD1;
                fixed4 vcolor : COLOR;
                float3 normal : NORMAL;
                #ifdef LIGHTMAP_ON
                float2 lmap : TEXCOORD3;
                #endif
                UNITY_FOG_COORDS(4)
                UNITY_VERTEX_OUTPUT_STEREO
            };

            v2f vert(appdata v) {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);

                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                o.uv_em = TRANSFORM_TEX(v.uv, _Emission);
                o.vcolor = fixed4(1, 1, 1, 1); // FORCE white - bypass vertex color entirely
                o.normal = UnityObjectToWorldNormal(v.normal);

                #ifdef LIGHTMAP_ON
                o.lmap = v.uv1.xy * unity_LightmapST.xy + unity_LightmapST.zw;
                #endif

                UNITY_TRANSFER_FOG(o, o.pos);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                fixed4 tex = tex2D(_MainTex, i.uv);
                if (_Cutoff > 0.01) {
                    clip(tex.a * _Color.a - _Cutoff);
                }

                fixed4 col = tex * _Color * i.vcolor;

                #ifdef LIGHTMAP_ON
                fixed3 lm = DecodeLightmap(UNITY_SAMPLE_TEX2D(unity_Lightmap, i.lmap));
                col.rgb *= lm;
                #else
                float3 lightDir = normalize(_WorldSpaceLightPos0.xyz);
                float NdotL = max(0.0, dot(normalize(i.normal), lightDir));
                fixed3 ambient = ShadeSH9(float4(i.normal, 1.0));
                col.rgb *= (_LightColor0.rgb * NdotL + ambient);
                #endif

                fixed4 em = tex2D(_Emission, i.uv_em) * _EmissionColor;
                col.rgb += em.rgb;

                UNITY_APPLY_FOG(i.fogCoord, col);
                return col;
            }
            ENDCG
        }
    }
    Fallback "Mobile/VertexLit"
}
