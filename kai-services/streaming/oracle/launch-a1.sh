#!/usr/bin/env bash
# Oracle Cloud に kai サーバー用 A1.Flex インスタンスを作成する。
# - Ubuntu 24.04 (aarch64) 最新イメージを自動選択
# - VCN/サブネットがなければ作成（kai-vcn / 10.0.0.0/16）
# - "Out of host capacity" は自動リトライ（A1 は容量エラーが頻発するため）
# - TS_AUTHKEY を渡すと cloud-init で Tailscale を自動導入・tailnet 加入（SSH は Tailscale SSH）
#
# 前提: `oci setup bootstrap` 済み（~/.oci/config が存在）
# 使い方:
#   TS_AUTHKEY=tskey-auth-... bash kai-services/streaming/oracle/launch-a1.sh
# 主な上書き可能変数: OCPUS(4) MEMORY_GB(24) BOOT_GB(100) NAME(kai-server) RETRY_INTERVAL(300)
set -euo pipefail

OCPUS="${OCPUS:-4}"
MEMORY_GB="${MEMORY_GB:-24}"
BOOT_GB="${BOOT_GB:-100}"
NAME="${NAME:-kai-server}"
RETRY_INTERVAL="${RETRY_INTERVAL:-300}"
SHAPE="VM.Standard.A1.Flex"
SSH_KEY_FILE="${SSH_KEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
TS_AUTHKEY="${TS_AUTHKEY:-}"

[[ -f "$SSH_KEY_FILE" ]] || { echo "SSH 公開鍵がありません: $SSH_KEY_FILE (SSH_KEY_FILE で指定可)"; exit 1; }

TENANCY="$(grep -m1 '^tenancy' ~/.oci/config | cut -d= -f2 | tr -d ' ')"
COMPARTMENT="${COMPARTMENT:-$TENANCY}"

echo "==> Availability Domain"
AD="$(oci iam availability-domain list -c "$TENANCY" --query 'data[0].name' --raw-output)"
echo "    $AD"

echo "==> Ubuntu 24.04 aarch64 イメージ"
IMAGE="$(oci compute image list -c "$TENANCY" \
  --operating-system 'Canonical Ubuntu' --operating-system-version '24.04' \
  --shape "$SHAPE" --sort-by TIMECREATED --sort-order DESC \
  --query 'data[0].id' --raw-output)"
echo "    $IMAGE"

echo "==> VCN / サブネット（kai-vcn がなければ作成）"
VCN_ID="$(oci network vcn list -c "$COMPARTMENT" --display-name kai-vcn --query 'data[0].id' --raw-output 2>/dev/null || true)"
if [[ -z "$VCN_ID" || "$VCN_ID" == "null" ]]; then
  VCN_ID="$(oci network vcn create -c "$COMPARTMENT" --display-name kai-vcn \
    --cidr-blocks '["10.0.0.0/16"]' --wait-for-state AVAILABLE \
    --query 'data.id' --raw-output)"
  IG_ID="$(oci network internet-gateway create -c "$COMPARTMENT" --vcn-id "$VCN_ID" \
    --display-name kai-ig --is-enabled true --wait-for-state AVAILABLE \
    --query 'data.id' --raw-output)"
  RT_ID="$(oci network vcn get --vcn-id "$VCN_ID" --query 'data."default-route-table-id"' --raw-output)"
  oci network route-table update --rt-id "$RT_ID" --force \
    --route-rules "[{\"destination\":\"0.0.0.0/0\",\"networkEntityId\":\"$IG_ID\"}]" >/dev/null
fi
SUBNET_ID="$(oci network subnet list -c "$COMPARTMENT" --vcn-id "$VCN_ID" --display-name kai-subnet --query 'data[0].id' --raw-output 2>/dev/null || true)"
if [[ -z "$SUBNET_ID" || "$SUBNET_ID" == "null" ]]; then
  SUBNET_ID="$(oci network subnet create -c "$COMPARTMENT" --vcn-id "$VCN_ID" \
    --display-name kai-subnet --cidr-block '10.0.0.0/24' --wait-for-state AVAILABLE \
    --query 'data.id' --raw-output)"
fi
echo "    VCN=$VCN_ID"
echo "    SUBNET=$SUBNET_ID"

echo "==> cloud-init 生成"
CLOUD_INIT="$(mktemp)"
trap 'rm -f "$CLOUD_INIT"' EXIT
{
  echo "#cloud-config"
  echo "package_update: true"
  echo "runcmd:"
  echo "  - ['sh', '-c', 'curl -fsSL https://tailscale.com/install.sh | sh']"
  if [[ -n "$TS_AUTHKEY" ]]; then
    # --ssh: Tailscale SSH を有効化（公開 22 番に依存しない）
    echo "  - ['tailscale', 'up', '--authkey=${TS_AUTHKEY}', '--ssh', '--hostname=${NAME}']"
  fi
} > "$CLOUD_INIT"

echo "==> インスタンス作成（$SHAPE ${OCPUS}ocpu/${MEMORY_GB}GB, boot ${BOOT_GB}GB）"
echo "    A1 の容量エラー時は ${RETRY_INTERVAL} 秒ごとにリトライします（Ctrl-C で中断）"
ATTEMPT=0
while :; do
  ATTEMPT=$((ATTEMPT + 1))
  echo "--- attempt #$ATTEMPT $(date '+%H:%M:%S')"
  set +e
  OUT="$(oci compute instance launch \
    -c "$COMPARTMENT" \
    --availability-domain "$AD" \
    --shape "$SHAPE" \
    --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEMORY_GB}" \
    --image-id "$IMAGE" \
    --subnet-id "$SUBNET_ID" \
    --display-name "$NAME" \
    --boot-volume-size-in-gbs "$BOOT_GB" \
    --assign-public-ip true \
    --ssh-authorized-keys-file "$SSH_KEY_FILE" \
    --user-data-file "$CLOUD_INIT" \
    --query 'data.id' --raw-output 2>&1)"
  RC=$?
  set -e
  if [[ $RC -eq 0 ]]; then
    INSTANCE_ID="$OUT"
    echo "==> 作成開始: $INSTANCE_ID"
    break
  fi
  if grep -qiE 'Out of host capacity|InternalError.*capacity|LimitExceeded' <<<"$OUT"; then
    echo "    容量エラー。${RETRY_INTERVAL}s 後にリトライ..."
    sleep "$RETRY_INTERVAL"
  else
    echo "$OUT" >&2
    exit "$RC"
  fi
done

echo "==> RUNNING まで待機"
oci compute instance get --instance-id "$INSTANCE_ID" --wait-for-state RUNNING >/dev/null 2>&1 || true
PUBLIC_IP="$(oci compute instance list-vnics --instance-id "$INSTANCE_ID" --query 'data[0]."public-ip"' --raw-output)"
echo ""
echo "完了: $NAME"
echo "  instance: $INSTANCE_ID"
echo "  public IP: $PUBLIC_IP"
if [[ -n "$TS_AUTHKEY" ]]; then
  echo "  数分後に tailnet に '$NAME' が現れます → 'tailscale status' で確認、'ssh ubuntu@$NAME' (Tailscale SSH)"
  echo "  接続確認後、Security List の 22/tcp (0.0.0.0/0) を閉じてください。"
else
  echo "  ssh ubuntu@$PUBLIC_IP で接続し、手動で tailscale を導入してください。"
fi
