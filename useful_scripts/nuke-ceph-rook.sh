#!/bin/bash
set -e

echo "🔪 Full force rook-ceph annihilation initiated."

# Step 0: Warning
echo "⚠️  WARNING: This will aggressively wipe all rook-ceph references from your cluster, skipping all cleanup logic."
read -p "Press ENTER to proceed or Ctrl+C to cancel..."

# Step 1: Brutally kill namespace (no hanging)
echo "🧹 Force deleting namespace rook-ceph (in background)..."
(kubectl delete ns rook-ceph --grace-period=0 --force || true) &

# Step 2: Nuke CRDs in background
echo "🧹 Force deleting all Rook/Ceph CRDs..."
kubectl get crd | grep -Ei 'ceph|rook' | awk '{print $1}' | while read crd; do
  echo "  🔸 Deleting $crd..."
  (kubectl delete crd "$crd" --wait=false --timeout=1s || true) &
done

# Step 3: Kill leftover secrets, configmaps, finalizer crap
echo "🧹 Killing leftover Ceph secrets/configmaps..."
kubectl get secret -A | grep rook | awk '{print $1 " " $2}' | while read ns name; do
  kubectl delete secret "$name" -n "$ns" --ignore-not-found &
done

kubectl get configmap -A | grep rook | awk '{print $1 " " $2}' | while read ns name; do
  kubectl delete configmap "$name" -n "$ns" --ignore-not-found &
done

# Step 4: Kill operator if somehow still present
echo "🧹 Killing rook-ceph-operator if still alive..."
kubectl delete deploy rook-ceph-operator -n rook-ceph --ignore-not-found || true

# Step 5: Full disk nuke
echo "🧨 Removing all Rook data from disk..."
sudo rm -rf /var/lib/rook /var/lib/kubelet/plugins/rook*

# Step 6: Flush final stuck NS objects manually if needed
echo "🧨 Forcing cleanup of stuck namespaces..."
(kubectl get ns rook-ceph -o json | sed 's/"kubernetes"//' | sed '/finalizers/,+2d' | kubectl replace --raw "/api/v1/namespaces/rook-ceph/finalize" -f -) 2>/dev/null || true

echo "✅ Rook-Ceph purge complete. You may now reinstall cleanly."