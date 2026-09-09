#!/usr/bin/env bash
# Creates the storage account that holds Terraform state, once, using the
# owner's `az login` session. Idempotent: if backend.hcl exists and names a
# reachable account, it exits without changes.
set -euo pipefail

RG="rg-bonfire-tfstate"
LOCATION="${LOCATION:-brazilsouth}"
HCL="$(cd "$(dirname "$0")" && pwd)/../envs/pilot/backend.hcl"

if [ -f "$HCL" ]; then
  SA=$(sed -n 's/^storage_account_name *= *"\(.*\)"/\1/p' "$HCL")
  if az storage account show -g "$RG" -n "$SA" -o none 2>/dev/null; then
    echo "state backend already exists: $SA"
    exit 0
  fi
  echo "backend.hcl names $SA but it does not exist; recreating" >&2
fi

SA="stbonfiretf$(openssl rand -hex 3)"
az group create -n "$RG" -l "$LOCATION" -o none
az storage account create -n "$SA" -g "$RG" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
  --allow-blob-public-access false -o none
az storage container create -n tfstate --account-name "$SA" -o none

cat > "$HCL" <<EOT
resource_group_name  = "$RG"
storage_account_name = "$SA"
container_name       = "tfstate"
key                  = "pilot.tfstate"
EOT
echo "wrote $HCL (account $SA)"
