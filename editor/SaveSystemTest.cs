using System;
using System.IO;
using System.Runtime.Serialization.Formatters.Binary;
using UnityEditor;
using UnityEngine;
using Lunacid.VR;

public class SaveSystemTest
{
    [MenuItem("Tools/Test Save System")]
    public static void RunSaveTest()
    {
        Debug.Log("=== Starting Save System Verification Test ===");

        string saveDir = LunacidFileSystemHelper.GetSaveDirectory();
        Debug.Log($"[SaveTest] Save Directory: {saveDir}");

        string testSaveFile = LunacidFileSystemHelper.GetSavePath("SAVE_99.MIDNIGHT");
        Debug.Log($"[SaveTest] Target Save Path: {testSaveFile}");

        // Ensure directory exists
        Directory.CreateDirectory(Path.GetDirectoryName(testSaveFile));

        // Create test PlayerData
        PlayerData originalData = new PlayerData(new Vector3(12.5f, -3.2f, 45.0f), null);
        originalData.PLAYER_NAME = "QUEST_HERO";
        originalData.PLAYER_CLASS = "Vampire";
        originalData.AREA = 3;
        originalData.PLAYER_LVL = 42;
        originalData.PLAYER_DEF = 10;
        originalData.POS_X = 12.5f;
        originalData.POS_Y = -3.2f;
        originalData.POS_Z = 45.0f;
        originalData.ITEMS = new string[128];
        originalData.ITEMS[0] = "MOONLIGHT_SWORD";

        // 1. Test Write
        BinaryFormatter bf = new BinaryFormatter();
        using (FileStream fs = new FileStream(testSaveFile, FileMode.Create))
        {
            bf.Serialize(fs, originalData);
        }
        Debug.Log($"[SaveTest] Successfully serialized PlayerData to {testSaveFile} ({new FileInfo(testSaveFile).Length} bytes)");

        // 2. Test FileExists helper
        bool exists = LunacidFileSystemHelper.FileExists(testSaveFile);
        Debug.Log($"[SaveTest] LunacidFileSystemHelper.FileExists: {exists}");
        if (!exists)
        {
            Debug.LogError("[SaveTest] FAILED: FileExists returned false for existing save file!");
            return;
        }

        // 3. Test Read & Deserialize
        PlayerData loadedData = null;
        using (FileStream fs = new FileStream(testSaveFile, FileMode.Open))
        {
            loadedData = (PlayerData)bf.Deserialize(fs);
        }

        // 4. Validate fields
        bool nameMatch = loadedData.PLAYER_NAME == originalData.PLAYER_NAME;
        bool classMatch = loadedData.PLAYER_CLASS == originalData.PLAYER_CLASS;
        bool areaMatch = loadedData.AREA == originalData.AREA;
        bool lvlMatch = loadedData.PLAYER_LVL == originalData.PLAYER_LVL;
        bool defMatch = loadedData.PLAYER_DEF == originalData.PLAYER_DEF;
        bool itemMatch = loadedData.ITEMS != null && loadedData.ITEMS[0] == originalData.ITEMS[0];
        bool posMatch = loadedData.POS_X == 12.5f && loadedData.POS_Y == -3.2f && loadedData.POS_Z == 45.0f;

        Debug.Log($"[SaveTest] Field Validations: Name={nameMatch}, Class={classMatch}, Area={areaMatch}, Level={lvlMatch}, Def={defMatch}, Item={itemMatch}, Pos={posMatch}");

        if (nameMatch && classMatch && areaMatch && lvlMatch && defMatch && itemMatch && posMatch)
        {
            Debug.Log("[SaveTest] SUCCESS: Save & Load round-trip verified 100%!");
        }
        else
        {
            Debug.LogError("[SaveTest] FAILED: Deserialized data does not match original data!");
        }

        // 5. Cleanup
        if (File.Exists(testSaveFile))
        {
            File.Delete(testSaveFile);
            Debug.Log("[SaveTest] Cleaned up temporary test save file.");
        }
    }
}
