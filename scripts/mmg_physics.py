#!/usr/bin/env python3
"""MMG ship step over UDP. Unreal sends the sea state and the hull state; this process returns the next motion.

Fuel leaves this process as tonnes per hour. It is `fuel_rate_kg_s(shaft_kW) * 3.6`,
with `fuel_rate_kg_s` in kilograms per second at 175 g/kWh.

Yaw is a first-order Nomoto response. The steady turning diameter is `2*U/r`
after the yaw rate settles. That is the diameter used for the 960 m reference.
The tactical diameter, the lateral transfer at a 180 degree heading change, is
a different measurement and is not substituted for it.
"""

import math
import socket
import struct
import sys

REQ = b"MMG1"
REP = b"RMG1"
HEADER = struct.Struct("<4sIIffffffff")
SHIP = struct.Struct("<I18f")
REPLY = struct.Struct("<I9f")
ACK = struct.Struct("<4s6f")

RHO_WATER = 1025.0
RHO_AIR = 1.225
GRAVITY = 9.81
SFOC_G_PER_KWH = 175.0
# Reference hull for the 15.5 kn, 35 degree turning circle. This is the
# container ship: it is the only fleet hull whose service speed is above
# 15.5 kn, so the approach speed is actually reachable.
REFERENCE_LENGTH_M = 300.0
REFERENCE_SPEED_KN = 15.5
REFERENCE_RUDDER_DEG = 35.0
# Steady turning diameter 2*U/r, not the tactical diameter. With the
# advance below, these two numbers identify the nondimensional Nomoto
# gain and time constant. See scripts/test_turning_circle.py.
REFERENCE_STEADY_DIAMETER_M = 960.0
REFERENCE_ADVANCE_M = 992.0
KNOT_MS = 0.514444


def fuel_rate_kg_s(power_kw):
    """Return shaft fuel flow in kg/s at the adopted 175 g/kWh.

    power_kw * 175 / 1000 / 3600. The 1000 converts grams to kilograms.
    """
    return power_kw * SFOC_G_PER_KWH / 3_600_000.0


def nomoto_coefficients(length_m, surge_ms):
    """First-order Nomoto gain (1/s per radian of rudder) and time constant (s).

    K' and T' are constant. K = K' * U / L and T = T' * L / U, so the steady
    turning diameter of the reference hull is independent of speed and the
    advance matches the reference only at the reference speed.
    """
    delta = math.radians(REFERENCE_RUDDER_DEG)
    k_prime = (2.0 * REFERENCE_LENGTH_M) / (REFERENCE_STEADY_DIAMETER_M * delta)
    # T' from the reference advance. 86 s is the lag that puts the 90 degree
    # advance on 992 m when the steady diameter is 960 m; the turning-circle
    # test is the check that the integrated ship still lands there.
    t_prime = 86.0 * (REFERENCE_SPEED_KN * KNOT_MS) / REFERENCE_LENGTH_M
    speed = max(abs(surge_ms), 0.4)
    length = max(length_m, 1.0)
    return k_prime * speed / length, t_prime * length / speed


def wrap_deg(degrees):
    while degrees > 180.0:
        degrees -= 360.0
    while degrees < -180.0:
        degrees += 360.0
    return degrees


def direction(degrees, speed):
    radians = math.radians(degrees)
    return (math.cos(radians) * speed, math.sin(radians) * speed)


def wave_surface(x_cm, y_cm, amplitude_cm, direction_deg, sim_time):
    if amplitude_cm <= 0.0:
        return 0.0
    radians = math.radians(direction_deg)
    wave_number = 2.0 * math.pi / 9000.0
    omega = math.sqrt(980.0 * wave_number)
    phase = wave_number * (x_cm * math.cos(radians) + y_cm * math.sin(radians)) - omega * sim_time
    return amplitude_cm * math.sin(phase)


