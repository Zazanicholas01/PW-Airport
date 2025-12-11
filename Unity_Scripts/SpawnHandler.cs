using UnityEngine;

[RequireComponent(typeof(MessageDispatcher))]
public class SpawnHandler : MonoBehaviour
{
    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private PrefabRegistry prefabRegistry;
    [SerializeField] private Transform spawnParent;

    private void Awake()
    {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();

        if (prefabRegistry == null)
        {
            prefabRegistry = FindObjectOfType<PrefabRegistry>();
        }
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

        var position = Vector3.zero;
        if (command.position != null)
        {
            position = new Vector3(command.position.x, command.position.y, command.position.z);
        }

        Instantiate(prefab, position, Quaternion.identity, spawnParent);
        Debug.Log($"[SpawnHandler] Spawned '{command.prefab}' at {position} (stand {command.stand_id}).");
    }
}
