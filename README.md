# Raspberry Pi 5 4TB NVMe Drive Setup

This guide will help you set up and use a **4TB NVMe drive** on a **Raspberry Pi 5**. This process involves partitioning, formatting, cloning partitions, updating `/etc/fstab`, and troubleshooting common issues.

I could not get `rpi-clone` to work with a 4TB drive as it seems to reset the MBR and not use GPT.  This causes the paritions to be resized so this is a manual process to perform the copy from sdCard to NVMe drive.  This is very tedious and problematic to weave thru.  **Use at your own risk!**

I am using a 64GB sdCard and transitioning the `/boot` and `/` mounts to a `4TB NVMe` using the `52Pi POE plus PCIe HAT`.  This will partition the NVMe just slifhtly larger than the partitions on the sdCard so the dd transfers complete without error but we do not waster a ton of space.  All the sector definitions are based on this size sdCard for gdisk.  If you are using a smaller or larger sdCard you will need to modify the partition tables.  Be carefull as there is a small and unnoticeable error messages after you dd the files over that is easy to miss and will foobar the whole thing.


### 1. Prepare the 4TB NVMe Drive

#### 1.1. Open `gdisk` to Partition the NVMe Drive
1. Open `gdisk` on the NVMe drive:
   ```bash
   sudo gdisk /dev/nvme0n1
   ```

#### 1.2. Create Partitions for the Drive
1. **Delete existing partitions** (if necessary):
   - Type `d` to delete any existing partitions.

2. **Create the EFI Partition (`/dev/nvme0n1p1`)**:
   - **Partition number**: `1` (default).
   - **First sector**: `2048` (default).
   - **Last sector**: `2099199`.
   - **Hex code**: `EF00` for EFI system partition.

3. **Create the Root Partition (`/dev/nvme0n1p2`)**:
   - **Partition number**: `2` (default).
   - **First sector**: `2099200`.
   - **Last sector**: `127099199`.
   - **Hex code**: `8300` for Linux filesystem.

4. **Optional: Create the third partition** (for data) if needed:
   - **Partition number**: `3` (default).
   - **First sector**: Next available sector.
   - **Last sector**: Use remaining space.

5. **Write the Partition Table**:
   - Type `p` to print the partition table and verify.
   - Type `w` to write the changes and exit `gdisk`.

### 2. Format the Partitions
1. **Format the EFI partition (`/dev/nvme0n1p1`)**:
   ```bash
   sudo mkfs.vfat -F32 /dev/nvme0n1p1
   ```
2. **Format the root partition (`/dev/nvme0n1p2`)**:
   ```bash
   sudo mkfs.ext4 /dev/nvme0n1p2
   ```
3. **Optional: Format Partition 3 (`/dev/nvme0n1p3`)**:
   ```bash
   sudo mkfs.ext4 /dev/nvme0n1p3
   ```

### 3. Update `/etc/fstab`, `/boot/firmware/config.txt`, and `/boot/firmware/cmdline.txt` 
1. Retrieve `PARTUUID` values:
   ```bash
   sudo blkid
   ```
2. Edit `/etc/fstab`:
   ```bash
   sudo nano /mnt/root/etc/fstab
   ```
3. Update the entries to match new `PARTUUID` from the `blkid` return values. `/etc/fstab`
```
PARTUUID=3eea8674-a042-4467-a338-2776bd91343c  /boot/firmware  vfat  defaults  0  2
PARTUUID=f597843b-69f4-4ddf-b0f1-d89310f6d4f1  /               ext4  defaults,noatime  0  1
```
4. Save and exit.

5. Update `/boot/firmware/config.txt` append to the end
```
 dtparam=pciex1
 dtparam=pciex1_gen=3
 boot_delay=1
 rootwait
```
6. Save and exit

7. Update the `/boot/firmware/cmdline.txt` to put the `/` Partition UUID in the command line:
```
console=serial0,115200 console=tty1 root=PARTUUID=f597843b-69f4-4ddf-b0f1-d89310f6d4f1 rootfstype=ext4 fsck.repair=yes rootwait 
```

8. Save and exit

### 4. Clone the sdCard Partitions to the NVMe Partitions Using `dd`
1. **Clone the EFI partition**:
   ```bash
   sudo dd if=/dev/mmcblk0p1 of=/dev/nvme0n1p1 bs=4M status=progress
   ```
2. **Clone the root partition**:
   ```bash
   sudo dd if=/dev/mmcblk0p2 of=/dev/nvme0n1p2 bs=4M status=progress
   ```

### 5. Run `e2fsck` to verify the NVMe Partitions are intact and ready to support booting
1. Run `e2fsck`:
   ```bash
   sudo e2fsck -f /dev/nvme0n1p2
   ```
2. Try a different superblock if needed:
   ```bash
   sudo e2fsck -b 32768 /dev/nvme0n1p2
   ```
3. Check the VFAT partition
   ```bash
   sudo fsck.vfat -a /dev/nvme0n1p1
   ```
4. Have fsck and efsck repair anything it finds

5. Check `/boot/firmware/config.txt` and `/boot/firmware/cmdline.txt` files if this had any failures

### 6. Mount the Partitions
1. Reload systemd:
   ```bash
   sudo systemctl daemon-reload
   ```
2. Create mount points:
   ```bash
   sudo mkdir -p /mnt/boot/firmware
   sudo mkdir -p /mnt/root
   ```
3. Mount the EFI partition:
   ```bash
   sudo mount /dev/nvme0n1p1 /mnt/boot/firmware
   ```
4. Mount the root partition:
   ```bash
   sudo mount /dev/nvme0n1p2 /mnt/root
   ```

