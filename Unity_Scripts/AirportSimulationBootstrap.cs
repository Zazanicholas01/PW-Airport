using System;
using System.Threading.Tasks;
using UnityEngine;

public class AirportSimulationBootstrap : MonoBehaviour {

    [SerializeField] private AutoARPlacementController placementController;
    [SerializeField] private LocalWebSocketClient webSocketClient;
    [SerializeField] private SplineRegistry splineRegistry;
    [SerializeField] private PrefabRegistry prefabRegistry;
    [SerializeField] private StartPathHandler startPathHandler;

    [Header("Optional")]
    [SerializeField] private bool startSimulationAfterPlacement = false;
    [SerializeField] private bool sendSetupInit = true;
    [SerializeField] private bool logDebug = true;

    private bool startupTriggered;
    private bool startupCompleted;

    private async void Awake() {

        if (placementController == null)
            placementController = FindObjectOfType<AutoARPlacementController>();

        if (webSocketClient == null)
            webSocketClient = FindObjectOfType<LocalWebSocketClient>();

        if (splineRegistry == null)
            splineRegistry = FindObjectOfType<SplineRegistry>();

        if (prefabRegistry == null)
            prefabRegistry = FindObjectOfType<PrefabRegistry>();

        if (startPathHandler == null)
            startPathHandler = FindObjectOfType<StartPathHandler>();
    }

    private void OnEnable()
    {
        if (placementController != null)
        {
            placementController.OnPlacementCompleted.AddListener(HandlePlacementCompleted);
            placementController.OnPlacementReset.AddListener(HandlePlacementReset);
        }

        if (placementController != null && placementController.IsPlaced && startSimulationAfterPlacement)
            _ = StartSimulationAsync();
    }

    private void OnDisable()
    {
        if (placementController != null)
        {
            placementController.OnPlacementCompleted.RemoveListener(HandlePlacementCompleted);
            placementController.OnPlacementReset.RemoveListener(HandlePlacementReset);
        }
    }

    private async void HandlePlacementCompleted()
    {
        if (!startSimulationAfterPlacement)
        {
            if (logDebug)
                Debug.Log("[Bootstrap] Placement completed. Simulator startup is disabled for AR-only placement.");
            return;
        }

        await StartSimulationAsync();
    }

    private void HandlePlacementReset()
    {
        startupTriggered = false;
        startupCompleted = false;

        if (logDebug)
            Debug.Log("[Bootstrap] Placement reset. Startup state cleared.");
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
            
            if (startPathHandler != null)
            {
                startPathHandler.RebuildSplineCache();

                if (logDebug)
                    Debug.Log("[Bootstrap] Rebuilt spline cache after AR placement.");
            }

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
