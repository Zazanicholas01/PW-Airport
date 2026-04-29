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
    private class ParkingEnteredEvent
    {
        public string type = "event";
        public string @event = "parking_entered";
        public string airplane_id;
        public int route_id;
        public string parking_spline;
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
            follower.OnParkingEntered -= OnParkingEntered;
        }
        
        follower = f;

        if (follower != null) {
            follower.OnPathCompleted += OnCompleted;
            follower.OnPlaneLeftStand += OnPlaneLeftStand;
            follower.OnParkingEntered += OnParkingEntered;
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

    private async void OnParkingEntered(string airplaneId, int routeId, string parkingSpline)
    {
        if (ws == null || !ws.IsConnected || string.IsNullOrWhiteSpace(airplaneId))
        {
            Debug.LogWarning(
                $"[PathCompletionReporter] parking_entered skipped airplane_id={airplaneId} " +
                $"route_id={routeId} connected={(ws != null && ws.IsConnected)}"
            );
            return;
        }

        var payload = new ParkingEnteredEvent
        {
            airplane_id = airplaneId,
            route_id = routeId,
            parking_spline = parkingSpline,
        };

        try
        {
            await ws.Send(JsonUtility.ToJson(payload));
            Debug.Log(
                $"[PathCompletionReporter] parking_entered sent airplane_id={airplaneId} " +
                $"route_id={routeId} parking_spline={parkingSpline}"
            );
        } catch (Exception ex)
        {
            Debug.LogWarning($"[PathCompletionReporter] parking_entered send failed: {ex.Message}");
        }
    }

    private void OnDisable() {

        if (follower != null) {
            follower.OnPathCompleted -= OnCompleted;
            follower.OnPlaneLeftStand -= OnPlaneLeftStand;
            follower.OnParkingEntered -= OnParkingEntered;
        }
    }
}
