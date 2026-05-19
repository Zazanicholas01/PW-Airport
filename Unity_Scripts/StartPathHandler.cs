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
    [SerializeField] private List<Transform> additionalSplineRoots = new();


    private Dictionary<string, SplineContainer> splineByName;

    private void Awake() {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();
        if (registry == null) registry = FindObjectOfType<GameObjectRegistry>();
        BuildSplineCache();
    }

    private void OnEnable() {
        if (dispatcher != null)
        {
            dispatcher.OnStartPathCommand += HandleStartPath;
            dispatcher.OnClearParkingCommand += HandleClearParking;
            dispatcher.OnContinuePathCommand += HandleContinuePath;
        } 
    }

    private void OnDisable() {
        if (dispatcher != null)
        {
            dispatcher.OnStartPathCommand -= HandleStartPath;
            dispatcher.OnClearParkingCommand -= HandleClearParking;
            dispatcher.OnContinuePathCommand -= HandleContinuePath;
        } 
    }

    public void RebuildSplineCache()
    {
        BuildSplineCache();
    }

    private void BuildSplineCache()
    {
        splineByName = new Dictionary<string, SplineContainer>(StringComparer.OrdinalIgnoreCase);
        var seen = new HashSet<SplineContainer>();

        void AddContainers(IEnumerable<SplineContainer> containers)
        {
            foreach (var container in containers)
            {
                if (container == null || container.gameObject == null || container.Spline == null)
                    continue;

                if (!seen.Add(container))
                    continue;

                string splineName = container.gameObject.name;
                if (string.IsNullOrWhiteSpace(splineName))
                    continue;

                splineByName[splineName] = container;
            }
        }

        if (splineRoot != null)
            AddContainers(splineRoot.GetComponentsInChildren<SplineContainer>(includeInactive));

        if (additionalSplineRoots != null)
        {
            foreach (var root in additionalSplineRoots)
            {
                if (root == null)
                    continue;

                AddContainers(root.GetComponentsInChildren<SplineContainer>(includeInactive));
            }
        }

        if (splineByName.Count == 0)
        {
            AddContainers(FindObjectsOfType<SplineContainer>(includeInactive));
            Debug.LogWarning("[StartPathHandler] No spline roots assigned. Falling back to scene-wide spline search.");
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

        var radarTarget = plane.GetComponentInChildren<RadarTarget>();
        if (radarTarget != null && !string.IsNullOrWhiteSpace(cmd.flight_id))
        {
            radarTarget.flightId = cmd.flight_id;
        }

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

    private void HandleContinuePath(MessageDispatcher.ContinuePathCommand cmd)
    {
        if (registry == null || !registry.TryGet(cmd.airplane_id, out var plane) || plane == null)
        {
            Debug.LogWarning($"[StartPathHandler] Plane not found for continue_path airplane_id={cmd.airplane_id}");
            return;
        }

        var follower = plane.GetComponent<SplineFollower>();
        if (follower == null)
        {
            Debug.LogWarning($"[StartPathHandler] Plane has no SplineFollower for continue_path airplane_id={cmd.airplane_id}");
            return;
        }

        Debug.Log($"[StartPathHandler] continue_path airplane_id={cmd.airplane_id} route_id={cmd.route_id} segments={cmd.segments.Length}");
        follower.SetContinuationPath(cmd.segments, cmd.route_id);
    }

    private void HandleClearParking(MessageDispatcher.ClearParkingCommand cmd)
    {
        if (registry == null || !registry.TryGet(cmd.airplane_id, out var plane) || plane == null)
        {
            Debug.LogWarning($"[StartPathHandler] Plane not found for clear_parking airplane_id={cmd.airplane_id}");
            return;
        }

        var follower = plane.GetComponent<SplineFollower>();

        if (follower == null)
        {
            Debug.LogWarning($"[StartPathHandler] Plane has no SplineFollower airplane_id={cmd.airplane_id}");
            return;
        }

        Debug.Log($"[StartPathHandler] clear_parking airplane_id={cmd.airplane_id}");
        follower.ClearParking();
    }

    private SplineContainer FindSpline(string name) {

        if (splineByName == null || splineByName.Count == 0) BuildSplineCache();
        if (string.IsNullOrWhiteSpace(name)) return null;

        return splineByName.TryGetValue(name, out var container) ? container : null;
    }
}
