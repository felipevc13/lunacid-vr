# Lunacid VR Port: Baseline Extraction & Setup Guide

## 1. Ferramentas Necessárias
* **AssetRipper**: Versão `2.0.0` (Apple Silicon GUI/CLI).
* **Unity**: Versão `6000.0.85f1` (Unity 6 LTS, Apple Silicon).
* **Lunacid**: Cópia legal do jogo adquirida na Steam (Steam AppID 1745510, baseada na Unity 2020.3.4f1 Mono).

## 2. Configurações Mandatórias do AssetRipper
Ao exportar o projeto no AssetRipper, a seguinte configuração é **obrigatória** para evitar crash de estouro de pilha durante o processamento de texturas de iluminação:
* `LightmapTextureExportFormat`: **`Exr`** (nunca PNG).
* `ScriptContentLevel`: `Level2` (Decompiled C# code).

## 3. Aplicação dos Patches de Portabilidade
Depois de exportar o projeto para uma pasta com sistema de arquivos APFS (ou imagem esparsa APFS para unidades externas), execute o patcher reproduzível:

```bash
python3 tools/patcher.py /caminho/para/ExportedProject
```

O patcher irá:
1. Detectar e resolver automaticamente GUIDs duplicadas geradas pelo exportador nas cenas, preservando a ordem 0 a 29 do build (`EditorBuildSettings.asset`).
2. Instalar os shaders compatíveis com estéreo VR (`Shader Forge/Object` e `Lunacid/VR_Fallback`) com suporte completo a lightmaps e vertex colors, preservando os GUIDs originais dos materiais.
3. Remover a DLL obsoleta `com.unity.multiplayer-hlapi.Runtime.dll`.
4. Corrigir o caminho de gravação de arquivos de salvamento para `Application.persistentDataPath` em builds Android.
