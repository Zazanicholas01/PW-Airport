using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Splines;

[RequireComponent(typeof(MessageDispatcher))]
public class StandServiceProgressManager : MonoBehaviour
{
    [SerializeField] private MessageDispatcher dispatcher;
    [SerializeField] private Transform splineRoot;
    [SerializeField] private List<Transform> additionalSplineRoots = new();
    [SerializeField] private bool includeInactive = true;

    [Header("Widget Placement")]
    [SerializeField] private Vector3 worldOffset = new Vector3(0f, 0.8f, 0f);
    [SerializeField] private Vector3 worldScale = new Vector3(0.0012f, 0.0012f, 0.0012f);

    private readonly Dictionary<string, ProgressWidget> widgetsByStand = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, SplineContainer> splineByName = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<string> completedStandIds = new();

    private Camera mainCamera;

    private class ProgressWidget
    {
        public GameObject root;
        public TMP_Text label;
        public RectTransform fillRect;
        public float duration;
        public float startedAt;
        public Vector3 anchorPosition;
    }

    private void Awake()
    {
        dispatcher = dispatcher ?? GetComponent<MessageDispatcher>();
        mainCamera = Camera.main;
        BuildSplineCache();
    }

    private void OnEnable()
    {
        if (dispatcher == null) return;

        dispatcher.OnStartServiceProgressCommand += HandleStart;
        dispatcher.OnStopServiceProgressCommand += HandleStop;
    }

    private void OnDisable()
    {
        if (dispatcher == null) return;

        dispatcher.OnStartServiceProgressCommand -= HandleStart;
        dispatcher.OnStopServiceProgressCommand -= HandleStop;
    }

    private void Update()
    {
        completedStandIds.Clear();

        foreach (var pair in widgetsByStand)
        {
            string standId = pair.Key;
            var widget = pair.Value;
            if (widget == null || widget.root == null)
            {
                completedStandIds.Add(standId);
                continue;
            }

            widget.root.transform.position = widget.anchorPosition + worldOffset;

            if (mainCamera != null)
            {
                Vector3 toCamera = widget.root.transform.position - mainCamera.transform.position;
                if (toCamera.sqrMagnitude > 0.0001f)
                    widget.root.transform.rotation = Quaternion.LookRotation(toCamera.normalized, Vector3.up);
            }

            float elapsed = Time.time - widget.startedAt;
            float progress = Mathf.Clamp01(elapsed / Mathf.Max(0.01f, widget.duration));

            if (widget.fillRect != null)
                widget.fillRect.anchorMax = new Vector2(progress, 1f);

            if (progress >= 1f)
                completedStandIds.Add(standId);
        }

        foreach (string standId in completedStandIds)
            RemoveWidget(standId);
    }

    private void HandleStart(MessageDispatcher.StartServiceProgressCommand cmd)
    {
        Vector3? anchor = ResolveStandAnchor(cmd.stand_id);
        if (anchor == null)
        {
            Debug.LogWarning($"[StandServiceProgress] No stand anchor found for stand_id={cmd.stand_id}");
            return;
        }
        Debug.Log(
            $"[StandServiceProgress] stand={cmd.stand_id} anchor={anchor.Value} worldOffset={worldOffset}"
        );

        if (widgetsByStand.TryGetValue(cmd.stand_id, out var existing) && existing?.root != null)
            Destroy(existing.root);

        var widget = CreateWidget(
            labelText: string.IsNullOrWhiteSpace(cmd.label) ? "Service" : cmd.label,
            anchorPosition: anchor.Value,
            duration: cmd.duration_seconds
        );

        widgetsByStand[cmd.stand_id] = widget;
    }

    private void HandleStop(MessageDispatcher.StopServiceProgressCommand cmd)
    {
        if (string.IsNullOrWhiteSpace(cmd.stand_id))
            return;

        if (!widgetsByStand.ContainsKey(cmd.stand_id))
            return;

        RemoveWidget(cmd.stand_id);
    }

    private void RemoveWidget(string standId)
    {
        if (string.IsNullOrWhiteSpace(standId))
            return;

        if (!widgetsByStand.TryGetValue(standId, out var widget))
            return;

        if (widget?.root != null)
            Destroy(widget.root);

        widgetsByStand.Remove(standId);
    }

