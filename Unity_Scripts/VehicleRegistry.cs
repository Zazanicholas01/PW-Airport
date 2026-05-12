using System;
using System.Collections.Generic;
using UnityEngine;

public class VehicleRegistry : MonoBehaviour
{
    [Serializable]
    public class VehicleBinding
    {
        public string vehicleId;
        public GameObject vehicleObject;
    }

    [SerializeField] private VehicleBinding[] bindings;
    private readonly Dictionary<string, GameObject> byId = new(StringComparer.OrdinalIgnoreCase);

    private void Awake()
    {
        byId.Clear();

        if (bindings == null)
            return;

        foreach (var binding in bindings)
        {
            if (binding == null || string.IsNullOrWhiteSpace(binding.vehicleId) || binding.vehicleObject == null)
                continue;

            byId[binding.vehicleId] = binding.vehicleObject;
        }
    }

    public bool TryGet(string vehicleId, out GameObject go)
    {
        return byId.TryGetValue(vehicleId, out go);
    }
}
