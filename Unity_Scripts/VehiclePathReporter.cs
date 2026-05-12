using System;
using UnityEngine;

public class VehiclePathReporter : MonoBehaviour
{
    [SerializeField] private LocalWebSocketClient ws;
    private SplineFollower follower;
    private string vehicleId;
    private string direction;

    [Serializable]
    private class VehicleRuntimeEvent
    {
        public string type = "event";
        public string @event;
        public string vehicle_id;
    }

    private void Awake()
    {
        if (ws == null)
            ws = FindObjectOfType<LocalWebSocketClient>();
    }

    public void Attach(SplineFollower f, string boundVehicleId, string boundDirection)
    {
        if (follower != null)
            follower.OnPathCompleted -= OnCompleted;

        follower = f;
        vehicleId = boundVehicleId;
        direction = boundDirection;

        if (follower != null)
            follower.OnPathCompleted += OnCompleted;
    }

    private async void OnCompleted(string _, int __)
    {
        if (ws == null || !ws.IsConnected || string.IsNullOrWhiteSpace(vehicleId))
            return;

        var payload = new VehicleRuntimeEvent
        {
            @event = direction == "to_home" ? "vehicle_returned_home" : "vehicle_arrived",
            vehicle_id = vehicleId,
        };

        try
        {
            await ws.Send(JsonUtility.ToJson(payload));
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[VehiclePathReporter] send failed: {ex.Message}");
        }
    }

    private void OnDisable()
    {
        if (follower != null)
            follower.OnPathCompleted -= OnCompleted;
    }
}
