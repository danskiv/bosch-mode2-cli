#!/usr/bin/env bash
set -e

LAPTOP_USER="spu-tech"
LAPTOP_IP="10.10.10.2"
SSH_KEY="$HOME/.ssh/id_nodix1_to_laptop"
DEST_PATH="C:/Users/tech/Documents/GitHub/bosch-mode2-cli"

echo "=========================================================="
echo "  Syncing bosch-mode2-cli to Laptop HUAWEI ($LAPTOP_IP)"
echo "=========================================================="

if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes "$LAPTOP_USER@$LAPTOP_IP" "echo OK" >/dev/null 2>&1; then
    echo "[!] ERROR: Laptop HUAWEI ($LAPTOP_IP) is currently unreachable."
    echo "    Please verify that:"
    echo "    1. Laptop is powered on and awake."
    echo "    2. WireGuard client is connected on the laptop."
    echo "    3. SSH server is running on the laptop."
    exit 1
fi

echo "[+] Laptop is online! Creating folder: $DEST_PATH"
ssh -i "$SSH_KEY" "$LAPTOP_USER@$LAPTOP_IP" "powershell -Command \"New-Item -ItemType Directory -Force -Path '$DEST_PATH' | Out-Null\""

echo "[+] Syncing repository files..."
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.git' \
    -e "ssh -i $SSH_KEY" \
    ./ "$LAPTOP_USER@$LAPTOP_IP:$DEST_PATH/"

echo "[✓] Sync completed successfully!"
echo "    On your laptop, navigate to:"
echo "    cd C:\Users\tech\Documents\GitHub\bosch-mode2-cli"
