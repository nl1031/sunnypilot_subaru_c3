# Outback 2023 Angle Port (C3 / tici)

## Goal

Enable **lateral control** for **Subaru Outback 2023** (`LKAS_ANGLE`, **Harness D**) on **comma three (C3 / tici)**, based on sunnypilot `master-tici`. CAN / safety design follows **JacobW** (`openpilot_jacobwaller`); fault-hardening and rate tuning come from on-road iteration (2026-08-04 … 2026-08-06).


## Status (2026-08-07)

| Item | Value |
|------|--------|
| **Current tree (dev machine)** | Curve-authority stack — hard hand-yield, Request `0→1` first frame `cmd=meas`, angle rate **3.0 / 2.0 / 1.0** °/TX |
| Branch | `outback-2023-angle-tici` |
| GitHub (last pushed baseline) | https://github.com/nl1031/sunnypilot_subaru_c3/tree/outback-2023-angle-tici |
| opendbc | https://github.com/nl1031/opendbc/tree/outback-2023-angle-tici |
| AGNOS | **12.6** (match office C3; see `launch_env.sh`) |
| Tree (dev machine) | `/opt/develop/c3/sunnypilot_subaru_c3` |
| Working tree | opendbc rate/yield/delay changes may be **local / not yet committed** — verify before relying on remote tip |

**Road result (device-deployed code):**

| Stage | Result |
|-------|--------|
| Pure Jacob (~5 km) | Usable lateral; **~2×** `LKAS Fault: Restart the Car` |
| Aggressive mitigations (`2a`–`2d`) | **Regressed** — faults sooner / lat flaky |
| Routes **33 / 36** | Request chatter + `0→1` step > rate limit → EPS latch |
| Route **37** (~12:40–47) | **No UI EPS/LKAS fault**; enable ~153 s; `sfp≈0` |
| After 1°/TX flat + sticky yield | Stable but **slow / understeery** in curves |
| 2.5 / 1.6 / 1.0 + looser yield | Still felt slow on turns |
| **Current (3.0 / 2.0 / 1.0 + delay 0.18 + looser holdoff)** | Code ready; **must reflash panda** then road-test |

---

## Base / references

| Item | Value |
|------|--------|
| Upstream base | sunnypilot `master-tici` @ `737a6c423` |
| JacobW | `/opt/develop/c3/openpilot_jacobwaller` — angle TX, safety 0x124, `Steering_2` / `ES_Brake`, engage re-anchor |
| justin `outback-23` | Historical proof of engage (old stack); Cruise_Fault / soft rate ideas |
| Harness | **Subaru D** |

---

## Current code behavior

| Item | Behavior |
|------|----------|
| Unlock control | `dashcamOnly` for `LKAS_ANGLE` only when `is_release` (non-release branch can control) |
| `safetyParam` | `GEN2 \| LKAS_ANGLE` (e.g. **9**) |
| `steerControlType` | **angle** |
| Steering measure | **`Steering_2.Steering_Angle`** (matches panda `angle_meas`) |
| Cruise enabled | **`ES_Brake.Cruise_Activated`** (matches panda PCM check) |
| Lateral TX | **`ES_LKAS_ANGLE` (0x124)** on bus 0 |
| Engage | Re-anchor `apply_angle_last` to live measured angle; optional **hold-off** if \|angle\| large / not calm / hands fighting |
| Inactive / not lat active | Command angle = measured, `LKAS_Request=0` |
| Request **0→1** first frame | **`cmd = meas`** (Δangle ≈ 0 vs last TX), then rate-limit toward desired — fixes route-36 dropouts |
| Angle rate (CC + panda) | **`[0, 5, 35] → [3.0, 2.0, 1.0]`** °/TX @ ~50 Hz — **must stay in sync** (`values.py` ↔ `subaru.h`, **3 breakpoints only**) |
| Hand yield | Hard only (no soft yield): torque ≥ **55** → `LKAS_Request=0`; resume ≤ **35** after min hold + calm frames |
| Min yield / calm | **8** STEER_STEP frames (~0.16 s) + **4** calm (~0.08 s); large \|meas\| ≥22° uses **6** calm frames |
| Soft yield (`\|des−meas\|` + residual torque) | **Off** — caused Request chatter (route 33) |
| Resume \|des−meas\| gate | **Removed** — kept Request=0 too long then snapped (route 36) |
| `Cruise_Fault` (stock long + LKAS_ANGLE) | **Non-critical** (`carFaultedNonCritical`), not `accFaulted` — avoids sticky “Cruise Fault: Restart” |
| `steeringPressed` threshold (LKAS_ANGLE) | **40** |
| Outback 2023 delays | `steerActuatorDelay=0.18`, `steerLimitTimer=0.8` |
| `ES_LKAS_State` when disabled | Jacob: **`LKAS_Dash_State=0`** |
| LKAS_ANGLE safety init | Enabled **outside** `ALLOW_DEBUG` on this fork (non-debug panda still accepts param bit 8) |

