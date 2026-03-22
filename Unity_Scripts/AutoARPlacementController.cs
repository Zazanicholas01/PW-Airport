using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Events;
using UnityEngine.InputSystem;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;
using System.Threading.Tasks.Dataflow;

public class AutoARPlacementController : MonoBehaviour
{
    [Header("Scene References")]
    [SerializeField] private ARPlaneManager planeManager;
    [SerializeField] private ARAnchorManager anchorManager;
    [SerializeField] private ARRaycastManager raycastManager;
    [SerializeField] private Camera arCamera;
    [SerializeField] private Transform airportRoot;

    [Header("Placement Rules")]
    [SerializeField] private float minPlaneArea = 0.5f;
    [SerializeField] private float airportScale = 0.05f;
    [SerializeField] private float placementHeightOffset = 0.2f;
    [SerializeField] private bool disablePlaneVisualizationAfterPlacement = false;
    [SerializeField] private bool keepPlaneTrackingAfterPlacement = true;
    [SerializeField] private bool spawnDebugMarker = false;

    [Header("Editor Debug")]
    [SerializeField] private Transform debugPlacementPose;
    [SerializeField] private GameObject debugSimulationButton;
    [SerializeField] private bool enableDebugSimulationInEditor = true;

    [Header("Optional Debug")]
    [SerializeField] private bool logDebug = true;

    public UnityEvent OnPlacementStarted;
    public UnityEvent OnPlacementCompleted;
    public UnityEvent OnPlacementReset;

    private ARAnchor currentAnchor;
    private TransformBlock fallbackAnchor;
    private bool placed;
    private bool placementPromptLogged;

    private static readonly List<ARRaycastHit> RaycastHits = new();

    public bool IsPlaced => placed;
    public ARAnchor CurrentAnchor => currentAnchor;

    private void Awake()
    {
        if (planeManager == null)
            planeManager = FindObjectOfType<ARPlaneManager>();

        if (anchorManager == null)
            anchorManager = FindObjectOfType<ARAnchorManager>();

        if (raycastManager == null)
            raycastManager = FindObjectOfType<ARRaycastManager>();

        if (arCamera == null)
            arCamera = Camera.main;

        if (logDebug && airportRoot != null)
            Debug.Log($"[AutoARPlacement] airportRoot assigned to: {airportRoot.name}");

        if (airportRoot != null)
            airportRoot.gameObject.SetActive(false);

        bool showDebugButton = enableDebugSimulationInEditor && ApplicationException.isEditor;
        if (debugSimulationButton != null)
            debugSimulationButton.SetActive(showDebugButton);
    }

    private void Update()
    {
        if (placed || planeManager == null || anchorManager == null || raycastManager == null || arCamera == null || airportRoot == null)
            return;

        if (!HasAnyValidPlane())
            return;

        if (!placementPromptLogged && logDebug)
        {
            placementPromptLogged = true;
            Debug.Log("[AutoARPlacement] Valid plane detected. Tap the plane to place the airport.");
        }

        TryPlaceFromTouch();
    }

