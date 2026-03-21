using UnityEngine;
using TMPro;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

public class ARSessionStateDebugLabel : MonoBehaviour
{
    [SerializeField] private TMP_Text uiText;
    [SerializeField] private bool logStateChanges = true;

    private ARSessionState lastState;

    private void Start()
    {
        lastState = ARSession.state;
        UpdateLabel(lastState, ARSession.notTrackingReason);
    }

    private void Update()
    {
        var state = ARSession.state;
        var reason = ARSession.notTrackingReason;

        UpdateLabel(state, reason);

        if (logStateChanges && state != lastState)
        {
            Debug.Log($"[ARSessionState] State={state}, NotTrackingReason={reason}");
            lastState = state;
        }
    }

    private void UpdateLabel(ARSessionState state, NotTrackingReason reason)
    {
        if (uiText == null)
            return;

        uiText.text = $"AR State: {state}\nNot Tracking: {reason}";
    }
}
