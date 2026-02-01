using System;
using TMPro;
using UnityEngine;

public class SimTimeLabel : MonoBehaviour {

    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private TMP_Text label;

    private static readonly TimeSpan DisplayOffset = TimeSpan.FromHours(1);

    private void Awake(){
        if (dispatcher == null) dispatcher = FindObjectOfType<MessageDispatcher>();
        if (label == null) label = GetComponent<TMP_Text>();
    }

    private void OnEnable() {
        if (dispatcher != null) dispatcher.OnClockSync += HandleClockSync;
    }

    private void OnDisable() {
        if (dispatcher != null) dispatcher.OnClockSync -= HandleClockSync;
    }

    private void HandleClockSync(MessageDispatcher.ClockSyncCommand cmd) {

        var utc = DateTimeOffset.FromUnixTimeMilliseconds(cmd.sim_unix_ms);
        var utcPlus1 = utc.ToOffset(DisplayOffset);

        label.text = $"Sim time: {utcPlus1:yyyy-MM-dd HH:mm:ss} (x{cmd.time_scale:0.##})";
    }
}