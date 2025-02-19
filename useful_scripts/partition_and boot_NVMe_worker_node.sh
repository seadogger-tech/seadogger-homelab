#!/bin/bash

# Exit on any error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    echo -e "${GREEN}=== $1 ===${NC}"
}

print_warning() {
    echo -e "${YELLOW}WARNING: $1${NC}"
}

print_error() {
    echo -e "${RED}ERROR: $1${NC}"
}

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root"
    exit 1
fi

# Function to get user confirmation
confirm() {
    read -p "This script will erase partitions and reformat them erasing all data.  USE AT YOUR OWN RISK.  This script assumes you are booting from a 64GB SD Card,  Smaller should be ok but larger than 64GB WILL NOT WORK, Do you want to continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_message "Operation cancelled by user"
        exit 1
    fi
}

# 1. Create partition table
create_partitions() {
    print_message "Creating partitions on /dev/nvme0n1"
    print_warning "This will delete all data on /dev/nvme0n1"
    confirm

    # Create GPT partition table and partitions
    sgdisk --zap-all /dev/nvme0n1
    sgdisk --new=1:2048:2099199 --typecode=1:EF00 --change-name=1:"EFI System" /dev/nvme0n1
    sgdisk --new=2:2099200:127099199 --typecode=2:8300 --change-name=2:"Linux Root" /dev/nvme0n1
    sgdisk --new=3:127099200:0 --typecode=3:8300 --change-name=3:"Data" /dev/nvme0n1
    sync
}

# 2. Format partitions
format_partitions() {
    print_message "Formatting partitions"
    mkfs.vfat -F32 /dev/nvme0n1p1
    mkfs.ext4 /dev/nvme0n1p2
    sync
}

# 3. Update system configuration files
update_system_configs() {
    print_message "Updating system configuration files"
    
    # Get PARTUUIDs
    EFI_UUID=$(blkid -s PARTUUID -o value /dev/nvme0n1p1)
    ROOT_UUID=$(blkid -s PARTUUID -o value /dev/nvme0n1p2)

    # Update /etc/fstab
    print_message "Updating /etc/fstab"
    cp /etc/fstab /etc/fstab.backup
    cat > /etc/fstab << EOF
PARTUUID=${EFI_UUID}  /boot/firmware  vfat  defaults  0  2
PARTUUID=${ROOT_UUID}  /               ext4  defaults,noatime  0  1
EOF

    # Update config.txt
    print_message "Updating config.txt"
    cp /boot/firmware/config.txt /boot/firmware/config.txt.backup
    
    # Ensure the file exists
    touch /boot/firmware/config.txt
    
    # Read existing content
    EXISTING_CONFIG=$(cat /boot/firmware/config.txt)
    
    # Create new config with existing content plus our additions
    {
        echo "$EXISTING_CONFIG"
        echo ""
        echo "# NVMe boot configuration"
        echo "dtparam=pciex1=on"
        echo "dtparam=pciex1_gen=3"
        echo "boot_delay=1"
        echo "rootwait"
    } > /boot/firmware/config.txt

    # Update cmdline.txt
    print_message "Updating cmdline.txt"
    cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.backup
    
    # Create new cmdline.txt with all necessary parameters
    echo "console=serial0,115200 console=tty1 root=PARTUUID=${ROOT_UUID} rootfstype=ext4 fsck.repair=yes rootwait" > /boot/firmware/cmdline.txt
}

# 4. Clone partitions
clone_partitions() {
    print_message "Cloning partitions from SD card to NVMe"
    dd if=/dev/mmcblk0p1 of=/dev/nvme0n1p1 bs=4M status=progress
    dd if=/dev/mmcblk0p2 of=/dev/nvme0n1p2 bs=4M status=progress
    sync
}

# 5. Verify filesystems
verify_filesystems() {
    print_message "Verifying filesystems"
    e2fsck -f /dev/nvme0n1p2 || true
    fsck.vfat -a /dev/nvme0n1p1 || true
}

# 6. Test mount
test_mount() {
    print_message "Testing mounts"
    mkdir -p /mnt/boot/firmware
    mkdir -p /mnt/root
    
    mount /dev/nvme0n1p1 /mnt/boot/firmware
    mount /dev/nvme0n1p2 /mnt/root
    
    umount /mnt/boot/firmware
    umount /mnt/root
    
    mount -a
}

# 7. Configure boot order
configure_boot() {
    print_message "Configuring boot order"
    
    # Create temporary config file
    TEMP_CONF=$(mktemp)
    
    # If existing config exists, read it
    if [ -f /boot/firmware/bootconf.txt ]; then
        cp /boot/firmware/bootconf.txt "$TEMP_CONF"
    else
        touch "$TEMP_CONF"
    fi
    
    # Update or append PCIE_PROBE
    if grep -q "^PCIE_PROBE=" "$TEMP_CONF"; then
        sed -i 's/^PCIE_PROBE=.*/PCIE_PROBE=1/' "$TEMP_CONF"
    else
        echo "PCIE_PROBE=1" >> "$TEMP_CONF"
    fi
    
    # Update or append BOOT_ORDER
    if grep -q "^BOOT_ORDER=" "$TEMP_CONF"; then
        sed -i 's/^BOOT_ORDER=.*/BOOT_ORDER=0xf416/' "$TEMP_CONF"
    else
        echo "BOOT_ORDER=0xf416" >> "$TEMP_CONF"
    fi
    
    # Apply the configuration
    rpi-eeprom-config --apply "$TEMP_CONF"
    
    # Cleanup
    rm "$TEMP_CONF"
}

# Main execution
main() {
    print_message "Starting NVMe setup script"
    
    create_partitions
    format_partitions
    update_system_configs
    clone_partitions
    verify_filesystems
#    test_mount #I think this is causing problem
    configure_boot
    
    print_message "Setup complete! Please shutdown the system, remove the SD card, and reboot."
    print_message "After reboot, verify partitions with: lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT"
}

# Run main function
main