# Outback 2023 Angle Port (C3 / tici)

## Goal

Enable **lateral control** for **Subaru Outback 2023** (`LKAS_ANGLE`, **Harness D**) on **comma three (C3 / tici)**, based on sunnypilot `master-tici`, with angle path aligned to **JacobW** (`openpilot_jacobwaller`).

## Status (2026-08-06)

| Item | Value |
|------|--------|
| **Baseline on device / GitHub** | **Pure JacobW angle** (most stable road result so far) |
| Parent branch | `outback-2023-angle-tici` @ `21904c733` |
| opendbc branch | `outback-2023-angle-tici` @ `0b4c207` |
| GitHub | https://github.com/nl1031/sunnypilot_subaru_c3/tree/outback-2023-angle-tici |
| opendbc | https://github.com/nl1031/opendbc/tree/outback-2023-angle-tici |
| AGNOS | **12.6** (match office C3; see `launch_env.sh`) |
| Tree (dev machine) | `/opt/develop/c3/sunnypilot_subaru_c3` |

**Road feedback:** pure Jacob port drove on the order of **~5 km with only ~2× “LKAS Fault: Restart the Car”**. Later “mitigations” (1°/TX + hand priority, then tighter hand/rate gates) **felt worse** and failed sooner (routes `2a`–`2d`). Those experiments remain in git history; **HEAD is rolled back to pure Jacob**.

---

## Base / references

| Item | Value |
|------|--------|
| Upstream base | sunnypilot `master-tici` @ `737a6c423` |
| JacobW | `/opt/develop/c3/openpilot_jacobwaller` — angle TX, safety 0x124, `Steering_2` / `ES_Brake`, engage re-anchor |
| justin `outback-23` | Historical proof of engage (old stack); not current baseline |
| Harness | **Subaru D** |

---

## Current code behavior (pure Jacob baseline)

| Item | Behavior |
|------|----------|
| Unlock control | `dashcamOnly` for `LKAS_ANGLE` only when `is_release` (non-release branch can control) |
| `safetyParam` | `GEN2 \| LKAS_ANGLE` (e.g. **9**) |
| `steerControlType` | **angle** |
| Steering measure | **`Steering_2.Steering_Angle`** (matches panda `angle_meas`) |
| Cruise enabled | **`ES_Brake.Cruise_Activated`** (matches panda PCM check) |
| Lateral TX | **`ES_LKAS_ANGLE` (0x124)** on bus 0 |
| Engage | **Re-anchor** `apply_angle_last` to live measured angle on rising `latActive` |
| Inactive / not lat active | Command angle = measured, `LKAS_Request=0` |
| Angle rate (controller + panda) | Jacob table **5 / 0.8 / 0.15** ° per TX by speed |
| Hand / brake priority | **None** (stock OP `steeringPressed` threshold ~80) |
| `ES_Distance.Cruise_Fault` | Mapped to **`accFaulted`** when not OP-long (Jacob) |
| `ES_LKAS_State` when disabled | Jacob: **`LKAS_Dash_State=0`** |
| LKAS_ANGLE safety init | Enabled **outside** `ALLOW_DEBUG` on this fork (so non-debug panda builds still accept param bit 8) |

### Key files (`opendbc_repo`)

| File | Role |
|------|------|
| `opendbc/car/subaru/interface.py` | dashcam / `LKAS_ANGLE` safety param |
| `opendbc/car/subaru/carcontroller.py` | `handle_angle_lateral` + re-anchor |
| `opendbc/car/subaru/carstate.py` | `Steering_2`, `ES_Brake`, Cruise_Fault |
| `opendbc/car/subaru/values.py` | `ANGLE_LIMITS`, platforms |
| `opendbc/car/subaru/subarucan.py` | pack 0x124 / HUD messages |
| `opendbc/car/subaru/test_carcontroller.py` | re-anchor unit test |
| `opendbc/safety/modes/subaru.h` | 0x124 TX/RX, angle checks, rate table |

---

## Road-test log (summary)

### Pure Jacob (~5 km) — best so far

- Lateral usable; **more stable** than pre-Jacob / experimental stacks.
- **~2×** `TAKE CONTROL IMMEDIATELY` / **`LKAS Fault: Restart the Car`**.
- Alert path: `Steer_Error_1` → `steerFaultPermanent` → `steerUnavailable`.
- Key cycle clears EPS latch; **C3 need not reboot**.

### After “mitigations” (regressed) — routes `2a`–`2c` (clock OK, 2026-08-06)

| Change | Result |
|--------|--------|
| 1°/TX all speeds + hand priority (tq 45/20) | Faulted **quickly** at low speed (~25–30 km/h) |
| Logs | High wheel rate / hand fight; still `Steer_Error_1` |

