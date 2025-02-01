#!/bin/bash

echo "Checking installed packages..."
packages=("btop" "open-iscsi" "nfs-common" "util-linux" "cryptsetup")
for pkg in "${packages[@]}"; do
    if dpkg -l | grep -qw "$pkg"; then
        echo "[✔] $pkg is installed"
    else
        echo "[✘] $pkg is NOT installed"
    fi
done

echo "Checking if iscsid service is enabled and running..."
if systemctl is-enabled iscsid &>/dev/null; then
    echo "[✔] iscsid service is enabled"
else
    echo "[✘] iscsid service is NOT enabled"
fi

if systemctl is-active --quiet iscsid; then
    echo "[✔] iscsid service is running"
else
    echo "[✘] iscsid service is NOT running"
fi

echo "Checking loaded kernel modules..."
modules=("dm_crypt" "rbd")
for mod in "${modules[@]}"; do
    if lsmod | grep -qw "$mod"; then
        echo "[✔] Kernel module $mod is loaded"
    else
        echo "[✘] Kernel module $mod is NOT loaded"
    fi
done

echo "Checking /etc/modules for persistence..."
for mod in "${modules[@]}"; do
    if grep -qx "$mod" /etc/modules; then
        echo "[✔] $mod is listed in /etc/modules"
    else
        echo "[✘] $mod is NOT listed in /etc/modules"
    fi
done

echo "Checking Raspberry Pi firmware version..."
if uname -r | grep -q "6.6"; then
    echo "[✔] Kernel is updated to rpi-6.6.y"
else
    echo "[✘] Kernel is NOT updated to rpi-6.6.y"
fi

echo "Check complete!"