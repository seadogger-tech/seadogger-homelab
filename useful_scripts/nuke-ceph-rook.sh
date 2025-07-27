#!/bin/bash

set -euo pipefail

echo "\n🔪 Nuking rook-ceph from your cluster..."

### STEP 1: Delete namespace
if kubectl get ns rook-ceph &>/dev/null; then
  echo "🧹 Step 1: Forcibly delete rook-ceph namespace..."
  kubectl delete ns rook-ceph --grace-period=0 --force || true
else
  echo "✅ Namespace rook-ceph already deleted"
fi

### STEP 2: Delete CRDs
echo "🧹 Step 2: Delete all rook/ceph CRDs (skip if gone)..."
kubectl get crd | grep -Ei 'rook|ceph' | awk '{print $1}' | while read -r crd; do
  echo "  🔸 Deleting $crd"
  kubectl delete crd "$crd" --ignore-not-found || true
done

### STEP 3: Remove Helm release
if helm list -A | grep -q rook-ceph; then
  echo "🧹 Step 3: Uninstalling rook-ceph Helm release..."
  helm uninstall rook-ceph -n rook-ceph || true
else
  echo "✅ Helm release rook-ceph already removed"
fi

### STEP 4: Delete any lingering PVCs or PVs
echo "🧹 Step 4: Deleting lingering PVCs and PVs..."
kubectl delete pvc -l app=rook-ceph --all-namespaces --ignore-not-found || true
kubectl delete pv -l app=rook-ceph --ignore-not-found || true

### STEP 5: Delete leftover filesystem data
echo "🧹 Step 5: Removing data directories..."
sudo rm -rf /var/lib/rook || true
sudo rm -rf /var/lib/kubelet/plugins/rook* || true

### STEP 6: Validation

echo -e "\n✅ Validating rook-ceph cleanup..."

if kubectl get ns | grep -q rook-ceph; then
  echo "❌ Namespace rook-ceph still exists"
else
  echo "✅ Namespace rook-ceph not found"
fi

if kubectl get crd | grep -Ei 'rook|ceph'; then
  echo "❌ Rook/Ceph CRDs still present"
else
  echo "✅ No Rook/Ceph CRDs found"
fi

if helm list -A | grep -q rook-ceph; then
  echo "❌ Helm release rook-ceph still exists"
else
  echo "✅ Helm release rook-ceph not found"
fi

if [ -d /var/lib/rook ]; then
  echo "❌ Found /var/lib/rook directory"
else
  echo "✅ /var/lib/rook not present"
fi

if ls /var/lib/kubelet/plugins/ 2>/dev/null | grep -q rook; then
  echo "❌ Found rook plugin directories"
else
  echo "✅ No rook plugin directories"
fi

echo -e "\n🎉 Cleanup and validation complete!"