using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
using TMPro;
using System.Collections;

[System.Serializable]
public class SensorData
{
    public int light_value;
    public string led_state;
    public string datetime;
}

public class SensorUIController : MonoBehaviour
{
    // Configurazione server
    private string serverUrl = "http://10.0.20.72:5000/sensor";
    
    // UI Elements - Assegnali nell'Inspector
    public TMP_Text lightValueText;      // Per TextMeshPro
    public TMP_Text ledStateText;
    public TMP_Text datetimeText;
    
    // Oppure usa Text normale invece di TMP_Text
    // public Text lightValueText;
    // public Text ledStateText;
    // public Text datetimeText;
    
    // Elementi visivi opzionali
    public Image ledIndicator;           // Immagine che cambia colore
    public Slider lightSlider;           // Slider per visualizzare il valore
    
    void Start()
    {
        // Richiedi dati ogni secondo
        InvokeRepeating("FetchData", 0f, 1f);
    }
    
    void FetchData()
    {
        StartCoroutine(GetSensorData());
    }
    
    IEnumerator GetSensorData()
    {
        UnityWebRequest request = UnityWebRequest.Get(serverUrl);
        yield return request.SendWebRequest();
        
        if (request.result == UnityWebRequest.Result.Success)
        {
            string json = request.downloadHandler.text;
            SensorData data = JsonUtility.FromJson<SensorData>(json);
            
            // Aggiorna UI
            UpdateUI(data);
        }
        else
        {
            Debug.LogError("Errore connessione: " + request.error);
            
            // Mostra errore nella UI
            if (lightValueText != null)
                lightValueText.text = "Errore connessione";
        }
    }
    
    void UpdateUI(SensorData data)
    {
        // Aggiorna testo
        if (lightValueText != null)
            lightValueText.text = "Luce: " + data.light_value;
        
        if (ledStateText != null)
            ledStateText.text = "LED: " + data.led_state;
        
        if (datetimeText != null)
            datetimeText.text = data.datetime;
        
        // Aggiorna slider (range 0-1023 per sensore analogico Arduino)
        if (lightSlider != null)
            lightSlider.value = data.light_value;
        
        // Cambia colore indicatore LED
        if (ledIndicator != null)
        {
            if (data.led_state == "ON")
                ledIndicator.color = Color.green;
            else
                ledIndicator.color = Color.red;
        }
        
        Debug.Log($"UI aggiornata - Luce: {data.light_value}, LED: {data.led_state}");
    }
}

