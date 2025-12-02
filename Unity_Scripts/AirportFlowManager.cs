// Assets/PWAirport/Scripts/AirportFlowManager.cs
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Splines;

public class AirportFlowManager : MonoBehaviour
{
    [Header("Dynamic Spline Loading")]
    [Tooltip("Nome del GameObject che contiene MainPW con le spline (lascia vuoto per 'MainPW(Clone)')")]
    public string mainPWObjectName = "MainPW(Clone)";

    [Header("Splines Comuni")]
    public SplineContainer splineAtterraggio;
    public SplineContainer splineDecollo;

    [Header("Splines Atterraggio (Ritorno)")]
    public SplineContainer spline_O1_Ritorno;
    public SplineContainer spline_O2_Ritorno;
    public SplineContainer spline_O3_Ritorno;
    public SplineContainer spline_O4_Ritorno;
    public SplineContainer spline_O5_Ritorno;
    public SplineContainer spline_P1_Ritorno;
    public SplineContainer spline_P2_Ritorno;
    public SplineContainer spline_P3_Ritorno;
    public SplineContainer spline_C1_Ritorno;
    public SplineContainer spline_C2_Ritorno;
    public SplineContainer spline_C3_Ritorno;

    [Header("Splines Decollo (Andata)")]
    public SplineContainer spline_O1_Andata;
    public SplineContainer spline_O2_Andata;
    public SplineContainer spline_O3_Andata;
    public SplineContainer spline_O4_Andata;
    public SplineContainer spline_O5_Andata;
    public SplineContainer spline_P1_Andata;
    public SplineContainer spline_P2_Andata;
    public SplineContainer spline_P3_Andata;
    public SplineContainer spline_C1_Andata;
    public SplineContainer spline_C2_Andata;
    public SplineContainer spline_C3_Andata;

    [Header("Airplane Prefabs")]
    public GameObject a320Prefab;
    public GameObject aeroplanoLeggendarioPrefab;
    public GameObject b737Prefab;
    public GameObject e190Prefab;
    public GameObject b787Prefab;
    public GameObject jetPrefab;
    public GameObject turboelicaPrefab;

    [Header("Runtime References")]
    public AirportWsClient wsClient;

    // Stato piazzole: piazzola -> (occupata, aereo GameObject, tipo aereo)
    private Dictionary<string, PiazzolaInfo> piazzoleState = new Dictionary<string, PiazzolaInfo>();

    // Lista piazzole
    private string[] piazzole = { "O1", "O2", "O3", "O4", "O5", "P1", "P2", "P3", "C1", "C2", "C3" };

    // ######################### INTERNAL CLASSES #######################################

    class PiazzolaInfo
    {
        public bool occupied = false;
        public GameObject airplane = null;
        public string airplaneType = null;
    }

    // ######################### UNITY LIFECYCLE #######################################

    void Start()
    {
        // Inizializza stato piazzole
        foreach (string p in piazzole)
        {
            piazzoleState[p] = new PiazzolaInfo();
        }

        // Trova WebSocket client se non assegnato
        if (wsClient == null)
        {
            wsClient = FindObjectOfType<AirportWsClient>();
        }

        Debug.Log("[AirportFlowManager] Initialized with " + piazzole.Length + " piazzole");

        // Avvia ricerca automatica delle spline
        StartCoroutine(FindSplinesWhenReady());
    }

    /// <summary>
    /// Trova automaticamente le spline quando MainPW viene spawned
    /// </summary>
    System.Collections.IEnumerator FindSplinesWhenReady()
    {
        Debug.Log("[AirportFlowManager] Cercando MainPW e splines...");

        // Aspetta finché non trova MainPW
        GameObject mainPW = null;
        Transform splinesContainer = null;

        while (splinesContainer == null)
        {
            // Cerca MainPW nella scena
            mainPW = GameObject.Find(mainPWObjectName);

            // Fallback: cerca qualsiasi oggetto con "MainPW" nel nome
            if (mainPW == null)
            {
                GameObject[] allObjects = GameObject.FindObjectsOfType<GameObject>();
                foreach (GameObject obj in allObjects)
                {
                    if (obj.name.Contains("MainPW"))
                    {
                        mainPW = obj;
                        Debug.Log($"[AirportFlowManager] Trovato MainPW: {obj.name}");
                        break;
                    }
                }
            }

            if (mainPW != null)
            {
                // Cerca container Splines dentro MainPW
                splinesContainer = mainPW.transform.Find("Splines");

                if (splinesContainer != null)
                {
                    Debug.Log("[AirportFlowManager] Splines container trovato! Caricamento in corso...");
                    break;
                }
            }

            yield return new WaitForSeconds(0.5f);
        }

        // Carica tutte le spline
        LoadSplineReferences(splinesContainer);
    }

