#!/usr/bin/env python3
"""
Fault-triggered CAN ring buffer logger for C3 (limited storage / write bandwidth).

Design:
  - Keep the last PRE_S seconds of RX (`can`) + TX (`sendcan`) in RAM only.
  - On fault: keep recording POST_S more seconds, then write ONE file under /tmp
    (tmpfs), and copy to /data/can_faults/ for persistence.
  - Does not write every frame to disk in the hot path.

Typical size: a few MB for 10s of Subaru CAN — fine for /tmp (150MB tmpfs).

Usage on C3:
  cd /data/openpilot
  # stop is not required; runs alongside OP
  python3 selfdrive/debug/can_fault_ringlog.py
  # optional:
  python3 selfdrive/debug/can_fault_ringlog.py --pre 5 --post 5 --outdir /data/can_faults
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import time
from collections import deque
from datetime import datetime, timezone

import cereal.messaging as messaging


# OnroadEvent names that indicate a real fault (not override / lane-change noise)
FAULT_EVENTS = {
  "steerUnavailable",
  "steerTempUnavailable",
  "steerTempUnavailableSilent",
  "canError",
  "canBusMissing",
  "controlsMismatch",
  "accFaulted",
  "fcw",
  "stockAeb",
  "aeb",
  "steerSaturated",
  "cruiseMismatch",
  "commIssue",
  "commIssueAvgFreq",
  "radarFault",
}

# selfdriveState.alertStatus enum: normal=0, userPrompt=1, critical=2
ALERT_STATUS_USER_PROMPT = 1
ALERT_STATUS_CRITICAL = 2


def _now_name() -> str:
  return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


class CanRing:
  """Time-pruned ring of (t_mono, direction, src, address, dat)."""

  __slots__ = ("pre_s", "buf")

  def __init__(self, pre_s: float):
    self.pre_s = pre_s
    # unbounded deque; prune by timestamp (cheaper than per-frame maxlen guess)
    self.buf: deque[tuple[float, str, int, int, bytes]] = deque()

  def add(self, t: float, direction: str, src: int, address: int, dat: bytes) -> None:
    self.buf.append((t, direction, src, address, dat))
    self._prune(t)

  def _prune(self, t: float) -> None:
    cutoff = t - self.pre_s
    while self.buf and self.buf[0][0] < cutoff:
      self.buf.popleft()

  def snapshot(self) -> list[tuple[float, str, int, int, bytes]]:
    return list(self.buf)

  def clear(self) -> None:
    self.buf.clear()

  def approx_bytes(self) -> int:
    # rough: 24B overhead + data
    return sum(24 + len(x[4]) for x in self.buf)


def _write_dump(path: str, rows: list[tuple[float, str, int, int, bytes]],
                meta: dict) -> None:
  """Write a compact text dump (easy to inspect; gzip optional later)."""
  t0 = rows[0][0] if rows else 0.0
  with open(path, "w", buffering=1024 * 1024) as f:
    f.write("# can_fault_ringlog\n")
    for k, v in meta.items():
      f.write(f"# {k}: {v}\n")
    f.write("# columns: t_rel_s direction bus address data_hex\n")
    for t, direction, src, address, dat in rows:
      f.write(f"{t - t0:.6f} {direction} {src} {address:03X} {dat.hex()}\n")


def _copy_to_data(tmp_path: str, outdir: str) -> str | None:
  try:
    os.makedirs(outdir, exist_ok=True)
    dest = os.path.join(outdir, os.path.basename(tmp_path))
    shutil.copy2(tmp_path, dest)
    return dest
  except OSError as e:
    print(f"copy to {outdir} failed: {e}")
    return None


def main() -> None:
  # Defaults work when started by manager (no CLI). Env overrides for field use:
  #   CAN_FAULT_PRE, CAN_FAULT_POST, CAN_FAULT_TMPDIR, CAN_FAULT_OUTDIR, CAN_FAULT_ADDRS
  ap = argparse.ArgumentParser(description="RAM ring-buffer CAN logger; dump on fault")
  ap.add_argument("--pre", type=float, default=float(os.environ.get("CAN_FAULT_PRE", "5")),
                  help="seconds kept before fault (RAM)")
  ap.add_argument("--post", type=float, default=float(os.environ.get("CAN_FAULT_POST", "5")),
                  help="seconds kept after fault")
  ap.add_argument("--tmpdir", default=os.environ.get("CAN_FAULT_TMPDIR", "/tmp/can_faults"),
                  help="tmpfs write dir")
  ap.add_argument("--outdir", default=os.environ.get("CAN_FAULT_OUTDIR", "/data/can_faults"),
                  help="persistent copy dir on /data")
  ap.add_argument("--cooldown", type=float, default=float(os.environ.get("CAN_FAULT_COOLDOWN", "15")),
                  help="min seconds between dumps (avoid spam)")
  ap.add_argument("--also-prompt", action="store_true",
                  default=os.environ.get("CAN_FAULT_ALSO_PROMPT", "1") not in ("0", "false", "False"),
                  help="also trigger on userPrompt alerts (not only critical/fault events)")
  ap.add_argument("--addrs", default=os.environ.get("CAN_FAULT_ADDRS", ""),
                  help="optional comma-separated CAN IDs (hex or dec) to keep only, e.g. 124,11A,119")
  # Manager launches via multiprocessing with parent argv (./manager.py); ignore unknowns.
  args, _unknown = ap.parse_known_args()

  addr_filter: set[int] | None = None
  if args.addrs.strip():
    addr_filter = set()
    for part in args.addrs.split(","):
      part = part.strip()
      if not part:
        continue
      if part.lower().startswith("0x"):
        addr_filter.add(int(part, 16))
      elif any(c in part.lower() for c in "abcdef"):
        addr_filter.add(int(part, 16))
      else:
        addr_filter.add(int(part, 10))

  os.makedirs(args.tmpdir, exist_ok=True)

  # conflate=False so we do not drop frames in the ring
  sock_can = messaging.sub_sock("can", conflate=False, timeout=100)
  sock_send = messaging.sub_sock("sendcan", conflate=False, timeout=100)
  sock_cs = messaging.sub_sock("carState", conflate=True, timeout=100)
  sock_ss = messaging.sub_sock("selfdriveState", conflate=True, timeout=100)
  sock_ev = messaging.sub_sock("onroadEvents", conflate=True, timeout=100)

  ring = CanRing(args.pre)
  post_until: float | None = None
  post_rows: list[tuple[float, str, int, int, bytes]] = []
  pre_rows: list[tuple[float, str, int, int, bytes]] = []
  fault_meta: dict = {}
  last_dump_t = 0.0
  last_status_t = 0.0

  # edge detect
  prev_perm = False
  prev_temp = False
  prev_event_names: set[str] = set()

  print(
    f"can_fault_ringlog: pre={args.pre}s post={args.post}s "
    f"tmpdir={args.tmpdir} outdir={args.outdir} filter={addr_filter}"
  )
  print("waiting for can/sendcan + faults...")

  while True:
    t = time.monotonic()

    # --- ingest CAN ---
    for msg in messaging.drain_sock(sock_can):
      for c in msg.can:
        if addr_filter is not None and c.address not in addr_filter:
          continue
        dat = bytes(c.dat)
        if post_until is not None:
          post_rows.append((t, "RX", int(c.src), int(c.address), dat))
        else:
          ring.add(t, "RX", int(c.src), int(c.address), dat)

    for msg in messaging.drain_sock(sock_send):
      try:
        items = msg.sendcan
      except Exception:
        continue
      for c in items:
        if addr_filter is not None and c.address not in addr_filter:
          continue
        dat = bytes(c.dat)
        if post_until is not None:
          post_rows.append((t, "TX", int(c.src), int(c.address), dat))
        else:
          ring.add(t, "TX", int(c.src), int(c.address), dat)

    # --- fault detection (only when not already in post-capture) ---
    triggered = False
    reason = ""

    if post_until is None and (t - last_dump_t) >= args.cooldown:
      for msg in messaging.drain_sock(sock_cs):
        cs = msg.carState
        perm = bool(cs.steerFaultPermanent)
        temp = bool(cs.steerFaultTemporary)
        if perm and not prev_perm:
          triggered, reason = True, "steerFaultPermanent"
        elif temp and not prev_temp:
          triggered, reason = True, "steerFaultTemporary"
        prev_perm, prev_temp = perm, temp

      for msg in messaging.drain_sock(sock_ev):
        names = {str(e.name) for e in msg.onroadEvents}
        new_faults = (names & FAULT_EVENTS) - prev_event_names
        if new_faults:
          triggered, reason = True, "events:" + ",".join(sorted(new_faults))
        prev_event_names = names

      for msg in messaging.drain_sock(sock_ss):
        ss = msg.selfdriveState
        status = int(ss.alertStatus)
        text1 = str(ss.alertText1) if ss.alertText1 else ""
        text2 = str(ss.alertText2) if ss.alertText2 else ""
        atype = str(ss.alertType) if ss.alertType else ""
        interesting = status >= ALERT_STATUS_CRITICAL or (
          args.also_prompt and status >= ALERT_STATUS_USER_PROMPT and "startup" not in atype.lower()
        )
        # always catch LKAS / CAN / BRAKE style prompts
        blob = f"{text1} {text2} {atype}".lower()
        if any(k in blob for k in ("lkas fault", "can bus", "brake!", "cruise fault", "steer", "eyesight")):
          if status >= ALERT_STATUS_USER_PROMPT and "branch is not tested" not in blob:
            interesting = True
        if interesting and "branch is not tested" not in blob:
          triggered, reason = True, f"alert:{status}:{text1}|{text2}"

    if triggered and post_until is None:
      pre_rows = ring.snapshot()
      post_rows = []
      post_until = t + args.post
      fault_meta = {
        "reason": reason,
        "trigger_mono": f"{t:.6f}",
        "utc": _now_name(),
        "pre_s": args.pre,
        "post_s": args.post,
        "pre_frames": len(pre_rows),
        "ring_approx_bytes": ring.approx_bytes(),
      }
      print(f"[{time.strftime('%H:%M:%S')}] FAULT trigger: {reason}  "
            f"pre_frames={len(pre_rows)} ~{ring.approx_bytes()/1e6:.2f}MB — capturing post {args.post}s")

    # --- finish post window → write ---
    if post_until is not None and t >= post_until:
      rows = pre_rows + post_rows
      fault_meta["post_frames"] = len(post_rows)
      fault_meta["total_frames"] = len(rows)
      name = f"canfault_{fault_meta['utc']}_{fault_meta['reason'].replace(':', '_').replace(',', '-')[:80]}"
      # sanitize filename
      name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
      tmp_path = os.path.join(args.tmpdir, name + ".log")
      _write_dump(tmp_path, rows, fault_meta)
      size = os.path.getsize(tmp_path)
      dest = _copy_to_data(tmp_path, args.outdir)
      print(f"[{time.strftime('%H:%M:%S')}] wrote {tmp_path} ({size/1e6:.2f} MB)"
            + (f" -> {dest}" if dest else " (no /data copy)"))
      last_dump_t = t
      post_until = None
      pre_rows = []
      post_rows = []
      fault_meta = {}
      ring.clear()

    # status line
    if t - last_status_t > 5.0 and post_until is None:
      last_status_t = t
      print(f"[{time.strftime('%H:%M:%S')}] ring_frames={len(ring.buf)} "
            f"~{ring.approx_bytes()/1e6:.2f}MB  (waiting for fault)")


if __name__ == "__main__":
  main()
