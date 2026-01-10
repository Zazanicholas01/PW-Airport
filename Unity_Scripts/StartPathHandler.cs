using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Splines;

[RequireComponent(typeof(MessageDispatcher))]
public class StartPathHandler : MonoBehaviour {
    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private GameObjectRegistry registry;

    private readonly Dictionary<string, Coroutine> runningByPlaneId = new(StringComparer.OrdinalIgnoreCase);
    private Dictionary<string, SplineContainer> splineByName;

    private void Awake() {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();
        if (registry == null) registry = FindObjectOfType<GameObjectRegistry>();
        BuildSplineCache();
    }

    private void OnEnable() {
        if (dispatcher != null) dispatcher.OnStartPathCommand += HandleStartPath;
    }

    private void OnDisable() {
        if (dispatcher != null) dispatcher.OnStartPathCommand -= HandleStartPath;
    }

    private void BuildSplineCache() {
        splineByName = new Dictionary<string, SplineContainer>(StringComparer.OrdinalIgnoreCase);
        foreach (var c in FindObjectsOfType<SplineContainer>(includeInactive: true)) {
            if (c != null && c.gameObject != null)
                splineByName[c.gameObject.name] = c;
        }
    }

    private void HandleStartPath(MessageDispatcher.StartPathCommand cmd) {

        if (registry == null || !registry.TryGet(cmd.airplane_id, out var plane) || plane == null) {
            Debug.LogWarning($"[StartPathHandler] Plane not found for airplane_id={cmd.airplane_id}");
            return;
        }

        if (runningByPlaneId.TryGetValue(cmd.airplane_id, out var existing) && existing != null) {
            StopCoroutine(existing);
        }

        var speed = cmd.speed > 0f ? cmd.speed : 5f;
        runningByPlaneId[cmd.airplane_id] = StartCoroutine(FollowSegments(plane.transform, cmd.segments, speed));
    }

    private SplineContainer FindSpline(string name) {

        if (splineByName == null || splineByName.Count == 0) BuildSplineCache();
        if (string.IsNullOrWhiteSpace(name)) return null;

        return splineByName.TryGetValue(name, out var container) ? container : null;
    }

    private IEnumerator FollowSegments(Transform target, MessageDispatcher.PathSegment[] segments, float speed) {

        foreach (var seg in segments) {

            var container = FindSpline(seg.name);
            if (container == null || container.Spline == null) {
                Debug.LogWarning($"[StartPathHandler] Missing spline '{seg.name}'");
                continue;
            }

            float t0 = Mathf.Clamp01(seg.t_start);
            float t1 = Mathf.Clamp01(seg.t_end);
            float dir = t1 >= t0 ? 1f : -1f;
            float range = Mathf.Abs(t1 - t0);

            if (range <= 0.0001f) {
                target.position = EvalWorld(container, t1);
                continue;
            }

            float length = ApproxSegmentLength(container, t0, t1, 30);
            if (length <= 0.0001f) length = 0.0001f;

            float t = t0;
            target.position = EvalWorld(container, t);

            while ((dir > 0f && t < t1) || (dir < 0f && t > t1)) {

                float ft = Time.deltaTime;
                float deltaT = (speed * dt / length) * range;
                t = Mathf.Clamp01(t + dir * deltaT);

                if (dir > 0f && t > t1) t = t1;
                if (dir < 0f && t < t1) t = t1;

                target.position = EvalWorld(container, t);
                yield return null;
            }
        }
    }

    private static Vector3 EvalWorld(SplineContainer container, float t) {
        var local = SplineUtility.EvaluatePosition(container.Spline, t);
        return container.transform.TransformPoint((Vector3)local);
    }

    private static float ApproxSegmentLength(SplineContainer container, float t0, float t1, int samples) {

        samples = Mathf.Max(2, samples);
        float dir = t1 >= t0 ? 1f : -1f;
        float a = t0, b = t1;

        Vector3 prev = EvalWorld(container, a);
        float total = 0f;

        for (int i = 1; i <= samples; i++) {
            float u = i / (float)samples;
            float t = a + (b - a) * u;
            Vector3 p = EvalWorld(container, t);
            total += Vector3.Distance(prev, p);
            prev = p;
        }

        return total;
    }
}