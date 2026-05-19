using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;

public class RadarController : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private Transform airportCenter;
    [SerializeField] private RectTransform blipContainer;
    [SerializeField] private RadarBlip blipPrefab;
    [SerializeField] private LocalWebSocketClient wsClient;

    [Header("Radar Settings")]
    [SerializeField] private float radarRangeMeters = 110000f;
    [SerializeField] private float metersPerUnityUnit = 867.08f;
    [SerializeField] private float radarRadiusPixels = 95f;
    [SerializeField] private float updateIntervalSeconds = 0.1f;
    [SerializeField] private float innerExclusionRangeMeters = 3000f;

    [Header("Orientation")]
    [SerializeField] private bool rotateWithAirport = false;

    [Header("Smoothing")]
    [SerializeField] private float blipMoveLerp = 0.35f;

    [Header("Sweep Highlight")]
    [SerializeField] private RectTransform sweepPivot;

    [Header("Debug")]
    [SerializeField] private bool debugRadarInput = true;
    [SerializeField] private int debugRaycastResultLimit = 5;
    [SerializeField] private float manualClickRadiusPixels = 28f;

    private float previousSweepAngle;
    private bool hasPreviousSweepAngle;


    private readonly Dictionary<RadarTarget, RadarBlip> blips = new();
    private readonly List<RaycastResult> debugRaycastResults = new();
    private float nextUpdateTime;
    private float lastManualClickTime = -1f;
    private float RadarRangeUnityUnits => radarRangeMeters / metersPerUnityUnit;
    private float InnerExclusionRangeUnityUnits => innerExclusionRangeMeters / metersPerUnityUnit;
    private const float ManualClickDebounceSeconds = 0.25f;

    [Serializable]
    private class HighlightFlightCommand
    {
        public string command = "highlight_flight";
        public string flight_id;
        public string airplane_id;
    }

    private void Awake()
    {
        UnityEngine.InputSystem.EnhancedTouch.EnhancedTouchSupport.Enable();

        if (wsClient == null)
        {
            wsClient = FindObjectOfType<LocalWebSocketClient>();
        }

        if (blipContainer != null)
        {
            blipContainer.SetAsLastSibling();
        }
    }

    private void Update()
    {
        ProcessRadarPointerInput();

        if (Time.time < nextUpdateTime)
            return;
        
        nextUpdateTime = Time.time + updateIntervalSeconds;
        RefreshRadar();
    }

    private void RefreshRadar()
    {
        if (airportCenter == null || blipContainer == null || blipPrefab == null)
        {
            return;
        }

        float currentSweepAngle = GetSweepAngleDegrees();

        if (!hasPreviousSweepAngle)
        {
            previousSweepAngle = currentSweepAngle;
            hasPreviousSweepAngle = true;
        }

        RadarTarget[] targets = FindObjectsByType<RadarTarget>(FindObjectsSortMode.None);
        HashSet<RadarTarget> seenTargets = new();

        foreach (RadarTarget target in targets)
        {
            if (target == null || !target.isVisibleOnRadar)
            {
                RemoveBlip(target);
                continue;
            }

            Vector3 offset = target.transform.position - airportCenter.position;

            if (rotateWithAirport)
            {
                offset = Quaternion.Inverse(airportCenter.rotation) * offset;
            }

            Vector2 flatOffset = new Vector2(offset.x, offset.z);

            float distanceUnityUnits = flatOffset.magnitude;
            float radarRangeUnityUnits = RadarRangeUnityUnits;
            float innerExclusionRangeUnityUnits = InnerExclusionRangeUnityUnits;

            if (distanceUnityUnits > radarRangeUnityUnits || distanceUnityUnits < innerExclusionRangeUnityUnits)
            {
                RemoveBlip(target);
                continue;
            }

            Vector2 radarPosition = flatOffset / radarRangeUnityUnits * radarRadiusPixels;

            RadarBlip blip = GetOrCreateBlip(target, radarPosition);
            seenTargets.Add(target);

            blip.RectTransform.anchoredPosition = Vector2.Lerp(
                blip.RectTransform.anchoredPosition,
                radarPosition,
                blipMoveLerp
            );

            float headingDegrees = GetTargetHeadingDegrees(target.transform);
            blip.SetRotationSmooth(headingDegrees);
            blip.SetColor(target.blipColor);

            TryPingBlipFromSweep(blip, radarPosition, previousSweepAngle, currentSweepAngle);

            blip.gameObject.SetActive(true);
        }

        RemoveStaleBlips(seenTargets);
        previousSweepAngle = currentSweepAngle;
    }

    private RadarBlip GetOrCreateBlip(RadarTarget target, Vector2 initialRadarPosition)
    {
        if (blips.TryGetValue(target, out RadarBlip existingBlip))
        {
            return existingBlip;
        }

        RadarBlip blip = Instantiate(blipPrefab, blipContainer);
        blip.RectTransform.anchoredPosition = initialRadarPosition;
        blip.RectTransform.SetAsLastSibling();
        blip.Bind(target, HandleRadarBlipClicked);
        blips[target] = blip;
        return blip;
    }

    private async void HandleRadarBlipClicked(RadarTarget target)
    {
        Debug.Log(
            $"[RadarClick] HandleRadarBlipClicked airplane_id={(target != null ? target.airplaneId : "null")} " +
            $"flight_id={(target != null ? target.flightId : "null")} " +
            $"ws={(wsClient != null)} connected={(wsClient != null && wsClient.IsConnected)}"
        );

        if (target == null || string.IsNullOrWhiteSpace(target.flightId))
        {
            Debug.LogWarning("[Radar] highlight_flight skipped: missing flightId.");
            return;
        }

        if (wsClient == null || !wsClient.IsConnected)
        {
            Debug.LogWarning("[Radar] highlight_flight skipped: websocket not connected.");
            return;
        }

        var payload = new HighlightFlightCommand
        {
            flight_id = target.flightId,
            airplane_id = target.airplaneId
        };

        await wsClient.Send(JsonUtility.ToJson(payload));
        Debug.Log($"[RadarClick] Sent highlight_flight flight_id={target.flightId} airplane_id={target.airplaneId}");
    }

    private void ProcessRadarPointerInput()
    {
        bool handledTouch = false;

        if (Touchscreen.current != null)
        {
            foreach (var touch in Touchscreen.current.touches)
            {
                if (!touch.press.wasPressedThisFrame)
                {
                    continue;
                }

                Vector2 position = touch.position.ReadValue();
                TryHandleManualRadarClick(position, $"touch id={touch.touchId.ReadValue()}");
                handledTouch = true;
            }
        }

        foreach (var touch in UnityEngine.InputSystem.EnhancedTouch.Touch.activeTouches)
        {
            if (touch.phase != UnityEngine.InputSystem.TouchPhase.Began)
            {
                continue;
            }

            TryHandleManualRadarClick(touch.screenPosition, $"enhanced-touch id={touch.touchId}");
            handledTouch = true;
        }

        if (!handledTouch)
        {
            for (int i = 0; i < UnityEngine.Input.touchCount; i++)
            {
                Touch touch = UnityEngine.Input.GetTouch(i);

                if (touch.phase != UnityEngine.TouchPhase.Began)
                {
                    continue;
                }

                TryHandleManualRadarClick(touch.position, $"legacy-touch id={touch.fingerId}");
            }
        }

        if (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame)
        {
            Vector2 position = Mouse.current.position.ReadValue();
            TryHandleManualRadarClick(position, "mouse");
        }
    }

    private void TryHandleManualRadarClick(Vector2 screenPosition, string source)
    {
        if (debugRadarInput)
        {
            LogPointerRaycast(screenPosition, source);
        }

        if (blipContainer == null)
        {
            Debug.LogWarning($"[RadarInput] {source} ignored: blipContainer=null");
            return;
        }

        if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(
                blipContainer,
                screenPosition,
                null,
                out Vector2 localPoint
            ))
        {
            Debug.LogWarning($"[RadarInput] {source} ignored: screen point could not be converted pos={screenPosition}");
            return;
        }

        RadarTarget closestTarget = null;
        RadarBlip closestBlip = null;
        float closestDistance = float.PositiveInfinity;

        foreach (var entry in blips)
        {
            RadarTarget target = entry.Key;
            RadarBlip blip = entry.Value;

            if (target == null || blip == null || !blip.gameObject.activeInHierarchy)
            {
                continue;
            }

            float distance = Vector2.Distance(localPoint, blip.RectTransform.anchoredPosition);

            if (distance < closestDistance)
            {
                closestDistance = distance;
                closestTarget = target;
                closestBlip = blip;
            }
        }

        bool insideBlipContainer = RectTransformUtility.RectangleContainsScreenPoint(blipContainer, screenPosition, null);
        float hitRadius = Mathf.Max(1f, manualClickRadiusPixels);

        Debug.Log(
            $"[RadarInput] {source} manual pos={screenPosition} local={localPoint} insideBlipContainer={insideBlipContainer} " +
            $"blips={blips.Count} closest={(closestBlip != null ? closestBlip.name : "none")} " +
            $"distance={(float.IsPositiveInfinity(closestDistance) ? -1f : closestDistance):0.0} radius={hitRadius:0.0}"
        );

        if (closestTarget == null || closestDistance > hitRadius)
        {
            return;
        }

        if (Time.unscaledTime - lastManualClickTime < ManualClickDebounceSeconds)
        {
            Debug.Log($"[RadarInput] {source} manual ignored: debounce");
            return;
        }

        lastManualClickTime = Time.unscaledTime;
        Debug.Log(
            $"[RadarInput] {source} manual hit airplane_id={closestTarget.airplaneId} " +
            $"flight_id={closestTarget.flightId} distance={closestDistance:0.0}"
        );
        HandleRadarBlipClicked(closestTarget);
    }

    private void LogPointerRaycast(Vector2 screenPosition, string source)
    {
        bool insideBlipContainer = blipContainer != null &&
            RectTransformUtility.RectangleContainsScreenPoint(blipContainer, screenPosition, null);

        if (EventSystem.current == null)
        {
            Debug.LogWarning($"[RadarInput] {source} pos={screenPosition} insideBlipContainer={insideBlipContainer} EventSystem=null");
            return;
        }

        debugRaycastResults.Clear();

        var pointerData = new PointerEventData(EventSystem.current)
        {
            position = screenPosition
        };

        EventSystem.current.RaycastAll(pointerData, debugRaycastResults);

        int limit = Mathf.Min(debugRaycastResults.Count, Mathf.Max(1, debugRaycastResultLimit));
        var names = new List<string>(limit);

        for (int i = 0; i < limit; i++)
        {
            RaycastResult result = debugRaycastResults[i];
            string objectName = result.gameObject != null ? result.gameObject.name : "null";
            string moduleName = result.module != null ? result.module.GetType().Name : "null";
            names.Add($"{i}:{objectName}/module={moduleName}/depth={result.depth}");
        }

        Debug.Log(
            $"[RadarInput] {source} pos={screenPosition} insideBlipContainer={insideBlipContainer} " +
            $"raycastCount={debugRaycastResults.Count} top=[{string.Join(", ", names)}]"
        );
    }

    private void RemoveBlip(RadarTarget target)
    {
        if (target == null)
        {
            return;
        }

        if (!blips.TryGetValue(target, out RadarBlip blip))
        {
            return;
        }

        Destroy(blip.gameObject);
        blips.Remove(target);
    }

    private void RemoveBlipEntry(RadarTarget target)
    {
        if (!blips.TryGetValue(target, out RadarBlip blip))
        {
            return;
        }

        if (blip != null)
        {
            Destroy(blip.gameObject);
        }

        blips.Remove(target);
    }

    public void RemoveAirplane(string airplaneId)
    {
        if (string.IsNullOrWhiteSpace(airplaneId))
        {
            return;
        }

        List<RadarTarget> matchingTargets = new();

        foreach (RadarTarget target in blips.Keys)
        {
            if (target != null && target.airplaneId == airplaneId)
            {
                matchingTargets.Add(target);
            }
        }

        foreach (RadarTarget target in matchingTargets)
        {
            RemoveBlipEntry(target);
        }
    }

    private void RemoveStaleBlips(HashSet<RadarTarget> seenTargets)
    {
        List<RadarTarget> staleTargets = new();

        foreach (RadarTarget target in blips.Keys)
        {
            if (target == null || !seenTargets.Contains(target))
            {
                staleTargets.Add(target);
            }
        }

        foreach (RadarTarget target in staleTargets)
        {
            RemoveBlipEntry(target);
        }
    }

    private float GetTargetHeadingDegrees(Transform targetTransform)
    {
        Vector3 forward = targetTransform.forward;

        if (rotateWithAirport)
        {
            forward = Quaternion.Inverse(airportCenter.rotation) * forward;
        }

        Vector2 flatForward = new Vector2(forward.x, forward.z);

        if (flatForward.sqrMagnitude < 0.0001f)
        {
            return 0f;
        }

        float angle = Mathf.Atan2(flatForward.x, flatForward.y) * Mathf.Rad2Deg;
        return -angle;
    }

    private void TryPingBlipFromSweep(
        RadarBlip blip,
        Vector2 radarPosition,
        float previousAngle,
        float currentAngle
    )
    {
        if (sweepPivot == null || radarPosition.sqrMagnitude < 0.001f)
        {
            return;
        }

        float blipAngle = Mathf.Atan2(radarPosition.x, radarPosition.y) * Mathf.Rad2Deg;
        blipAngle = NormalizeAngle(blipAngle);

        if (WasAngleSwept(previousAngle, currentAngle, blipAngle))
        {
            blip.Ping();
        }
    }

    private float GetSweepAngleDegrees()
    {
        if (sweepPivot == null)
        {
            return 0f;
        }

        return NormalizeAngle(-sweepPivot.localEulerAngles.z);
    }

    private bool WasAngleSwept(float previousAngle, float currentAngle, float targetAngle)
    {
        previousAngle = NormalizeAngle(previousAngle);
        currentAngle = NormalizeAngle(currentAngle);
        targetAngle = NormalizeAngle(targetAngle);

        if (currentAngle >= previousAngle)
        {
            return targetAngle >= previousAngle && targetAngle <= currentAngle;
        }

        return targetAngle >= previousAngle || targetAngle <= currentAngle;
    }

    private float NormalizeAngle(float angle)
    {
        angle %= 360f;

        if (angle < 0f)
        {
            angle += 360f;
        }

        return angle;
    }

}
