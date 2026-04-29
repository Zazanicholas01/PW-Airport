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

    [Header("Orientation")]
    [SerializeField] private bool rotateWithAirport = false;

    private readonly Dictionary<RadarTarget, RadarBlip> blips = new();
    private float nextUpdateTime;
    private float RadarRangeUnityUnits => radarRangeMeters / metersPerUnityUnit;

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

            if (distanceUnityUnits > radarRangeUnityUnits)
            {
                RemoveBlip(target);
                continue;
            }

            RadarBlip blip = GetOrCreateBlip(target);
            seenTargets.Add(target);

            Vector2 radarPosition = flatOffset / radarRangeUnityUnits * radarRadiusPixels;
            blip.RectTransform.anchoredPosition = radarPosition;

            float headingDegrees = GetTargetHeadingDegrees(target.transform);
            blip.SetRotation(headingDegrees);
            blip.SetColor(target.blipColor);
            blip.gameObject.SetActive(true);
        }

        RemoveStaleBlips(seenTargets);
    }

    private RadarBlip GetOrCreateBlip(RadarTarget target)
    {
        if (blips.TryGetValue(target, out RadarBlip existingBlip))
        {
            return existingBlip;
        }

        RadarBlip blip = Instantiate(blipPrefab, blipContainer);
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
            RemoveBlip(target);
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
}