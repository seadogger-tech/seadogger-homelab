#!/bin/bash

set -euo pipefail

echo "🔪 Nuking rook-ceph from your cluster..."

echo "🧹 Step 1: Forcibly delete rook-ceph namespace..."
kubectl delete ns rook-ceph --grace-period=0 --force 2>/dev/null || echo "✅ Namespace already gone or not found"

echo "🧹 Step 2: Delete all rook/ceph CRDs (skip if gone)..."
for crd in $(kubectl get crd -o name | grep -Ei 'rook|ceph' || true); do
  echo "  🔸 Deleting $crd"
  kubectl delete "$crd" --ignore-not-found || true
done

echo "🧹 Step 3: Delete any leftover ceph/rook resources in all namespaces..."
for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
  for kind in pods deployments daemonsets statefulsets services configmaps secrets pvc; do
    kubectl get "$kind" -n "$ns" --no-headers 2>/dev/null | grep -Ei 'rook|ceph' | awk '{print $1}' | \
      xargs -r -I {} kubectl delete "$kind" -n "$ns" {} --ignore-not-found || true
  done
done

echo "🧹 Step 4: Delete rook/ceph ClusterRoles and Bindings..."
kubectl get clusterrole -o name | grep -Ei 'rook|ceph' | xargs -r kubectl delete --ignore-not-found || true
kubectl get clusterrolebinding -o name | grep -Ei 'rook|ceph' | xargs -r kubectl delete --ignore-not-found || true

echo "🧹 Step 5: Delete any related webhook configs..."
kubectl get validatingwebhookconfigurations -o name | grep -Ei 'rook|ceph' | xargs -r kubectl delete --ignore-not-found || true
kubectl get mutatingwebhookconfigurations -o name | grep -Ei 'rook|ceph' | xargs -r kubectl delete --ignore-not-found || true

echo "🧹 Step 6: Delete persistent volumes related to rook/ceph..."
kubectl get pv -o name | grep -Ei 'rook|ceph' | xargs -r kubectl delete --ignore-not-found || true

echo "🧹 Step 7: Delete storageclasses related to rook/ceph..."
kubectl get storageclass -o name | grep -Ei 'rook|ceph' | xargs -r kubectl delete --ignore-not-found || true

echo "🧹 Step 8: Wipe local disk paths (needs sudo)..."
sudo rm -rf /var/lib/rook
sudo rm -rf /var/lib/kubelet/plugins/rook*
sudo rm -rf /var/lib/kubelet/pods/*/volumes/kubernetes.io~csi/pvc-*/mount 2>/dev/null || true

echo "✅ Done. rook-ceph has been annihilated without mercy."