using System;
using System.Collections.Generic;
using UnityEngine;

[RequireComponent(typeof(LocalWebSocketClient))]
public class MessageDispatcher : MonoBehaviour
{
    private LocalWebSocketClient wsClient;
    private readonly Queue<string> messageQueue = new();
    private readonly object queueLock = new();

    public event Action<SpawnCommand> OnSpawnCommand;
    public event Action<ClockSyncCommand> OnClockSync;
    public event Action<StartPathCommand> OnStartPathCommand;
    public event Action<DespawnPlaneCommand> OnDespawnPlaneCommand;
    public event Action<ClearParkingCommand> OnClearParkingCommand;
    public event Action<ContinuePathCommand> OnContinuePathCommand;

    [Serializable]
    private class CommandEnvelope
    {
        public string command;
    }

    [Serializable]
    public class SpawnCommand
    {
        public string command;
        public string prefab;
        public string stand_id;
        public string airplane_id;
        public SerializableVector3 position;
    }

    [Serializable]
    public class DespawnPlaneCommand {
        public string command;
        public string airplane_id;
    }

    [Serializable]
    public class ClockSyncCommand {
        public string command;
        public long sim_unix_ms;
        public float time_scale;
        public int sync_id;
    }

    [Serializable]
    public class ContinuePathCommand
    {
        public string command;
        public string airplane_id;
        public int route_id;
        public PathSegment[] segments;
    }

    [Serializable]
    public class ClearParkingCommand
    {
        public string command;
        public string airplane_id;
    }

    [Serializable]
    public class SpeedParams
    {
        public float initial_speed_kmh;
        public float target_speed_kmh;
        public float acceleration_mps2;
        public float deceleration_mps2;
    }

    [Serializable]
    public class SpeedProfile
    {
        public string purpose;
        public float initial_speed_kmh;
        public float target_speed_kmh;
        public float acceleration_mps2;
        public float deceleration_mps2;
    }

    [Serializable]
    public class StartPathCommand {
        public string command;
        public string airplane_id;
        public int route_id;
        public PathSegment[] segments;
    }

    [Serializable]
    public class PathSegment {
        public string name;
        public float t_start;
        public float t_end;
        public SpeedProfile speed_profile;
        public float hold_seconds;

        public bool auto_start_from_previous_end;
        public bool loop_until_cleared;
        public bool auto_exit_to_next_start;
    }

    [Serializable]
    public class SerializableVector3
    {
        public float x;
        public float y;
        public float z;
    }

    private void Awake()
    {
        wsClient = GetComponent<LocalWebSocketClient>();
    }

    private void OnEnable()
    {
        if (wsClient != null)
        {
            wsClient.MessageReceived += EnqueueMessage;
        }
    }

    private void OnDisable()
    {
        if (wsClient != null)
        {
            wsClient.MessageReceived -= EnqueueMessage;
        }
    }

    private void EnqueueMessage(string json)
    {
        lock (queueLock)
        {
            messageQueue.Enqueue(json);
        }
    }

    private void Update()
    {
        while (true)
        {
            string json;
            lock (queueLock)
            {
                if (messageQueue.Count == 0) break;
                json = messageQueue.Dequeue();
            }

            Dispatch(json);
        }
    }

    private void Dispatch(string json)
    {
        if (string.IsNullOrWhiteSpace(json)) return;

        CommandEnvelope envelope = null;
        try
        {
            envelope = JsonUtility.FromJson<CommandEnvelope>(json);
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[MessageDispatcher] Invalid message skipped: {ex.Message}");
            return;
        }

        if (envelope == null || string.IsNullOrWhiteSpace(envelope.command))
        {
            Debug.LogWarning("[MessageDispatcher] Message missing 'command' field; skipped.");
            return;
        }

        var cmd = envelope?.command?.Trim();
        if (string.IsNullOrEmpty(cmd)){ return; }

        switch (cmd.ToLowerInvariant())
        {
            case "clock_sync":
                HandleClockSync(json);
                break;
            case "spawn":
            case "spawn_plane": // legacy name from Python side
                HandleSpawn(json);
                break;
            case "start_path":
                HandleStartPath(json);
                break;
            case "despawn_plane":
                HandleDespawnPlane(json);
                break;
            case "continue_path":
                HandleContinuePath(json);
                break;
            case "clear_parking":
                HandleClearParking(json);
                break;
            default:
                Debug.LogWarning($"[MessageDispatcher] Unsupported command '{envelope.command}'.");
                break;
        }
    }