### Tighter hand/rate gates — route `2d` (clock wrong / no hotspot)

| Change | Result |
|--------|--------|
| tq ON 28, release ~0.5 s, rate hold/resume gates | **Worse**: many `steerOverride`, lat flaky |
| Fault pattern | After hand whip, **cmd angle drifted from measured** (~7° error) then EPS latch even when tq≈0 |

**Lesson:** on this car, **do not stack aggressive hand-priority + rate gates** without a strong “re-anchor + cmd≈meas before re-request” rule. Prefer **one change at a time** on top of pure Jacob.

### Other notes

- Harness D + panda `check_relay` **block stock 0x124** → OP must continuously send a valid substitute.
- C3 **RTC is unreliable** (often stuck near 1970). Use **phone hotspot / office Wi‑Fi for NTP** before a drive so route mtimes are useful. Internal `logMonoTime` remains consistent within a drive either way.
- Device was **UnregisteredDevice** in office tests; local rlog/qlog still written under `/data/media/0/realdata/`.

---

## Experiments kept in git history (not on HEAD)

| opendbc commit | Intent |
|----------------|--------|
| `d4288cd` | Pure Jacob port |
| `830e4a7` | 1°/TX + hand priority 45 + ES_LKAS_State passthrough |
| `7039c40` | Earlier yield 28 + rate-gated re-engage |
| `0b4c207` | **Restore pure Jacob** (current) |

Parent bumps: `91f7a9937` → … → `21904c733` (restore).

---

## Device install / update (C3)

1. AGNOS **12.6** (or match `launch_env.sh` / device `/VERSION`).  
2. **Do not** install generic sunnypilot/openpilot **master** (non-tici).  
3. Deploy branch to `/data/openpilot` (rsync or clone + submodule):

```bash
# Example rsync from dev machine
rsync -avz --exclude '.git/' --exclude '*/.git/' --exclude '__pycache__/' \
  /opt/develop/c3/sunnypilot_subaru_c3/ comma:/data/openpilot/
```

4. Hardware: **Harness D**, Outback 2023 EyeSight.  
5. After any change to **`subaru.h`**: rebuild and flash panda on device:

```bash
ssh comma 'source /usr/local/venv/bin/activate
  export PYTHONPATH=/data/openpilot
  cd /data/openpilot && python3 panda/board/flash.py && sudo reboot'
```

6. Fingerprint: force / extend FW if needed; confirm `SUBARU_OUTBACK_2023`, `dashcamOnly=False`, `safetyParam` includes LKAS_ANGLE (bit 8).  
7. Prefer **non-release** install (`IsReleaseBranch=0`) so LKAS_ANGLE is not dashcam-only.

### Pull on another PC

```bash
git clone --recurse-submodules -b outback-2023-angle-tici \
  git@github.com:nl1031/sunnypilot_subaru_c3.git
# or update existing:
git pull origin outback-2023-angle-tici && git submodule update --init --recursive
```

Remote: keep **`origin`** → `nl1031/sunnypilot_subaru_c3`; optional **`upstream`** → sunnypilot/sunnypilot. Duplicate remotes with the same URL can be removed.

### Clear device logs (before a clean test)

```bash
# On device (stop OP first if needed)
find /data/media/0/realdata -mindepth 1 -maxdepth 1 ! -name crash -exec rm -rf {} +
mkdir -p /data/media/0/realdata/boot /data/media/0/realdata/crash
find /data/log -maxdepth 1 -name 'swaglog*' -delete
```

---

## Validation checklist

- [x] Boots on C3 (AGNOS 12.6) with this tree  
- [x] Car recognized as Outback 2023; not dashcamOnly  
- [x] ACC engage → lateral works (pure Jacob)  
- [x] Occasional EPS LKAS fault still possible (~2 / 5 km observed)  
- [ ] Long / multi-condition drive without latch  
- [ ] Hand override without permanent fault (not solved on pure Jacob)  
- [ ] Curve tracking / re-engage tuning (only after baseline stays Jacob)  

---

## Reading faults from C3

```bash
ssh comma 'ls -lt /data/media/0/realdata | head'
# Parse with device venv:
ssh comma 'source /usr/local/venv/bin/activate
  export PYTHONPATH=/data/openpilot
  # LogReader on .../qlog.zst or rlog.zst
'
```

Useful signals: `carState.steerFaultPermanent`, `onroadEvents` → `steerUnavailable`, `selfdriveState.alertText2` = `LKAS Fault: Restart the Car`.

---

## Safety note

**Experimental.** Not upstream-ready. Not a finished product for public-road reliance. Always be ready to take over. Safety / panda changes require dual review before flash when possible.