### Key parameters (2026-08-07)

| Parameter | Value |
|-----------|--------|
| `ANGLE_LIMITS` | speeds `[0, 5, 35]` → rates `[3.0, 2.0, 1.0]` °/TX |
| `LKAS_ANGLE_HAND_YIELD` / `HAND_RESUME` | **55 / 35** |
| `LKAS_ANGLE_YIELD_MIN_FRAMES` | **8** (~0.16 s) |
| `LKAS_ANGLE_RESUME_CALM_FRAMES` | **4** (~0.08 s) |
| `LKAS_ANGLE_LARGE_ANGLE_DEG` / `CALM` | **22° / 6** (~0.12 s) |
| `LKAS_ANGLE_ENGAGE_MAX_ANGLE` / `RATE` | **35° / 30°/s** |
| `steerActuatorDelay` (Outback/Ascent 2023) | **0.18** |
| 0→1 first frame | **cmd = meas** |
| soft yield | **disabled** |

### Rate evolution (controller + panda)

| Stage | °/TX (low / mid / high) | Note |
|-------|-------------------------|------|
| Jacob baseline | 5 / 0.8 / **0.15** | Highway 0.15 often → `safetyTxBlocked` |
| Flat stable | **1 / 1 / 1** | Route 37 OK; felt slow |
| Responsive v1 | **2.5 / 1.6 / 1.0** | Still understeery on turns |
| **Current curve authority** | **3.0 / 2.0 / 1.0** | Low/mid bump; highway floor 1° |

Any change to the rate table requires **rebuild + flash panda**.

### Key files

| File | Role |
|------|------|
| `opendbc/car/subaru/interface.py` | dashcam / safety param / Outback delay & timer |
| `opendbc/car/subaru/carcontroller.py` | `handle_angle_lateral` (yield, hold-off, 0→1 meas) |
| `opendbc/car/subaru/carstate.py` | `Steering_2`, `ES_Brake`, Cruise_Fault, press threshold |
| `opendbc/car/subaru/values.py` | `ANGLE_LIMITS`, yield/holdoff constants, platforms |
| `opendbc/car/subaru/subarucan.py` | pack 0x124 / HUD messages |
| `opendbc/car/subaru/test_carcontroller.py` | re-anchor, yield, 0→1 unit tests |
| `opendbc/safety/modes/subaru.h` | 0x124 TX/RX, angle checks, **same** rate table |
| `opendbc/safety/tests/test_subaru.py` | Gen2 angle safety tests |
| `selfdrive/debug/can_fault_ringlog.py` | onroad CAN ring buffer around faults → `/data/can_faults` |
| `selfdrive/controls/lib/latcontrol_angle.py` | Subaru sat threshold **6°**; honor steer-limited |
| `selfdrive/selfdrived/selfdrived.py` | stock-long: disable OP model/planner **FCW** |

---

## Fault model (why EPS latches)

