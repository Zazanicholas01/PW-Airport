using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Splines;

[RequireComponent(typeof(MessageDispatcher))]
public class StartPathHandler : MonoBehaviour {
    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private GameObjectRegistry registry;

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

        var follower = plane.GetComponent<SplineFollower>();
        if (follower == null) follower = plane.AddComponent<SplineFollower>();

        follower.ResolveSplineByName = FindSpline;

        var reporter = plane.GetComponent<PathCompletionReporter>();
        if (reporter == null) reporter = plane.AddComponent<PathCompletionReporter>();
        reporter.Attach(follower);

        var speed = cmd.speed > 0f ? cmd.speed : 5f;
        follower.SetPath(cmd.segments, speed, cmd.airplane_id, cmd.route_id);
    }

    private SplineContainer FindSpline(string name) {

        if (splineByName == null || splineByName.Count == 0) BuildSplineCache();
        if (string.IsNullOrWhiteSpace(name)) return null;

        return splineByName.TryGetValue(name, out var container) ? container : null;
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

    private static Vector3 EvalWorld(SplineContainer container, float t)
    {
        if (container == null || container.Spline == null) return Vector3.zero;
        var local = SplineUtility.EvaluatePosition(container.Spline, t);
        return container.transform.TransformPoint((Vector3)local);
    }
}
