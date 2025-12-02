using System;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class LocalWebSocketClient : MonoBehaviour
{
    [SerializeField] private string uri = "ws://localhost:8765";
    private ClientWebSocket socket;
    private CancellationTokenSource cts;
    private TaskCompletionSource<bool> connectedTcs = new(TaskCreationOptions.RunContinuationsAsynchronously);

    public Task<bool> WaitForConnectionAsync() => connectedTcs.Task;
    public bool IsConnected => socket?.State == WebSocketState.Open;

    private async void Start()
    {
        socket = new ClientWebSocket();
        cts = new CancellationTokenSource();

        try
        {
            await socket.ConnectAsync(new Uri(uri), cts.Token);
            Debug.Log("[WS] Connected");
            connectedTcs.TrySetResult(true);
            _ = ListenLoop();
            await Send("Hello from Unity");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[WS] Connect failed: {ex.Message}");
            connectedTcs.TrySetResult(false);
        }
    }

    private async Task ListenLoop()
    {
        var buffer = new byte[1024];
        while (socket.State == WebSocketState.Open)
        {
            using var ms = new MemoryStream();
            WebSocketReceiveResult result;
            do
            {
                result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cts.Token);
                ms.Write(buffer, 0, result.Count);
            } while (!result.EndOfMessage);

            var message = Encoding.UTF8.GetString(ms.ToArray());
            Debug.Log($"[WS] Received: {message}");
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
}
