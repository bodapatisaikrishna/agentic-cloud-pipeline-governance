#!/usr/bin/env bash
# Deploy ACDE to one Azure VM. THIS CREATES BILLABLE RESOURCES -- read the cost note below.
#
#   Azure for Students blocks the Intel B-series in southeastasia; the Arm (Bpsv2) sizes are open.
#   Cost (retail, southeastasia, Linux): Standard_B2pls_v2 (2 vCPU, 4 GB) ~ $0.0424/h (~$31/mo),
#   Standard_B2ps_v2 (2 vCPU, 8 GB) ~ $0.0848/h (~$62/mo). Disk and public IP add ~$5-10/mo.
#   `az vm deallocate` stops compute billing; `az group delete` removes everything.
#
# Usage:  deploy/azure/deploy.sh [vm-size]     (default Standard_B2pls_v2, Arm64)
# Allowed regions on Azure for Students: southeastasia uaenorth malaysiawest eastasia austriaeast
set -euo pipefail
SIZE="${1:-Standard_B2pls_v2}"
LOC="${LOC:-southeastasia}"
RG="${RG:-rg-acde}"
VM="${VM:-acde-vm}"
LABEL="${LABEL:-acde-$(openssl rand -hex 3)}"
DOMAIN="${LABEL}.${LOC}.cloudapp.azure.com"
MYIP="$(curl -fsS https://api.ipify.org)"
# Arm sizes (Bpsv2, Dpsv5, ...) need an Arm64 image; everything else uses the x64 one.
if [[ "$SIZE" =~ ^Standard_[A-Za-z]+[0-9]+p ]]; then
  IMAGE="Canonical:ubuntu-24_04-lts:server-arm64:latest"
else
  IMAGE="Canonical:ubuntu-24_04-lts:server:latest"
fi

az group create -n "$RG" -l "$LOC" -o none
sed "s|__ACDE_DOMAIN__|${DOMAIN}|" "$(dirname "$0")/cloud-init.yaml" > /tmp/acde-cloud-init.yaml
az vm create -g "$RG" -n "$VM" -l "$LOC" --size "$SIZE" \
  --image "$IMAGE" --admin-username acde --generate-ssh-keys \
  --public-ip-address-dns-name "$LABEL" --public-ip-sku Standard \
  --os-disk-size-gb 30 --storage-sku Standard_LRS \
  --custom-data /tmp/acde-cloud-init.yaml \
  --nsg-rule NONE -o none
NSG="$(az network nsg list -g "$RG" --query '[0].name' -o tsv)"
az network nsg rule create -g "$RG" --nsg-name "$NSG" -n ssh-me --priority 100 \
  --access Allow --protocol Tcp --destination-port-ranges 22 --source-address-prefixes "$MYIP" -o none
az network nsg rule create -g "$RG" --nsg-name "$NSG" -n web --priority 110 \
  --access Allow --protocol Tcp --destination-port-ranges 80 443 --source-address-prefixes '*' -o none
echo "VM created. First boot installs Docker and builds the images (~10-15 min)."
echo "URL: https://${DOMAIN}   (dashboard /ui; admin key: ssh acde@${DOMAIN} sudo grep API_KEYS /opt/acde/.env.prod)"
echo "Stop billing for compute:  az vm deallocate -g ${RG} -n ${VM}     Remove everything: az group delete -n ${RG}"
