using System;
using UnityEngine;

public class PathCompletionReporter : MonoBehaviour {

    [SerializeField] private LocalWebSocketClient ws;
    private SplineFollower follower;

    [Serializable]
    private class PathCompletedEvent {
        public string type = "event";
        public string @event = "path_completed";
        public string airplane_id;
        public int route_id;
    }

    [Serializable]
    private class PlaneLeftStandEvent {
        public string type = "event";
        public string @event = "plane_left_stand";
        public string airplane_id;
        public int route_id;
    }

    private void Awake() {

        if (ws == null) ws = FindObjectOfType<LocalWebSocketClient>();
    }

    public void Attach(SplineFollower f) {
        
        if (follower != null) {
            follower.OnPathCompleted -= OnCompleted;
            follower.OnPlaneLeftStand -= OnPlaneLeftStand;
        }
        
        follower = f;

        if (follower != null) {
            follower.OnPathCompleted += OnCompleted;
            follower.OnPlaneLeftStand += OnPlaneLeftStand;
        }
    }

    private async void OnCompleted(string airplaneId, int routeId) {

        if (ws == null || !ws.IsConnected || string.IsNullOrWhiteSpace(airplaneId)) return;

        var payload = new PathCompletedEvent {
            airplane_id = airplaneId,
            route_id = routeId
        };
        try {
            await ws.Send(JsonUtility.ToJson(payload));
        } catch (Exception ex) {
            Debug.LogWarning($"[PathCompletionReporter] send failed: {ex.Message}");
        }
    }

    public async void OnPlaneLeftStand(string airplaneId, int routeId) {
        if (ws == null || !ws.IsConnected || string.IsNullOrWhiteSpace(airplaneId)) return;

        var payload = new PlaneLeftStandEvent {
            airplane_id = airplaneId,
            route_id = routeId
        };

        try {
            await ws.Send(JsonUtility.ToJson(payload));
        } catch (Exception ex) {
            Debug.LogWarning($"[PathCompletionReporter] plane_left_stand send failed: {ex.Message}");
        }
    }

    private void OnDisable() {

        if (follower != null) {
            follower.OnPathCompleted -= OnCompleted;
            follower.OnPlaneLeftStand -= OnPlaneLeftStand;
        }
    }
}