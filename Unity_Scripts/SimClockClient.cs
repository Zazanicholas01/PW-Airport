using UnityEngine;

[RequireComponent(typeof(MessageDispatcher))]

public class SimClockClient : MonoBehaviour {
    [SerializeField] private MessageDispatcher dispatcher;

    private long lastSimUnixMs;
    private float lastSyncRealtime;
    private float timeScale = 1f;
    private int lastSyncId;

    public double SimNowUnixMs {
        get {
            var dtReal = Time.realtimeSinceStartup - lastSyncRealtime;
            return lastSimUnixMs + dtReal * timeScale * 1000.0;
        }
    }

    public float TimeScale => timeScale;
    public int LastSyncId => lastSyncId;

    public void Awake() {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();
    }

    private void OnEnable() {
        dispatcher.OnClockSync += OnClockSync;
    }

    private void OnDisable() {
        dispatcher.OnClockSync -= OnClockSync;
    }

    private void OnClockSync(MessageDispatcher.ClockSyncCommand cmd) {
        lastUnixMs = cmd.sim_unix_ms;
        timeScale = cmd.time_scale;
        lastSyncId = cmd.sync_id;
        lastSyncRealtime = Time.realtimeSinceStartup;
    }
}