def step_once(ship, env, dt):
    yaw_deg, surge, sway, yaw_rate, rudder, desired_ms = ship[0:6]
    mass, length_cm, beam_cm, draft_cm, freeboard_cm, power_w, wetted, frontal, lateral, service_cms = ship[6:16]
    x_cm, y_cm = ship[16], ship[17]
    length_m = max(length_cm / 100.0, 1.0)
    beam_m = max(beam_cm / 100.0, 1.0)
    draft_m = max(draft_cm / 100.0, 0.5)
    yaw = math.radians(yaw_deg)
    forward = (math.cos(yaw), math.sin(yaw))
    right = (-math.sin(yaw), math.cos(yaw))
    ground = (forward[0] * surge + right[0] * sway, forward[1] * surge + right[1] * sway)
    current = direction(env["current_deg"], env["current_cms"])
    wind = direction(env["wind_deg"], env["wind_cms"])
    rel_water = (ground[0] - current[0], ground[1] - current[1])
    rel_wind = (wind[0] - ground[0], wind[1] - ground[1])
    rel_surge = rel_water[0] * forward[0] + rel_water[1] * forward[1]
    rel_sway = rel_water[0] * right[0] + rel_water[1] * right[1]
    wind_surge = rel_wind[0] * forward[0] + rel_wind[1] * forward[1]
    wind_sway = rel_wind[0] * right[0] + rel_wind[1] * right[1]
    rel_surge_ms = rel_surge / 100.0
    rel_sway_ms = rel_sway / 100.0
    wind_surge_ms = wind_surge / 100.0
    wind_sway_ms = wind_sway / 100.0
    resist = 0.5 * RHO_WATER * 0.0018 * wetted * rel_surge_ms * abs(rel_surge_ms)
    sway_drag = 0.5 * RHO_WATER * 0.85 * length_m * draft_m * rel_sway_ms * abs(rel_sway_ms)
    wind_surge_n = 0.5 * RHO_AIR * 0.8 * frontal * wind_surge_ms * abs(wind_surge_ms)
    wind_sway_n = 0.5 * RHO_AIR * 0.9 * lateral * wind_sway_ms * abs(wind_sway_ms)
    encounter = math.radians(wrap_deg(env["wave_deg"] - yaw_deg))
    head = max(0.0, -math.cos(encounter))
    amplitude_m = env["wave_cm"] / 100.0
    wave_resist = 0.5 * RHO_WATER * GRAVITY * amplitude_m * amplitude_m * beam_m * 0.35 * head
    surge_ms = surge / 100.0
    accel_cmd = max(-0.04, min(0.05, (desired_ms - surge_ms) * 0.2))
    bollard = power_w * 0.45 / 8.0
    needed = accel_cmd * mass * 1.08 + resist + wave_resist - min(wind_surge_n, resist)
    thrust = max(-0.25 * bollard, min(bollard, needed))
    useful = max(0.0, resist + wave_resist - wind_surge_n)
    shaft_w = max(0.0, min(power_w, useful * max(surge_ms, 0.4) / 0.55))
    fuel_tph = fuel_rate_kg_s(shaft_w / 1000.0) * 3.6
    surge_acc = (thrust - resist - wave_resist + wind_surge_n) / (mass * 1.08)
    current_sway = current[0] * right[0] + current[1] * right[1]
    sway_acc = (wind_sway_n - sway_drag) / (mass * 1.5) + (current_sway - sway) / 100.0 / 8.0
    surge = max(0.0, min(service_cms, surge + surge_acc * 100.0 * dt))
    sway = max(-400.0, min(400.0, sway + sway_acc * 100.0 * dt))
    nomoto_k, nomoto_t = nomoto_coefficients(length_m, surge / 100.0)
    wind_yaw = (wind_sway_n / max(mass * length_m, 1.0)) * 0.015
    yaw_acc = (nomoto_k * math.radians(rudder) + wind_yaw - yaw_rate) / nomoto_t
    yaw_rate = max(-0.12, min(0.12, yaw_rate + yaw_acc * dt))
    yaw_deg = wrap_deg(yaw_deg + math.degrees(yaw_rate) * dt)
    bow_x = x_cm + math.cos(yaw) * length_cm * 0.45
    bow_y = y_cm + math.sin(yaw) * length_cm * 0.45
    stern_x = x_cm - math.cos(yaw) * length_cm * 0.45
    stern_y = y_cm - math.sin(yaw) * length_cm * 0.45
    port_x = x_cm - right[0] * beam_cm * 0.45
    port_y = y_cm - right[1] * beam_cm * 0.45
    starboard_x = x_cm + right[0] * beam_cm * 0.45
    starboard_y = y_cm + right[1] * beam_cm * 0.45
    mid = wave_surface(x_cm, y_cm, env["wave_cm"], env["wave_deg"], env["time"])
    bow = wave_surface(bow_x, bow_y, env["wave_cm"], env["wave_deg"], env["time"])
    stern = wave_surface(stern_x, stern_y, env["wave_cm"], env["wave_deg"], env["time"])
    port = wave_surface(port_x, port_y, env["wave_cm"], env["wave_deg"], env["time"])
    starboard = wave_surface(starboard_x, starboard_y, env["wave_cm"], env["wave_deg"], env["time"])
    pitch = max(-8.0, min(8.0, math.degrees(math.atan2(bow - stern, length_cm * 0.9))))
    roll = max(-12.0, min(12.0, math.degrees(math.atan2(starboard - port, beam_cm))))
    return (yaw_deg, surge, sway, yaw_rate, rudder, desired_ms, mass, length_cm, beam_cm, draft_cm, freeboard_cm, power_w, wetted, frontal, lateral, service_cms, x_cm, y_cm), fuel_tph, mid, pitch, roll


def integrate(ship, env, dt):
    fuel = 0.0
    heave = 0.0
    pitch = 0.0
    roll = 0.0
    remaining = max(0.0, dt)
    if remaining <= 0.0:
        _, fuel, heave, pitch, roll = step_once(ship, env, 0.0)
        return ship, fuel, heave, pitch, roll
    while remaining > 1.0e-5:
        step_dt = min(0.02, remaining)
        ship, fuel, heave, pitch, roll = step_once(ship, env, step_dt)
        env["time"] += step_dt
        remaining -= step_dt
    return ship, fuel, heave, pitch, roll