    private void HandleSpawn(string json)
    {
        SpawnCommand cmd = null;
        try
        {
            cmd = JsonUtility.FromJson<SpawnCommand>(json);
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[MessageDispatcher] Invalid spawn payload: {ex.Message}");
            return;
        }

        if (cmd == null)
        {
            Debug.LogWarning("[MessageDispatcher] Spawn payload deserialized to null.");
            return;
        }

        OnSpawnCommand?.Invoke(cmd);
        Debug.Log("[MessageDispatcher] Spawn command dispatched.");
    }

    private void HandleClockSync(string json) {
        ClockSyncCommand cmd;
        try {
            cmd = JsonUtility.FromJson<ClockSyncCommand>(json);
        }catch { return; }

        if (cmd == null) return;
        OnClockSync?.Invoke(cmd);
    }

    private void HandleStartPath(string json) {
        StartPathCommand cmd = null;
        try {
            cmd = JsonUtility.FromJson<StartPathCommand>(json);
        } catch(Exception ex) {
            Debug.LogWarning($"[MessageDispatcher] Invalid start_path payload: {ex.Message}");
            return;
        }

        if (cmd == null || string.IsNullOrWhiteSpace(cmd.airplane_id) || cmd.segments == null || cmd.segments.Length == 0){
            Debug.LogWarning("[MessageDispatcher] start_path payload missing airplane_id/segments.");
            return;
        }

        OnStartPathCommand?.Invoke(cmd);
        Debug.Log("[MessageDispatcher] StartPath command dispatched.");
    }

    private void HandleDespawnPlane(string json) {

        DespawnPlaneCommand cmd = null;
        try {
            cmd = JsonUtility.FromJson<DespawnPlaneCommand>(json);
        } catch (Exception ex) {
            Debug.LogWarning($"[MessageDispatcher] Invalid despawn_plane payload: {ex.Message}");
            return;
        }

        if (cmd == null || string.IsNullOrWhiteSpace(cmd.airplane_id)) {
            Debug.LogWarning("[MessageDispatcher] despawn_plane payload missing airplane_id.");
            return;
        }

        OnDespawnPlaneCommand?.Invoke(cmd);
        Debug.Log($"[MessageDispatcher] DespawnPlane command dispatched airplane_id={cmd.airplane_id}");
    }

    private void HandleClearParking(string json)
    {
        ClearParkingCommand cmd = null;

        try
        {
            cmd = JsonUtility.FromJson<ClearParkingCommand>(json);
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[MessageDispatcher] Invalid clear_parking payload: {ex.Message}");
            return;
        }

        if (cmd == null || string.IsNullOrWhiteSpace(cmd.airplane_id))
        {
            Debug.LogWarning("[MessageDispatcher] clear_parking payload missing airplane_id.");
            return;
        }

        OnClearParkingCommand?.Invoke(cmd);
        Debug.Log($"[MessageDispatcher] ClearParking dispatched airplane_id={cmd.airplane_id}");
    }

    private void HandleContinuePath(string json)
    {
        ContinuePathCommand cmd = null;

        try
        {
            cmd = JsonUtility.FromJson<ContinuePathCommand>(json);
        } catch (Exception ex) {
            Debug.LogWarning($"[MessageDispatcher] Invalid continue_path payload: {ex.Message}");
            return;
        }

        if (cmd == null || string.IsNullOrWhiteSpace(cmd.airplane_id) || cmd.segments == null || cmd.segments.Length == 0) {
            Debug.LogWarning("[MessageDispatcher] continue_path payload missing airplane_id/segments.");
            return;
        }

        OnContinuePathCommand?.Invoke(cmd);
        Debug.Log($"[MessageDispatcher] ContinuePath dispatched airplane_id={cmd.airplane_id} route_id={cmd.route_id} segments={cmd.segments.Length}");
    }
}
