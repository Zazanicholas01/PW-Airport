using System;
using TMPro;
using UnityEngine;

public class SimTimeLabel : MonoBehaviour {

    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private TMP_Text label;
    [SerializeField] private SimClockClient clockClient;
    [SerializeField] private float refreshIntervalSeconds = 0.25f;

    private float nextRefreshRealtime;
    private TimeZoneInfo displayTimeZone;

    private void Awake() {
        if (dispatcher == null) dispatcher = FindObjectOfType<MessageDispatcher>();
        if (label == null) label = GetComponent<TMP_Text>();
        if (clockClient == null) clockClient = FindObjectOfType<SimClockClient>();

        displayTimeZone = ResolveRomeTimeZone();

        if (label != null && string.IsNullOrWhiteSpace(label.text))
            label.text = "Sim time: syncing";
    }

    private void OnEnable() {
        if (dispatcher != null) dispatcher.OnClockSync += HandleClockSync;
    }

    private void OnDisable() {
        if (dispatcher != null) dispatcher.OnClockSync -= HandleClockSync;
    }

    private void HandleClockSync(MessageDispatcher.ClockSyncCommand cmd) {

        UpdateLabel(cmd.sim_unix_ms, cmd.time_scale);
    }

    private static TimeZoneInfo ResolveRomeTimeZone() {
        try { return TimeZoneInfo.FindSystemTimeZoneById("Europe/Rome"); }
        catch {
            try { return TimeZoneInfo.FindSystemTimeZoneById("W. Europe Standard Time"); }
            catch { return null; }
        }
    }

    private void Update() {

        if (label == null || clockClient == null || !clockClient.HasReceivedSync) return;
        if (Time.unscaledTime < nextRefreshRealtime) return;

        nextRefreshRealtime = Time.unscaledTime + Mathf.Max(0.05f, refreshIntervalSeconds);
        UpdateLabel((long)Math.Round(clockClient.SimNowUnixMs), clockClient.TimeScale);
    }

    private void UpdateLabel(long simUnixMs, float timeScale) {
        if (label == null) return;

        var utc = DateTimeOffset.FromUnixTimeMilliseconds(simUnixMs);
        var localTime = ConvertUtcToRome(utc);

        label.text = $"Sim time: {localTime:yyyy-MM-dd HH:mm:ss} (x{timeScale:0.##})";
    }

    private DateTimeOffset ConvertUtcToRome(DateTimeOffset utc) {
        if (displayTimeZone != null) {
            try {
                return TimeZoneInfo.ConvertTime(utc, displayTimeZone);
            }
            catch {
            }
        }

        return ApplyRomeDstRules(utc);
    }

    private static DateTimeOffset ApplyRomeDstRules(DateTimeOffset utc) {
        var utcInstant = utc.ToUniversalTime();
        var year = utcInstant.Year;

        var dstStartUtc = LastSunday(year, 3).AddHours(1);
        var dstEndUtc = LastSunday(year, 10).AddHours(1);
        var offset = (utcInstant >= dstStartUtc && utcInstant < dstEndUtc)
            ? TimeSpan.FromHours(2)
            : TimeSpan.FromHours(1);

        return utcInstant.ToOffset(offset);
    }

    private static DateTimeOffset LastSunday(int year, int month) {
        var lastDay = new DateTimeOffset(year, month, DateTime.DaysInMonth(year, month), 0, 0, 0, TimeSpan.Zero);
        while (lastDay.DayOfWeek != DayOfWeek.Sunday) {
            lastDay = lastDay.AddDays(-1);
        }
        return lastDay;
    }
}
