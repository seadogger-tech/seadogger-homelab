#!/bin/bash

echo "Starting K3s worker node uninstallation..."

# Step 1: Run the official K3s uninstall script (this is available on worker nodes as well)
if [ -f /usr/local/bin/k3s-uninstall.sh ]; then
  echo "Running K3s uninstall script..."
  sudo /usr/local/bin/k3s-uninstall.sh
else
  echo "K3s uninstall script not found, skipping."
fi

# Step 2: Clean up K3s-related directories
echo "Cleaning up K3s directories..."
sudo rm -rf /etc/rancher/k3s
sudo rm -rf /var/lib/rancher/k3s
sudo rm -rf /var/log/k3s

# Step 3: Remove kubeconfig file (optional)
echo "Removing Kubeconfig..."
sudo rm -f /etc/rancher/k3s/k3s.yaml

# Step 4: Verify that K3s is gone
echo "Verifying uninstallation..."

# Check for K3s processes
if pgrep -x "k3s" > /dev/null; then
  echo "Error: K3s process still running."
else
  echo "K3s process not running."
fi

# Check if K3s-related files still exist
if [ -d /etc/rancher/k3s ] || [ -d /var/lib/rancher/k3s ] || [ -d /var/log/k3s ]; then
  echo "Error: Some K3s directories still exist."
else
  echo "K3s directories removed successfully."
fi

# Check if kubeconfig exists
if [ -f /etc/rancher/k3s/k3s.yaml ]; then
  echo "Error: K3s kubeconfig file still exists."
else
  echo "K3s kubeconfig file removed successfully."
fi

echo "K3s worker node uninstallation complete!"