1. **Harness D + panda `check_relay`** block stock **0x124**. OP must continuously send a valid substitute. Dropped or illegal TX → EPS **LKAS / EyeSight latch** (often needs **key cycle**; C3 reboot not required).
2. **Angle source mismatch** (e.g. inactive cmd from `Steering_Torque` while safety uses `Steering_2`) → TX rejected.
3. **Rate table too tight** (Jacob **0.15°/TX** highway) vs controller command → `safetyTxBlocked`.
4. **Request 0↔1 chatter** (soft yield) → EPS sees illegal control stream (route **33**).
5. **Long Request=0 then sudden 0→1** with first step larger than rate limit (route **36**) → fixed by **first active frame `cmd=meas`**.
6. **Over-aggressive hand priority / rate gates** without re-anchor rules → worse faults (routes `2a`–`2d`).

Alert path: `Steer_Error_1` → `steerFaultPermanent` → `steerUnavailable` / UI **“LKAS Fault: Restart the Car”**.

---

## Road-test log (summary)

### Pure Jacob (~5 km) — early baseline

- Lateral usable; more stable than pre-Jacob experiments.
- **~2×** permanent LKAS fault over ~5 km.
- Key cycle clears EPS latch.

### Aggressive mitigations — routes `2a`–`2d` (regressed)

| Change | Result |
|--------|--------|
| 1°/TX all speeds + hand priority (tq 45/20) | Faulted quickly at low speed (~25–30 km/h) |
| Tighter hand/rate gates (`2d`) | Many `steerOverride`; cmd drifted from meas then EPS latch |

**Lesson:** do not stack aggressive hand-priority + rate gates without **re-anchor + cmd≈meas on re-request**. Prefer **one change at a time**.

### Fault loop (2026-08-06 afternoon)

| Route / time | Observation | Fix |
|--------------|-------------|-----|
| `2e` / **30** | LKAS fault; `txBlocked` | Rate / cmd consistency |
| **33** ~12:16 | Request 0↔1 chatter | Drop soft yield; hard yield + min hold + calm |
| **36** ~12:33 | Long Request=0 then 0→1 dA too large | First Request=1 frame: **cmd = meas** |
| **37** ~12:40–47 | **No UI fault**; enable ~153 s | Keep anti-chatter + 0→1 meas |
| Post-37 | Slow tracking | Raise rates to **2.5 / 1.6 / 1.0**, loosen yield |
| Post 2.5/1.6 | Still slow on turns | **3.0 / 2.0 / 1.0**, delay **0.18**, looser holdoff |

`can_fault_ringlog` writes snippets under `/data/can_faults/` (e.g. `canfault_*_steerFaultPermanent.log`). Device logs/routes were cleared **2026-08-06 12:50** for clean follow-up tests.

### Other notes

- C3 **RTC is unreliable** (often stuck near 1970). Use phone hotspot / office Wi‑Fi for NTP before a drive so route mtimes are useful. Internal `logMonoTime` stays consistent within a drive.
- Device may show **UnregisteredDevice** in office tests; local rlog/qlog still under `/data/media/0/realdata/`.
- loggerd on tici can be flaky; swaglog + `can_fault_ringlog` remain primary debug sources.

---

## Experiments kept in git history

| opendbc / parent tip (examples) | Intent |
|----------------------------------|--------|
| `d4288cd` / pure Jacob port | Jacob-aligned angle control |
| `830e4a7` | 1°/TX + hand priority 45 + ES_LKAS_State passthrough |
| `7039c40` | Earlier yield + rate-gated re-engage |
| `0b4c207` / `21904c733` | Restore pure Jacob after regression |
| Local working tree (post–route 37) | Hard yield, 0→1 meas, **2.5 / 1.6 / 1.0** rates |

Do not assume remote HEAD matches the device; compare hashes and flash status.

---

## Device install / update (C3)

1. AGNOS **12.6** (or match `launch_env.sh` / device `/VERSION`).  
2. **Do not** install generic sunnypilot/openpilot **master** (non-tici).  
3. Deploy branch to `/data/openpilot`:

```bash
# Example rsync from dev machine
rsync -avz --exclude '.git/' --exclude '*/.git/' --exclude '__pycache__/' \
  /opt/develop/c3/sunnypilot_subaru_c3/ comma:/data/openpilot/
```

