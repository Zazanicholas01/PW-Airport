using UnityEngine;

[RequireComponent(typeof(MessageDispatcher))]
public class SimClockClient : MonoBehaviour {

    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private bool logDebug = false;

    private long lastSimUnixMs;
    private float lastSyncRealtime;
    private float timeScale = 1f;
    private int lastSyncId;
    private bool hasReceivedSync;

    public double SimNowUnixMs {
        get {
            if (!hasReceivedSync) return 0;
            var dtReal = Time.realtimeSinceStartup - lastSyncRealtime;
            return lastSimUnixMs + dtReal * timeScale * 1000.0;
        }
    }

    public float TimeScale => timeScale;
    public int LastSyncId => lastSyncId;
    public bool HasReceivedSync => hasReceivedSync;

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
        
        lastSimUnixMs = cmd.sim_unix_ms;
        timeScale = cmd.time_scale;
        lastSyncId = cmd.sync_id;
        lastSyncRealtime = Time.realtimeSinceStartup;
        hasReceivedSync = true;

        if (logDebug)
        {
            Debug.Log(
                $"[SimClockClient] clock_sync sync_id={cmd.sync_id} sim_unix_ms={cmd.sim_unix_ms} " +
                $"time_scale={cmd.time_scale:0.###} realtime={lastSyncRealtime:0.###}"
            );
        }
    }

}