    private bool HasAnyValidPlane()
    {
        foreach (var plane in planeManager.trackables)
        {
            if (IsPlaneValid(plane))
                return true;
        }

        return false;
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

    private bool TryGetScreenPress(out Vector2 screenPos, out int fingerId)
    {
        screenPos = default;
        fingerId = -1;

        var touchscreen = Touchscreen.current;
        if (touchscreen != null)
        {
            var touches = touchscreen.touches;
            for (int i = 0; i < touches.Count; i++)
            {
                var touch = touches[i];
                if (!touch.press.isPressed)
                    continue;

                var phase = touch.phase.ReadValue();
                var position = touch.position.ReadValue();
                var id = touch.touchId.ReadValue();

                if (logDebug)
                    Debug.Log($"[AutoARPlacement] Raw touch {i}: phase={phase}, position={position}, fingerId={id}");

                if (phase == UnityEngine.InputSystem.TouchPhase.Began ||
                    phase == UnityEngine.InputSystem.TouchPhase.Ended)
                {
                    screenPos = position;
                    fingerId = id;
                    return true;
                }
            }
        }

        if (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame)
        {
            screenPos = Mouse.current.position.ReadValue();
            return true;
        }

        return false;
    }

    private void TryPlaceFromTouch()
    {
        if (!TryGetScreenPress(out var screenPos, out var fingerId))
            return;

        if (EventSystem.current != null && fingerId >= 0 && EventSystem.current.IsPointerOverGameObject(fingerId))
        {
            if (logDebug)
                Debug.Log("[AutoARPlacement] Ignoring tap because it is over UI.");
            return;
        }

        if (logDebug)
            Debug.Log($"[AutoARPlacement] Screen press at {screenPos}");

        if (!raycastManager.Raycast(screenPos, RaycastHits, TrackableType.PlaneWithinPolygon))
        {
            if (logDebug)
                Debug.Log($"[AutoARPlacement] Tap at {screenPos} did not hit a detected plane.");
            return;
        }

        if (logDebug)
            Debug.Log($"[AutoARPlacement] Tap at {screenPos} produced {RaycastHits.Count} AR raycast hit(s).");

        foreach (var hit in RaycastHits)
        {
            if (!planeManager.trackables.TryGetTrackable(hit.trackableId, out var plane))
            {
                if (logDebug)
                    Debug.Log($"[AutoARPlacement] Raycast hit {hit.trackableId}, but no ARPlane was found for that trackable.");
                continue;
            }

            if (!IsPlaneValid(plane))
            {
                if (logDebug)
                {
                    Debug.Log($"[AutoARPlacement] Raycast hit plane {plane.trackableId}, but it was rejected. trackingState={plane.trackingState}, alignment={plane.alignment}, area={GetPlaneArea(plane):F3}, subsumed={(plane.subsumedBy != null)}");
                }
                continue;
            }

            if (logDebug)
                Debug.Log($"[AutoARPlacement] Tap hit valid plane: {plane.trackableId}");

            StartCoroutine(PlaceOnPlane(plane, hit.pose));
            return;
        }
    }

    private IEnumerator PlaceOnPlane(ARPlane plane, Pose hitPose)
    {
        if (placed || plane == null)
            yield break;

        placed = true;
        OnPlacementStarted?.Invoke();

        Pose pose = GetPlacementPose(hitPose);
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

        if (spawnDebugMarker)
        {
            var marker = GameObject.CreatePrimitive(PrimitiveType.Cube);
            marker.name = "ARPlacementDebugMarker";
            marker.transform.SetParent(currentAnchor.transform, false);
            marker.transform.localPosition = Vector3.up * 0.25f;
            marker.transform.localScale = Vector3.one * 0.25f;

            var markerRenderer = marker.GetComponent<Renderer>();
            if (markerRenderer != null)
                markerRenderer.material.color = Color.red;
        }

        airportRoot.SetParent(currentAnchor.transform, worldPositionStays: false);
        airportRoot.localPosition = Vector3.up * placementHeightOffset;
        airportRoot.localRotation = Quaternion.identity;
        airportRoot.localScale = Vector3.one * airportScale;

        SetHierarchyActive(airportRoot, true);

        if (logDebug)
        {
            var renderers = airportRoot.GetComponentsInChildren<Renderer>(true);
            int activeRendererCount = 0;

            foreach (var renderer in renderers)
            {
                if (renderer.gameObject.activeInHierarchy)
                    activeRendererCount++;
            }

            Debug.Log($"[AutoARPlacement] Airport localPosition={airportRoot.localPosition}, localScale={airportRoot.localScale}, worldPosition={airportRoot.position}");
            Debug.Log($"[AutoARPlacement] Airport renderer count={renderers.Length}, active renderer count={activeRendererCount}");

            for (int i = 0; i < Mathf.Min(renderers.Length, 10); i++)
            {
                var renderer = renderers[i];
                Debug.Log($"[AutoARPlacement] Renderer {i}: name={renderer.name}, enabled={renderer.enabled}, activeInHierarchy={renderer.gameObject.activeInHierarchy}, boundsCenter={renderer.bounds.center}");
            }
        }

        if (disablePlaneVisualizationAfterPlacement)
            SetPlaneVisualization(false);

        if (logDebug)
            Debug.Log("[AutoARPlacement] Airport placed successfully.");

        Debug.Log("[AutoARPlacement] Invoking OnPlacementCompleted");
        OnPlacementCompleted?.Invoke();
        Debug.Log("[AutoARPlacement] OnPlacementCompleted invoked");
        yield return null;
    }

    private Pose GetPlacementPose(Pose hitPose)
    {
        Vector3 position = hitPose.position;

        Vector3 cameraForward = arCamera.transform.forward;
        Vector3 flatForward = Vector3.ProjectOnPlane(cameraForward, Vector3.up).normalized;

        if (flatForward.sqrMagnitude < 0.001f)
            flatForward = Vector3.forward;

        Quaternion rotation = Quaternion.LookRotation(flatForward, Vector3.up);
        return new Pose(position, rotation);
    }

    public void ResetPlacement()
    {
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

        if (fallbackAnchor != null)
        {
            Destroy(fallbackAnchor.gameObject);
            fallbackAnchor = null;
        }

        placed = false;
        placementPromptLogged = false;

        SetPlaneVisualization(true);

        if (logDebug)
            Debug.Log("[AutoARPlacement] Placement reset.");
        
        if (debugSimulationButton != null)
            debugSimulationButton.SetActive(enableDebugSimulationInEditor && Application.isEditor);

        OnPlacementReset?.Invoke();
    }

    private void SetPlaneVisualization(bool enabled)
    {
        if (planeManager == null)
            return;

        foreach (var plane in planeManager.trackables)
        {
            foreach (var renderer in plane.GetComponentsInChildren<Renderer>(true))
                renderer.enabled = enabled;

            foreach (var lineRenderer in plane.GetComponentsInChildren<LineRenderer>(true))
                lineRenderer.enabled = enabled;
        }

        if (!keepPlaneTrackingAfterPlacement)
            planeManager.enabled = enabled;
    }

    private void SetHierarchyActive(Transform root, bool isActive)
    {
        if (root == null)
            return;

        root.gameObject.SetActive(isActive);

        for (int i = 0; i < root.childCount; i++)
            SetHierarchyActive(root.GetChild(i), isActive);
    }

        public void StartDebugSimulation()
    {
        if (!Application.isEditor || !enableDebugSimulationInEditor)
            return;

        if (placed)
        {
            if (logDebug)
                Debug.Log("[AutoARPlacement] Debug simulation ignored because placement already exists.");
            return;
        }

        if (debugPlacementPose == null)
        {
            Debug.LogError("[AutoARPlacement] Debug simulation requires a debugPlacementPose.");
            return;
        }

        StartCoroutine(PlaceAtDebugPose());
    }

    private IEnumerator PlaceAtDebugPose()
    {
        placed = true;
        OnPlacementStarted?.Invoke();

        var anchorObject = new GameObject("EditorDebugAnchor");
        anchorObject.transform.SetPositionAndRotation(
            debugPlacementPose.position,
            debugPlacementPose.rotation
        );

        fallbackAnchor = anchorObject.transform;

        airportRoot.SetParent(fallbackAnchor, worldPositionStays: false);
        airportRoot.localPosition = Vector3.up * placementHeightOffset;
        airportRoot.localRotation = Quaternion.identity;
        airportRoot.localScale = Vector3.one * airportScale;

        SetHierarchyActive(airportRoot, true);

        if (logDebug)
            Debug.Log("[AutoARPlacement] Debug simulation placement completed.");

        OnPlacementCompleted?.Invoke();
        yield return null;
    }

}
