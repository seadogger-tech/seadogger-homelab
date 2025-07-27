#!/bin/bash
set -e

echo "🔪 Nuking rook-ceph with extreme prejudice..."

# Step 0: Make sure jq is installed
if ! command -v jq &> /dev/null; then
  echo "❌ 'jq' is required but not installed. Run: sudo apt install jq"
  exit 1
fi

# Step 1: Kill finalizers in any remaining Ceph resources across all namespaces
echo "🧨 Step 1: Removing finalizers from Ceph-related resources..."
CRDS=$(kubectl get crds -o name | grep -E 'ceph|rook') || true
for crd in $CRDS; do
  resources=$(kubectl get "$crd" --all-namespaces -o json | jq -r '.items[] | "\(.metadata.namespace) \(.kind) \(.metadata.name)"' 2>/dev/null) || true
  for res in $resources; do
    ns=$(echo "$res" | awk '{print $1}')
    kind=$(echo "$res" | awk '{print $2}')
    name=$(echo "$res" | awk '{print $3}')
    echo "  🧹 Patching finalizer on $kind/$name in $ns..."
    kubectl -n "$ns" patch "$kind" "$name" --type=merge -p '{"metadata":{"finalizers":[]}}' || true
  done
done

# Step 2: Force delete namespace
echo "🧹 Step 2: Force delete namespace rook-ceph if still exists..."
kubectl get ns rook-ceph &>/dev/null && kubectl delete ns rook-ceph --grace-period=0 --force || echo "✅ Namespace already gone"

# Step 3: Nuke all related CRDs again
echo "🧹 Step 3: Deleting all Ceph/Rook CRDs..."
kubectl get crds | grep -E 'ceph|rook' | awk '{print $1}' | xargs -r kubectl delete crd --ignore-not-found || true

# Step 4: Final local cleanup
echo "🧹 Step 4: Removing /var/lib/rook directory..."
sudo rm -rf /var/lib/rook

echo "✅ Rook-Ceph nuked successfully."