    private ProgressWidget CreateWidget(string labelText, Vector3 anchorPosition, float duration)
    {
        var root = new GameObject($"StandProgress_{labelText}");
        root.transform.position = anchorPosition + worldOffset;
        root.transform.localScale = worldScale;

        var canvas = root.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.WorldSpace;

        root.AddComponent<CanvasScaler>();
        root.AddComponent<GraphicRaycaster>();

        var rootRect = root.GetComponent<RectTransform>();
        rootRect.sizeDelta = new Vector2(180f, 42f);

        var panel = new GameObject("Panel");
        panel.transform.SetParent(root.transform, false);

        var panelRect = panel.AddComponent<RectTransform>();
        panelRect.anchorMin = Vector2.zero;
        panelRect.anchorMax = Vector2.one;
        panelRect.offsetMin = Vector2.zero;
        panelRect.offsetMax = Vector2.zero;

        var panelBg = panel.AddComponent<Image>();
        panelBg.color = new Color(0f, 0f, 0f, 0.68f);

        var labelObj = new GameObject("Label");
        labelObj.transform.SetParent(panel.transform, false);

        var labelRect = labelObj.AddComponent<RectTransform>();
        labelRect.anchorMin = new Vector2(0.05f, 0.50f);
        labelRect.anchorMax = new Vector2(0.95f, 0.94f);
        labelRect.offsetMin = Vector2.zero;
        labelRect.offsetMax = Vector2.zero;

        var label = labelObj.AddComponent<TextMeshProUGUI>();
        label.text = labelText;
        label.fontSize = 14;
        label.alignment = TextAlignmentOptions.Center;
        label.color = Color.white;

        var barBgObj = new GameObject("BarBackground");
        barBgObj.transform.SetParent(panel.transform, false);

        var barBgRect = barBgObj.AddComponent<RectTransform>();
        barBgRect.anchorMin = new Vector2(0.08f, 0.12f);
        barBgRect.anchorMax = new Vector2(0.92f, 0.38f);
        barBgRect.offsetMin = Vector2.zero;
        barBgRect.offsetMax = Vector2.zero;

        var barBg = barBgObj.AddComponent<Image>();
        barBg.color = new Color(1f, 1f, 1f, 0.16f);

        var fillObj = new GameObject("BarFill");
        fillObj.transform.SetParent(barBgObj.transform, false);

        var fillRect = fillObj.AddComponent<RectTransform>();

        var fill = fillObj.AddComponent<Image>();
        fill.color = new Color(0.14f, 0.82f, 0.34f, 1f);

        fillRect.anchorMin = new Vector2(0f, 0f);
        fillRect.anchorMax = new Vector2(0f, 1f);
        fillRect.pivot = new Vector2(0f, 0.5f);
        fillRect.offsetMin = Vector2.zero;
        fillRect.offsetMax = Vector2.zero;

        return new ProgressWidget
        {
            root = root,
            label = label,
            fillRect = fillRect,
            duration = duration,
            startedAt = Time.time,
            anchorPosition = anchorPosition,
        };
    }

    private Vector3? ResolveStandAnchor(string standId)
    {
        if (string.IsNullOrWhiteSpace(standId))
            return null;

        var spline = FindSpline($"Spline_{standId}");
        if (spline == null)
            return null;

        return spline.transform.position;
    }

    private void BuildSplineCache()
    {
        splineByName.Clear();

        void AddFromRoot(Transform root)
        {
            if (root == null)
                return;

            foreach (var container in root.GetComponentsInChildren<SplineContainer>(includeInactive))
            {
                if (container == null || container.gameObject == null)
                    continue;

                splineByName[container.gameObject.name] = container;
            }
        }

        AddFromRoot(splineRoot);

        if (additionalSplineRoots != null)
        {
            foreach (var root in additionalSplineRoots)
                AddFromRoot(root);
        }

        if (splineByName.Count == 0)
        {
            foreach (var container in FindObjectsOfType<SplineContainer>(includeInactive))
            {
                if (container == null || container.gameObject == null)
                    continue;

                splineByName[container.gameObject.name] = container;
            }

            Debug.LogWarning("[StandServiceProgress] No spline roots configured. Falling back to scene-wide spline search.");
        }
    }

    private SplineContainer FindSpline(string name)
    {
        if (splineByName.Count == 0)
            BuildSplineCache();

        return splineByName.TryGetValue(name, out var container) ? container : null;
    }
}
