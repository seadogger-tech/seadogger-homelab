#!/bin/bash

set -euo pipefail

echo "🔪 Nuking rook-ceph from your cluster..."

# 1. Force delete rook-ceph namespace
echo "🧹 Deleting namespace rook-ceph (forced)..."
kubectl delete ns rook-ceph --grace-period=0 --force || true

# 2. Delete all Rook/Ceph CRDs
echo "🧹 Deleting all Rook/Ceph CRDs..."
kubectl get crd | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete crd --ignore-not-found || true

# 3. Delete ClusterRoles
echo "🧹 Deleting Rook-related ClusterRoles..."
kubectl get clusterrole | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete clusterrole --ignore-not-found || true

# 4. Delete ClusterRoleBindings
echo "🧹 Deleting Rook-related ClusterRoleBindings..."
kubectl get clusterrolebinding | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete clusterrolebinding --ignore-not-found || true

# 5. Delete Webhook Configurations
echo "🧹 Deleting webhook configurations..."
kubectl get validatingwebhookconfigurations | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete validatingwebhookconfiguration --ignore-not-found || true
kubectl get mutatingwebhookconfigurations | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete mutatingwebhookconfiguration --ignore-not-found || true

# 6. Clean up PVCs and PVs
echo "🧹 Deleting PersistentVolumeClaims and PersistentVolumes..."
kubectl get pvc --all-namespaces | grep -Ei 'rook|ceph' | awk '{print $2 " -n " $1}' | xargs -r -n 3 kubectl delete pvc --ignore-not-found || true
kubectl get pv | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete pv --ignore-not-found || true

# 7. Delete on-disk rook data
echo "🧹 Deleting Rook-related directories on host..."
sudo rm -rf /var/lib/rook
sudo rm -rf /var/lib/kubelet/plugins/rook*
sudo rm -rf /var/lib/kubelet/pods/*/volumes/kubernetes.io~csi/pvc-*/mount

# 8. Final check
echo "✅ Final cluster check:"
kubectl get all --all-namespaces | grep rook || echo "✅ No Rook pods running"
kubectl get crd | grep -Ei 'rook|ceph' || echo "✅ No Rook CRDs remaining"

echo "🎉 Rook-Ceph has been obliterated."