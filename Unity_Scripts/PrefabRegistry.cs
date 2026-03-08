using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

[RequireComponent(typeof(LocalWebSocketClient))]
public class PrefabRegistry : MonoBehaviour
{
    [SerializeField] private PrefabEntry[] registeredPrefabs;

    private readonly Dictionary<string, PrefabEntry> prefabMap =
        new(StringComparer.OrdinalIgnoreCase);

    private bool prefabMapBuilt;
    private LocalWebSocketClient ws;

    public enum PrefabKind
    {
        Plane,
        GroundVehicle,
        Unknown
    }

    [Serializable]
    public class PrefabEntry
    {
        public string name;
        public PrefabKind type;
        public GameObject prefab;
    }

    [Serializable]
    private class SimpleEvent
    {
        public string type = "event";
        public string @event;
    }

    [Serializable]
    private class PrefabPayload
    {
        public string type;
        public string name;
    }

    [Serializable]
    private class PrefabListPayload
    {
        public PrefabPayload[] prefabs;
    }

    private void Awake()
    {
        ws = GetComponent<LocalWebSocketClient>();
        BuildPrefabMap();
    }

    private void BuildPrefabMap()
    {
        prefabMap.Clear();

        if (registeredPrefabs == null || registeredPrefabs.Length == 0)
        {
            Debug.LogWarning("[PrefabRegistry] registeredPrefabs is empty; no prefabs will be spawnable.");
            prefabMapBuilt = false;
            return;
        }

        foreach (var entry in registeredPrefabs)
        {
            if (entry == null || string.IsNullOrWhiteSpace(entry.name) || entry.prefab == null)
                continue;

            if (!prefabMap.ContainsKey(entry.name))
                prefabMap.Add(entry.name, entry);
        }

        prefabMapBuilt = prefabMap.Count > 0;
        Debug.Log($"[PrefabRegistry] Built prefab map with {prefabMap.Count} entries.");
    }

    public bool TryGetPrefab(string name, out GameObject prefab)
    {
        prefab = null;

        if (string.IsNullOrWhiteSpace(name))
            return false;

        if (!prefabMapBuilt)
        {
            Debug.LogWarning("[PrefabRegistry] Prefab map not built.");
            return false;
        }

        if (prefabMap.TryGetValue(name, out var entry) && entry != null)
        {
            prefab = entry.prefab;
            return prefab != null;
        }

        return false;
    }

    public async Task SendPrefabNames()
    {
        if (registeredPrefabs == null || registeredPrefabs.Length == 0)
        {
            Debug.LogWarning("[PrefabRegistry] No prefabs configured.");
            return;
        }

        var prefabs = registeredPrefabs
            .Where(entry => entry != null && !string.IsNullOrWhiteSpace(entry.name))
            .Select(entry => new PrefabPayload
            {
                type = entry.type switch
                {
                    PrefabKind.Plane => "plane",
                    PrefabKind.GroundVehicle => "vehicle",
                    _ => "unknown"
                },
                name = entry.name
            })
            .ToArray();

        if (prefabs.Length == 0)
        {
            Debug.LogWarning("[PrefabRegistry] No prefabs sent.");
            return;
        }

        await ws.Send(JsonUtility.ToJson(new SimpleEvent { @event = "send-prefabs" }));

        var payload = new PrefabListPayload { prefabs = prefabs };
        var json = JsonUtility.ToJson(payload);
        await ws.Send(json);

        Debug.Log($"[PrefabRegistry] Sent {prefabs.Length} prefabs: {json}");

        await ws.Send(JsonUtility.ToJson(new SimpleEvent { @event = "finish-send-prefabs" }));
    }
}
