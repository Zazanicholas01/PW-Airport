using UnityEngine;
using UnityEngine.UI;

public class RadarBlip : MonoBehaviour
{
    [SerializeField] private Image arrowImage;

    public RectTransform RectTransform { get; private set; }

    private void Awake()
    {
        RectTransform = GetComponent<RectTransform>();

        if (arrowImage == null)
        {
            arrowImage = GetComponent<Image>();
        }
    }

    public void SetColor(Color color)
    {
        if (arrowImage != null)
        {
            arrowImage.color = color;
        }
    }

    public void SetRotation(float degrees)
    {
        RectTransform.localRotation = Quaternion.Euler(0f, 0f, degrees);
    }
}
