using UnityEngine;

[RequireComponent(typeof(MessageDispatcher))]
public class DespawnHandler : MonoBehaviour {

    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private GameObjectRegistry registry;

    private void Awake() {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();
        if (registry == null) registry = FindObjectOfType<GameObjectRegistry>();
    }

    private void OnEnable() {
        if (dispatcher != null)
            dispatcher.OnDespawnPlaneCommand += HandleDespawnPlane;
    }

    private void OnDisable() {
        if (dispatcher != null)
            dispatcher.OnDespawnPlaneCommand -= HandleDespawnPlane;
    }

    private void HandleDespawnPlane(MessageDispatcher.DespawnPlaneCommand cmd) {

        if (registry == null) {
            Debug.LogWarning("[DespawnHandler] GameObjectRegistry not found.");
            return;
        }

        if (!registry.TryGet(cmd.airplane_id, out var plane) || plane == null) {
            Debug.LogWarning($"[DespawnHandler] Plane not found for airplane_id={cmd.airplane_id}");
            return;
        }

        registry.Unregister(cmd.airplane_id);
        Destroy(plane);

        Debug.Log($"[DespawnHandler] Despawned airplane_id={cmd.airplane_id}");
    }
}