    /// <summary>
    /// Carica tutti i riferimenti alle spline dal container
    /// </summary>
    void LoadSplineReferences(Transform container)
    {
        // Spline comuni
        splineAtterraggio = FindSplineByName(container, "Spline_Atterraggio");
        splineDecollo = FindSplineByName(container, "Spline_Decollo");

        // Spline Ritorno (Atterraggio)
        spline_O1_Ritorno = FindSplineByName(container, "Spline_O1_Ritorno");
        spline_O2_Ritorno = FindSplineByName(container, "Spline_O2_Ritorno");
        spline_O3_Ritorno = FindSplineByName(container, "Spline_O3_Ritorno");
        spline_O4_Ritorno = FindSplineByName(container, "Spline_O4_Ritorno");
        spline_O5_Ritorno = FindSplineByName(container, "Spline_O5_Ritorno");
        spline_P1_Ritorno = FindSplineByName(container, "Spline_P1_Ritorno");
        spline_P2_Ritorno = FindSplineByName(container, "Spline_P2_Ritorno");
        spline_P3_Ritorno = FindSplineByName(container, "Spline_P3_Ritorno");
        spline_C1_Ritorno = FindSplineByName(container, "Spline_C1_Ritorno");
        spline_C2_Ritorno = FindSplineByName(container, "Spline_C2_Ritorno");
        spline_C3_Ritorno = FindSplineByName(container, "Spline_C3_Ritorno");

        // Spline Andata (Decollo)
        spline_O1_Andata = FindSplineByName(container, "Spline_O1_Andata");
        spline_O2_Andata = FindSplineByName(container, "Spline_O2_Andata");
        spline_O3_Andata = FindSplineByName(container, "Spline_O3_Andata");
        spline_O4_Andata = FindSplineByName(container, "Spline_O4_Andata");
        spline_O5_Andata = FindSplineByName(container, "Spline_O5_Andata");
        spline_P1_Andata = FindSplineByName(container, "Spline_P1_Andata");
        spline_P2_Andata = FindSplineByName(container, "Spline_P2_Andata");
        spline_P3_Andata = FindSplineByName(container, "Spline_P3_Andata");
        spline_C1_Andata = FindSplineByName(container, "Spline_C1_Andata");
        spline_C2_Andata = FindSplineByName(container, "Spline_C2_Andata");
        spline_C3_Andata = FindSplineByName(container, "Spline_C3_Andata");

        Debug.Log("[AirportFlowManager] ✅ Tutte le spline caricate con successo!");
    }

    /// <summary>
    /// Trova una spline per nome nel container
    /// </summary>
    SplineContainer FindSplineByName(Transform container, string name)
    {
        Transform splineTransform = container.Find(name);

        if (splineTransform == null)
        {
            Debug.LogWarning($"[AirportFlowManager] ⚠️ Spline '{name}' non trovata!");
            return null;
        }

        SplineContainer spline = splineTransform.GetComponent<SplineContainer>();

        if (spline == null)
        {
            Debug.LogWarning($"[AirportFlowManager] ⚠️ SplineContainer non trovato su '{name}'!");
            return null;
        }

        return spline;
    }

    // ######################### LANDING LOGIC #######################################

