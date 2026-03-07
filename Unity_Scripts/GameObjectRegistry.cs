using System;
using System.Collections.Generic;
using UnityEngine;

public class GameObjectRegistry : MonoBehaviour
{
    private readonly Dictionary<string, GameObject> byUuid = new Dictionary<string, GameObject>(StringComparer.OrdinalIgnoreCase);

    public bool Register(string uuid, GameObject go) {
        if (string.IsNullOrWhiteSpace(uuid) || go == null) return false;
        byUuid[uuid] = go;
        Debug.Log($"[GameObjectRegistry] Registered new plane {uuid}");
        return true;
    }

    public bool TryGet(string uuid, out GameObject go) => byUuid.TryGetValue(uuid, out go);

    public GameObject GetOrNull(string uuid) {
        return (uuid != null && byUuid.TryGetValue(uuid, out var go)) ? go : null;
    }

    public bool Unregister(string uuid) {

        if (string.IsNullOrWhiteSpace(uuid)) return false;

        var removed = byUuid.Remove(uuid);
        if (removed)
            Debug.Log($"[GameObjectRegistry] Unregistered plane {uuid}");

        return removed;
    }

    public void Clear() => byUuid.Clear();
}