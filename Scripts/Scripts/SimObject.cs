// Assets/Scripts/SimObject.cs
using UnityEngine;

public class SimObject : MonoBehaviour
{
    [Tooltip("Stable ID shared with Python (e.g., CUBE_1)")]
    public string Id = "CUBE_1";

    void Awake()
    {
        if (string.IsNullOrWhiteSpace(Id))
            Id = gameObject.name;
    }
}
