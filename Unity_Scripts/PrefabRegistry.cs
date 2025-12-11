using UnityEngine;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

[RequireComponent(typeof(LocalWebSocketClient))]
public class PrefabRegistry : MonoBehaviour
{
    [SerializeField] private string aereiFolder = "PWAirport/Prefabs/Aerei";
    [SerializeField] private string mezziFolder = "PWAirport/Prefabs/Mezzi";
    [SerializeField] private bool sendOnStart = true;
    [SerializeField] private SplineRegistry splineRegistry;

    [SerializeField]
    private GameObject[] registeredPrefabs;

    [Serializable]
    public class PrefabEntry{
        public string name;        // Nome che arriva da Python
        public GameObject prefab;  // Riferimento effettivo al Prefab da istanziare
    }

    private readonly Dictionary<string, GameObject> prefabMap = new Dictionary<string, GameObject>(StringComparer.OrdinalIgnoreCase);
    private bool prefabMapBuilt = false;

    private LocalWebSocketClient ws;

    [Serializable]
    private class SimpleEvent {
        public string type = "event";
        public string @event;
    }

    [Serializable]
    private class PrefabPayload {
        public string type;
        public string name;
    }

    [Serializable]
    private class PrefabListPayload {
        public PrefabPayload[] prefabs;
    }

    private void Awake() {
        ws = GetComponent<LocalWebSocketClient>();
    } 

    private void BuildPrefabMap() {
        prefabMap.Clear();
        if (registeredPrefabs == null || registeredPrefabs.Length == 0) {

            Debug.LogWarning("[PrefabRegistry] registeredPrefabs is empty; no prefabs will be spawnable.");
            return;
        }

        foreach (var go in registeredPrefabs) {
            if (go == null) continue;
            
            if (!prefabMap.ContainsKey(go.name)){
                prefabMap.Add(go.name, go);
            }
        }

        prefabMapBuilt = true;
        Debug.Log($"[PrefabRegistry] Built prefab map with {prefabMap.Count} entries.");
        Debug.Log(prefabMap);
    }

    public bool TryGetPrefab(string name, out GameObject prefab) {
        if (string.IsNullOrWhiteSpace(name)){
            prefab = null;
            return false;
        }

        if (!prefabMapBuilt)
        {
            Debug.LogWarning("[PrefabRegistry] Prefab map not built yet; did SendPrefabNames() complete?");
            prefab = null;
            return false;
        }

        return prefabMap.TryGetValue(name, out prefab);
    }

    private async void Start()
    {
        if (!sendOnStart) return;

        // Ensure websocket connected, then wait for splines to go out before sending prefabs.
        var connected = await ws.WaitForConnectionAsync();
        if (!connected)
        {
            Debug.LogWarning("[PrefabRegistry] WebSocket not connected; skipping prefab send.");
            return;
        }
        await EnsureSplineRegistryReady();
        await SendPrefabNames();
    }

    private async Task EnsureSplineRegistryReady()
    {
        if (splineRegistry == null)
        {
            splineRegistry = FindObjectOfType<SplineRegistry>();
        }

        if (splineRegistry != null)
        {
            var sent = await splineRegistry.WaitForSplineSendAsync();
            if (!sent)
            {
                Debug.LogWarning("[PrefabRegistry] SplineRegistry did not send splines; prefab send will still proceed.");
            }
        }
        else
        {
            Debug.LogWarning("[PrefabRegistry] No SplineRegistry found; sending prefabs anyway.");
        }
    }

    public async Task SendPrefabNames()
    {
        var prefabs = new List<PrefabPayload>();
        prefabs.AddRange(GetPrefabNames(aereiFolder).Select(name => new PrefabPayload { type = "aereo", name = name }));
        prefabs.AddRange(GetPrefabNames(mezziFolder).Select(name => new PrefabPayload { type = "mezzo", name = name }));

        if (prefabs.Count == 0)
        {
            Debug.LogWarning("[PrefabRegistry] No prefabs sent.");
            return;
        }

        // Begin Batch
        await ws.Send(JsonUtility.ToJson(new SimpleEvent {@event = "send-prefabs"}));

        var payload = new PrefabListPayload { prefabs = prefabs.ToArray() };
        var json = JsonUtility.ToJson(payload);
        await ws.Send(json);
        Debug.Log($"[PrefabRegistry] Sent {prefabs.Count} prefabs: {json}");

        // Finish Batch
        await ws.Send(JsonUtility.ToJson(new SimpleEvent { @event = "finish-send-prefabs"}));

        BuildPrefabMap();
    }

    private string[] GetPrefabNames(string relativeFolder)
    {
        string folderPath = Path.Combine(Application.dataPath, relativeFolder);

        if (!Directory.Exists(folderPath))
        {
            Debug.LogWarning($"[PrefabRegistry] Folder not found: {folderPath}");
            return Array.Empty<string>();
        }

        var names = Directory.GetFiles(folderPath, "*.prefab", SearchOption.TopDirectoryOnly)
            .Select(Path.GetFileNameWithoutExtension)
            .OrderBy(n => n)
            .ToArray();

        if (names.Length == 0)
        {
            return Array.Empty<string>();
        }

        return names;
    }

}
