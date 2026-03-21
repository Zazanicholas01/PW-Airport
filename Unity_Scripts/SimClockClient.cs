using UnityEngine;

[RequireComponent(typeof(MessageDispatcher))]
public class SimClockClient : MonoBehaviour {

    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private bool logDebug = true;

    private long lastSimUnixMs;
    private float lastSyncRealtime;
    private float timeScale = 1f;
    private int lastSyncId;
    private float nextTickLogRealtime;
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

    private void Update()
    {
        if (!logDebug || !hasReceivedSync)
            return;

        if (Time.realtimeSinceStartup < nextTickLogRealtime)
            return;

        nextTickLogRealtime = Time.realtimeSinceStartup + 1f;
        Debug.Log(
            $"[SimClockClient] tick sim_now_unix_ms={SimNowUnixMs:0} time_scale={timeScale:0.###} last_sync_id={lastSyncId}"
        );
    }
}
