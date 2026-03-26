import time
import pygame
from pymavlink import mavutil

# ============================================================
# CONFIG
# ============================================================

# Change this to match your setup:
# Examples:
#   udpout:192.168.4.1:14550
#   udp:192.168.4.1:14550
#   tcp:192.168.4.1:5760
#   /dev/tty.usbserial-0001
MAVLINK_CONNECTION = "udp:0.0.0.0:14555"
MAVLINK_BAUD = 921600  # only used for serial links

JOYSTICK_INDEX = 0
SEND_HZ = 20
DEADZONE = 0.05

# Radiomaster / pygame axis mapping
# Adjust if needed after testing.
ROLL_AXIS = 0       # RC channel 1
PITCH_AXIS = 1      # RC channel 2
THROTTLE_AXIS = 2   # RC channel 3
YAW_AXIS = 3        # RC channel 4
ARM_AXIS = 4        # RC channel 5
MODE_AXIS = 5       # RC channel 6


# Invert channels if they move the wrong way
INVERT_ROLL = False
INVERT_PITCH = True
INVERT_THROTTLE = False
INVERT_YAW = False

ARM_THRESHOLD = 0.5

# RC channel order for ArduPilot is usually:
# CH1 Roll, CH2 Pitch, CH3 Throttle, CH4 Yaw, CH5 Flight mode / aux
# Here we use CH5 as ARM switch because that is what you asked for.

# ============================================================
# HELPERS
# ============================================================

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def apply_deadzone(value: float, deadzone: float = DEADZONE) -> float:
    if abs(value) < deadzone:
        return 0.0
    return value

MODE_MAP = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
}

def update_flight_mode(master, current_mode):
    msg = master.recv_match(type="HEARTBEAT", blocking=False)
    if msg:
        return MODE_MAP.get(msg.custom_mode, f"UNKNOWN({msg.custom_mode})")
    return current_mode

def maybe_invert(value: float, invert: bool) -> float:
    return -value if invert else value


def axis_to_rc_centered(value: float, invert: bool = False) -> int:
    """
    Map joystick axis -1..1 to RC 1000..2000 with center at 1500.
    Good for roll, pitch, yaw.
    """
    value = apply_deadzone(value)
    value = maybe_invert(value, invert)
    value = clamp(value, -1.0, 1.0)
    return int(1500 + value * 500)


def axis_to_rc_throttle(value: float, invert: bool = False) -> int:
    """
    Map joystick axis -1..1 to throttle 1000..2000.
    """
    value = maybe_invert(value, invert)
    value = clamp(value, -1.0, 1.0)
    return int(((value + 1.0) / 2.0) * 1000 + 1000)


def switch_to_rc(value: float, threshold: float = ARM_THRESHOLD) -> int:
    """
    Two-position switch from axis value to RC.
    """
    return 2000 if value > threshold else 1000


def get_axis_safe(joystick, axis_index: int) -> float:
    if axis_index < joystick.get_numaxes():
        return joystick.get_axis(axis_index)
    return 0.0


def connect_mavlink():
    print(f"Connecting MAVLink: {MAVLINK_CONNECTION}")
    if MAVLINK_CONNECTION.startswith("/dev/"):
        master = mavutil.mavlink_connection(MAVLINK_CONNECTION, baud=MAVLINK_BAUD)
        print("Waiting for heartbeat on serial link...")
        master.wait_heartbeat(timeout=30)
        print(f"Connected to system={master.target_system}, component={master.target_component}")
    elif MAVLINK_CONNECTION.startswith("udpout:"):
        master = mavutil.mavlink_connection(MAVLINK_CONNECTION)
        print("UDP out connection created. Not waiting for heartbeat.")
        # Set manually if needed
        master.target_system = 1
        master.target_component = 1
    else:
        master = mavutil.mavlink_connection(MAVLINK_CONNECTION)
        print("Waiting for heartbeat...")
        master.wait_heartbeat(timeout=10)
        print(f"Connected to system={master.target_system}, component={master.target_component}")

    return master


def init_joystick():
    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    if count == 0:
        raise RuntimeError("No joystick found. Check USB/BLE connection.")

    js = pygame.joystick.Joystick(JOYSTICK_INDEX)
    js.init()

    print(f"Joystick connected: {js.get_name()}")
    print(f"Axes: {js.get_numaxes()}")
    print(f"Buttons: {js.get_numbuttons()}")
    return js
def mode_to_rc(value: float) -> int:

    """
    3-posisjonsbryter:
    ned   -> 1100 -> FLTMODE1 -> ACRO
    midt  -> 1500 -> FLTMODE2 -> GUIDED
    opp   -> 1900 -> FLTMODE3 -> LOITER
    """
    if value < -0.5:
        return 1900
    elif value < 0.5:
        return 1500
    else:
        return 1110

def send_rc_override(master, ch1, ch2, ch3, ch4, ch5, ch6):
    master.mav.rc_channels_override_send(
        master.target_system,
        master.target_component,
        ch1,
        ch2,
        ch3,
        ch4,
        ch5,
        ch6,
        65535,
        65535
    )


# ============================================================
# MAIN
# ============================================================

def main():
    master = connect_mavlink()
    joystick = init_joystick()

    interval = 1.0 / SEND_HZ
    last_print = 0.0
    current_mode = "---"

    print("Starting RC override loop...")
    print("Move sticks and flip the ARM switch.")
    print("Press Ctrl+C to stop.")

    while True:
        pygame.event.pump()

        roll_raw = get_axis_safe(joystick, ROLL_AXIS)
        pitch_raw = get_axis_safe(joystick, PITCH_AXIS)
        throttle_raw = get_axis_safe(joystick, THROTTLE_AXIS)
        yaw_raw = get_axis_safe(joystick, YAW_AXIS)
        arm_raw = get_axis_safe(joystick, ARM_AXIS)
        mode_raw = get_axis_safe(joystick, MODE_AXIS)

        # Match FC channel map from QGC:
        # CH1=Throttle, CH2=Roll, CH3=Pitch, CH4=Yaw, CH5=Arm, CH6=Mode
        ch1 = axis_to_rc_throttle(throttle_raw, INVERT_THROTTLE)
        ch2 = axis_to_rc_centered(roll_raw, INVERT_ROLL)
        ch3 = axis_to_rc_centered(pitch_raw, INVERT_PITCH)
        ch4 = axis_to_rc_centered(yaw_raw, INVERT_YAW)
        ch5 = switch_to_rc(arm_raw)
        ch6 = mode_to_rc(mode_raw)

        send_rc_override(master, ch1, ch2, ch3, ch4, ch5, ch6)

        current_mode = update_flight_mode(master, current_mode)

        now = time.time()
        if now - last_print > 0.25:
            axes = [round(joystick.get_axis(i), 2) for i in range(joystick.get_numaxes())]
            print(
                f"\rMode={current_mode} | "
                f"Axes={axes} | "
                f"RC: ch1={ch1} ch2={ch2} ch3={ch3} ch4={ch4} ch5={ch5} ch6={ch6}",
                end="",
                flush=True
            )
            last_print = now

        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            pygame.quit()
        except Exception:
            pass