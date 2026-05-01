using UnityEngine;
using UnityEngine.UI;

public class RadarBlip : MonoBehaviour
{
    [SerializeField] private Image arrowImage;
    [SerializeField] private Image glowImage;

    [Header("Base")]
    [SerializeField] private float baseAlpha = 0.35f;

    [Header("Sweep Highlight")]
    [SerializeField] private float highlightFadeSpeed = 1.8f;
    [SerializeField] private float highlightAlphaBoost = 0.65f;
    [SerializeField] private float highlightScaleBoost = 0.25f;

    public RectTransform RectTransform { get; private set; }

    private Color baseColor = Color.green;
    private float highlight;

    private void Awake()
    {
        RectTransform = GetComponent<RectTransform>();

        if (arrowImage == null)
        {
            arrowImage = GetComponent<Image>();
        }
    }

    private void Update()
    {
        highlight = Mathf.MoveTowards(
            highlight,
            0f,
            highlightFadeSpeed * Time.deltaTime
        );

        float alpha = Mathf.Clamp01(baseAlpha + highlight * highlightAlphaBoost);
        float scale = 1f + highlight * highlightScaleBoost;

        Color arrowColor = baseColor;
        arrowColor.a = alpha;

        if (arrowImage != null)
        {
            arrowImage.color = arrowColor;
        }

        if (glowImage != null)
        {
            Color glowColor = baseColor;
            glowColor.a = highlight * 0.5f;
            glowImage.color = glowColor;
        }

        RectTransform.localScale = Vector3.one * scale;
    }

    public void Ping()
    {
        highlight = 1f;
    }

    public void SetColor(Color color)
    {
        baseColor = color;
    }

    public void SetRotationSmooth(float degrees)
    {
        Quaternion targetRotation = Quaternion.Euler(0f, 0f, degrees);

        RectTransform.localRotation = Quaternion.Lerp(
            RectTransform.localRotation,
            targetRotation,
            0.25f
        );
    }
}
