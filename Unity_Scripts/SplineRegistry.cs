using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Splines;

[RequireComponent(typeof(LocalWebSocketClient))]
public class SplineRegistry : MonoBehaviour
{
    [SerializeField] private List<SplineContainer> registeredSplines = new();
    [SerializeField] private string masterSplineName = "MasterSpline";
    [SerializeField] private bool includeInactive = true;

    private LocalWebSocketClient ws;
    private TaskCompletionSource<bool> sendCompletedTcs = new(TaskCreationOptions.RunContinuationsAsynchronously);

    [Serializable]
    private class SimpleEvent {
        public string type = "event";
        public string @event;
    }

    [Serializable]
    private class SplineEvent {
        public string type = "event";
        public string @event = "spline";
        public SplineRecord spline;
    }

    private void Awake() => ws = GetComponent<LocalWebSocketClient>();

    private async void Start()
    {
        // Wait for websocket, then send once on play; call SendAllSplines() again after edits.
        var connected = await ws.WaitForConnectionAsync();
        if (!connected)
        {
            Debug.LogWarning("[SplineRegistry] WebSocket not connected; skipping spline send.");
            sendCompletedTcs.TrySetResult(false);
            return;
        }
        try
        {
            await SendAllSplines();
            sendCompletedTcs.TrySetResult(true);
        }
        catch (Exception ex)
        {
            Debug.LogError($"[SplineRegistry] Failed to send splines: {ex.Message}");
            sendCompletedTcs.TrySetResult(false);
        }
    }

    public Task<bool> WaitForSplineSendAsync() => sendCompletedTcs.Task;

    public async Task SendAllSplines()
    {

        // Begin Batch
        await ws.Send(JsonUtility.ToJson(new SimpleEvent {@event = "send-splines"}));

        foreach (var splineRecord in EnumerateSplines())
        {
            var payload = new SplineEvent { spline = splineRecord };
            var json = JsonUtility.ToJson(payload, true);
            await ws.Send(json);
            int knotCount = splineRecord.knots != null ? splineRecord.knots.Count : 0;
            Debug.Log($"[SplineRegistry] Sent spline '{splineRecord.name}' with {knotCount} knots.");
            await Task.Yield(); // avoid flooding in one frame
        }

        // Finish Batch
        await ws.Send(JsonUtility.ToJson(new SimpleEvent {@event = "finish-send-splines"}));
    }

    private IEnumerable<SplineRecord> EnumerateSplines()
    {
        IEnumerable<SplineContainer> containers =
            (registeredSplines != null && registeredSplines.Count > 0)
                ? registeredSplines
                : FindObjectsOfType<SplineContainer>(includeInactive);

        var seen = new HashSet<SplineContainer>();

        foreach (var container in containers)
        {
            if (container == null || container.Spline == null) continue;
            if (!seen.Add(container)) continue;
            
            string splineName = container.gameObject.name;

            bool isMaster = container.gameObject.name == masterSplineName;

            List<KnotEntry> knotEntries = isMaster ? new List<KnotEntry>() : null;
            LastKnotPosition lastKnotPos = null;

            int knotIndex = 0;

            foreach (var knot in container.Spline.Knots)
            {
                Vector3 pos = container.transform.TransformPoint(knot.Position);

                if (isMaster) {
                    Vector3 tanIn = container.transform.TransformDirection(knot.TangentIn);
                    Vector3 tanOut = container.transform.TransformDirection(knot.TangentOut);
                    Quaternion rot = container.transform.rotation * knot.Rotation;

                    // Each knot entry holds an id and a list of points (single point here for compatibility).
                    knotEntries.Add(new KnotEntry
                    {
                        id = knotIndex.ToString(),
                        parameters = new List<KnotPoint>
                        {
                            new KnotPoint
                            {
                                x = pos.x, y = pos.y, z = pos.z,
                                inX = tanIn.x, inY = tanIn.y, inZ = tanIn.z,
                                outX = tanOut.x, outY = tanOut.y, outZ = tanOut.z,
                                rotX = rot.x, rotY = rot.y, rotZ = rot.z, rotW = rot.w
                            }
                        }
                    });
                }

                lastKnotPos = new LastKnotPosition {
                    x = pos.x,
                    y = pos.y,
                    z = pos.z
                };

                knotIndex++;
            }

            yield return new SplineRecord
            {
                name = splineName,
                closed = container.Spline.Closed,
                knots = knotEntries,
                lastKnotPos = lastKnotPos
            };
        }
    }

    [Serializable] 
    private class SingleSplinePayload { 
        public SplineRecord spline; 
    }

    [Serializable] 
    private class SplineRecord { 
        public string name; 
        public bool closed; 
        public List<KnotEntry> knots; 
        public LastKnotPosition lastKnotPosition;
    }

    [Serializable] 
    private class KnotEntry { 
        public string id; 
        public List<KnotPoint> parameters; 
    }

    [Serializable] 
    private class KnotPoint {
        public float x, y, z;
        public float inX, inY, inZ;
        public float outX, outY, outZ;
        public float rotX, rotY, rotZ, rotW;
    }

    [Serializable]
    private class LastKnotPosition {
        public float x, y, z;
    }
}
