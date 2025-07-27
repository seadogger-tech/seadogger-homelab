#!/bin/bash

set -e

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
NC="\033[0m" # No Color

function info() {
  echo -e "${YELLOW}$1${NC}"
}

function success() {
  echo -e "${GREEN}$1${NC}"
}

function fail() {
  echo -e "${RED}$1${NC}"
}

info "\n🔪 Nuking rook-ceph from your cluster..."

# Step 1: Delete namespace
info "🧹 Step 1: Forcibly delete rook-ceph namespace..."
kubectl delete ns rook-ceph --grace-period=0 --force 2>/dev/null || success "✅ Namespace rook-ceph already deleted"

# Step 2: Delete CRDs
info "🧹 Step 2: Delete all rook/ceph CRDs (skip if gone)..."
for crd in $(kubectl get crd | grep -Ei 'rook|ceph' | awk '{print $1}'); do
  echo "  🔸 Deleting $crd"
  kubectl delete crd "$crd" --ignore-not-found
done

# Step 3: Clean local disk
info "🧹 Step 3: Remove local /var/lib/rook and plugins..."
sudo rm -rf /var/lib/rook
sudo rm -rf /var/lib/kubelet/plugins/rook* || true

# Step 4: Validation
info "🧪 Step 4: Validating cleanup..."

function check_empty() {
  local desc="$1"
  local cmd="$2"
  if eval "$cmd" | grep -q .; then
    fail "❌ $desc still present"
    eval "$cmd"
  else
    success "✅ $desc cleaned"
  fi
}

check_empty "Rook namespace" "kubectl get ns | grep rook"
check_empty "Rook/Ceph CRDs" "kubectl get crd | grep -Ei 'ceph|rook'"
check_empty "Helm releases" "helm list -A | grep rook"
check_empty "PVCs" "kubectl get pvc -A | grep rook"
check_empty "PVs" "kubectl get pv | grep rook"

if [ -d "/var/lib/rook" ]; then
  fail "❌ /var/lib/rook directory still exists"
else
  success "✅ /var/lib/rook directory removed"
fi

if ls /var/lib/kubelet/plugins/rook* &>/dev/null; then
  fail "❌ /var/lib/kubelet/plugins/rook* still exists"
else
  success "✅ /var/lib/kubelet/plugins/rook* removed"
fi

success "\n🏁 Rook-Ceph nuke complete!"



# Step 5: Validate disk usage on worker nodes
info "📦 Step 5: Validating disks on worker nodes..."

for node in obiwan anakin rey; do
  echo -e "${YELLOW}🔍 Checking disk usage on $node...${NC}"
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "pi@${node}.local" bash -s <<'EOF'
    echo "🔎 lsblk -f:"
    lsblk -f

    echo "🔎 blkid:"
    sudo blkid

    echo "🔎 Mounted Ceph volumes:"
    mount | grep ceph || echo "✅ No Ceph mounts found"

    ceph_devs=$(lsblk -f | grep -i ceph | awk '{print $1}')
    if [ -n "$ceph_devs" ]; then
      echo "⚠️ Found Ceph partitions: $ceph_devs"
      for dev in $ceph_devs; do
        full_dev="/dev/$dev"
        read -p "❓ Wipe $full_dev on $(hostname)? This will destroy all data. (y/n): " confirm
        if [[ "$confirm" == "y" ]]; then
          echo "💥 Wiping $full_dev"
          sudo sgdisk --zap-all "$full_dev"
          sudo wipefs -a "$full_dev"
          echo "✅ $full_dev wiped"
        else
          echo "⏭️ Skipped $full_dev"
        fi
      done
    else
      echo "✅ No Ceph-labeled partitions found"
    fi
EOF
done
