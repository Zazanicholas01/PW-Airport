// Assets/PWAirport/Scripts/AirplaneController.cs
using UnityEngine;
using UnityEngine.Splines;
using Unity.Mathematics;

public class AirplaneController : MonoBehaviour
{
    [Header("Spline Movement")]
    public SplineContainer currentSpline;
    private float progress = 0f;
    private float currentSpeed = 0.15f; // Velocità corrente (calcolata dinamicamente)

    [Header("Speed Settings")]
    public float flightSpeed = 0.05f;    // Velocità per spline principali (volo)
    public float taxiSpeed = 0.15f;      // Velocità per spline piazzole (rullaggio)

    [Header("Multi-Spline Path")]
    public SplineContainer[] splinePath; // Array di spline da seguire in sequenza
    private int currentSplineIndex = 0;

    [Header("Flight Info")]
    public string assignedPiazzola = "";
    public string airplaneType = "";
    public bool isLanding = true; // true = atterraggio, false = decollo

    [Header("Landing Detection")]
    [Tooltip("Distanza massima per considerare valido il trigger (scala aeroporto)")]
    public float maxTriggerDistance = 1f;

    private AirportFlowManager airportManager;
    private float previousDistanceToNextSpline = float.MaxValue;

    // ######################### UNITY LIFECYCLE #######################################

    void Start()
    {
        // Trova AirportFlowManager
        airportManager = FindObjectOfType<AirportFlowManager>();
    }

    void Update()
    {
        if (currentSpline == null || splinePath == null || splinePath.Length == 0)
        {
            return; // Nessun percorso assegnato, non fare nulla
        }

        // Muovi lungo la spline corrente
        progress += currentSpeed * Time.deltaTime;

        // Valuta posizione sulla spline
        Vector3 position = currentSpline.EvaluatePosition(progress);
        transform.position = position;

        // Ruota l'aereo nella direzione della spline
        Vector3 forward = currentSpline.EvaluateTangent(progress);
        if (forward != Vector3.zero)
        {
            transform.rotation = Quaternion.LookRotation(forward);
        }

        // LANDING: controlla se siamo passati il punto di closest approach
        if (isLanding && currentSplineIndex + 1 < splinePath.Length && progress > 0.1f)
        {
            SplineContainer nextSpline = splinePath[currentSplineIndex + 1];

            // Trova distanza dal punto di INIZIO (t=0) della spline successiva
            Vector3 nextSplineStart = nextSpline.EvaluatePosition(0);
            float currentDistance = Vector3.Distance(transform.position, nextSplineStart);

            // Se la distanza sta AUMENTANDO rispetto al frame precedente = abbiamo passato il punto più vicino
            // MA solo se siamo abbastanza vicini (evita false trigger quando passa dietro)
            if (currentDistance > previousDistanceToNextSpline && previousDistanceToNextSpline < maxTriggerDistance)
            {
                currentSplineIndex++;
                SwitchToNextSpline();
                previousDistanceToNextSpline = float.MaxValue; // Reset per la prossima spline
                return;
            }

            // Salva la distanza per il prossimo frame
            previousDistanceToNextSpline = currentDistance;
        }

        // Se ha finito la spline corrente, passa alla prossima
        if (progress >= 1f)
        {
            currentSplineIndex++;

            if (currentSplineIndex < splinePath.Length)
            {
                // Passa alla prossima spline con closest point matching
                SwitchToNextSpline();
            }
            else
            {
                // Ha finito tutte le spline
                OnPathCompleted();
            }
        }
    }

    // ######################### PATH MANAGEMENT #######################################

    /// <summary>
    /// Avvia il percorso dell'aereo
    /// </summary>
    /// <param name="path">Array di spline da seguire</param>
    /// <param name="piazzola">Piazzola assegnata</param>
    /// <param name="planeType">Tipo di aereo</param>
    /// <param name="landing">true se atterraggio, false se decollo</param>
    public void StartPath(SplineContainer[] path, string piazzola, string planeType, bool landing)
    {
        splinePath = path;
        assignedPiazzola = piazzola;
        airplaneType = planeType;
        isLanding = landing;
        currentSplineIndex = 0;
        currentSpline = splinePath[0];
        progress = 0f;

        // Imposta velocità in base al tipo di spline
        UpdateSpeed();

        // Posiziona l'aereo all'inizio
        transform.position = currentSpline.EvaluatePosition(0);
        Vector3 tangent = currentSpline.EvaluateTangent(0);
        if (tangent != Vector3.zero)
        {
            transform.rotation = Quaternion.LookRotation(tangent);
        }

        Debug.Log($"[AirplaneController] {planeType} {(landing ? "atterrando su" : "decollando da")} {piazzola}");
    }

