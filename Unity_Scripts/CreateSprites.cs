using System.IO;
using UnityEditor;
using UnityEngine;

public static class CreateRadarSprites
{
    [MenuItem("Tools/Radar/Create UI Sprites")]
    public static void CreateSprites()
    {
        string folder = "Assets/PWAirport/Sprites";
        Directory.CreateDirectory(folder);

        CreateCircle($"{folder}/RadarCircle.png", 256);
        CreateRing($"{folder}/RadarRing_Thin.png", 256, 1);
        CreateRing($"{folder}/RadarRing_Normal.png", 256, 2);
        CreateRing($"{folder}/RadarRing_Thick.png", 256, 4);
        CreateTriangle($"{folder}/RadarArrow.png", 128);
        CreateSweepTrail($"{folder}/RadarSweepTrail.png", 256, 55f);

        AssetDatabase.Refresh();

        ConfigureSprite($"{folder}/RadarCircle.png");
        ConfigureSprite($"{folder}/RadarRing_Thin.png");
        ConfigureSprite($"{folder}/RadarRing_Normal.png");
        ConfigureSprite($"{folder}/RadarRing_Thick.png");
        ConfigureSprite($"{folder}/RadarArrow.png");
        ConfigureSprite($"{folder}/RadarSweepTrail.png");

        Debug.Log("Radar sprites created in Assets/PWAirport/Sprites.");
    }

    private static void CreateCircle(string path, int size)
    {
        Texture2D texture = NewTransparentTexture(size);
        Color white = Color.white;

        Vector2 center = new Vector2(size / 2f, size / 2f);
        float radius = size / 2f - 2f;

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float distance = Vector2.Distance(new Vector2(x, y), center);
                if (distance <= radius)
                {
                    texture.SetPixel(x, y, white);
                }
            }
        }

        SaveTexture(path, texture);
    }

    private static void CreateRing(string path, int size, int thickness)
    {
        Texture2D texture = NewTransparentTexture(size);
        Color white = Color.white;

        Vector2 center = new Vector2(size / 2f, size / 2f);
        float outerRadius = size / 2f - 2f;
        float innerRadius = outerRadius - thickness;

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float distance = Vector2.Distance(new Vector2(x, y), center);
                bool inRing = distance <= outerRadius && distance >= innerRadius;

                if (inRing)
                {
                    texture.SetPixel(x, y, white);
                }
            }
        }

        SaveTexture(path, texture);
    }

    private static void CreateTriangle(string path, int size)
    {
        Texture2D texture = NewTransparentTexture(size);
        Color white = Color.white;

        Vector2 top = new Vector2(size / 2f, size - 6f);
        Vector2 left = new Vector2(12f, 10f);
        Vector2 right = new Vector2(size - 12f, 10f);

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                Vector2 p = new Vector2(x, y);

                if (IsPointInTriangle(p, top, left, right))
                {
                    texture.SetPixel(x, y, white);
                }
            }
        }

        SaveTexture(path, texture);
    }

    private static Texture2D NewTransparentTexture(int size)
    {
        Texture2D texture = new Texture2D(size, size, TextureFormat.RGBA32, false);
        Color clear = new Color(0f, 0f, 0f, 0f);

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                texture.SetPixel(x, y, clear);
            }
        }

        return texture;
    }

    private static void SaveTexture(string path, Texture2D texture)
    {
        texture.Apply();
        File.WriteAllBytes(path, texture.EncodeToPNG());
    }

    private static bool IsPointInTriangle(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
    {
        float area = TriangleArea(a, b, c);
        float area1 = TriangleArea(p, b, c);
        float area2 = TriangleArea(a, p, c);
        float area3 = TriangleArea(a, b, p);

        return Mathf.Abs(area - (area1 + area2 + area3)) < 0.5f;
    }

    private static float TriangleArea(Vector2 a, Vector2 b, Vector2 c)
    {
        return Mathf.Abs(
            (a.x * (b.y - c.y) +
             b.x * (c.y - a.y) +
             c.x * (a.y - b.y)) / 2f
        );
    }

    private static void ConfigureSprite(string path)
    {
        TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;

        if (importer == null)
        {
            Debug.LogWarning($"Could not configure sprite: {path}");
            return;
        }

        importer.textureType = TextureImporterType.Sprite;
        importer.spriteImportMode = SpriteImportMode.Single;
        importer.alphaIsTransparency = true;
        importer.mipmapEnabled = false;
        importer.SaveAndReimport();
    }

    private static void CreateSweepTrail(string path, int size, float angleDegrees)
    {
        Texture2D texture = NewTransparentTexture(size);

        Vector2 center = new Vector2(size / 2f, size / 2f);
        float radius = size / 2f - 2f;

        float halfAngle = angleDegrees * 0.5f;

        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                Vector2 p = new Vector2(x, y);
                Vector2 offset = p - center;

                float distance = offset.magnitude;

                if (distance > radius || distance <= 1f)
                {
                    continue;
                }

                float angle = Mathf.Atan2(offset.x, offset.y) * Mathf.Rad2Deg;

                if (angle < 0f)
                {
                    angle += 360f;
                }

                bool insideTrail = angle <= angleDegrees;

                if (!insideTrail)
                {
                    continue;
                }

                float angleFade = 1f - Mathf.Clamp01(angle / angleDegrees);
                float distanceFade = Mathf.Clamp01(distance / radius);

                float alpha = angleFade * distanceFade * 0.45f;

                Color color = new Color(1f, 1f, 1f, alpha);
                texture.SetPixel(x, y, color);
            }
        }

        SaveTexture(path, texture);
    }

}