    /// <summary>
    /// Chiamato dal WebSocket client per far atterrare un aereo
    /// </summary>
    public void TriggerLanding(string planeType, string piazzola)
    {
        // Controlla se le spline sono state caricate
        if (splineAtterraggio == null)
        {
            Debug.LogWarning($"[Landing] Spline non ancora caricate, attendi che MainPW venga spawned...");
            return;
        }

        // Valida piazzola
        if (!piazzoleState.ContainsKey(piazzola))
        {
            Debug.LogError($"[Landing] Piazzola {piazzola} non valida!");
            return;
        }

        // Controlla se piazzola occupata
        if (piazzoleState[piazzola].occupied)
        {
            Debug.LogWarning($"[Landing] Piazzola {piazzola} già occupata da {piazzoleState[piazzola].airplaneType}!");
            return;
        }

        Debug.Log($"[Landing] {planeType} → {piazzola}");

        // Spawna aereo
        GameObject plane = SpawnPlane(planeType);
        if (plane == null)
        {
            Debug.LogError($"[Landing] Impossibile spawnare aereo {planeType}");
            return;
        }

        // Ottieni spline di ritorno (atterraggio)
        SplineContainer splineRitorno = GetRitornoSpline(piazzola);
        if (splineRitorno == null)
        {
            Debug.LogError($"[Landing] Spline di ritorno non trovata per {piazzola}");
            Destroy(plane);
            return;
        }

        if (splineAtterraggio == null)
        {
            Debug.LogError("[Landing] SplineAtterraggio non assegnata!");
            Destroy(plane);
            return;
        }

        // Posiziona aereo all'inizio della spline di atterraggio
        plane.transform.position = splineAtterraggio.EvaluatePosition(0);
        plane.transform.rotation = Quaternion.LookRotation(splineAtterraggio.EvaluateTangent(0));

        // Avvia percorso: SplineAtterraggio → Spline_XX_Ritorno
        var controller = plane.GetComponent<AirplaneController>();
        if (controller != null)
        {
            controller.StartPath(new SplineContainer[] { splineAtterraggio, splineRitorno }, piazzola, planeType, true); // true = landing
        }

        // Marca piazzola come occupata
        piazzoleState[piazzola].occupied = true;
        piazzoleState[piazzola].airplane = plane;
        piazzoleState[piazzola].airplaneType = planeType;
    }

    // ######################### TAKEOFF LOGIC #######################################

    /// <summary>
    /// Chiamato dal WebSocket client per far decollare un aereo
    /// </summary>
    public void TriggerTakeoff(string piazzola)
    {
        // Controlla se le spline sono state caricate
        if (splineDecollo == null)
        {
            Debug.LogWarning($"[Takeoff] Spline non ancora caricate, attendi che MainPW venga spawned...");
            return;
        }

        // Valida piazzola
        if (!piazzoleState.ContainsKey(piazzola))
        {
            Debug.LogError($"[Takeoff] Piazzola {piazzola} non valida!");
            return;
        }

        // Controlla se piazzola vuota
        if (!piazzoleState[piazzola].occupied)
        {
            Debug.LogWarning($"[Takeoff] Piazzola {piazzola} è vuota, nessun aereo da far decollare!");
            return;
        }

        Debug.Log($"[Takeoff] {piazzoleState[piazzola].airplaneType} da {piazzola}");

        // Ottieni aereo e tipo
        GameObject plane = piazzoleState[piazzola].airplane;
        string planeType = piazzoleState[piazzola].airplaneType;

        // Ottieni spline di andata (decollo)
        SplineContainer splineAndata = GetAndataSpline(piazzola);
        if (splineAndata == null)
        {
            Debug.LogError($"[Takeoff] Spline di andata non trovata per {piazzola}");
            return;
        }

        if (splineDecollo == null)
        {
            Debug.LogError("[Takeoff] SplineDecollo non assegnata!");
            return;
        }

        // Riposiziona aereo all'inizio della spline di andata
        plane.transform.position = splineAndata.EvaluatePosition(0);
        plane.transform.rotation = Quaternion.LookRotation(splineAndata.EvaluateTangent(0));

        // Avvia percorso di decollo: Spline_XX_Andata → SplineDecollo
        var controller = plane.GetComponent<AirplaneController>();
        if (controller != null)
        {
            controller.StartPath(new SplineContainer[] { splineAndata, splineDecollo }, piazzola, planeType, false); // false = takeoff
        }

        // Libera piazzola (verrà confermato quando l'aereo completa il percorso)
        piazzoleState[piazzola].occupied = false;
        piazzoleState[piazzola].airplane = null;
        piazzoleState[piazzola].airplaneType = null;
    }