4. Hardware: **Harness D**, Outback 2023 EyeSight.  
5. After any change to **`subaru.h`**: stop manager, rebuild and flash panda, clear CarParams cache, relaunch:

```bash
ssh comma 'source /usr/local/venv/bin/activate
  export PYTHONPATH=/data/openpilot
  cd /data/openpilot
  # stop manager / pandad first
  python3 panda/board/flash.py
  rm -f /data/params/d/CarParams /data/params/d/CarParamsCache \
        /data/params/d/CarParamsPersistent
  # then launch_openpilot.sh (or reboot)
'
```

6. Fingerprint: force / extend FW if needed; confirm `SUBARU_OUTBACK_2023`, `dashcamOnly=False`, `safetyParam` includes LKAS_ANGLE (bit 8).  
7. Prefer **non-release** install (`IsReleaseBranch=0`) so LKAS_ANGLE is not dashcam-only.  
8. Pull fault CAN after a drive:

```bash
rsync -avz comma:/data/can_faults/ ./can_faults/
```

### Pull on another PC

```bash
git clone --recurse-submodules -b outback-2023-angle-tici \
  git@github.com:nl1031/sunnypilot_subaru_c3.git
# or update existing:
git pull origin outback-2023-angle-tici && git submodule update --init --recursive
```

Remote: keep **`origin`** → `nl1031/sunnypilot_subaru_c3`; optional **`upstream`** → sunnypilot/sunnypilot.

### Clear device logs (before a clean test)

```bash
# On device (stop OP first if needed)
find /data/media/0/realdata -mindepth 1 -maxdepth 1 ! -name crash -exec rm -rf {} +
mkdir -p /data/media/0/realdata/boot /data/media/0/realdata/crash
find /data/log -maxdepth 1 -name 'swaglog*' -delete
# optional: clear can_faults snippets (keep README if present)
```

---

## Parent-tree UX mitigations (stock longitudinal)

These are outside opendbc but shipped with this fork for Outback 2023 stock ACC:

| Change | Why |
|--------|-----|
| Disable OP model/planner **FCW** when not OP-long | High-speed follow-to-decel false “BRAKE! / Risk of Collision” while EyeSight owns brakes |
| Subaru angle sat threshold **2.5° → 6°**; honor CC rate limit | Fewer false “Turn Exceeds Steering Limit” mid-corner |
| Outback `steerLimitTimer` **0.8 s** | Brief lag less likely to nag |

True collision risk still relies on **stock FCW/AEB** (dash/buzzer may still fire).

---

## Validation checklist

- [x] Boots on C3 (AGNOS 12.6) with this tree  
- [x] Car recognized as Outback 2023; not dashcamOnly  
- [x] ACC engage → lateral works  
- [x] Route **37**: no permanent EPS latch over multi-minute enable  
- [x] Unit tests: carcontroller angle path (device venv; 9/9 when last run)  
- [x] panda flashed for **2.5 / 1.6 / 1.0** rate table  
- [ ] Road re-test current rates: curve authority vs new EPS faults  
- [ ] Highway / long multi-condition drive  
- [ ] Commit + push working-tree opendbc/parent changes if still dirty  
- [ ] If still slow: try low-speed **3.0°/TX** (reflash panda); if oscillates: drop toward **2.0**  

---

## Reading faults from C3

```bash
ssh comma 'ls -lt /data/media/0/realdata | head'
ssh comma 'ls -lt /data/can_faults | head'

# Parse with device venv:
ssh comma 'source /usr/local/venv/bin/activate
  export PYTHONPATH=/data/openpilot
  # LogReader on .../qlog.zst or rlog.zst
'
```

Useful signals: `carState.steerFaultPermanent`, `onroadEvents` → `steerUnavailable`, `selfdriveState.alertText2` = `LKAS Fault: Restart the Car`, panda `safetyTxBlocked`, 0x124 `LKAS_Request` / angle vs `Steering_2`.

---

## Safety note

**Experimental.** Not upstream-ready. Not a finished product for public-road reliance. Always be ready to take over. Safety / panda changes require dual review before flash when possible.
