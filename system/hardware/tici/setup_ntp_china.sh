#!/usr/bin/env bash
# Apply China NTP servers to systemd-timesyncd on AGNOS.
#
# AGNOS mounts / read-only; this keeps the desired config on /data and
# copies it into /etc when missing or stale (survives reboot; reapplies
# after an AGNOS flash as long as /data/openpilot is kept).

set -euo pipefail

DROPIN_DIR="/etc/systemd/timesyncd.conf.d"
DROPIN="$DROPIN_DIR/china.conf"
DATA_COPY="/data/etc/timesyncd-china.conf"

CONTENT='[Time]
NTP=ntp.aliyun.com ntp1.aliyun.com ntp.tencent.com ntp.ntsc.ac.cn
FallbackNTP=time.cloudflare.com ntp.ubuntu.com
'

sudo mkdir -p /data/etc
printf '%s' "$CONTENT" | sudo tee "$DATA_COPY" >/dev/null

if [[ -f "$DROPIN" ]] && cmp -s "$DATA_COPY" "$DROPIN"; then
  exit 0
fi

sudo mount -o remount,rw /
sudo mkdir -p "$DROPIN_DIR"
sudo cp "$DATA_COPY" "$DROPIN"
sudo chmod 644 "$DROPIN"
sudo mount -o remount,ro /
sudo systemctl restart systemd-timesyncd || true