### 7. Make sure the '/etc/fstab' is correct 
1. Un Mount the partitions:
   ```bash
   sudo umount /mnt/boot/firmware
   sudo umount /mnt/root
   ```

2. Remount all filesystems:
   ```bash
   sudo mount -a
   ```
Make sure this mounts everything without errors otherwise there is a problem in the /etc/fstab and you need to to look into that problem before proceeding

### 8. Setup the NVMe to boot first and Reboot the System
1. `sudo raspi-config` 
Under advanced options set the boot order to boot the NVMe first.  When prompted to reboot `decline`.  
We will reboot in the next step.

2. `sudo rpi-eeprom-config --edit`

3. Add and modify the following to set the boot order:
    ```
    PCIE_PROBE=1
    BOOT_ORDER=0xf416
    ```

4. Shutdown:
   ```bash
   sudo shutdown now
   ```
5. Pull the sdCard out and reboot

6. Verify partitions are correctly mounted:
   ```bash
   lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
   ```

### 9. Troubleshoot 4TB Drive Issues
1. Update the Raspberry Pi OS:
   ```bash
   sudo apt update && sudo apt full-upgrade
   ```
2. Ensure the partition table is GPT using `gdisk`.
4. Update Raspberry Pi firmware:
   ```bash
   sudo rpi-eeprom-update -a
   sudo reboot
   ```

## Summary
1. Partition the NVMe drive using GPT.
2. Format partitions (`vfat` for EFI, `ext4` for root).
3. Clone partitions from the SD card using `dd`.
4. Mount the partitions.
5. Update `/etc/fstab`, `/boot/firmware/config.txt`, and `/boot/firmware/cmdline.txt`
7. Cloning the sdCard to the NVMe partition structure
6. Running disk checks on the NVMe `e2fsck` and `fsck.vfat`
7. Reload systemd daemon.
8. Rebooting and system verify everything worked.
9. Shutting down and removing the sdCard
9. Troubleshooting ideas if necessary.

# Raspberry Pi Cluster Mangement with Ansible

## Usage

  1. Make sure [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html) is installed on your remote PC (in my case it is a Macbook Air and is attached on the same subnet as my cluster).
  
  2. Copy the `example.hosts.ini` inventory file to `hosts.ini`. Make sure it has the `control_plane` and `node`(s) configured correctly (for my examples I named my nodes `node[1-4].local`).
  
  3. Copy the `example.config.yml` file to `config.yml`, and modify the variables to your liking.

### Raspberry Pi Setup

This setup assumes a Raspberry Pi5 64 bit OS Lite (no desktop) will be setup in a k3s cluster with a single server node and 3 worker nodes with 4TB in each worker node. 

The approach taken to get to here included flashing the Raspberry Pi OS (64-bit, lite) to the storage devices using Raspberry Pi Imager onto a 64GB sdCard.  This was then installed into each Pi and transferred to the NVMe in the previous section.  This should be successful before proceeding into this step.

To make network discovery and integration easier, I edit the advanced configuration in Imager, and set the following options:

  - Set hostname: `node1.local` (set to `2` for node 2, `3` for node 3, etc.)
  - Enable SSH
  - Disable WiFi

  `TODO - put a picture of the remote session with cluster`
  `TODO - Use ssh-copy-id to get the cluster to work with remote ansible`

After setting all those options, and the hostname is unique to each node (and matches what is in `hosts.ini`), I inserted the microSD cards into the respective Pis, or installed the NVMe SSDs into the correct slots, and booted the cluster.

### SSH connection test

To test the SSH connection from the host or PC you intend to run Ansible from, connect to each server individually, and accepted the hostkey.  This must be done for all nodes so password is not requested by the nodes during the Ansible playbook run:

```
ssh-copy-id pi@node[X].local
ssh pi@node[X].local
```

This ensures Ansible will also be able to connect via SSH in the following steps. You can test Ansible's connection with:

```
ansible all -m ping
```

It should respond with a 'SUCCESS' message for each node.


### Cluster configuration and K3s installation

Run the playbook:

```
ansible-playbook main.yml
```
   1.  Update apt package cache
   2.  Ensure cgroups are configured correctly in cmdline.txt.
   3.  Install necessary packages
   4.  Enable and start iscsid service
   5.  Ensure PCIe settings exist in config.txt
   6.  Load dm_crypt kernel module
   7.  Load rbd kernel module
   8.  Append dm_crypt and rbd to /etc/modules
   9.  Update Raspberry Pi firmware to rpi-6.6.y
   10. Setup/deploy k3s to the control_plane (e.g. server node)
   11. Setup/deploy k3s to the worker node(s)

### Upgrading the cluster

Run the upgrade playbook:

```
ansible-playbook upgrade.yml
```

### Benchmarking the cluster

See the README file within the `benchmarks` folder.  **Credit and Thanks to [Jeff Geerling](https://www.jeffgeerling.com)**

### Shutting down the cluster

The safest way to shut down the cluster is to run the following command:

```
ansible all -m community.general.shutdown -b
```

You can reboot all the nodes with:

```
ansible all -m reboot -b
```

### CEPH-ROOK Storage Configuration

TODO You could also run Ceph on a Pi cluster—see the storage configuration playbook inside the `ceph` directory.

This configuration is not yet integrated into the general K3s setup.

### ArgoCD Deployment 
TODO:  We will use gitOps design pattern to deploy apps, update, manage the cluster


# Cluster App Deployment using GitOps with ArgoCD
`TODO`

## Author

The repository was forked from [Jeff Geerling](https://www.jeffgeerling.com)'s Pi-Cluster project and was modified to support my cluster requirements and deployment by [seadogger]().