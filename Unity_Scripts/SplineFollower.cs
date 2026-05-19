using System;
using System.Diagnostics;
using UnityEngine;
using UnityEngine.Splines;

public class SplineFollower : MonoBehaviour {

    [SerializeField] private SimClockClient clock;
    [SerializeField] private bool orientToSpline = true;
    [SerializeField] private Vector3 up = default;
    [SerializeField] private int arcSamples = 200;

    public event Action<string, int> OnPathCompleted;
    public event Action<string, int> OnPlaneLeftStand;
    public event Action<string, int, string> OnParkingEntered;
    
    private bool parkingEnteredReported;
    private bool standLeftReported;

    private const string MasterSplineName = "MasterSpline";
    private const string DepartureSplineName = "Spline_Departure";

    private string airplaneId;
    private int routeId;

    private MessageDispatcher.PathSegment[] segments;


    private const float KmhToMs = 1000f / 3600f;
    private float currentSpeedMps;
    private float targetSpeedMps;
    private float accelerationMps2;
    private float decelerationMps2;
    private string currentSpeedPurpose;

    private bool holding;
    private float holdRemainingSeconds;
    private bool advanceAfterHold;

    private int segIndex = -1;
    private SplineContainer currentContainer;
    private ArcLengthTable currentTable;
    private float traveled;
    private bool running;
    private bool currentSegmentReversed;
    private bool currentSegmentRotationReversed;

    private bool parkingCleared;
    private bool currentSegmentIsParkingLoop;
    private float currentParkingExitT;

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

    public void SetPath(
        MessageDispatcher.PathSegment[] newSegments,
        string newAirplaneId, 
        int newRouteId
    ) {
        
        airplaneId = newAirplaneId;
        routeId = newRouteId;
        segments = newSegments;

        currentSpeedMps = 0f;
        targetSpeedMps = 0f;
        accelerationMps2 = 0.5f;
        decelerationMps2 = 0.5f;
        currentSpeedPurpose = null;

        segIndex = -1;
        currentContainer = null;
        traveled = 0f;

        running = segments != null && segments.Length > 0;

        hasPrevEnd = false;
        prevSplineName = null;
        prevEndT = 0f;
        hasLastSim = false;
        standLeftReported = false;

        holding = false;
        holdRemainingSeconds = 0f;
        advanceAfterHold = false;

        parkingCleared = false;
        currentSegmentIsParkingLoop = false;
        currentParkingExitT = 0f;
        parkingEnteredReported = false;

        if (running)
        {
            if (!BeginSegment(0))
            {
                Stop();
                return;
            }

            hasLastSim = false;
        }
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
        standLeftReported = false;

        airplaneId = null;
        routeId = 0; 

        holding = false;
        holdRemainingSeconds = 0f;
        advanceAfterHold = false;  

        parkingCleared = false;
        currentSegmentIsParkingLoop = false;
        currentParkingExitT = 0f;
        parkingEnteredReported = false;
    }

    public Func<string, SplineContainer> ResolveSplineByName { get; set; }

    private void UpdateSpeed(float dt)
    {
        float rate = currentSpeedMps < targetSpeedMps
            ? accelerationMps2
            : decelerationMps2;
        
        currentSpeedMps = Mathf.MoveTowards(
            currentSpeedMps,
            targetSpeedMps,
            rate * dt 
        );
    }

    public void ClearParking()
    {
        parkingCleared = true;

        if (running && currentSegmentIsParkingLoop && currentContainer != null)
        {
            if (TryRebuildParkingLoopToExit())
                hasLastSim = false;
        }
    }

