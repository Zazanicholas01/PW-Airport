from typing import Dict, Optional
import csv, time

POS_CSV = 'pos.csv'

######################### SAVE POSITIONS TO CSV ######################################

def append_position_to_csv(target_id: str, t_sim: Optional[float], pos: Dict[str, float]) -> None:
    exists = POS_CSV.exists()
    with POS_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["target_id", "t_sim", "x", "y", "z"])
        w.writerow([
            target_id,
            "" if t_sim is None else f"{t_sim:.3f}",
            f"{pos['x']:.6f}",
            f"{pos['y']:.6f}",
            f"{pos['z']:.6f}",
        ])

############################# SAVE EVENTS LOGS ###########################################

ROUTE_LOG_CSV = 'route_log.csv'

def log_route_event(target_id: str, event: str, ref_msg_id: str | None, t_sim: Optional[float]) -> None:
    exists = ROUTE_LOG_CSV.exists()
    with ROUTE_LOG_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["target_id", "event", "t_host", "t_sim", "ref_msg_id"])
        w.writerow([target_id, event, f"{time.time():.3f}", "" if t_sim is None else f"{t_sim:.3f}", ref_msg_id or ""])

############################# SAVE SPEED LOGS ############################################

SPEED_LOG_CSV = 'speed_log.csv'

def log_speed_change(target_id: str, cmd_id: str, speed: float, accel_up: Optional[float], accel_down: Optional[float]) -> None:
    exists = SPEED_LOG_CSV.exists()
    with SPEED_LOG_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["target_id", "t_host", "cmd_id", "speed_mps", "accel_up", "accel_down"])
        w.writerow([target_id, f"{time.time():.3f}", cmd_id, f"{speed:.3f}",
                    "" if accel_up is None else f"{accel_up:.3f}",
                    "" if accel_down is None else f"{accel_down:.3f}"])
