using System;
using UnityEngine;

public class RouteFollower : MonoBehaviour
{
    // ---- Speed & Acceleration ----
    [Header("Speed")]
    [Tooltip("Initial/cruise target speed in m/s")]
    public float speedMetersPerSec = 2f;
    public float minSpeed = 0f;
    public float maxSpeed = 6f;

    [Header("Acceleration")]
    [Tooltip("m/s^2 when accelerating")]
    public float accelUp = 2.0f;
    [Tooltip("m/s^2 when decelerating")]
    public float accelDown = 3.0f;

    // ---- Steering & Waypoints ----
    [Header("Steering")]
    public bool orientToVelocity = true;
    [Tooltip("Distance to waypoint considered 'reached' (meters)")]
    public float waypointTolerance = 0.05f;

    // ---- Orientation Offset (baked visual rotation) ----
    // Keep this as the visual's authored offset so runtime facing is preserved.
    [Header("Orientation Offset")]
    [Tooltip("Fixed rotation applied AFTER facing so your model keeps its authored orientation")]
    public Vector3 baseEulerOffset = new Vector3(-90f, 180f, 0f);

    // ---- Runtime state ----
    Vector3[] _wps;
    int _idx = -1;
    bool _active;

    float _currentSpeed;   // actual speed (ramped)
    float _targetSpeed;    // desired target speed

    Quaternion _baseRotation;

    public Action OnRouteComplete;

    void Awake()
    {
        _baseRotation = Quaternion.Euler(baseEulerOffset);
        _targetSpeed  = Mathf.Clamp(speedMetersPerSec, minSpeed, maxSpeed);
        _currentSpeed = Mathf.Clamp(_currentSpeed,       minSpeed, maxSpeed);
    }

    void Update()
    {
        if (!_active || _wps == null || _idx < 0 || _idx >= _wps.Length)
            return;

        float dt = Time.deltaTime;

        // Ramp toward target speed
        float delta = _targetSpeed - _currentSpeed;
        float a = (delta >= 0f) ? accelUp : accelDown;
        float step = Mathf.Sign(delta) * a * dt;
        if (Mathf.Abs(step) > Mathf.Abs(delta)) step = delta;
        _currentSpeed = Mathf.Clamp(_currentSpeed + step, minSpeed, maxSpeed);

        var pos = transform.position;
        var target = _wps[_idx];

        // If nearly stopped, optionally face the next waypoint so it looks natural
        if (_currentSpeed <= 1e-4f)
        {
            if (orientToVelocity)
            {
                Vector3 toTarget = (target - pos);
                if (toTarget.sqrMagnitude > 1e-8f)
                {
                    var facing = Quaternion.LookRotation(toTarget.normalized, Vector3.up);
                    transform.rotation = facing * _baseRotation; // <-- preserves your offset
                }
            }
            return;
        }

        // Move
        Vector3 next = Vector3.MoveTowards(pos, target, _currentSpeed * dt);

        // Face motion direction (with baked offset)
        if (orientToVelocity)
        {
            Vector3 v = next - pos;
            if (v.sqrMagnitude > 1e-10f)
            {
                var facing = Quaternion.LookRotation(v.normalized, Vector3.up);
                transform.rotation = facing * _baseRotation;
            }
        }

        transform.position = next;

        // Waypoint reached?
        if ((transform.position - target).sqrMagnitude <= waypointTolerance * waypointTolerance)
        {
            _idx++;
            if (_idx >= _wps.Length)
            {
                _active = false;
                OnRouteComplete?.Invoke();
            }
        }
    }

    // ---- Public API ----

    /// <summary>
    /// Start following a set of waypoints. Units: meters in Unity world space.
    /// </summary>
    public void StartRoute(Vector3[] waypoints, float? speedOverride = null)
    {
        if (waypoints == null || waypoints.Length == 0) return;
        _wps = waypoints;
        _idx = 0;
        _active = true;

        if (speedOverride.HasValue)
            _targetSpeed = Mathf.Clamp(speedOverride.Value, minSpeed, maxSpeed);
        else
            _targetSpeed = Mathf.Clamp(speedMetersPerSec,   minSpeed, maxSpeed);

        // Keep current speed (smooth start). If you want an immediate start, set _currentSpeed = _targetSpeed.
        _currentSpeed = Mathf.Clamp(_currentSpeed, minSpeed, maxSpeed);
    }

    /// <summary>
    /// Change target speed. Optional overrides for accel/decel for this command.
    /// </summary>
    public void SetTargetSpeed(float newSpeed, float? accelUpOverride = null, float? accelDownOverride = null)
    {
        _targetSpeed = Mathf.Clamp(newSpeed, minSpeed, maxSpeed);
        if (accelUpOverride.HasValue)   accelUp   = Mathf.Max(0f, accelUpOverride.Value);
        if (accelDownOverride.HasValue) accelDown = Mathf.Max(0f, accelDownOverride.Value);
    }

    /// <summary>
    /// Immediately stop (sets both current and target to 0).
    /// </summary>
    public void StopNow()
    {
        _currentSpeed = 0f;
        _targetSpeed  = 0f;
    }

    /// <summary>
    /// Cancel current route without firing completion.
    /// </summary>
    public void CancelRoute()
    {
        _active = false;
        _wps = null;
        _idx = -1;
    }

    // ---- Helpers / Properties ----
    public bool  IsActive      => _active;
    public int   WaypointIndex => Mathf.Max(_idx, 0);
    public float CurrentSpeed  => _currentSpeed;
    public float TargetSpeed   => _targetSpeed;

    /// <summary>
    /// If you change baseEulerOffset at runtime, call this to apply it.
    /// </summary>
    public void RecomputeBaseRotation()
    {
        _baseRotation = Quaternion.Euler(baseEulerOffset);
    }
}
