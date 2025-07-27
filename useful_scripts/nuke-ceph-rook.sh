#!/bin/bash

set -euo pipefail

echo "🔪 Nuking rook-ceph from your cluster..."

# 1. Force delete namespace
echo "🧹 Forcing namespace deletion of rook-ceph..."
kubectl get ns rook-ceph &> /dev/null && {
  kubectl get namespace rook-ceph -o json | \
    jq 'del(.spec.finalizers)' > rook-ceph-ns.json
  kubectl replace --raw "/api/v1/namespaces/rook-ceph/finalize" -f rook-ceph-ns.json || true
  rm -f rook-ceph-ns.json
} || echo "✅ Namespace rook-ceph already gone."

# 2. Delete all Rook/Ceph CRDs
echo "🧹 Deleting all Rook/Ceph CRDs..."
kubectl get crd | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete crd --ignore-not-found || true

# 3. Delete any leftover Ceph/Rook resources in all namespaces
echo "🧹 Deleting leftover resources..."
for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
  kubectl get all -n "$ns" | grep -Ei 'rook|ceph' | awk '{print $1}' | \
    xargs -r -I {} kubectl delete -n "$ns" {} --ignore-not-found || true
done

# 4. Clean ClusterRoles and Bindings
echo "🧹 Deleting ClusterRoles and ClusterRoleBindings..."
kubectl get clusterrole | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete clusterrole --ignore-not-found || true
kubectl get clusterrolebinding | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete clusterrolebinding --ignore-not-found || true

# 5. Webhooks
echo "🧹 Deleting webhook configs..."
kubectl get validatingwebhookconfigurations | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete validatingwebhookconfiguration --ignore-not-found || true
kubectl get mutatingwebhookconfigurations | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete mutatingwebhookconfiguration --ignore-not-found || true

# 6. Delete PVCs and PVs
echo "🧹 Deleting PVCs and PVs..."
kubectl get pvc --all-namespaces | grep -Ei 'rook|ceph' | awk '{print $2 " -n " $1}' | xargs -r -n 3 kubectl delete pvc --ignore-not-found || true
kubectl get pv | grep -Ei 'rook|ceph' | awk '{print $1}' | xargs -r kubectl delete pv --ignore-not-found || true

# 7. Disk cleanup
echo "🧹 Deleting on-disk rook data..."
sudo rm -rf /var/lib/rook
sudo rm -rf /var/lib/kubelet/plugins/rook*
sudo rm -rf /var/lib/kubelet/pods/*/volumes/kubernetes.io~csi/pvc-*/mount

# 8. Final check
echo "✅ Final check:"
kubectl get ns | grep rook || echo "✅ Namespace gone"
kubectl get crd | grep -Ei 'rook|ceph' || echo "✅ No CRDs left"

echo "🎉 Rook-Ceph has been annihilated."