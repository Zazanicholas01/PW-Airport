using System;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class LocalWebSocketClient : MonoBehaviour
{
    [SerializeField] private string uri = "ws://192.168.1.22:8765";
    [SerializeField] private int connectTimeoutSeconds = 8;
    [SerializeField] private float reconnectDelaySeconds = 2f;
    [SerializeField] private bool autoReconnect = true;

    private bool reconnecting;
    private bool shuttingDown;

    private ClientWebSocket socket;
    private CancellationTokenSource lifetimeCts;
    private TaskCompletionSource<bool> connectedTcs = new(TaskCreationOptions.RunContinuationsAsynchronously);

    // Evento ascoltato dai Dispatchers
    public event Action<string> MessageReceived;
    public event Action Connected;
    public event Action Disconnected;

    public Task<bool> WaitForConnectionAsync() => connectedTcs.Task;
    public bool IsConnected => socket?.State == WebSocketState.Open;

    public async Task<bool> ConnectAsync()
    {
        if (socket != null && socket.State == WebSocketState.Open)
            return true;

        socket?.Dispose();
        lifetimeCts?.Cancel();
        lifetimeCts?.Dispose();

        connectedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        socket = new ClientWebSocket();
        lifetimeCts = new CancellationTokenSource();

        if (!Uri.TryCreate(uri, UriKind.Absolute, out var parsedUri))
        {
            Debug.LogError($"[WS] Invalid URI '{uri}'.");
            connectedTcs.TrySetResult(false);
            return false;
        }

        Debug.Log(
            $"[WS] Connecting to {parsedUri} | host={parsedUri.Host} | port={parsedUri.Port} | " +
            $"scheme={parsedUri.Scheme} | reachability={Application.internetReachability} | " +
            $"platform={Application.platform}"
        );

        try
        {
            using var connectCts = CancellationTokenSource.CreateLinkedTokenSource(lifetimeCts.Token);
            connectCts.CancelAfter(TimeSpan.FromSeconds(Mathf.Max(1, connectTimeoutSeconds)));

            await socket.ConnectAsync(parsedUri, connectCts.Token);

            Debug.Log($"[WS] Connected to {uri}");
            connectedTcs.TrySetResult(true);
            Connected?.Invoke();
            _ = ListenLoop();

            return true;
        }
        catch (Exception ex)
        {
            Debug.LogError($"[WS] Connect failed for {uri}: {FormatException(ex)}");
            connectedTcs.TrySetResult(false);
            return false;
        }
    }

    private async Task ListenLoop()
    {
        var buffer = new byte[1024];

        try {


            while (socket != null && socket.State == WebSocketState.Open)
            {
                using var ms = new MemoryStream();
                WebSocketReceiveResult result;
                do
                {
                    result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), lifetimeCts.Token);

                    if (result.MessageType == WebSocketMessageType.Close) {
                            Debug.LogWarning("[WS] Server closed the connection.");
                            HandleDisconnect();
                            return;
                    }
                    ms.Write(buffer, 0, result.Count);

                } while (!result.EndOfMessage);

                var message = Encoding.UTF8.GetString(ms.ToArray());

                // Control to log all messages except clock messages from Python
                var compact = message.Replace(" ", "");
                var isClockSync = compact.Contains("\"command\":\"clock_sync\"");

                if (!isClockSync)
                    Debug.Log($"[WS] Received: {message}");

                // Richiamo a Unity Main Thread Dispatcher
                if (MessageReceived != null){
                    UnityMainThreadDispatcher.Instance.Enqueue(() =>{
                        try{
                            MessageReceived?.Invoke(message);
                        }catch(Exception ex){
                            Debug.LogError($"[WS] MessageReceived handler error: {ex.Message}");
                        }
                    });
                }
            }
        } catch (OperationCanceledException) {
            if (!shuttingDown) {
                Debug.LogWarning("[WS] Listen loop cancelled.");
                HandleDisconnect();   
            }
        } catch (Exception ex) {
            if (!shuttingDown) {
                Debug.LogWarning($"[WS] Listen loop failed: {FormatException(ex)}");
                HandleDisconnect();
            }
        }
    }

    private void HandleDisconnect() {
        if (shuttingDown) return;

        if (socket != null) {
            try { socket.Dispose(); } catch { }
            socket = null;
        }

        try {
            lifetimeCts?.Cancel();
            lifetimeCts?.Dispose();
        } catch {}

        lifetimeCts = null;

        if (!connectedTcs.Task.IsCompleted)
            connectedTcs.TrySetResult(false);

        Disconnected?.Invoke();

        if (autoReconnect)
            BeginReconnectLoop();
    }

    private async void BeginReconnectLoop() {

        if (reconnecting || shuttingDown) return;

        reconnecting = true;

        try {
            while (!shuttingDown && !IsConnected) {
                Debug.Log($"[WS] Reconnect attempt in {reconnectDelaySeconds:0.0}s...");
                await Task.Delay(TimeSpan.FromSeconds(Mathf.Max(0.25f, reconnectDelaySeconds)));

                if (shuttingDown) return;

                var ok = await ConnectAsync();
                if (ok) {
                    Debug.Log("[WS] Reconnect successful");
                    return;
                }
            }
        } finally {
            reconnecting = false;
        }
    }

    public async Task Send(string message)
    {
        if (socket?.State != WebSocketState.Open) return;

        var data = Encoding.UTF8.GetBytes(message);

        await socket.SendAsync(
            new ArraySegment<byte>(data), 
            WebSocketMessageType.Text, 
            true, 
            cts.Token
        );
    }

    private async void OnDestroy()
    {
        shuttingDown = true;

        try
        {
            if (socket?.State == WebSocketState.Open)
            {
                await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing", CancellationToken.None);
            }
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[WS] Close issue: {ex.Message}");
        }
        finally
        {
            socket?.Dispose();
            cts?.Cancel();
            cts?.Dispose();
            if (!connectedTcs.Task.IsCompleted)
            {
                connectedTcs.TrySetCanceled();
            }
        }
    }

    private static string FormatException(Exception ex)
    {
        if (ex == null) return "Unknown exception";

        var sb = new StringBuilder();
        int depth = 0;
        Exception current = ex;

        while (current != null && depth < 6)
        {
            if (depth > 0)
                sb.Append(" | Inner: ");

            sb.Append(current.GetType().Name);
            sb.Append(": ");
            sb.Append(current.Message);

            current = current.InnerException;
            depth++;
        }

        return sb.ToString();
    }
}
