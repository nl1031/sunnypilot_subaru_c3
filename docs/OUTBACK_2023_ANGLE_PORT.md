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

## Justin / Jacob alignment

| Item | Behavior |
|------|----------|
| `ES_Distance.Cruise_Fault` | **Not** mapped to `accFaulted` on LKAS_ANGLE (justin) |
| Cruise enabled | `ES_Brake.Cruise_Activated` (jacob + panda safety) |
| Steering angle | **`Steering_2.Steering_Angle`** (jacob + panda `angle_meas` / 0x124 scale) |
| Angle rate limit | ~1°/step all speeds (justin-style soft limit) |
| Inactive 0x124 | Command = measured angle, `LKAS_Request=0`, rolling COUNTER |
| `ES_LKAS_State` when not enabled | Pass through stock ACTIVE/Dash_State (do not force 0) |

### Why C3-on caused EyeSight / LKAS Fault

Harness D + panda `check_relay` **block stock** `ES_LKAS_ANGLE` (0x124). OP must replace it.
If inactive angle was taken from `Steering_Torque` (different scale/source than safety's `Steering_2`), panda **drops** OP TX → EPS sees no valid angle stream → latched LKAS/EyeSight fault until key cycle. C3 off = pass-through stock = no fault.

### Why light wheel input / random faults (vs justin outback-23)

Justin-era panda (`safety_subaru.h` on outback-forester-22):

| Item | justin | modern JacobW-style (was ours) |
|------|--------|--------------------------------|
| Angle meas | `Steering_Torque` × -0.0217 (deg) | `Steering_2` raw (0.01 deg) |
| Rate limit | **1°/TX all speeds** | 5 → 0.8 → **0.15°/TX** with speed |
| Cruise engage bit | `ES_Status` + `ES_STATUS` flag | `ES_Brake` |
| LKAS_ANGLE param bit | `2` | `8` |

Carcontroller uses ~1°/step (justin). If panda only allows 0.15°/TX, **TX is rejected** → missing 0x124 → EPS fault. Light hand torque without `steerOverride` (threshold 80) keeps `LKAS_Request=1` while angle fights → `Steer_Warning` / `Steer_Error`.

**Mitigations (fault / hand-priority era):** safety rate **1°/TX all speeds**; hand-control in carcontroller.

### Road-test: hand OK, slow re-engage, weak on curves (2026-08-05)

Symptoms after hand-priority work:
- Manual priority while engaged: **OK, no EPS fault**
- Release wheel → OP resumes **too late**
- Bends: OP under-steers / late; must intervene or leave lane

Likely causes (code):
1. `ANGLE_OVERRIDE_RELEASE_FRAMES=25` (~0.5 s) pure delay before re-engage
2. Torque enter **25** + soft-yield at **3°** + residual torque **>12** → **false hand-control mid-curve** (road/EPS torque), drops `LKAS_Request`
3. `steeringPressed` threshold **25** → controlsd also pauses lat on curves
4. `steerActuatorDelay=0.1` a bit low for angle look-ahead

**Tuning (opendbc only, no panda reflash required for this step):**
| Param | Was | Now |
|-------|-----|-----|
| TORQUE_ON / OFF | 25 / 12 | **50 / 22** |
| ERR_YIELD | 3° + tq>OFF | **8° + tq≥ON** |
| RELEASE_FRAMES | 25 (~0.5s) | **8 (~0.16s)** |
| steeringPressed | 25 | **50** |
| steerActuatorDelay (Outback 2023) | 0.1 | **0.2** |

If curves still lag with hands off and no false yield: next levers are mild rate raise (must match panda), `steerRatio`, live lateral delay.

### Alerts: highway follow / curves

| Symptom | Likely event | Mitigation on this fork |
|---------|----------------|-------------------------|
| Lead slows → OP "BRAKE!" after stock ACC decelerates | `EventName.fcw` from model `hardBrakePredicted` (stock long) | **Disable OP model/planner FCW when not OP-long** (`selfdrived.py`) |
| Bad corner → "Take Control / Turn Exceeds Steering Limit" | `steerSaturated` | Higher angle sat threshold, honor rate-limit in sat timer, `steerLimitTimer=1.0` for LKAS_ANGLE |
| EPS unhappy | `steerTempUnavailable` from `Steer_Warning` | Fix tracking / hand-control false yield (§ hand-priority) |

**Must rebuild/flash panda** only after `subaru.h` safety change (not for carcontroller-only tuning).

Still experimental.

## Safety note

Experimental. Not upstream-ready. Public-road “finished product” use is not appropriate until validated. Always ready to take over.
