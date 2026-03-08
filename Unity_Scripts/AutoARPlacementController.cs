using System.Collections;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

public class AutoARPlacementController : MonoBehaviour {

    [Header("Scene References")]
    [SerializeField] private ARPlaneManager planeManager;
    [SerializeField] private ARAnchorManager anchorManager;
    [SerializeField] private Camera arCamera;
    [SerializeField] private Transform airportRoot;

    [Header("Placement Rules")]
    [SerializeField] private float minPlaneArea = 0.15f;
    [SerializeField] private float stabilizationTime = 1.0f;
    [SerializeField] private float airportScale = 0.01f;
    [SerializeField] private bool disablePlaneVisualizationAfterPlacement = true;

    [Header("Optional Debug")]
    [SerializeField] private bool logDebug = true;

    public UnityEvent OnPlacementStarted;
    public UnityEvent OnPlacementCompleted;
    public UnityEvent OnPlacementReset;

    private ARPlane candidatePlane;
    private float candidateStableSince = -1f;
    private ARAnchor currentAnchor;
    private bool placed;

    public bool IsPlaced => placed;
    public ARAnchor CurrentAnchor => currentAnchor;

    private void Awake()
    {
        if (planeManager == null)
            planeManager = FindObjectOfType<ARPlaneManager>();

        if (anchorManager == null)
            anchorManager = FindObjectOfType<ARAnchorManager>();

        if (arCamera == null)
            arCamera = Camera.main;

        if (airportRoot != null)
            airportRoot.gameObject.SetActive(false);
    }

    private void Update() {

        if (placed || planeManager == null || anchorManager == null || arCamera == null || airportRoot == null)
            return;

        var bestPlane = FindBestPlane();
        if (bestPlane == null)
        {
            candidatePlane = null;
            candidateStableSince = -1f;
            return;
        }

        if (candidatePlane != bestPlane)
        {
            candidatePlane = bestPlane;
            candidateStableSince = Time.time;

            if (logDebug)
                Debug.Log($"[AutoARPlacement] New candidate plane: {candidatePlane.trackableId}");
        }

        if (Time.time - candidateStableSince >= stabilizationTime)
        {
            StartCoroutine(PlaceOnPlane(candidatePlane));
        }
    }

    private ARPlane FindBestPlane()
    {
        ARPlane best = null;
        float bestArea = 0f;

        foreach (var plane in planeManager.trackables)
        {
            if (!IsPlaneValid(plane))
                continue;

            float area = GetPlaneArea(plane);
            if (area > bestArea)
            {
                best = plane;
                bestArea = area;
            }
        }

        return best;
    }

    private bool IsPlaneValid(ARPlane plane)
    {
        if (plane == null)
            return false;

        if (plane.trackingState != TrackingState.Tracking)
            return false;

        if (plane.alignment != PlaneAlignment.HorizontalUp)
            return false;

        if (plane.subsumedBy != null)
            return false;

        if (GetPlaneArea(plane) < minPlaneArea)
            return false;

        return true;
    }

    private float GetPlaneArea(ARPlane plane)
    {
        Vector2 size = plane.size;
        return size.x * size.y;
    }

    private IEnumerator PlaceOnPlane(ARPlane plane) {
        if (placed || plane == null)
            yield break;

        placed = true;
        OnPlacementStarted?.Invoke();

        Pose pose = GetPlacementPose(plane);
        ARAnchor anchor = anchorManager.AttachAnchor(plane, pose);

        if (anchor == null)
        {
            if (logDebug)
                Debug.LogWarning("[AutoARPlacement] AttachAnchor failed, trying plain AddComponent fallback.");

            GameObject anchorObject = new GameObject("AirportAnchor");
            anchorObject.transform.SetPositionAndRotation(pose.position, pose.rotation);
            anchor = anchorObject.AddComponent<ARAnchor>();
        }

        currentAnchor = anchor;

        airportRoot.SetParent(currentAnchor.transform, worldPositionStays: false);
        airportRoot.localPosition = Vector3.zero;
        airportRoot.localRotation = Quaternion.identity;
        airportRoot.localScale = Vector3.one * airportScale;
        airportRoot.gameObject.SetActive(true);

        if (disablePlaneVisualizationAfterPlacement)
            SetPlaneVisualization(false);
        
        if (logDebug)
            Debug.Log("[AutoARPlacement] Airport placed successfully.");

        OnPlacementCompleted?.Invoke();
        yield return null;
    }

    private Pose GetPlacementPose(ARPlane plane) {

        Vector3 position = plane.center;

        Vector3 cameraForward = arCamera.transform.forward;
        Vector3 flatForward = Vector3.ProjectOnPlane(cameraForward, Vector3.up).normalized;

        if (flatForward.sqrMagnitude < 0.001f)
            flatForward = Vector3.forward;

        Quaternion rotation = Quaternion.LookRotation(flatForward, Vector3.up);
        return new Pose(position, rotation);
    }

    public void ResetPlacement() {

        StopAllCoroutines();

        if (airportRoot != null)
        {
            airportRoot.SetParent(null, true);
            airportRoot.gameObject.SetActive(false);
        }

        if (currentAnchor != null)
        {
            Destroy(currentAnchor.gameObject);
            currentAnchor = null;
        }

        placed = false;
        candidatePlane = null;
        candidateStableSince = -1f;

        SetPlaneVisualization(true);

        if (logDebug)
            Debug.Log("[AutoARPlacement] Placement reset.");

        OnPlacementReset?.Invoke();
    }

    private void SetPlaneVisualization(bool enabled) {

        if (planeManager == null)
            return;
        
        foreach (var plane in planeManager.trackables)
        {
            plane.gameObject.SetActive(enabled);
        }

        planeManager.enabled = enabled;
    }
}