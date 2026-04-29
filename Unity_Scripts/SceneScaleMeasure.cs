using UnityEngine;

public class SceneScaleMeasure : MonoBehaviour
{
    [SerializeField] private Transform pointA;
    [SerializeField] private Transform pointB;
    [SerializeField] private float realDistanceMeters = 1000f;

    private void OnValidate()
    {
        PrintScale();
    }

    [ContextMenu("Print Scale")]
    public void PrintScale()
    {
        if (pointA == null || pointB == null)
        {
            return;
        }

        float unityDistance = Vector3.Distance(pointA.position, pointB.position);

        if (unityDistance <= 0.0001f)
        {
            Debug.LogWarning("Unity distance is too small.");
            return;
        }

        float metersPerUnityUnit = realDistanceMeters / unityDistance;
        float unityUnitsPerMeter = unityDistance / realDistanceMeters;

        Debug.Log($"Unity distance: {unityDistance:F2} units");
        Debug.Log($"Real distance: {realDistanceMeters:F2} meters");
        Debug.Log($"Scale: 1 Unity unit = {metersPerUnityUnit:F2} meters");
        Debug.Log($"Scale: 1 meter = {unityUnitsPerMeter:F4} Unity units");
    }
}
