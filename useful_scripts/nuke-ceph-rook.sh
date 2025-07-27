#!/bin/bash

echo "Starting aggressive Rook-Ceph cleanup..."

# Remove finalizers from all resources first
for kind in cephcluster cephblockpool cephfilesystem cephobjectstore; do
    for resource in $(kubectl -n rook-ceph get $kind -o name 2>/dev/null); do
        echo "Removing finalizers from $resource"
        kubectl -n rook-ceph patch $resource --type merge -p '{"metadata":{"finalizers":[]}}' 2>/dev/null || true
    done
done

# Delete Helm releases with timeout
echo "Deleting Helm releases..."
helm delete rook-ceph-cluster -n rook-ceph --timeout 5m 2>/dev/null || true
helm delete rook-ceph -n rook-ceph --timeout 5m 2>/dev/null || true

# Force delete all Rook-Ceph resources
echo "Force deleting Rook-Ceph resources..."
for kind in $(kubectl api-resources --verbs=delete -o name); do
    kubectl -n rook-ceph get $kind -o name 2>/dev/null | \
    while read resource; do
        echo "Force deleting $resource"
        kubectl -n rook-ceph delete $resource --force --grace-period=0 2>/dev/null || true
    done
done

# Remove the namespace finalizer
echo "Removing namespace finalizer..."
kubectl get namespace rook-ceph -o json | jq '.spec.finalizers = []' | kubectl replace --raw "/api/v1/namespaces/rook-ceph/finalize" -f - 2>/dev/null || true

# Force delete namespace
echo "Force deleting namespace..."
kubectl delete namespace rook-ceph --force --grace-period=0 2>/dev/null || true

# Delete CRDs
echo "Deleting CRDs..."
for crd in $(kubectl get crd | grep -E 'ceph.rook.io|objectbucket.io' | awk '{print $1}'); do
    echo "Deleting CRD $crd"
    kubectl patch crd $crd --type merge -p '{"metadata":{"finalizers":[]}}' 2>/dev/null || true
    kubectl delete crd $crd --force --grace-period=0 2>/dev/null || true
done

# Clean up storage on each node
for node in anakin obiwan rey; do
    echo "Cleaning up node $node..."
    ssh pi@$node.local "
        sudo systemctl stop rook-ceph-operator || true
        sudo killall -9 ceph-osd || true
        sudo killall -9 ceph-mon || true
        sudo killall -9 ceph-mgr || true
        sudo rm -rf /var/lib/rook
        sudo rm -rf /var/lib/kubelet/plugins/rook*
        sudo rm -rf /var/lib/kubelet/plugins_registry/rook*
        sudo rm -rf /dev/mapper/ceph-*
        sudo rm -rf /dev/ceph-*
        sudo dmsetup remove_all || true
        sudo wipefs -af /dev/nvme0n1p3 || true
        sudo dd if=/dev/zero of=/dev/nvme0n1p3 bs=1M count=100 || true
        sudo sgdisk --zap-all /dev/nvme0n1p3 || true
    " || echo "Warning: Some cleanup commands failed on $node"
done

# Verify all pods are gone
echo "Waiting for all pods to be deleted..."
while kubectl -n rook-ceph get pods 2>/dev/null | grep -q .; do
    echo "Waiting for pods to be deleted..."
    sleep 5
done

echo "Cleanup complete! Please check for any remaining resources manually."

# Final verification
echo "Checking for remaining resources..."
kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found -n rook-ceph

echo "Checking for Rook-Ceph CRDs..."
kubectl get crd | grep -E 'ceph.rook.io|objectbucket.io' || echo "No Rook-Ceph CRDs found"