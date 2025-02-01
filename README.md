# Raspberry Pi Cluster

## Usage

  1. Make sure [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html) is installed on your remote PC (in my case it is a Macbook Air and is attached on the same subnet as my cluster).
  2. Copy the `example.hosts.ini` inventory file to `hosts.ini`. Make sure it has the `control_plane` and `node`s configured correctly (for my examples I named my nodes `node[1-4].local`).
  3. Copy the `example.config.yml` file to `config.yml`, and modify the variables to your liking.

### Raspberry Pi Setup

I am running Raspberry Pi 64 bit OS on a 4 Pi5 cluster. 

I flashed Raspberry Pi OS (64-bit, lite) to the storage devices using Raspberry Pi Imager to a 64GB sdCard and then booted and transferred the files over to an NVMe.  Since this NVMe is 4TB I have not had much luck with rpi-clone

To make network discovery and integration easier, I edit the advanced configuration in Imager, and set the following options:

  - Set hostname: `node1.local` (set to `2` for node 2, `3` for node 3, etc.)
  - Enable SSH: 'Allow public-key', and paste in my public SSH key(s)
  - Diaable wifi

After setting all those options, and the hostname is unique to each node (and matches what is in `hosts.ini`), I inserted the microSD cards into the respective Pis, or installed the NVMe SSDs into the correct slots, and booted the cluster.

### SSH connection test

To test the SSH connection from my Ansible controller (my main workstation, where I'm running all the playbooks), I connected to each server individually, and accepted the hostkey:

```
ssh pi@node1.local
```

This ensures Ansible will also be able to connect via SSH in the following steps. You can test Ansible's connection with:

```
ansible all -m ping
```

It should respond with a 'SUCCESS' message for each node.

### Storage Configuration

#### Ceph Storage Configuration

You could also run Ceph on a Pi cluster—see the storage configuration playbook inside the `ceph` directory.

This configuration is not yet integrated into the general K3s setup.

### Cluster configuration and K3s installation

Run the playbook:

```
ansible-playbook main.yml
```

### Upgrading the cluster

Run the upgrade playbook:

```
ansible-playbook upgrade.yml
```

### Benchmarking the cluster

See the README file within the `benchmarks` folder.  Credit and Thanks to [Jeff Geerling](https://www.jeffgeerling.com)

### Shutting down the cluster

The safest way to shut down the cluster is to run the following command:

```
ansible all -m community.general.shutdown -b
```


You can reboot all the nodes with:

```
ansible all -m reboot -b
```

# Raspberry Pi 5 4TB NVMe Drive Setup

This guide will help you set up and use a **4TB NVMe drive** on a **Raspberry Pi 5**. This process involves partitioning, formatting, cloning partitions, updating `/etc/fstab`, and troubleshooting common issues.

I could not get rpi-clone to work with a 4TB drive as it seems to reset the MBR and not use GPT.  This causes the paritions to be resized so I have developed a process to perform the copy from sdCard to NVMe drive manually.  This is very tedious and problematic to weave thru.  Use at your own risk

## Steps to Set Up and Use a 4TB NVMe Drive on Raspberry Pi 5
This is important.  I am using a 64GB sdCard and all the sector definitions are based on this size sdCard.  This is important becuase if you try to copy with dd into a smaller partition or you get it too far off you will waste space.  If you are using a smaller or larger sdCard you will need to modify the partition tables.  Be carefull as there is a small and unnoticeable error messages after you dd the files over that is easy to miss and will foobar the whole thing

## Steps to Set Up and Use a 4TB NVMe Drive on Raspberry Pi 5

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

### 3. Clone the Partitions Using `dd`
1. **Clone the EFI partition**:
   ```bash
   sudo dd if=/dev/mmcblk0p1 of=/dev/nvme0n1p1 bs=4M status=progress
   ```
2. **Clone the root partition**:
   ```bash
   sudo dd if=/dev/mmcblk0p2 of=/dev/nvme0n1p2 bs=4M status=progress
   ```

### 4. Mount the Partitions
1. Create mount points:
   ```bash
   sudo mkdir -p /mnt/boot/firmware
   sudo mkdir -p /mnt/root
   ```
2. Mount the EFI partition:
   ```bash
   sudo mount /dev/nvme0n1p1 /mnt/boot/firmware
   ```
3. Mount the root partition:
   ```bash
   sudo mount /dev/nvme0n1p2 /mnt/root
   ```

### 5. Update `/etc/fstab`, `/boot/firmware/config.txt`, and `/boot/firmware/cmdline.txt` 
1. Retrieve `PARTUUID` values:
   ```bash
   sudo blkid
   ```
2. Edit `/etc/fstab`:
   ```bash
   sudo nano /mnt/root/etc/fstab
   ```
3. Update the entries to match new `PARTUUID` values. `/etc/fstab`
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

7. Update the `/boot/firmware/cmdline.txt`
```
console=serial0,115200 console=tty1 root=PARTUUID=f597843b-69f4-4ddf-b0f1-d89310f6d4f1 rootfstype=ext4 fsck.repair=yes rootwait 
```

8. Save and exit

### 6. Run `e2fsck` Check the Partitions to make sure they will boot!!!!
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

### 7. Reload systemd and Remount Filesystems
1. Reload systemd:
   ```bash
   sudo systemctl daemon-reload
   ```
2. Remount all filesystems:
   ```bash
   sudo mount -a
   ```

### 8. Setup the NVMe to boot first and Reboot the System
1. `sudo rpi-eeprom-config --edit`

2. Add the following:
  ```
  PCIE_PROBE=1
  BOOT_ORDER=0xf416
  ```

3. Shutdown:
   ```bash
   sudo shutdown now
   ```
4. Pull sdCard out and reboot

5. Verify partitions are correctly mounted:
   ```bash
   lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
   ```

### 9. Troubleshoot 4TB Drive Issues
1. Update the Raspberry Pi OS:
   ```bash
   sudo apt update && sudo apt full-upgrade
   ```
2. Ensure the partition table is GPT using `gdisk`.
3. Check power supply (use powered USB hub if necessary).
4. Update Raspberry Pi firmware:
   ```bash
   sudo rpi-eeprom-update -a
   sudo reboot
   ```

### 10. Summary
1. Partition the NVMe drive using GPT.
2. Format partitions (`vfat` for EFI, `ext4` for root).
3. Clone partitions from the SD card using `dd`.
4. Mount the partitions.
5. Update `/etc/fstab`.
6. Run `e2fsck` if partitions fail to mount.
7. Reload systemd and remount filesystems.
8. Reboot the system and verify partitions.
9. Troubleshoot 4TB drive issues if necessary.

## Author

The repository was created in 2025 by [seadogger]() using the examples from [Jeff Geerling](https://www.jeffgeerling.com).