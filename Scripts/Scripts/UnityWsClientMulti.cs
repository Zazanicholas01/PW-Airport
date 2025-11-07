// Assets/Scripts/UnityWsClientMulti.cs
using System;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

// ######################## JSON STRUCTURE DEFINITION ###########################################

[Serializable] class Position { public float x, y, z; }
[Serializable] class QueryMsg { public string type; public string query; public string target_id; public string msg_id; }
[Serializable] class Args { public Position[] waypoints; public float speed = -1f; public float accel_up = -1f; public float accel_down = -1f;}
[Serializable] class CommandMsg { public string type; public string command; public string target_id; public string msg_id; public Args args; }

[Serializable] class ResponseMsg {
    public string type = "response";
    public string query, target_id, msg_id;
    public float t_sim;
    public Position result;   // if ok
    public string error;      // if error
}
[Serializable] class EventMsg {
    public string type = "event";
    public string @event, target_id, ref_msg_id, detail;
    public float t_sim;
}

// #################### CLASS DEFINITION ##################################################à

public class UnityWsClientMulti : MonoBehaviour
{
    [Header("WebSocket")]
    public string PythonWsUrl = "ws://10.0.20.36:8765";
    public float ReconnectDelaySec = 2f;

    // Scan the scene for components
    Dictionary<string, GameObject> _byId = new();
    Dictionary<string, RouteFollower> _follow = new();

    ClientWebSocket _ws;
    CancellationTokenSource _cts;

    // ######################### SEARCH COMPONENTS LOOP #######################################à

    async void Start()
    {
        Application.runInBackground = true;

        // Search for SimObject and Route Follower Loop
        foreach (var so in FindObjectsOfType<SimObject>(true))
        {
            if (string.IsNullOrWhiteSpace(so.Id)) continue;
            _byId[so.Id] = so.gameObject; // Recupera GameObject in base all'ID
            var rf = so.GetComponent<RouteFollower>();
            if (rf != null)
            {
                _follow[so.Id] = rf; // Recupera RouteFollower in base all'ID
                rf.OnRouteComplete = () =>
                {
                    var evn = new EventMsg { @event = "route.complete", target_id = so.Id, t_sim = Time.time };
                    _ = Send(JsonUtility.ToJson(evn)); // Se RouteComplete invia evento a Python
                };
            }
        }

        await ConnectLoop();
    }

    // ######################## CONNECTION & RECONNECTION LOOP #############################

    async Task ConnectLoop()
    {
        while (true)
        {
            // Instantiate client websocket
            _cts = new CancellationTokenSource();
            _ws = new ClientWebSocket();

            try
            {
                // Connect to server Python
                await _ws.ConnectAsync(new Uri(PythonWsUrl), _cts.Token);
                Debug.Log("[WS] Connected");
                await ReceiveLoop();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[WS] Disconnected: " + e.Message);
            }

            // Auto Reconnection
            await Task.Delay(TimeSpan.FromSeconds(ReconnectDelaySec));
        }
    }

    // #################### RECEIVE MESSAGES LOOP ######################################

    async Task ReceiveLoop()
    {
        var buf = new byte[1 << 16];
        while (_ws.State == WebSocketState.Open)
        {
            var sb = new StringBuilder();
            WebSocketReceiveResult res;

            // Loop until end of the message
            do
            {
                var seg = new ArraySegment<byte>(buf);
                res = await _ws.ReceiveAsync(seg, _cts.Token);
                if (res.MessageType == WebSocketMessageType.Close) return;
                sb.Append(Encoding.UTF8.GetString(seg.Array, 0, res.Count));
            } while (!res.EndOfMessage);

            // Pass the message to the client logic
            HandleMessage(sb.ToString());
        }
    }

    // ###################### CLIENT MESSAGE LOGIC #############################################

    void HandleMessage(string json)
    {
        // Queries
        var q = JsonUtility.FromJson<QueryMsg>(json);
        if (q != null && q.type == "query" && q.query == "get.position")
        {
            if (_byId.TryGetValue(q.target_id, out var go))
            {
                // Find Current Position of GameObject
                var p = go.transform.position;

                // Create Position Response Following Protocol 
                var resp = new ResponseMsg {
                    query = q.query, target_id = q.target_id, msg_id = q.msg_id,
                    t_sim = Time.time, result = new Position { x = p.x, y = p.y, z = p.z }, type = "response"
                };

                // Send ack to Python
                _ = Send(JsonUtility.ToJson(resp));
            }
            else
            {
                // Send error to Python
                var resp = new ResponseMsg { type="response", query=q.query, target_id=q.target_id, msg_id=q.msg_id, t_sim=Time.time, error="not_found" };
                _ = Send(JsonUtility.ToJson(resp));
            }
            return;
        }

        // Commands
        var c = JsonUtility.FromJson<CommandMsg>(json);

        if (c != null && c.type == "command")
        {
            if (c.command == "speed.set")
            {
                // Check if RouteFollower Exists
                if (_follow.TryGetValue(c.target_id, out var rf))
                {
                    // Set Speed
                    float sp = (c.args != null && c.args.speed > -0.5f) ? c.args.speed : rf.TargetSpeed;
                    float? up   = (c.args != null && c.args.accel_up   > -0.5f) ? c.args.accel_up   : (float?)null;
                    float? down = (c.args != null && c.args.accel_down > -0.5f) ? c.args.accel_down : (float?)null;
                    rf.SetTargetSpeed(sp, up, down);

                    // Send Ack
                    var ack = new EventMsg { @event = "command.ack", target_id = c.target_id, ref_msg_id = c.msg_id, t_sim = Time.time, detail = "speed.set" };
                    _ = Send(JsonUtility.ToJson(ack));
                }
                else
                {
                    // Send Error
                    var nack = new EventMsg { @event = "command.error", target_id = c.target_id, ref_msg_id = c.msg_id, t_sim = Time.time, detail = "invalid_target" };
                    _ = Send(JsonUtility.ToJson(nack));
                }
                return;
            }
        }


        if (c != null && c.type == "command" && c.command == "set.route")
        {
            // Validate Waypoints & Check RouteFollower Exists
            if (!_follow.TryGetValue(c.target_id, out var rf) || c.args?.waypoints == null || c.args.waypoints.Length == 0)
            {
                // Send Error
                var nack = new EventMsg { @event = "command.error", target_id = c.target_id, ref_msg_id = c.msg_id, t_sim = Time.time, detail = "invalid_target_or_waypoints" };
                _ = Send(JsonUtility.ToJson(nack));
                return;
            }

            // Convert JSON to Vector3 & Start Route
            var wps = new Vector3[c.args.waypoints.Length];
            for (int i = 0; i < wps.Length; i++)
                wps[i] = new Vector3(c.args.waypoints[i].x, c.args.waypoints[i].y, c.args.waypoints[i].z);

            rf.StartRoute(wps, c.args.speed > 0 ? c.args.speed : null);

            // Send Ack
            var ack = new EventMsg { @event = "command.ack", target_id = c.target_id, ref_msg_id = c.msg_id, t_sim = Time.time, detail = "set.route" };
            _ = Send(JsonUtility.ToJson(ack));
        }
    }

    // #################### SEND MESSAGES TO PYTHON ##########################################

    async Task Send(string json)
    {
        if (_ws == null || _ws.State != WebSocketState.Open) return;
        var bytes = Encoding.UTF8.GetBytes(json);
        await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
    }
}
