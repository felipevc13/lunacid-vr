# Procedimento para Adicionar um Novo Jogo ao Pipeline

Este guia descreve o fluxo de trabalho passo a passo para portar um novo jogo Unity de PC (2D ou 3D) para Meta Quest standalone em VR, reaproveitando a arquitetura modular e prevenindo regressões.

---

### Passo 1: Triagem Inicial com o `detect` (Pré-Compra ou Pré-Porte)

Antes de qualquer descompilação ou alteração, execute a ferramenta de triagem estática sobre os arquivos da versão de PC (Windows x64):

```bash
python3 core/detect.py /caminho/para/jogo-win --json triagem.json
```

O relatório gerado responde imediatamente:
1. **É Unity?** Identifica `UnityPlayer.dll` e a pasta `*_Data`.
2. **Versão do Unity:** Extraída de `globalgamemanagers` (ex: `2020.3.4f1`).
3. **Backend de Scripts:** `Mono` (risco baixo) vs `IL2CPP` (risco alto, exige desofuscação com Cpp2IL).
4. **Render Pipeline:** Built-in vs URP vs HDRP.
5. **Pacotes & Terceiros:** TextMeshPro, Input System, Shader Forge, I2 Localization, PostProcessing, etc.
6. **Proteções:** Steamworks DRM, EasyAntiCheat, BattlEye, Denuvo.

---

### Passo 2: Extração Limpa com AssetRipper

Use o AssetRipper para exportar um projeto Unity Editor a partir da instalação do PC:
- **Mono games:** Utilize `ScriptContentLevel: Level2` para exportar código C# recuperado e manter referências de scripts.
- **Estrutura de saída:** O projeto de exportação gerado conterá as pastas `Assets/` e `ProjectSettings/`.

---

### Passo 3: Criar o Perfil do Jogo (`games/<nome>.json`)

Crie um arquivo de perfil mínimo contendo apenas dados específicos do jogo:

```json
{
  "name": "NomeDoJogo",
  "appid": 123456,
  "steam_name": "NomeDoJogo",
  "unity_version": "2021.3.16f1",
  "target_unity_version": "6000.0.85f1",
  "target_platform": "Android",
  "target_graphics_api": "Vulkan",
  "scenes": [
    "Assets/Scenes/Menu.unity",
    "Assets/Scenes/Level1.unity"
  ],
  "material_overrides": [],
  "shader_overrides": [],
  "quirks": []
}
```

---

### Passo 4: Executar os Passes Modulares com o Runner

O orquestrador `core/runner.py` executa o ciclo completo de auditoria e correção:

1. **Detecção de Problemas:**
   ```bash
   python3 core/runner.py detect /caminho/para/ExportedProject --profile games/<nome>.json
   ```
2. **Simulação Sem Alterações (Dry-Run):**
   ```bash
   python3 core/runner.py apply /caminho/para/ExportedProject --profile games/<nome>.json --dry-run
   ```
3. **Aplicação das Correções Idempotentes:**
   ```bash
   python3 core/runner.py apply /caminho/para/ExportedProject --profile games/<nome>.json
   ```
4. **Verificação de Sucesso:**
   ```bash
   python3 core/runner.py verify /caminho/para/ExportedProject --profile games/<nome>.json
   ```

---

### Passo 5: Compilação no Unity 6 e Validação no Headset

1. Abra o projeto no Unity 6 LTS com o módulo Android Build Support instalado.
2. Execute o pré-aquecimento de shaders via `ShaderVariantCollectionBuilder` para evitar stripping.
3. Gere o APK com target ARM64 e Vulkan Graphics API.
4. Instale no headset via ADB:
   ```bash
   adb install -r build.apk
   adb logcat -s Unity
   ```
5. Valide a renderização e confira os logs para garantir ausência de erros de shaders ou exceções de I/O de arquivos.

