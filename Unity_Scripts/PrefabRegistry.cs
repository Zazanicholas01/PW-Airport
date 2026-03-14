using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

[RequireComponent(typeof(LocalWebSocketClient))]
public class PrefabRegistry : MonoBehaviour
{
    [SerializeField] private PrefabEntry[] registeredPrefabs;
    [SerializeField] private bool logDebug = true;

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
        LogConfiguredPrefabs();
        BuildPrefabMap();
    }

    private void LogConfiguredPrefabs()
    {
        if (!logDebug)
            return;

        if (registeredPrefabs == null)
        {
            Debug.LogWarning("[PrefabRegistry] registeredPrefabs is null.");
            return;
        }

        Debug.Log($"[PrefabRegistry] Awake on {Application.platform}. configured entries={registeredPrefabs.Length}");

        for (int i = 0; i < registeredPrefabs.Length; i++)
        {
            var entry = registeredPrefabs[i];
            if (entry == null)
            {
                Debug.LogWarning($"[PrefabRegistry] Entry[{i}] is null.");
                continue;
            }

            string prefabName = entry.prefab != null ? entry.prefab.name : "null";
            Debug.Log(
                $"[PrefabRegistry] Entry[{i}] name='{entry.name}' type={entry.type} " +
                $"prefab={(entry.prefab == null ? "NULL" : prefabName)}"
            );
        }
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
            if (entry == null)
            {
                if (logDebug)
                    Debug.LogWarning("[PrefabRegistry] Skipping null entry while building prefab map.");
                continue;
            }

            if (string.IsNullOrWhiteSpace(entry.name))
            {
                if (logDebug)
                    Debug.LogWarning($"[PrefabRegistry] Skipping entry with empty name for prefab '{(entry.prefab == null ? "NULL" : entry.prefab.name)}'.");
                continue;
            }

            if (entry.prefab == null)
            {
                if (logDebug)
                    Debug.LogWarning($"[PrefabRegistry] Skipping entry '{entry.name}' because prefab reference is null.");
                continue;
            }

            if (!prefabMap.ContainsKey(entry.name))
                prefabMap.Add(entry.name, entry);
            else if (logDebug)
                Debug.LogWarning($"[PrefabRegistry] Duplicate prefab entry name '{entry.name}' ignored.");
        }

        prefabMapBuilt = prefabMap.Count > 0;
        Debug.Log($"[PrefabRegistry] Built prefab map with {prefabMap.Count} valid entries from {registeredPrefabs.Length} configured entries.");

        if (logDebug && prefabMap.Count > 0)
            Debug.Log($"[PrefabRegistry] Runtime keys: {string.Join(", ", prefabMap.Keys.OrderBy(key => key))}");
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

        if (logDebug)
            Debug.LogWarning($"[PrefabRegistry] Prefab '{name}' not found. Available keys: {string.Join(", ", prefabMap.Keys.OrderBy(key => key))}");

        return false;
    }

    public async Task SendPrefabNames()
    {
        var configuredCount = registeredPrefabs?.Length ?? 0;
        var prefabs = (registeredPrefabs ?? Array.Empty<PrefabEntry>())
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

        Debug.Log($"[PrefabRegistry] Sending prefab batch. configured={configuredCount} serializable={prefabs.Length}");

        if (logDebug)
        {
            for (int i = 0; i < prefabs.Length; i++)
                Debug.Log($"[PrefabRegistry] Payload[{i}] type={prefabs[i].type} name='{prefabs[i].name}'");
        }

        await ws.Send(JsonUtility.ToJson(new SimpleEvent { @event = "send-prefabs" }));

        var payload = new PrefabListPayload { prefabs = prefabs };
        var json = JsonUtility.ToJson(payload);
        await ws.Send(json);

        if (prefabs.Length == 0)
            Debug.LogWarning("[PrefabRegistry] Sent empty prefab batch. Setup can still complete, but runtime spawns will fail.");
        else
            Debug.Log($"[PrefabRegistry] Sent {prefabs.Length} prefabs: {json}");

        await ws.Send(JsonUtility.ToJson(new SimpleEvent { @event = "finish-send-prefabs" }));
        Debug.Log("[PrefabRegistry] Sent finish-send-prefabs.");
    }
}