    /// <summary>
    /// Trova la distanza minima tra una posizione e una spline
    /// </summary>
    float FindClosestPoint(SplineContainer spline, Vector3 position)
    {
        float minDistance = float.MaxValue;
        int samples = 50;

        for (int i = 0; i < samples; i++)
        {
            float t = (float)i / (samples - 1);
            Vector3 pointOnSpline = spline.EvaluatePosition(t);
            float distance = Vector3.Distance(position, pointOnSpline);

            if (distance < minDistance)
            {
                minDistance = distance;
            }
        }

        return minDistance;
    }

    /// <summary>
    /// Passa alla spline successiva con closest point matching
    /// </summary>
    void SwitchToNextSpline()
    {
        SplineContainer nextSpline = splinePath[currentSplineIndex];
        Vector3 currentPosition = transform.position;

        float bestT = 0f;
        float bestDistance = float.MaxValue;

        // Per LANDING: forza inizio spline (t=0) per evitare di skippare alla piazzola
        if (isLanding)
        {
            bestT = 0f;
            bestDistance = Vector3.Distance(currentPosition, nextSpline.EvaluatePosition(0));
        }
        else
        {
            // Per TAKEOFF: campiona punti lungo la spline per trovare il più vicino
            int samples = 100;
            for (int i = 0; i < samples; i++)
            {
                float t = (float)i / (samples - 1); // da 0 a 1
                Vector3 pointOnSpline = nextSpline.EvaluatePosition(t);

                // Distanza dal punto attuale
                float distance = Vector3.Distance(currentPosition, pointOnSpline);

                // Trova il punto più vicino
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    bestT = t;
                }
            }
        }

        // Imposta la nuova spline e il progress al punto più vicino
        currentSpline = nextSpline;
        progress = bestT;

        // Aggiorna velocità in base al tipo di spline
        UpdateSpeed();

        Debug.Log($"[AirplaneController] Switched to {nextSpline.name}, starting at t={bestT:F3} (distance: {bestDistance:F2}m)");
    }

    /// <summary>
    /// Aggiorna la velocità in base al tipo di spline corrente
    /// </summary>
    void UpdateSpeed()
    {
        if (currentSpline == null) return;

        string splineName = currentSpline.name.ToLower();

        // Spline principali = velocità volo
        if (splineName.Contains("atterraggio") || splineName.Contains("decollo"))
        {
            currentSpeed = flightSpeed;
        }
        // Spline piazzole = velocità rullaggio
        else if (splineName.Contains("andata") || splineName.Contains("ritorno"))
        {
            currentSpeed = taxiSpeed;
        }
        // Default = velocità volo
        else
        {
            currentSpeed = flightSpeed;
        }
    }

    void OnPathCompleted()
    {
        if (isLanding)
        {
            // Atterraggio completato
            Debug.Log($"[AirplaneController] {airplaneType} atterrato su {assignedPiazzola}");

            // Ferma l'aereo
            splinePath = null;
            currentSpline = null;

            // Notifica AirportFlowManager
            if (airportManager != null)
            {
                airportManager.OnLandingComplete(assignedPiazzola, airplaneType);
            }
        }
        else
        {
            // Decollo completato
            Debug.Log($"[AirplaneController] {airplaneType} decollato da {assignedPiazzola}");

            // Notifica AirportFlowManager (che distruggerà l'aereo)
            if (airportManager != null)
            {
                airportManager.OnTakeoffComplete(assignedPiazzola, airplaneType, gameObject);
            }
            else
            {
                // Fallback: distruggi direttamente
                Destroy(gameObject);
            }
        }
    }
}
