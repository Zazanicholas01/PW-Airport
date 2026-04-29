using UnityEngine;

public class RadarSweep : MonoBehaviour
{
    [SerializeField] private float degreesPerSecond = 120f;

    private void Update()
    {
        transform.Rotate(0f, 0f, -degreesPerSecond * Time.deltaTime);
    }
}
