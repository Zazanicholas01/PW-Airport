using System;
using UnityEngine;
using UnityEngine.Splines;

public class SplineFollower : MonoBehaviour {

    [SerializeField] private SimClockClient clock;
    [SerializeField] private bool orientToSpline = true;
    [SerializeField] private Vector3 up = default;
    [SerializeField] private int arcSamples = 200;

    public event Action<string, int> OnPathCompleted;
    private string airplaneId;
    private int routeId;

    private MessageDispatcher.PathSegment[] segments;
    private float speed;

    private int segIndex = -1;
    private SplineContainer currentContainer;
    private ArcLengthTable currentTable;
    private float traveled;
    private bool running;

    private double lastSimMs;
    private bool hasLastSim;

    private string prevSplineName;
    private float prevEndT;
    private bool hasPrevEnd;

    private void Awake()
    {
        if (clock == null) clock = FindObjectOfType<SimClockClient>();
        if (up == default) up = Vector3.up;
    }

    public void SetPath(MessageDispatcher.PathSegment[] newSegments, float newSpeed, string newAirplaneId, int newRouteId) {
        
        airplaneId = newAirplaneId;
        routeId = newRouteId;
        
        segments = newSegments;
        speed = Mathf.Max(0f, newSpeed);
        segIndex = -1;
        currentContainer = null;
        traveled = 0f;
        running = segments != null && segments.Length > 0 && speed > 0f;
        hasPrevEnd = false;
        prevSplineName = null;
        prevEndT = 0f;
        hasLastSim = false;
    }

    public void Stop() {
        running = false;
        segments = null;
        segIndex = -1;
        currentContainer = null;
        traveled = 0f;
        hasPrevEnd = false;
        prevSplineName = null;
        prevEndT = 0f;
        hasLastSim = false;

        airplaneId = null;
        routeId = 0;     
    }

    public Func<string, SplineContainer> ResolveSplineByName { get; set; }

    private void Update() {

        if (!running) return;

        float dt = GetSimDeltaSeconds();
        if (dt <= 0f) return;

        if (segIndex < 0 || currentContainer == null || currentTable.Equals(default(ArcLengthTable))) {

            if (!BeginSegment(0)) { Stop(); return; }

        }

        float reaminingDt = dt;
        while (reaminingDt > 0f && running) {

            float stepDist = speed * reaminingDt;
            float reaminingDist = currentTable.Length - traveled;

            if (stepDist < reaminingDist) {
                traveled += stepDist;
                ApplyPose(currentContainer, currentTable.EvaluateT(traveled));
                reaminingDt = 0f;
            } else {

                traveled = currentTable.Length;
                ApplyPose(currentContainer, currentTable.EvaluateT(traveled));

                prevSplineName = segments[segIndex].name;
                prevEndT = Mathf.Clamp01(segments[segIndex].t_end);
                hasPrevEnd = true;

                float usedDt = reaminingDist / Mathf.Max(0.0001f, speed);
                reaminingDt = Mathf.Max(0f, reaminingDt - usedDt);

                int next = segIndex + 1;

                if (segments == null || next >= segments.Length) {
                    var doneAirplaneId = airplaneId;
                    var doneRouteId = routeId;
                    Stop();
                    OnPathCompleted?.Invoke(doneAirplaneId, doneRouteId);
                    return;
                }

                if (!BeginSegment(next)) {
                    Stop();
                    return;
                }
            }
        }
    }

    private float GetSimDeltaSeconds() {

        if (clock == null)
            return Time.deltaTime;
        
        double now = clock.SimNowUnixMs;
        if (!hasLastSim) {
            lastSimMs = now;
            hasLastSim = true;
            return 0f;
        }

        double dtMs = now - lastSimMs;
        lastSimMs = now;

        if (dtMs <= 0) return 0f;
        return (float)(dtMs / 1000.0);
    }

    private bool BeginSegment(int index) {

        if (segments == null || index < 0 || index >= segments.Length) return false;
        if (ResolveSplineByName == null) return false;

        var seg = segments[index];
        var container = ResolveSplineByName(seg.name);
        if (container == null || container.Spline == null) return false;

        float t0 = Mathf.Clamp01(seg.t_start);
        float t1 = Mathf.Clamp01(seg.t_end);

        bool sameSplineAsPrev = index > 0 && string.Equals(segments[index - 1].name, seg.name, StringComparison.OrdinalIgnoreCase);

        if (hasPrevEnd && string.Equals(prevSplineName, seg.name, StringComparison.OrdinalIgnoreCase)) {
            if (t1 >= t0 && t0 < prevEndT) t0 = prevEndT;
            if (t1 <= t0 && t0 > prevEndT) t0 = prevEndT;
        }

        currentContainer = container;
        currentTable = BuildArcLengthTable(container, t0, t1, arcSamples);
        traveled = 0f;
        segIndex = index;

        if (index == 0 || !sameSplineAsPrev)
            ApplyPose(container, t0);
        
        return true;
    }

    private void ApplyPose(SplineContainer container, float t) {

        transform.position = EvalWorld(container, t);

        if (!orientToSpline) return;

        var tanLocal = SplineUtility.EvaluateTangent(container.Spline, t);
        Vector3 tanWorld = container.transform.TransformDirection((Vector3)tanLocal);
        if (tanWorld.sqrMagnitude > 1e-6f)
            transform.rotation = Quaternion.LookRotation(tanWorld.normalized, up);
    }

    private static Vector3 EvalWorld(SplineContainer container, float t)
    {
        var local = SplineUtility.EvaluatePosition(container.Spline, t);
        return container.transform.TransformPoint((Vector3)local);
    }

    private readonly struct ArcLengthTable
    {
        public readonly float[] Dist;
        public readonly float[] T;
        public float Length => Dist[^1];

        public ArcLengthTable(float[] dist, float[] t)
        {
            Dist = dist;
            T = t;
        }

        public float EvaluateT(float distance)
        {
            if (distance <= 0f) return T[0];
            float length = Length;
            if (distance >= length) return T[^1];

            int lo = 0, hi = Dist.Length - 1;
            while (lo + 1 < hi)
            {
                int mid = (lo + hi) >> 1;
                if (Dist[mid] < distance) lo = mid; else hi = mid;
            }

            float s0 = Dist[lo], s1 = Dist[hi];
            float t0 = T[lo], t1 = T[hi];
            float a = Mathf.InverseLerp(s0, s1, distance);
            return Mathf.LerpUnclamped(t0, t1, a);
        }
    }

    private static ArcLengthTable BuildArcLengthTable(SplineContainer container, float t0, float t1, int samples)
    {
        samples = Mathf.Max(8, samples);

        float[] dist = new float[samples + 1];
        float[] ts = new float[samples + 1];

        Vector3 prev = EvalWorld(container, t0);
        dist[0] = 0f;
        ts[0] = t0;

        for (int i = 1; i <= samples; i++)
        {
            float u = i / (float)samples;
            float t = Mathf.LerpUnclamped(t0, t1, u);
            Vector3 p = EvalWorld(container, t);
            dist[i] = dist[i - 1] + Vector3.Distance(prev, p);
            ts[i] = t;
            prev = p;
        }

        return new ArcLengthTable(dist, ts);
    }
}