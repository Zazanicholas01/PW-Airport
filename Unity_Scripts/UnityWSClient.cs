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
    private ClientWebSocket socket;
    private CancellationTokenSource cts;
    private TaskCompletionSource<bool> connectedTcs = new(TaskCreationOptions.RunContinuationsAsynchronously);

    // Evento ascoltato dai Dispatchers
    public event Action<string> MessageReceived;

    public Task<bool> WaitForConnectionAsync() => connectedTcs.Task;
    public bool IsConnected => socket?.State == WebSocketState.Open;

    public async Task<bool> ConnectAsync()
    {
        if (socket != null && socket.State == WebSocketState.Open)
            return true;

        socket?.Dispose();
        cts?.Cancel();
        cts?.Dispose();

        connectedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        socket = new ClientWebSocket();
        cts = new CancellationTokenSource(TimeSpan.FromSeconds(Mathf.Max(1, connectTimeoutSeconds)));

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
            await socket.ConnectAsync(parsedUri, cts.Token);
            Debug.Log($"[WS] Connected to {uri}");
            connectedTcs.TrySetResult(true);
            _ = ListenLoop();
            await Send("Hello from Unity");
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

        while (socket != null && socket.State == WebSocketState.Open)
        {
            using var ms = new MemoryStream();
            WebSocketReceiveResult result;
            do
            {
                result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cts.Token);

                if (result.MessageType == WebSocketMessageType.Close) {
                        Debug.LogWarning("[WS] Server closed the connection.");
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
    }

    public async Task Send(string message)
    {
        if (socket?.State != WebSocketState.Open) return;
        var data = Encoding.UTF8.GetBytes(message);
        await socket.SendAsync(new ArraySegment<byte>(data), WebSocketMessageType.Text, true, cts.Token);
    }

    private async void OnDestroy()
    {
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