    private void Update() {

        if (!running) return;

        if (holding)
        {
            holdRemainingSeconds -= Time.deltaTime;

            if (holdRemainingSeconds > 0f)
                return;
            
            holding = false;

            if (advanceAfterHold)
            {
                advanceAfterHold = false;
                int next = segIndex + 1;

                if (segments == null || next >= segments.Length)
                {
                    var doneAirplaneId = airplaneId;
                    var doneRouteId = routeId;
                    Stop();
                    OnPathCompleted?.Invoke(doneAirplaneId, doneRouteId);
                    return;
                }

                if (!BeginSegment(next))
                {
                    Stop();
                    return;
                }

                hasLastSim = false;
                return;
            }
        }

        float dt = GetSimDeltaSeconds();

        if (dt <= 0f) return;

        if (segIndex < 0 || currentContainer == null || currentTable.Equals(default(ArcLengthTable))) {

            if (!BeginSegment(0)) { Stop(); return; }

        }

        float remainingDt = dt;
        while (remainingDt > 0f && running) {

            UpdateSpeed(remainingDt);

            float stepDistMeters = currentSpeedMps * remainingDt;
            float remainingDistMeters = currentTable.Length - traveled;

            if (stepDistMeters < remainingDistMeters) {
                traveled += stepDistMeters;

                ApplyPose(currentContainer, currentTable.EvaluateT(traveled));
                remainingDt = 0f;
            } else {
                traveled = currentTable.Length;

                ApplyPose(currentContainer, currentTable.EvaluateT(traveled));

                if (segments[segIndex].loop_until_cleared)
                {
                    if (!parkingCleared || !HasNextSegment())
                    {
                        float currentT = currentTable.EvaluateT(traveled);

                        if (parkingCleared)
                        {
                            UnityEngine.Debug.LogWarning(
                                $"[SplineFollower] Parking cleared but continuation not ready airplane={airplaneId} " +
                                $"route={routeId} segment={segments[segIndex].name} segIndex={segIndex} currentT={Wrap01(currentT):0.000}"
                            );
                        }

                        currentTable = BuildArcLengthTable(
                            currentContainer,
                            currentT,
                            currentT + 1f,
                            arcSamples
                        );

                        traveled = 0f;
                        hasLastSim = false;
                        return;
                    }
                    currentSegmentIsParkingLoop = false;
                }

                prevSplineName = segments[segIndex].name;
                prevEndT = Mathf.Clamp01(segments[segIndex].t_end);
                hasPrevEnd = true;

                float holdSeconds = Mathf.Max(0f, segments[segIndex].hold_seconds);

                if (holdSeconds > 0f)
                {
                    holding = true;
                    advanceAfterHold = true;
                    holdRemainingSeconds = holdSeconds;
                    currentSpeedMps = 0f;

                    // Prevent GetSimDeltaSeconds from accumulating during hold
                    hasLastSim = false;

                    return;
                }

                float usedDt = remainingDistMeters / Mathf.Max(0.0001f, currentSpeedMps);
                remainingDt = Mathf.Max(0f, remainingDt - usedDt);

                int next = segIndex + 1;

                if (segments == null || next >= segments.Length) {
                    var doneAirplaneId = airplaneId;
                    var doneRouteId = routeId;
                    Stop();
                    OnPathCompleted?.Invoke(doneAirplaneId, doneRouteId);
                    return;
                }

                if (!standLeftReported &&
                    string.Equals(segments[segIndex].name, MasterSplineName, StringComparison.OrdinalIgnoreCase) &&
                    string.Equals(segments[next].name, DepartureSplineName, StringComparison.OrdinalIgnoreCase)
                ) {
                    standLeftReported = true;
                    OnPlaneLeftStand?.Invoke(airplaneId, routeId);
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

    private static bool IsDeparturePath(MessageDispatcher.PathSegment[] pathSegments)
    {
        if (pathSegments == null) return false;

        foreach (var segment in pathSegments)
        {
            if (string.Equals(segment.name, DepartureSplineName, StringComparison.OrdinalIgnoreCase))
                return true;
        }

        return false;
    }

    private bool BeginSegment(int index) {

        if (segments == null || index < 0 || index >= segments.Length) return false;
        if (ResolveSplineByName == null) return false;

        var seg = segments[index];
        var container = ResolveSplineByName(seg.name);
        if (container == null || container.Spline == null) return false;

        float t0 = Mathf.Clamp01(seg.t_start);
        float t1 = Mathf.Clamp01(seg.t_end);

        if (seg.auto_start_from_previous_end && hasPrevEnd)
        {
            t0 = FindClosestT(container, transform.position);
        }

        currentSegmentIsParkingLoop = seg.loop_until_cleared;

        if (currentSegmentIsParkingLoop)
        {
            currentSegmentReversed = false;
            currentSegmentRotationReversed = false;

            currentContainer = container;
            segIndex = index;

            float loopEndT = t0 + 1f;
            currentTable = BuildArcLengthTable(container, t0, loopEndT, arcSamples);

            traveled = 0f;

            ApplySpeedProfileForSegment(seg);
            ApplyPose(container, t0);

            if (!parkingEnteredReported)
            {
                parkingEnteredReported = true;
                OnParkingEntered?.Invoke(airplaneId, routeId, seg.name);
            }

            if (parkingCleared)
            {
                if (TryRebuildParkingLoopToExit())
                    hasLastSim = false;
            }

            return true;
        }

        currentSegmentReversed = t1 < t0;
        currentSegmentRotationReversed = currentSegmentReversed || (index == 0 && IsDeparturePath(segments));

        bool sameSplineAsPrev = index > 0 && string.Equals(segments[index - 1].name, seg.name, StringComparison.OrdinalIgnoreCase);

        if (hasPrevEnd && string.Equals(prevSplineName, seg.name, StringComparison.OrdinalIgnoreCase)) {
            if (t1 >= t0 && t0 < prevEndT) t0 = prevEndT;
            if (t1 <= t0 && t0 > prevEndT) t0 = prevEndT;
        }

        currentContainer = container;
        currentTable = BuildArcLengthTable(container, t0, t1, arcSamples);

        traveled = 0f;
        segIndex = index;

        ApplySpeedProfileForSegment(seg);

        if (index == 0 || !sameSplineAsPrev)
            ApplyPose(container, t0);
        
        return true;
    }

    private void ApplySpeedProfileForSegment(MessageDispatcher.PathSegment segment)
    {
        var profile = segment.speed_profile;

        if (profile == null)
        {
            targetSpeedMps = 12f * KmhToMs;
            accelerationMps2 = 0.4f;
            decelerationMps2 = 0.4f;
            currentSpeedPurpose = "fallback";
            return;
        }

        float desiredInitialMps = Mathf.Max(0f, profile.initial_speed_kmh) * KmhToMs;

        if (segIndex == 0 || string.Equals(profile.purpose, "departure_roll", StringComparison.OrdinalIgnoreCase))
            currentSpeedMps = desiredInitialMps;
        
        targetSpeedMps = Mathf.Max(0f, profile.target_speed_kmh) * KmhToMs;
        accelerationMps2 = Mathf.Max(0.01f, profile.acceleration_mps2);
        decelerationMps2 = Mathf.Max(0.01f, profile.deceleration_mps2);
        currentSpeedPurpose = profile.purpose;
    }

    private void ApplyPose(SplineContainer container, float t) {

        float evalT = container.Spline.Closed ? Wrap01(t) : Mathf.Clamp01(t);
        transform.position = EvalWorld(container, evalT);

        if (!orientToSpline) return;

        var tanLocal = SplineUtility.EvaluateTangent(container.Spline, evalT);
        Vector3 tanWorld = container.transform.TransformDirection((Vector3)tanLocal);

        if (currentSegmentRotationReversed)
            tanWorld = -tanWorld;

        if (tanWorld.sqrMagnitude > 1e-6f)
            transform.rotation = Quaternion.LookRotation(tanWorld.normalized, up);
    }

    private float FindClosestT(SplineContainer container, Vector3 worldPoint, int samples = 240)
    {
        float bestT = 0f;
        float bestDist = float.PositiveInfinity;

        for (int i = 0; i <= samples; i++)
        {
            float t = i / (float)samples;
            float d = (EvalWorld(container, t) - worldPoint).sqrMagnitude;

            if (d < bestDist)
            {
                bestDist = d;
                bestT = t;
            }
        }

        return bestT;
    }

    private float ForwardLoopEndT(float startT, float targetT)
    {
        float start = Wrap01(startT);
        float target = Wrap01(targetT);
        float delta = target - start;

        if (delta <= 0f)
            delta += 1f;

        if (delta < 0.01f)
            delta += 1f;

        return startT + delta;
    }

    private bool HasNextSegment()
    {
        return segments != null && segIndex >= 0 && segIndex + 1 < segments.Length;
    }

    private float ResolveExitTFromNextSegment()
    {
        int next = segIndex + 1;

        if (segments == null || next >= segments.Length || ResolveSplineByName == null)
        {
            UnityEngine.Debug.LogWarning(
                $"[SplineFollower] Parking exit fallback: no next segment airplane={airplaneId} " +
                $"route={routeId} segIndex={segIndex}"
            );
            return Wrap01(currentTable.EvaluateT(traveled));
        }

        var nextSegment = segments[next];
        var nextContainer = ResolveSplineByName(nextSegment.name);

        if (nextContainer == null || nextContainer.Spline == null)
        {
            UnityEngine.Debug.LogWarning(
                $"[SplineFollower] Parking exit fallback: next spline missing airplane={airplaneId} " +
                $"route={routeId} nextSegment={nextSegment.name}"
            );
            return Wrap01(currentTable.EvaluateT(traveled));
        }

        Vector3 nextStartWorld = EvalWorld(nextContainer, nextSegment.t_start);
        float resolvedT = FindClosestT(currentContainer, nextStartWorld);

        return resolvedT;
    }

    private void RebuildParkingLoopToExit()
    {
        float currentT = currentTable.EvaluateT(traveled);
        currentParkingExitT = ResolveExitTFromNextSegment();

        float exitEndT = ForwardLoopEndT(currentT, currentParkingExitT);

        currentTable = BuildArcLengthTable(currentContainer, currentT, exitEndT, arcSamples);
        traveled = 0f;
    }

    private bool TryRebuildParkingLoopToExit()
    {
        if (!HasNextSegment())
        {
            UnityEngine.Debug.LogWarning(
                $"[SplineFollower] Parking exit delayed: continuation missing airplane={airplaneId} " +
                $"route={routeId} segIndex={segIndex} totalSegments={(segments != null ? segments.Length : 0)}"
            );
            return false;
        }

        RebuildParkingLoopToExit();
        return true;
    }


    private static float Wrap01(float t)
    {
        t %= 1f;
        return t < 0f ? t + 1f : t;
    }

    public void SetContinuationPath(MessageDispatcher.PathSegment[] continuationSegments, int newRouteId)
    {
        if (continuationSegments == null || continuationSegments.Length == 0)
        {
            UnityEngine.Debug.LogWarning($"[SplineFollower] Empty continuation ignored airplane={airplaneId} route={routeId}");
            return;
        }

        if (!running || segments == null || segIndex < 0)
        {
            SetPath(continuationSegments, airplaneId, newRouteId);
            return;
        }

        int prefixCount = segIndex + 1;
        var merged = new MessageDispatcher.PathSegment[prefixCount + continuationSegments.Length];

        for (int i = 0; i < prefixCount; i++)
            merged[i] = segments[i];

        for (int i = 0; i < continuationSegments.Length; i++)
            merged[prefixCount + i] = continuationSegments[i];

        segments = merged;
        routeId = newRouteId;

        if (currentSegmentIsParkingLoop && parkingCleared)
            TryRebuildParkingLoopToExit();
    }

    private static Vector3 EvalWorld(SplineContainer container, float t)
    {
        float evalT = container.Spline.Closed ? Wrap01(t) : Mathf.Clamp01(t);
        var local = SplineUtility.EvaluatePosition(container.Spline, evalT);
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
