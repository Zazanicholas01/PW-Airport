using System;
using System.Threading.Tasks;
using UnityEngine;

public class AirportSimulationBootstrap : MonoBehaviour {

    [SerializeField] private AutoARPlacementController placementController;
    [SerializeField] private LocalWebSocketClient webSocketClient;
    [SerializeField] private SplineRegistry splineRegistry;
    [SerializeField] private PrefabRegistry prefabRegistry;

    [Header("Optional")]
    [SerializeField] private bool sendSetupInit = true;
    [SerializeField] private bool logDebug = true;

    private bool startupTriggered;
    private bool startupCompleted;

    private async void OnEnable() {

        if (placementController == null)
            placementController = FindObjectOfType<AutoARPlacementController>();

        if (webSocketClient == null)
            webSocketClient = FindObjectOfType<LocalWebSocketClient>();

        if (splineRegistry == null)
            splineRegistry = FindObjectOfType<SplineRegistry>();

        if (prefabRegistry == null)
            prefabRegistry = FindObjectOfType<PrefabRegistry>();

        if (placementController != null)
            placementController.OnPlacementCompleted.AddListener(HandlePlacementCompleted);

        if (placementController != null && placementController.IsPlaced)
            await StartSimulationAsync();
    }

    private void OnDisable()
    {
        if (placementController != null)
            placementController.OnPlacementCompleted.RemoveListener(HandlePlacementCompleted);
    }

    private async void HandlePlacementCompleted()
    {
        await StartSimulationAsync();
    }

    private async Task StartSimulationAsync() {

        if (startupTriggered || startupCompleted)
            return;

        startupTriggered = true;

        try {
            if (webSocketClient == null)
                throw new InvalidOperationException("LocalWebSocketClient not assigned.");

            if (splineRegistry == null)
                throw new InvalidOperationException("SplineRegistry not assigned.");

            if (prefabRegistry == null)
                throw new InvalidOperationException("PrefabRegistry not assigned.");

            if (logDebug)
                Debug.Log("[Bootstrap] Placement completed. Starting simulator initialization.");

            bool connected = await webSocketClient.ConnectAsync();
            if (!connected)
                throw new InvalidOperationException("WebSocket connection failed.");

            if (sendSetupInit)
            {
                await webSocketClient.Send("{\"type\":\"event\",\"event\":\"setup-init\"}");
                if (logDebug)
                    Debug.Log("[Bootstrap] Sent setup-init.");
            }

            await splineRegistry.SendAllSplines();
            if (logDebug)
                Debug.Log("[Bootstrap] Sent spline batch.");

            await prefabRegistry.SendPrefabNames();
            if (logDebug)
                Debug.Log("[Bootstrap] Sent prefab batch.");

            startupCompleted = true;

            if (logDebug)
                Debug.Log("[Bootstrap] Simulator initialization completed.");
                
        } catch (Exception ex) {
            startupTriggered = false;
            Debug.LogError($"[Bootstrap] Initialization failed: {ex.Message}");
        }
    }
}