# Outback 2023 Angle Port (C3 / tici)

## Goal

Enable lateral angle control for the **2023 Subaru Outback** (`LKAS_ANGLE`, **Harness D**) on **comma three (C3 / tici)**, based on sunnypilot `master-tici`.

The port uses the Subaru Gen2 angle-control CAN and panda safety design from JacobW, with additional request-transition, driver-override, and rate-limit handling for reliable operation on the Outback 2023 EPS.

## Baseline

| Item | Value |
|------|-------|
| Install branch | `main-c3` |
| Feature/history branch | `outback-2023-angle-tici` |
| sunnypilot base | `master-tici` @ `737a6c423` |
| opendbc branch | `main-c3` @ `43148a3` |
| Hardware | comma three, Subaru Harness D |
| AGNOS | 12.8, or the version required by `launch_env.sh` |
| Status | Road-tested and suitable for continued long-term testing; still experimental |

## Port design

### Vehicle and safety configuration

- Enable control for `LKAS_ANGLE` on non-release builds instead of leaving the vehicle in `dashcamOnly` mode.
- Configure `steerControlType` as angle control.
- Use `GEN2 | LKAS_ANGLE` as the panda `safetyParam` (normally `9`).
- Allow Subaru LKAS angle safety initialization on this fork without requiring `ALLOW_DEBUG`.
- Keep the controller and panda angle-rate tables identical. Any change to `subaru.h` requires rebuilding and flashing panda.

### CAN signals and messages

| Purpose | Signal/message |
|---------|----------------|
| Steering-angle measurement | `Steering_2.Steering_Angle` |
| Cruise-enabled state | `ES_Brake.Cruise_Activated` |
| Lateral-control transmit | `ES_LKAS_ANGLE` (`0x124`) on bus 0 |
| Disabled LKAS dash state | `LKAS_Dash_State=0` |

The controller and panda safety code must use the same measured-angle source. Harness D relay checking blocks the stock `0x124`, so openpilot must provide a continuous valid replacement message.

### Engage and request handling

- Re-anchor `apply_angle_last` to the live measured steering angle when lateral control engages.
- While lateral control is inactive, transmit the measured angle with `LKAS_Request=0`.
- On the first `LKAS_Request` transition from `0` to `1`, command the measured angle, then rate-limit subsequent commands toward the desired angle.
- Delay engagement when the steering angle or angular rate is too large, or when the driver is actively steering.
- Use hard driver hand-yield only. Disable soft yield based on desired/measured-angle error because it can cause request chatter.
- Resume only after the minimum yield hold and the required number of calm frames.

### Final control parameters

| Parameter | Value |
|-----------|-------|
| Angle-rate breakpoints | `[0, 5, 35]` |
| Angle rates | `[3.5, 2.2, 1.0]` °/TX at about 50 Hz |
| Hand-yield / resume torque | `55 / 35` |
| `steeringPressed` threshold | `55` |
| Minimum yield | `8` steering frames (about 0.16 s) |
| Normal resume calm period | `4` frames (about 0.08 s) |
| Large-angle threshold / calm period | `22° / 6` frames |
| Engage maximum angle / rate | `35° / 30°/s` |
| `steerActuatorDelay` | `0.18` s |
| `steerLimitTimer` | `0.8` s |
| First active command | Measured steering angle |
| Soft yield | Disabled |

### Fault and UI handling

- Treat `Cruise_Fault` as `carFaultedNonCritical` for stock longitudinal control rather than mapping it to `accFaulted`.
- Use `Steer_Error_1` to report a permanent steering fault through `steerFaultPermanent` / `steerUnavailable`.
- Set the Subaru angle saturation threshold to `6°` and honor controller rate limiting to reduce false steering-limit alerts.
- Disable openpilot model/planner FCW when EyeSight stock longitudinal control owns braking. Stock FCW/AEB remains responsible for collision warnings and intervention.

## Key files

| File | Responsibility |
|------|----------------|
| `opendbc/car/subaru/interface.py` | Vehicle enablement, safety parameters, actuator delay, and limit timer |
| `opendbc/car/subaru/carcontroller.py` | Angle control, engage anchoring, hand yield, and request transitions |
| `opendbc/car/subaru/carstate.py` | Steering angle, cruise state, faults, and driver-override threshold |
| `opendbc/car/subaru/values.py` | Angle-rate and yield/engagement constants |
| `opendbc/car/subaru/subarucan.py` | `0x124` and LKAS HUD message packing |
| `opendbc/safety/modes/subaru.h` | Subaru angle TX/RX safety checks and matching rate limits |
| `opendbc/car/subaru/test_carcontroller.py` | Controller tests for re-anchor, yield, and first active command |
| `opendbc/safety/tests/test_subaru.py` | Gen2 angle-safety tests |
| `selfdrive/controls/lib/latcontrol_angle.py` | Subaru saturation threshold and steer-limit handling |
| `selfdrive/selfdrived/selfdrived.py` | FCW behavior with stock longitudinal control |

## Validation requirements

- Detect the vehicle as `SUBARU_OUTBACK_2023` with `dashcamOnly=False`.
- Confirm `safetyParam` includes the `LKAS_ANGLE` bit and panda is flashed with the same rate table as the controller.
- Verify that ACC engagement enables lateral control and driver override cleanly drops the request.
- Test request re-engagement without an angle step or `safetyTxBlocked` event.
- Run the Subaru car-controller and panda safety tests after changing angle-control behavior.
- Continue highway, multi-condition, and multi-day durability testing; inspect `/data/can_faults` after any EPS/LKAS fault.

## Safety note

**Experimental.** This port is not upstream-ready or a finished product for public-road reliance. Always remain ready to take over. Safety and panda changes should receive dual review before flashing whenever possible.
