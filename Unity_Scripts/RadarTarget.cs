using UnityEngine;

public class RadarTarget : MonoBehaviour
{
    [Header("Radar")]
    public string airplaneId;
    public string flightId;
    public Color blipColor = Color.green;

    [Header("State")]
    public bool isVisibleOnRadar = true;
}
