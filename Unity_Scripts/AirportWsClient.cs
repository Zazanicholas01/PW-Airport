// Assets/PWAirport/Scripts/AirportWsClient.cs
using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
#if UNITY_EDITOR
using UnityEditor;
#endif

// ######################## JSON STRUCTURE DEFINITION ###########################################

[Serializable]
public class AirportCommand
{
    public string type;      // "command"
    public string command;   // "land" or "takeoff"
    public string airplane;  // "A320", "B737", etc.
    public string piazzola;  // "O1", "O2", etc.
    public string timestamp;
}

[Serializable]
public class AirportEvent
{
    public string type = "event";
    public string @event;     // "landing.complete" or "takeoff.complete"
    public string airplane;   // Tipo di aereo
    public string piazzola;   // Piazzola
    public float t_sim;       // Unity time
}

[Serializable]
public class AirportResponse
{
    public string type = "response";
    public string status;     // "ok" or "error"
    public string message;
    public float t_sim;
}

// #################### CLASS DEFINITION ##################################################

public class AirportWsClient : MonoBehaviour
{
    [Header("WebSocket Configuration")]
    [Tooltip("URL per Unity Editor (localhost)")]
    public string EditorServerUrl = "ws://localhost:8765";

    [Tooltip("URL per Build su dispositivo (IP del PC dove gira il backend)")]
    public string DeviceServerUrl = "ws://10.0.20.168:8765";

    public float ReconnectDelaySec = 2f;

    private string ServerUrl
    {
        get
        {
#if UNITY_EDITOR
            return EditorServerUrl;
#else
            return DeviceServerUrl;
#endif
        }
    }

    [Header("References")]
    public AirportFlowManager airportManager;

    private ClientWebSocket _ws;
    private CancellationTokenSource _cts;

    // ######################### UNITY LIFECYCLE #######################################

    async void Start()
    {
        // IMPORTANTE: Previeni connessione fuori da Play Mode
#if UNITY_EDITOR
        if (!EditorApplication.isPlaying)
        {
            Debug.Log("[AirportWS] Not in Play Mode (Editor check), skipping connection");
            return;
        }
#endif
        if (!Application.isPlaying)
        {
            Debug.Log("[AirportWS] Not in Play Mode, skipping connection");
            return;
        }

        Application.runInBackground = true;

        // Trova AirportFlowManager se non assegnato
        if (airportManager == null)
        {
            airportManager = FindObjectOfType<AirportFlowManager>();
            if (airportManager == null)
            {
                Debug.LogError("[AirportWS] AirportFlowManager not found!");
                return;
            }
        }

        Debug.Log("[AirportWS] Starting WebSocket client...");
        await ConnectLoop();
    }

    void OnDestroy()
    {
        // Chiudi connessione quando l'oggetto viene distrutto
        _cts?.Cancel();
        _ws?.Dispose();
    }

    // ######################## CONNECTION & RECONNECTION LOOP #############################

    async Task ConnectLoop()
    {
        while (Application.isPlaying)
        {
            // Verifica che siamo ancora in Play Mode
#if UNITY_EDITOR
            if (!EditorApplication.isPlaying)
            {
                Debug.Log("[AirportWS] Exited Play Mode, stopping connection loop");
                break;
            }
#endif

            _cts = new CancellationTokenSource();
            _ws = new ClientWebSocket();

            try
            {
                Debug.Log($"[AirportWS] Connecting to {ServerUrl}...");
                await _ws.ConnectAsync(new Uri(ServerUrl), _cts.Token);
                Debug.Log("[AirportWS] Connected!");
                await ReceiveLoop();
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[AirportWS] Disconnected: {e.Message}");
            }

            // Verifica ancora prima di riconnettere
            if (!Application.isPlaying)
            {
                Debug.Log("[AirportWS] Application no longer playing, stopping reconnection");
                break;
            }

            // Auto-reconnect
            Debug.Log($"[AirportWS] Reconnecting in {ReconnectDelaySec} seconds...");
            await Task.Delay(TimeSpan.FromSeconds(ReconnectDelaySec));
        }

        Debug.Log("[AirportWS] Connection loop ended");
    }

    // #################### RECEIVE MESSAGES LOOP ######################################

    async Task ReceiveLoop()
    {
        var buffer = new byte[1 << 16];

        while (_ws.State == WebSocketState.Open)
        {
            var sb = new StringBuilder();
            WebSocketReceiveResult result;

            // Ricevi messaggio completo
            do
            {
                var segment = new ArraySegment<byte>(buffer);
                result = await _ws.ReceiveAsync(segment, _cts.Token);

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    Debug.Log("[AirportWS] Server closed connection");
                    return;
                }

                sb.Append(Encoding.UTF8.GetString(segment.Array, 0, result.Count));
            }
            while (!result.EndOfMessage);

            string json = sb.ToString();
            Debug.Log($"[AirportWS] Received: {json}");

            // Processa messaggio nel main thread di Unity
            UnityMainThreadDispatcher.Instance.Enqueue(() => HandleMessage(json));
        }
    }

    // ###################### MESSAGE HANDLER #############################################

    void HandleMessage(string json)
    {
        try
        {
            // Prova a parsare come comando
            var cmd = JsonUtility.FromJson<AirportCommand>(json);

            if (cmd != null && cmd.type == "command")
            {
                HandleCommand(cmd);
                return;
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[AirportWS] Error parsing message: {e.Message}");
        }
    }

    void HandleCommand(AirportCommand cmd)
    {
        Debug.Log($"[AirportWS] Command: {cmd.command} | Airplane: {cmd.airplane} | Piazzola: {cmd.piazzola}");

        if (cmd.command == "land")
        {
            // Comando atterraggio
            if (string.IsNullOrEmpty(cmd.airplane) || string.IsNullOrEmpty(cmd.piazzola))
            {
                Debug.LogError("[AirportWS] Invalid land command: missing airplane or piazzola");
                return;
            }

            airportManager.TriggerLanding(cmd.airplane, cmd.piazzola);
        }
        else if (cmd.command == "takeoff")
        {
            // Comando decollo
            if (string.IsNullOrEmpty(cmd.piazzola))
            {
                Debug.LogError("[AirportWS] Invalid takeoff command: missing piazzola");
                return;
            }

            airportManager.TriggerTakeoff(cmd.piazzola);
        }
        else
        {
            Debug.LogWarning($"[AirportWS] Unknown command: {cmd.command}");
        }
    }

    // #################### SEND EVENTS TO BACKEND ##########################################

    public async void SendLandingComplete(string airplane, string piazzola)
    {
        var evt = new AirportEvent
        {
            @event = "landing.complete",
            airplane = airplane,
            piazzola = piazzola,
            t_sim = Time.time
        };

        await SendMessage(JsonUtility.ToJson(evt));
    }

    public async void SendTakeoffComplete(string airplane, string piazzola)
    {
        var evt = new AirportEvent
        {
            @event = "takeoff.complete",
            airplane = airplane,
            piazzola = piazzola,
            t_sim = Time.time
        };

        await SendMessage(JsonUtility.ToJson(evt));
    }

    async Task SendMessage(string json)
    {
        if (_ws == null || _ws.State != WebSocketState.Open)
        {
            Debug.LogWarning("[AirportWS] Cannot send message: not connected");
            return;
        }

        try
        {
            var bytes = Encoding.UTF8.GetBytes(json);
            await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
            Debug.Log($"[AirportWS] Sent: {json}");
        }
        catch (Exception e)
        {
            Debug.LogError($"[AirportWS] Error sending message: {e.Message}");
        }
    }
}
