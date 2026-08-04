# Outback 2023 Angle Port (C3 / master-tici)

## Goal

Enable **lateral control** for Subaru Outback 2023 (LKAS_ANGLE, Harness D) on **comma three**, based on sunnypilot `master-tici`.

## Base

| Item | Value |
|------|--------|
| Tree | `/opt/develop/c3/sunnypilot_tici` |
| Upstream | `master-tici` @ `737a6c423` |
| Branch | `outback-2023-angle` |
| AGNOS | 12.8 (tici) |

## References

| Tree | Role |
|------|------|
| JacobW `openpilot_jacobwaller` | Angle TX, safety 0x124, carstate Steering_2 / ES_Brake |
| openpilot `outback-23` | Historical proof of engage (old stack) |

## Audit (before port)

| Module | master-tici | Needed |
|--------|-------------|--------|
| Platform `OUTBACK_2023` + Harness D | Present | Keep |
| `dashcamOnly` on LKAS_ANGLE | Locked (interface + `_get_params_sp`) | Unlock for experimental |
| `steerControlType.angle` | Set | Keep |
| `CarController` | Torque only | Angle path + `ES_LKAS_ANGLE` |
| `create_steering_control_angle` | Exists unused | Use |
| Safety `0x124` / `LKAS_ANGLE` param | Missing | Port from JacobW |
| carstate angle / cruise | Steering_Torque / CruiseControl | Steering_2 / ES_Brake for LKAS_ANGLE |
| Fingerprints | Partial OUTBACK_2023 | Extend as needed |

## Code changes (this branch)

| File | Change |
|------|--------|
| `car/subaru/interface.py` | Unlock LKAS_ANGLE dashcam; set `SubaruSafetyFlags.LKAS_ANGLE` |
| `car/subaru/carcontroller.py` | `handle_angle_lateral` → `ES_LKAS_ANGLE` |
| `car/subaru/carstate.py` | `Steering_2` angle + `ES_Brake` cruise for LKAS_ANGLE |
| `car/subaru/values.py` | `ANGLE_LIMITS`, `SubaruSafetyFlags.LKAS_ANGLE` |
| `car/subaru/fingerprints.py` | Extra OUTBACK_2023 FW blobs |
| `safety/modes/subaru.h` | TX/RX/checks for 0x124 angle mode |

## Device install (C3)

1. Ensure flash.comma.ai completed successfully  
2. **Do not** install sunnypilot/`openpilot` **master**  
3. Baseline check (optional): install `staging-tici` / `master-tici` first  
4. Deploy this branch:
   - SSH: rsync/git clone this tree to `/data/openpilot` on device, or  
   - Push to GitHub and use `installer.comma.ai/<user>/outback-2023-angle`  
5. Hardware: **Harness D**, Outback 2023 EyeSight  
6. If fingerprint fails: force fingerprint / collect FW via SSH logs  

## Validation checklist

- [ ] Boots on C3 without Unsupported firmware  
- [ ] Car recognized as Outback 2023 (or forced)  
- [ ] Not dashcamOnly (`CarParams` / UI)  
- [ ] Engage ACC → lateral engages; wheel follows  
- [ ] No immediate EPS fault  
- [ ] Cancel / override works  

## Justin alignment (outback-23 behavior)

To reduce false **Cruise Fault** disengages (as seen on stock-long angle cars):

| Item | Behavior (match justin) |
|------|-------------------------|
| `ES_Distance.Cruise_Fault` | **Not** mapped to `accFaulted` on LKAS_ANGLE |
| Cruise enabled | `ES_Status.Cruise_Activated` |
| Steering angle | `Steering_Torque.Steering_Angle` |
| Angle rate limit | ~1°/step all speeds |

Still experimental. EyeSight may still set the bit on the bus; OP no longer hard-faults on it for angle cars.

## Safety note

Experimental. Not upstream-ready. Public-road “finished product” use is not appropriate until validated. Always ready to take over.
