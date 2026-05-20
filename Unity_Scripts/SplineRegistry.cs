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
    [SerializeField] private string departureSplineName = "Spline_Departure";
    [SerializeField] private bool includeInactive = true;
    [SerializeField] private Transform splineRoot;
    [SerializeField] private List<Transform> additionalSplineRoots = new();
    [SerializeField] private float metersPerUnityUnit = 867.08f;


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

    [Serializable] 
    private class SingleSplinePayload { 
        public SplineRecord spline; 
    }

    [Serializable] 
    private class SplineRecord { 
        public string name; 
        public bool closed; 
        public List<KnotEntry> knotEntries; 
        public KnotPosition firstKnotPos;
        public KnotPosition lastKnotPos;
        public float lengthUnits;
        public float lengthMeters;
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
    private class KnotPosition {
        public float x, y, z;
    }

    private static float EstimateSplineLengthWorld(SplineContainer container, int samples = 256)
    {
        if (container == null || container.Spline == null)
            return 0f;

        samples = Mathf.Max(8, samples);
        Vector3 previous = EvalWorld(container, 0f);
        float total = 0f;

        for (int i = 1; i <= samples; i++)
        {
            float t = i / (float)samples;
            Vector3 current = EvalWorld(container, t);
            total += Vector3.Distance(previous, current);
            previous = current;
        }

        return total;
    }

    private static Vector3 EvalWorld(SplineContainer container, float t)
    {
        var local = SplineUtility.EvaluatePosition(container.Spline, Mathf.Clamp01(t));
        return container.transform.TransformPoint((Vector3)local);
    }

    private void Awake() => ws = GetComponent<LocalWebSocketClient>();

    public Task<bool> WaitForSplineSendAsync() => sendCompletedTcs.Task;


    public async Task SendAllSplines()
    {
        sendCompletedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

        // Begin Batch
        await ws.Send(JsonUtility.ToJson(new SimpleEvent {@event = "send-splines"}));

        foreach (var splineRecord in EnumerateSplines())
        {
            var payload = new SplineEvent { spline = splineRecord };
            var json = JsonUtility.ToJson(payload, true);
            await ws.Send(json);

            int knotCount = splineRecord.knotEntries != null ? splineRecord.knotEntries.Count : 0;
            Debug.Log($"[SplineRegistry] Sent spline '{splineRecord.name}' with {knotCount} knots.");

            await Task.Yield(); // avoid flooding in one frame
        }

        // Finish Batch
        await ws.Send(JsonUtility.ToJson(new SimpleEvent {@event = "finish-send-splines"}));
        sendCompletedTcs.TrySetResult(true);
    }

    private IEnumerable<SplineContainer> EnumerateSplineContainers()
    {
        var seen = new HashSet<SplineContainer>();

        if (registeredSplines != null && registeredSplines.Count > 0)
        {
            foreach (var container in registeredSplines)
            {
                if (container == null || container.Spline == null) continue;
                if (seen.Add(container)) yield return container;
            }
            yield break;
        }

        if (splineRoot != null)
        {
            foreach (var container in splineRoot.GetComponentsInChildren<SplineContainer>(includeInactive))
            {
                if (container == null || container.Spline == null) continue;
                if (seen.Add(container)) yield return container;
            }
        }

        if (additionalSplineRoots != null)
        {
            foreach (var root in additionalSplineRoots)
            {
                if (root == null) continue;

                foreach (var container in root.GetComponentsInChildren<SplineContainer>(includeInactive))
                {
                    if (container == null || container.Spline == null) continue;
                    if (seen.Add(container)) yield return container;
                }
            }
        }

        if (seen.Count == 0)
        {
            foreach (var container in FindObjectsOfType<SplineContainer>(includeInactive))
            {
                if (container == null || container.Spline == null) continue;
                if (seen.Add(container)) yield return container;
            }

            Debug.LogWarning("[SplineRegistry] No spline roots configured. Falling back to scene-wide spline search.");
        }
    }


    private IEnumerable<SplineRecord> EnumerateSplines()
    {
        IEnumerable<SplineContainer> containers =
            (registeredSplines != null && registeredSplines.Count > 0)
                ? registeredSplines
                : FindObjectsOfType<SplineContainer>(includeInactive);

        var seen = new HashSet<SplineContainer>();

        foreach (var container in EnumerateSplineContainers())
        {
            if (container == null || container.Spline == null) continue;
            if (!seen.Add(container)) continue;
            
            string splineName = container.gameObject.name;

            bool isMaster = container.gameObject.name == masterSplineName;
            bool isDeparture = container.gameObject.name == departureSplineName;

            List<KnotEntry> knotEntries = (isMaster || isDeparture) ? new List<KnotEntry>() : null;

            KnotPosition firstKnotPos = null;
            KnotPosition lastKnotPos = null;

            int knotIndex = 0;

            foreach (var knot in container.Spline.Knots)
            {
                Vector3 pos = container.transform.TransformPoint(knot.Position);

                if (isMaster || isDeparture) {
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

                if (knotIndex == 0) {
                    firstKnotPos = new KnotPosition {
                        x = pos.x,
                        y = pos.y,
                        z = pos.z
                    };
                }

                lastKnotPos = new KnotPosition {
                    x = pos.x,
                    y = pos.y,
                    z = pos.z
                };

                knotIndex++;
            }

            float lengthUnits = EstimateSplineLengthWorld(container);
            float lengthMeters = lengthUnits * Mathf.Max(0.0001f, metersPerUnityUnit);

            yield return new SplineRecord
            {
                name = splineName,
                closed = container.Spline.Closed,
                knotEntries = knotEntries,
                firstKnotPos = firstKnotPos,
                lastKnotPos = lastKnotPos,
                lengthUnits = lengthUnits,
                lengthMeters = lengthMeters,
            };
        }
    }
}
