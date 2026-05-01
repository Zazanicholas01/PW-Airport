using System.Collections.Generic;
using UnityEngine;

public class RadarController : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private Transform airportCenter;
    [SerializeField] private RectTransform blipContainer;
    [SerializeField] private RadarBlip blipPrefab;

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

    private float previousSweepAngle;
    private bool hasPreviousSweepAngle;


    private readonly Dictionary<RadarTarget, RadarBlip> blips = new();
    private float nextUpdateTime;
    private float RadarRangeUnityUnits => radarRangeMeters / metersPerUnityUnit;
    private float InnerExclusionRangeUnityUnits => innerExclusionRangeMeters / metersPerUnityUnit;

    private void Update()
    {
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
        blips[target] = blip;
        return blip;
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
