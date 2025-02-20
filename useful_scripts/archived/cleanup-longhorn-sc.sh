#!/bin/bash

echo "=== Checking for Longhorn Resources ==="

# 1. Check Longhorn Namespace
echo "1. Checking Longhorn Namespace..."
if kubectl get namespace longhorn-system &>/dev/null; then
    echo "❌ Longhorn namespace still exists"
else
    echo "✅ Longhorn namespace not found"
fi

# 2. Check Longhorn CRDs
echo "2. Checking Longhorn CRDs..."
if kubectl get crd | grep -q "longhorn.io"; then
    kubectl get crd | grep "longhorn.io"
    echo "❌ Longhorn CRDs still exist"
else
    echo "✅ No Longhorn CRDs found"
fi

# 3. Check Longhorn StorageClass
echo "3. Checking for Longhorn StorageClass..."
if kubectl get storageclass | grep -q "longhorn"; then
    echo "❌ Longhorn StorageClass still exists"
else
    echo "✅ No Longhorn StorageClass found"
fi

# 4. Check Longhorn PVs
echo "4. Checking for Longhorn PVs..."
PV_OUTPUT=$(kubectl get pv | grep "longhorn")
if [ -n "$PV_OUTPUT" ]; then
    echo "$PV_OUTPUT"
    echo "❌ Longhorn PVs still exist"
else
    echo "No resources found"
    echo "✅ No Longhorn PVs found"
fi

# 5. Check Longhorn PVCs
echo "5. Checking for Longhorn PVCs..."
PVC_OUTPUT=$(kubectl get pvc --all-namespaces | grep "longhorn")
if [ -n "$PVC_OUTPUT" ]; then
    echo "$PVC_OUTPUT"
    echo "❌ Longhorn PVCs still exist"
else
    echo "No resources found"
    echo "✅ No Longhorn PVCs found"
fi

# 6. Check Longhorn DaemonSet
echo "6. Checking for Longhorn DaemonSet..."
if kubectl get ds --all-namespaces | grep -q "longhorn"; then
    kubectl get ds --all-namespaces | grep "longhorn"
    echo "❌ Longhorn DaemonSet still exists"
else
    echo "✅ No Longhorn DaemonSet found"
fi

# 7. Check Longhorn Deployments
echo "7. Checking for Longhorn Deployments..."
if kubectl get deployments --all-namespaces | grep -q "longhorn"; then
    kubectl get deployments --all-namespaces | grep "longhorn"
    echo "❌ Longhorn Deployments still exist"
else
    echo "✅ No Longhorn Deployments found"
fi

# 8. Check for Longhorn Pods
echo "8. Checking for Leftover Longhorn Pods..."
if kubectl get pods --all-namespaces | grep -q "longhorn"; then
    kubectl get pods --all-namespaces | grep "longhorn"
    echo "❌ Longhorn pods still exist"
else
    echo "✅ No Longhorn pods found"
fi

# 9. Check for Longhorn ConfigMaps
echo "9. Checking for Longhorn ConfigMaps..."
if kubectl get configmaps --all-namespaces | grep -q "longhorn"; then
    kubectl get configmaps --all-namespaces | grep "longhorn"
    echo "❌ Longhorn ConfigMaps still exist"
else
    echo "✅ No Longhorn ConfigMaps found"
fi

# 10. Check for Longhorn Secrets
echo "10. Checking for Longhorn Secrets..."
if kubectl get secrets --all-namespaces | grep -q "longhorn"; then
    kubectl get secrets --all-namespaces | grep "longhorn"
    echo "❌ Longhorn Secrets still exist"
else
    echo "✅ No Longhorn Secrets found"
fi

# Optional: Check for Longhorn volumes on nodes
# echo "11. Checking for Longhorn volumes on nodes..."
# if [ -d "/var/lib/longhorn" ]; then
#     echo "❌ Longhorn volume directory exists on node"
#     ls -l /var/lib/longhorn
# else
#     echo "✅ No Longhorn volume directory found"
# fi