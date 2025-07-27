#!/bin/bash

set -e

echo "Starting complete Rook-Ceph cleanup..."

# Delete all Rook-Ceph resources
echo "Deleting Helm releases..."
helm delete rook-ceph-cluster -n rook-ceph 2>/dev/null || true
helm delete rook-ceph -n rook-ceph 2>/dev/null || true

echo "Removing finalizers from CephCluster..."
kubectl -n rook-ceph patch cephcluster rook-ceph --type merge -p '{"metadata":{"finalizers": []}}' 2>/dev/null || true

echo "Deleting Ceph resources..."
kubectl -n rook-ceph delete cephcluster --all --force --grace-period=0 2>/dev/null || true
kubectl -n rook-ceph delete cephblockpool --all --force --grace-period=0 2>/dev/null || true
kubectl -n rook-ceph delete cephfilesystem --all --force --grace-period=0 2>/dev/null || true
kubectl -n rook-ceph delete cephobjectstore --all --force --grace-period=0 2>/dev/null || true

echo "Deleting namespace..."
kubectl delete namespace rook-ceph --force --grace-period=0 2>/dev/null || true

echo "Deleting CRDs..."
for crd in $(kubectl get crd | grep -i ceph | awk '{print $1}'); do
    kubectl delete crd $crd --force --grace-period=0 2>/dev/null || true
done

# Clean up storage on each node
for node in anakin obiwan rey; do
    echo "Cleaning up node $node..."
    ssh pi@$node.local "
        sudo rm -rf /var/lib/rook
        sudo rm -rf /var/lib/kubelet/plugins/rook*
        sudo rm -rf /var/lib/kubelet/plugins_registry/rook*
        sudo rm -rf /dev/mapper/ceph-*
        sudo dmsetup remove_all
        sudo wipefs -af /dev/nvme0n1p3
        sudo sgdisk --zap-all /dev/nvme0n1p3
    " || echo "Failed to clean $node completely"
done

echo "Cleanup complete!"