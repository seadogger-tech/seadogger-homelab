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

info "\n🔪 Aggressively nuking rook-ceph from your cluster..."

# Step 1: Remove finalizers from CephCluster
info "🧹 Step 1: Removing finalizers from CephCluster..."
kubectl -n rook-ceph patch cephcluster rook-ceph --type merge -p '{"metadata":{"finalizers": []}}' 2>/dev/null || true

# Step 2: Force delete all Ceph resources first
info "🧹 Step 2: Force deleting Ceph resources..."
for type in cephblockpool cephfilesystem cephobjectstore cephobjectuser; do
  kubectl -n rook-ceph get $type 2>/dev/null | grep -v NAME | awk '{print $1}' | \
  while read resource; do
    kubectl -n rook-ceph patch $type $resource --type merge -p '{"metadata":{"finalizers": []}}' 2>/dev/null || true
    kubectl -n rook-ceph delete $type $resource --force --grace-period=0 2>/dev/null || true
  done
done

# Step 3: Remove all finalizers from namespace
info "🧹 Step 3: Removing finalizers from namespace..."
kubectl get namespace rook-ceph -o json | jq '.spec.finalizers = []' | kubectl replace --raw "/api/v1/namespaces/rook-ceph/finalize" -f - 2>/dev/null || true

# Step 4: Force delete namespace
info "🧹 Step 4: Force deleting rook-ceph namespace..."
kubectl delete namespace rook-ceph --force --grace-period=0 2>/dev/null || true

# Step 5: Direct etcd cleanup of CRDs
info "🧹 Step 5: Forcibly removing CRDs..."
for crd in $(kubectl get crd | grep -Ei 'rook|ceph' | awk '{print $1}'); do
  echo "  🔸 Removing finalizers from $crd"
  kubectl patch crd $crd --type merge -p '{"metadata":{"finalizers": []}}' 2>/dev/null || true
  echo "  🔸 Deleting $crd"
  kubectl delete crd $crd --force --grace-period=0 2>/dev/null || true
done

# Step 6: Clean local disk on all nodes
info "🧹 Step 6: Cleaning local disks on all nodes..."
for node in yoda obiwan anakin rey; do
  echo "  🔸 Cleaning $node..."
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "pi@${node}.local" "
    sudo rm -rf /var/lib/rook
    sudo rm -rf /var/lib/kubelet/plugins/rook*
    sudo rm -rf /var/lib/kubelet/plugins_registry/rook*
    sudo rm -rf /var/lib/kubelet/pods/*rook*
    sudo rm -rf /var/lib/kubelet/plugins/ceph*
    sudo rm -rf /var/lib/kubelet/plugins_registry/ceph*
    sudo rm -rf /dev/mapper/ceph-*
    sudo rm -rf /dev/ceph-*
    sudo dmsetup remove_all
    sudo wipefs -af /dev/nvme0n1p3 || true
    sudo sgdisk --zap-all /dev/nvme0n1p3 || true
  " 2>/dev/null || echo "  ⚠️  Could not clean $node completely"
done

# Step 7: Kill any remaining processes
info "🧹 Step 7: Killing any remaining Ceph processes..."
for node in yoda obiwan anakin rey; do
  echo "  🔸 Checking $node..."
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "pi@${node}.local" "
    sudo pkill -9 -f ceph || true
    sudo pkill -9 -f rook || true
  " 2>/dev/null || echo "  ⚠️  Could not check processes on $node"
done

# Step 8: Validation
info "🧪 Step 8: Validating cleanup..."

function check_empty() {
  local desc="$1"
  local cmd="$2"
  if eval "$cmd" 2>/dev/null | grep -q .; then
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

# Step 9: Final disk check
info "📦 Step 9: Final disk validation..."
for node in yoda obiwan anakin rey; do
  echo -e "${YELLOW}🔍 Checking disk status on $node...${NC}"
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "pi@${node}.local" "
    echo '🔎 Disk status:'
    lsblk -f
    echo '🔎 Checking for remaining Ceph mounts:'
    mount | grep -i ceph || echo '✅ No Ceph mounts found'
  " 2>/dev/null || echo "  ⚠️  Could not check $node"
done

success "\n🏁 Rook-Ceph aggressive nuke complete!"