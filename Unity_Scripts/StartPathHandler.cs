using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Splines;

[RequireComponent(typeof(MessageDispatcher))]
public class StartPathHandler : MonoBehaviour {

    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private GameObjectRegistry registry;
    [SerializeField] private Transform splineRoot;
    [SerializeField] private bool includeInactive = true;

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

    public void RebuildSplineCache()
    {
        BuildSplineCache();
    }

    private void BuildSplineCache() {
        splineByName = new Dictionary<string, SplineContainer>(StringComparer.OrdinalIgnoreCase);
        IEnumerable<SplineContainer> containers;

        if (splineRoot != null)
        {
            containers = splineRoot.GetComponentsInChildren<SplineContainer>(includeInactive);
        }
        else
        {
            containers = FindObjectsOfType<SplineContainer>(includeInactive);
            Debug.LogWarning("[StartPathHandler] splineRoot not assigned. Falling back to scene-wide spline search.");
        }

        foreach (var container in containers)
        {
            if (container == null || container.gameObject == null)
                continue;

            string splineName = container.gameObject.name;

            if (string.IsNullOrWhiteSpace(splineName))
                continue;

            splineByName[splineName] = container;
        }

        Debug.Log($"[StartPathHandler] Cached {splineByName.Count} splines.");
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
        if (reporter == null) 
            reporter = plane.AddComponent<PathCompletionReporter>();
        reporter.Attach(follower);

        follower.SetPath(
            cmd.segments,
            cmd.airplane_id, 
            cmd.route_id
        );
    }

    private SplineContainer FindSpline(string name) {

        if (splineByName == null || splineByName.Count == 0) BuildSplineCache();
        if (string.IsNullOrWhiteSpace(name)) return null;

        return splineByName.TryGetValue(name, out var container) ? container : null;
    }
}
