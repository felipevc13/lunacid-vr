# VR Standalone Implementation Architecture (Meta Quest)

Este diretório conterá os componentes, prefabs e scripts específicos para VR Standalone (HorizonOS / OpenXR).

## O que entrará aqui nas próximas etapas:

1. **XR Initialization & Rig:**
   - Câmera estereoscópica independente (Left / Right Eye) configurada com IPD e tracking 6DoF do Quest.
   - Script de desacoplamento do `Main Camera` original (evitando distorções causadas por FOV fixo ou rotações forçadas de mouse/gamepad em 2D).
2. **Input Mapping (OpenXR / Meta Quest Controllers):**
   - Mapeamento das ações do novo Input System (`IA_Move`, `IA_Look`, `IA_Attack`, `IA_Cast`, `IA_Interact`, `IA_Menu`) para os botões físicos e touchpads do Quest Touch Plus (Grip, Trigger, Thumbstick, A/B/X/Y).
3. **World-Space UI Adapters:**
   - Conversores de `Canvas` Screen Space Overlay para World Space flutuante e curvo (Diegetic HUD / Wrist Watch).
4. **Budget de Desempenho VR (Quest 3S):**
   - 72 / 90 Hz estáveis.
   - Orçamento máximo de 11 ms de GPU por frame para ambos os olhos.
   - Restrição de luzes pontuais por pixel: prioritariamente VertexLit ou Bake, reservando ForwardAdd apenas para fontes primárias de destaque.

