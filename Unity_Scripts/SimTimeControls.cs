using System.Threading.Tasks;
using UnityEngine;

public class SimTimeControls : MonoBehaviour
{
    [SerializeField] private LocalWebSocketClient ws;

    private void Awake()
    {
        if (ws == null) ws = FindObjectOfType<LocalWebSocketClient>();
    }

    public async void Pause() => await SetTimeScale(0f);
    public async void Play() => await SetTimeScale(1f);
    public async void FastForward() => await SetTimeScale(4f);

    private async Task SetTimeScale(float scale)
    {
        if (ws == null) return;
        if (ws == null) { Debug.LogError("[UI] LocalWebSockerClient missing"); return; }

        var ok = await ws.WaitForConnectionAsync();
        if (!ok || !ws.IsConnected) { Debug.LogWarning("[UI] WS not connected"); return; }

        var requestId = Guid.NewGuid().ToString("N");

        var json = $"{{\"command\":\"set_time_scale\",\"time_scale\":{scale},\"request_id\":\"{requestId}\"}}";
        Debug.Log($"[UI] -> set_time_scale scale={scale} request_id={requestId}");

        try { await ws.Send(json); }
        catch (Exception ex) { Debug.LogError($"[UI] send failed: {ex.Message}"); }
    }
}