def compass_deg(degrees):
    if not math.isfinite(degrees):
        return None
    return degrees % 360.0


def clamp_environment(wind_cms, wind_deg, current_cms, current_deg, wave_cm, wave_deg):
    """Accept the UDP sea state or refuse a non-finite packet.

    Ranges match the fleet panel: wind 0-35 m/s, current 0-3 m/s, waves 0-6 m.
    Directions are degrees from +X toward +Y. Wave length stays 90 m inside
    wave_surface; this function does not add a period input.
    """
    wind_deg = compass_deg(wind_deg)
    current_deg = compass_deg(current_deg)
    wave_deg = compass_deg(wave_deg)
    numbers = (wind_cms, wind_deg, current_cms, current_deg, wave_cm, wave_deg)
    if wind_deg is None or current_deg is None or wave_deg is None or not all(math.isfinite(v) for v in numbers):
        return None
    return {
        "wind_cms": min(3500.0, max(0.0, wind_cms)),
        "wind_deg": wind_deg,
        "current_cms": min(300.0, max(0.0, current_cms)),
        "current_deg": current_deg,
        "wave_cm": min(600.0, max(0.0, wave_cm)),
        "wave_deg": wave_deg,
    }


def handle(payload):
    if len(payload) < HEADER.size or payload[:4] != REQ:
        return None
    magic, seq, count, dt, sim_time, wind_cms, wind_deg, current_cms, current_deg, wave_cm, wave_deg = HEADER.unpack_from(payload, 0)
    clamped = clamp_environment(wind_cms, wind_deg, current_cms, current_deg, wave_cm, wave_deg)
    if clamped is None or not math.isfinite(dt) or not math.isfinite(sim_time):
        return REP + struct.pack("<II", seq, 0) + b"REJ1"
    env = {
        "time": sim_time,
        "wind_cms": clamped["wind_cms"],
        "wind_deg": clamped["wind_deg"],
        "current_cms": clamped["current_cms"],
        "current_deg": clamped["current_deg"],
        "wave_cm": clamped["wave_cm"],
        "wave_deg": clamped["wave_deg"],
    }
    offset = HEADER.size
    replies = [REP, struct.pack("<II", seq, count)]
    for _ in range(count):
        if offset + SHIP.size > len(payload):
            break
        values = SHIP.unpack_from(payload, offset)
        offset += SHIP.size
        ship_id = values[0]
        x_cm, y_cm, yaw_deg, surge, sway, yaw_rate, rudder, desired_ms, mass, length_cm, beam_cm, draft_cm, freeboard_cm, power_w, wetted, frontal, lateral, service_cms = values[1:]
        ship = (yaw_deg, surge, sway, yaw_rate, rudder, desired_ms, mass, length_cm, beam_cm, draft_cm, freeboard_cm, power_w, wetted, frontal, lateral, service_cms, x_cm, y_cm)
        ship, fuel, heave, pitch, roll = integrate(ship, dict(env), dt)
        yaw_deg, surge, sway, yaw_rate = ship[0], ship[1], ship[2], ship[3]
        replies.append(REPLY.pack(ship_id, surge, sway, yaw_rate, yaw_deg, heave, pitch, roll, fuel, env["wave_cm"]))
    replies.append(ACK.pack(
        b"ACK1",
        env["wind_cms"],
        env["wind_deg"],
        env["current_cms"],
        env["current_deg"],
        env["wave_cm"],
        env["wave_deg"],
    ))
    return b"".join(replies)


def self_test():
    calm = {"time": 0.0, "wind_cms": 400.0, "wind_deg": 30.0, "current_cms": 25.0, "current_deg": 40.0, "wave_cm": 40.0, "wave_deg": 30.0}
    gale = {"time": 0.0, "wind_cms": 2200.0, "wind_deg": 210.0, "current_cms": 120.0, "current_deg": 130.0, "wave_cm": 400.0, "wave_deg": 200.0}
    base = (20.0, 450.0, 0.0, 0.0, -8.0, 6.0, 1.45e8, 30000.0, 4280.0, 1450.0, 800.0, 4.57e7, 18000.0, 340.0, 2400.0, 1157.0, 0.0, 0.0)
    for name, env in (("calm", calm), ("gale", gale)):
        ship = base
        fuel = heave = sway = peak = 0.0
        clock = dict(env)
        for _ in range(400):
            ship, fuel, heave, _, _ = integrate(ship, clock, 0.05)
            sway = ship[2]
            peak = max(peak, abs(heave))
        print(f"{name} surge {ship[1] / 100.0:.2f} m/s sway {sway / 100.0:.2f} m/s heave-peak {peak / 100.0:.2f} m fuel {fuel:.2f} t/h")


def serve():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 9001))
    print("MMG physics listening on 127.0.0.1:9001", flush=True)
    while True:
        payload, addr = sock.recvfrom(65535)
        reply = handle(payload)
        if reply:
            sock.sendto(reply, addr)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        serve()
