using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Splines;

[RequireComponent(typeof(MessageDispatcher))]
public class StartVehiclePathHandler : MonoBehaviour
{
    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private VehicleRegistry vehicleRegistry;
    [SerializeField] private Transform splineRoot;
    [SerializeField] private List<Transform> additionalSplineRoots = new();
    [SerializeField] private bool includeInactive = true;

    private Dictionary<string, SplineContainer> splineByName;

    private void Awake()
    {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();

        if (vehicleRegistry == null)
            vehicleRegistry = FindObjectOfType<VehicleRegistry>();

        BuildSplineCache();
    }

    private void OnEnable()
    {
        if (dispatcher != null)
            dispatcher.OnStartVehiclePathCommand += HandleStartVehiclePath;
    }

    private void OnDisable()
    {
        if (dispatcher != null)
            dispatcher.OnStartVehiclePathCommand -= HandleStartVehiclePath;
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
            Debug.LogWarning("[StartVehiclePathHandler] No spline roots assigned. Falling back to scene-wide spline search.");
        }

        Debug.Log($"[StartVehiclePathHandler] Cached {splineByName.Count} splines.");
    }

    private void HandleStartVehiclePath(MessageDispatcher.StartVehiclePathCommand cmd)
    {
        if (vehicleRegistry == null)
        {
            Debug.LogWarning("[StartVehiclePathHandler] VehicleRegistry not found.");
            return;
        }

        if (!vehicleRegistry.TryGet(cmd.vehicle_id, out var vehicle) || vehicle == null)
        {
            Debug.LogWarning($"[StartVehiclePathHandler] Vehicle not found for vehicle_id={cmd.vehicle_id}");
            return;
        }

        var follower = vehicle.GetComponent<SplineFollower>();
        if (follower == null)
            follower = vehicle.AddComponent<SplineFollower>();

        follower.ResolveSplineByName = FindSpline;

        var reporter = vehicle.GetComponent<VehiclePathReporter>();
        if (reporter == null)
            reporter = vehicle.AddComponent<VehiclePathReporter>();

        reporter.Attach(follower, cmd.vehicle_id, cmd.direction);

        follower.SetPath(
            cmd.segments,
            cmd.vehicle_id,
            cmd.route_id
        );

        Debug.Log(
            $"[StartVehiclePathHandler] start_vehicle_path vehicle_id={cmd.vehicle_id} " +
            $"route_id={cmd.route_id} direction={cmd.direction} segments={cmd.segments.Length}"
        );
    }

    private SplineContainer FindSpline(string name)
    {
        if (splineByName == null || splineByName.Count == 0)
            BuildSplineCache();

        if (string.IsNullOrWhiteSpace(name))
            return null;

        return splineByName.TryGetValue(name, out var container) ? container : null;
    }
}
