using UnityEngine;

[RequireComponent(typeof(MessageDispatcher))]
public class SpawnHandler : MonoBehaviour
{
    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private PrefabRegistry prefabRegistry;
    [SerializeField] private Transform spawnParent;
    [SerializeField] private GameObjectRegistry registry;

    private void Awake()
    {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();

        if (prefabRegistry == null) prefabRegistry = FindObjectOfType<PrefabRegistry>();
        if (registry == null) registry = FindObjectOfType<GameObjectRegistry>();

        if (spawnParent == null)
            Debug.LogWarning("[SpawnHandler] spawnParent is not assigned. Spawned planes will not be anchored under AirportRoot.");
    }

    private void OnEnable()
    {
        if (dispatcher != null)
        {
            dispatcher.OnSpawnCommand += HandleSpawn;
        }
    }

    private void OnDisable()
    {
        if (dispatcher != null)
        {
            dispatcher.OnSpawnCommand -= HandleSpawn;
        }
    }

    public void SetSpawnParent(Transform newSpawnParent)
    {
        spawnParent = newSpawnParent;
    }


    private void HandleSpawn(MessageDispatcher.SpawnCommand command)
    {
        if (prefabRegistry == null)
        {
            Debug.LogWarning("[SpawnHandler] PrefabRegistry not found; cannot spawn.");
            return;
        }

        if (!prefabRegistry.TryGetPrefab(command.prefab, out var prefab))
        {
            Debug.LogWarning($"[SpawnHandler] Prefab '{command.prefab}' not found in registry.");
            return;
        }
        
        if (spawnParent == null)
        {
            Debug.LogError("[SpawnHandler] spawnParent is null. Assign AirportRoot/SpawnParent before runtime spawning.");
            return;
        }

        var worldPosition = Vector3.zero;
        if (command.position != null)
        {
            worldPosition = new Vector3(command.position.x, command.position.y, command.position.z);
        }

        var localStandRotation = RotationForStand(command.stand_id);
        var worldRotation = spawnParent.rotation * localStandRotation;

        var instance = Instantiate(prefab, worldPosition, worldRotation, spawnParent);

        var radarTarget = instance.GetComponentInChildren<RadarTarget>();
        if (radarTarget != null)
        {
            radarTarget.airplaneId = command.airplane_id;
            radarTarget.isVisibleOnRadar = true;
        }

        if (registry != null && !string.IsNullOrWhiteSpace(command.airplane_id))
            registry.Register(command.airplane_id, instance);
            
        Debug.Log($"[SpawnHandler] Spawned '{command.prefab}' at {position} rotY={rotation.eulerAngles.y:0.##} (stand {command.stand_id}).");
        Debug.Log($"[SpawnHandler] spawn '{command.prefab}' airplane_id={command.airplane_id} " +
          $"pos={(command.position == null ? "NULL" : $"{command.position.x},{command.position.y},{command.position.z}")} " +
          $"spawnParent={(spawnParent == null ? "null" : spawnParent.position.ToString())}");

    }

    private static Quaternion RotationForStand(string standId)
    {
        switch (standId)
        {
            case "C2":
            case "P2":
                return Quaternion.Euler(0f, 180f, 0f);

            case "C3":
            case "P3":
                return Quaternion.Euler(0f, 90f, 0f);

            case "C1":
            case "P1":
                return Quaternion.Euler(0f, -90f, 0f);

            default:
                return Quaternion.identity;
        }
    }
}
