import math

from cereal import log
from openpilot.selfdrive.controls.lib.latcontrol import LatControl

# TODO This is speed dependent
STEER_ANGLE_SATURATION_THRESHOLD = 2.5  # Degrees
# Subaru LKAS_ANGLE: 1°/TX rate + EPS lag easily exceeds 2.5° mid-corner and
# falsely "Take Control / Turn Exceeds Steering Limit" after steerLimitTimer.
STEER_ANGLE_SATURATION_THRESHOLD_SUBARU = 6.0  # Degrees


class LatControlAngle(LatControl):
  def __init__(self, CP, CP_SP, CI):
    super().__init__(CP, CP_SP, CI)
    self.sat_check_min_speed = 5.
    self.use_steer_limited_by_safety = CP.brand == "tesla"
    self.angle_sat_threshold = (
      STEER_ANGLE_SATURATION_THRESHOLD_SUBARU if CP.brand == "subaru"
      else STEER_ANGLE_SATURATION_THRESHOLD
    )
    # carcontroller rate-limits angle (Subaru); honor that so sat timer does not
    # count while safety/CC is the bottleneck (stock path always passed False).
    self.honor_steer_limited = CP.brand in ("tesla", "subaru")

  def update(self, active, CS, VM, params, steer_limited_by_safety, desired_curvature, calibrated_pose, curvature_limited):
    angle_log = log.ControlsState.LateralAngleState.new_message()

    if not active:
      angle_log.active = False
      angle_steers_des = float(CS.steeringAngleDeg)
    else:
      angle_log.active = True
      angle_steers_des = math.degrees(VM.get_steer_from_curvature(-desired_curvature, CS.vEgo, params.roll))
      angle_steers_des += params.angleOffsetDeg

    if self.use_steer_limited_by_safety:
      # these cars' carcontrollers calculate max lateral accel and jerk, so we can rely on carOutput for saturation
      angle_control_saturated = steer_limited_by_safety
    else:
      # for cars which use a method of limiting torque such as a torque signal (Nissan and Toyota)
      # or relying on EPS (Ford Q3), carOutput does not capture maxing out torque  # TODO: this can be improved
      angle_control_saturated = abs(angle_steers_des - CS.steeringAngleDeg) > self.angle_sat_threshold
    limited = steer_limited_by_safety if self.honor_steer_limited else False
    angle_log.saturated = bool(self._check_saturation(angle_control_saturated, CS, limited, curvature_limited))
    angle_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    angle_log.steeringAngleDesiredDeg = angle_steers_des
    return 0, float(angle_steers_des), angle_log