    // ######################### PATH COMPLETION CALLBACKS #######################################

    /// <summary>
    /// Chiamato dall'AirplaneController quando completa il percorso di atterraggio
    /// </summary>
    public void OnLandingComplete(string piazzola, string planeType)
    {
        Debug.Log($"[Landing Complete] {planeType} atterrato su {piazzola}");

        // Notifica backend
        if (wsClient != null)
        {
            wsClient.SendLandingComplete(planeType, piazzola);
        }
    }

    /// <summary>
    /// Chiamato dall'AirplaneController quando completa il percorso di decollo
    /// </summary>
    public void OnTakeoffComplete(string piazzola, string planeType, GameObject airplane)
    {
        Debug.Log($"[Takeoff Complete] {planeType} decollato da {piazzola}");

        // Notifica backend
        if (wsClient != null)
        {
            wsClient.SendTakeoffComplete(planeType, piazzola);
        }

        // Distruggi aereo
        Destroy(airplane);
    }

    // ######################### SPLINE GETTERS #######################################

    SplineContainer GetRitornoSpline(string piazzola)
    {
        switch (piazzola)
        {
            case "O1": return spline_O1_Ritorno;
            case "O2": return spline_O2_Ritorno;
            case "O3": return spline_O3_Ritorno;
            case "O4": return spline_O4_Ritorno;
            case "O5": return spline_O5_Ritorno;
            case "P1": return spline_P1_Ritorno;
            case "P2": return spline_P2_Ritorno;
            case "P3": return spline_P3_Ritorno;
            case "C1": return spline_C1_Ritorno;
            case "C2": return spline_C2_Ritorno;
            case "C3": return spline_C3_Ritorno;
            default: return null;
        }
    }

    SplineContainer GetAndataSpline(string piazzola)
    {
        switch (piazzola)
        {
            case "O1": return spline_O1_Andata;
            case "O2": return spline_O2_Andata;
            case "O3": return spline_O3_Andata;
            case "O4": return spline_O4_Andata;
            case "O5": return spline_O5_Andata;
            case "P1": return spline_P1_Andata;
            case "P2": return spline_P2_Andata;
            case "P3": return spline_P3_Andata;
            case "C1": return spline_C1_Andata;
            case "C2": return spline_C2_Andata;
            case "C3": return spline_C3_Andata;
            default: return null;
        }
    }

    // ######################### AIRPLANE SPAWNING #######################################

    GameObject SpawnPlane(string planeType)
    {
        GameObject prefab = null;

        switch (planeType.ToUpper())
        {
            case "A320": prefab = a320Prefab; break;
            case "AEROPLANOLEGENDARIO":
            case "AEROPLANOLEGGENDARIO":
                prefab = aeroplanoLeggendarioPrefab; break;
            case "B737": prefab = b737Prefab; break;
            case "E190": prefab = e190Prefab; break;
            case "B787": prefab = b787Prefab; break;
            case "JET": prefab = jetPrefab; break;
            case "TURBOELICA": prefab = turboelicaPrefab; break;
            default:
                Debug.LogWarning($"Tipo aereo {planeType} non riconosciuto, uso B737");
                prefab = b737Prefab;
                break;
        }

        if (prefab == null)
        {
            Debug.LogError($"Prefab per {planeType} non assegnato!");
            return null;
        }

        return Instantiate(prefab);
    }

    // ######################### DEBUG & TESTING #######################################

    [ContextMenu("Test Landing B737 O1")]
    void TestLandingB737_O1()
    {
        TriggerLanding("B737", "O1");
    }

    [ContextMenu("Test Takeoff O1")]
    void TestTakeoff_O1()
    {
        TriggerTakeoff("O1");
    }

    [ContextMenu("Print Piazzole Status")]
    void PrintPiazzoleStatus()
    {
        Debug.Log("=== STATO PIAZZOLE ===");
        foreach (var kvp in piazzoleState)
        {
            string status = kvp.Value.occupied
                ? $"OCCUPATA da {kvp.Value.airplaneType}"
                : "LIBERA";
            Debug.Log($"{kvp.Key}: {status}");
        }
    }
}
