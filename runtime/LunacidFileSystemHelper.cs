using System;
using System.IO;
using UnityEngine;

namespace Lunacid.VR
{
    /// <summary>
    /// Cross-platform file system helper for Lunacid.
    /// Handles persistent save data on standalone platforms (e.g. Meta Quest / Android)
    /// and seamlessly redirects Resources/TXT streaming reads to TextAsset or persistentDataPath.
    /// </summary>
    public static class LunacidFileSystemHelper
    {
        public static string GetSaveDirectory()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            return Application.persistentDataPath;
#else
            // In Editor or desktop, persistentDataPath or project directory can be used
            return Application.persistentDataPath;
#endif
        }

        public static string GetSavePath(string filename)
        {
            string cleanName = filename.Replace("\\", "/");
            if (cleanName.Contains("/"))
            {
                cleanName = Path.GetFileName(cleanName);
            }
            return Path.Combine(GetSaveDirectory(), cleanName);
        }

        public static bool FileExists(string path)
        {
            if (string.IsNullOrEmpty(path)) return false;

            // 1. Check direct path
            if (File.Exists(path)) return true;

            // 2. Check redirected persistent path
            string savePath = GetSavePath(path);
            if (File.Exists(savePath)) return true;

            // 3. Check Resources
            string resPath = ExtractResourcePath(path);
            if (!string.IsNullOrEmpty(resPath))
            {
                TextAsset ta = Resources.Load<TextAsset>(resPath);
                if (ta != null) return true;
            }

            return false;
        }

        public static string ReadAllText(string path)
        {
            // 1. Check persistent override first
            string savePath = GetSavePath(path);
            if (File.Exists(savePath))
            {
                return File.ReadAllText(savePath);
            }

            // 2. Try loading from Resources
            string resPath = ExtractResourcePath(path);
            if (!string.IsNullOrEmpty(resPath))
            {
                TextAsset ta = Resources.Load<TextAsset>(resPath);
                if (ta != null)
                {
                    return ta.text;
                }
            }

            // 3. Try reading directly from disk
            if (File.Exists(path))
            {
                return File.ReadAllText(path);
            }

            Debug.LogWarning($"[LunacidFileSystemHelper] File not found: {path} (res: {resPath}, save: {savePath})");
            return string.Empty;
        }

        public static StreamReader OpenTextReader(string path)
        {
            string text = ReadAllText(path);
            byte[] bytes = System.Text.Encoding.UTF8.GetBytes(text);
            MemoryStream ms = new MemoryStream(bytes);
            return new StreamReader(ms);
        }

        public static StreamWriter CreateTextWriter(string path)
        {
            string targetPath = GetSavePath(path);
            string dir = Path.GetDirectoryName(targetPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }
            return new StreamWriter(targetPath);
        }

        public static FileStream OpenFileStream(string path, FileMode mode)
        {
            string targetPath = GetSavePath(path);
            string dir = Path.GetDirectoryName(targetPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }
            return new FileStream(targetPath, mode);
        }

        private static string ExtractResourcePath(string path)
        {
            string normalized = path.Replace("\\", "/");
            int idx = normalized.IndexOf("/Resources/", StringComparison.OrdinalIgnoreCase);
            if (idx >= 0)
            {
                string sub = normalized.Substring(idx + "/Resources/".Length);
                // Strip extension (.txt, .csv, etc.) for Resources.Load
                int dotIdx = sub.LastIndexOf('.');
                if (dotIdx > 0)
                {
                    sub = sub.Substring(0, dotIdx);
                }
                return sub;
            }
            return null;
        }
    }
}
