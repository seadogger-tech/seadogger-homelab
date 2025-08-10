# HomeLab Raspberry Pi k3s Deployment Guide

## Architecture Overview

![Pi Cluster Architecture](images/Architecture.png)


## Project Status
For detailed, up-to-date information about the project's context, architecture, and progress, please refer to the `memory-bank/` directory.

### Current Working State

### Core Infrastructure

1. Node Configuration
   - Control Plane: yoda (192.168.1.95)
   - Workers: anakin.local, obiwan.local, rey.local
   - K3s Version: v1.32.6+k3s1
   - OS: Debian GNU/Linux 12 (bookworm)
   - Kernel: 6.6.51+rpt-rpi-2712

2. Storage System (Rook-Ceph)
   - Status: HEALTH_OK
   - Capacity: 11 TiB total available
   - Configuration:
     * 3 OSDs using NVMe devices
     * 1 active MDS with 1 hot standby
     * Erasure-coded data pool (2+1)
     * Replicated metadata pool (size 3)

3. Network Configuration
   - MetalLB IP Range: 192.168.1.241-254
   - Service IP Assignments:
     * Traefik: 192.168.1.241
     * Bedrock Gateway: 192.168.1.242
     * OpenWebUI: 192.168.1.243
     * Prometheus: 192.168.1.244
     * Grafana: 192.168.1.245
     * Alertmanager: 192.168.1.246
     * ArgoCD: 192.168.1.247
     * Ceph Dashboard: 192.168.1.248
     * PiHole Web: 192.168.1.249
     * PiHole DNS: 192.168.1.250
     * Plex: 192.168.1.251
     * N8N: 192.168.1.252

### Deployed Applications

1. Core Services
   - ArgoCD: GitOps deployment management
   - Traefik: Ingress controller
   - MetalLB: Load balancer for bare metal

2. User Services
   - PiHole: DNS and ad blocking
   - OpenWebUI: Web interface for AI interactions
   - Bedrock Access Gateway: AWS Bedrock integration
   - N8N: Workflow automation

### Storage Classes
   - rook-ceph-filesystem-ec: Erasure-coded filesystem (default for shared storage)
   - ceph-block: RBD block storage (default for block storage)
   - local-path: Local storage provisioner

All components are managed through ArgoCD, ensuring GitOps practices and consistent deployment states.


## Prerequisites

### Hardware Requirements
- Raspberry Pi5 nodes (1 server node and 3 worker nodes)
- POE switch (recommended: Ubiquiti Dream @Machine SE)
  - Powers Raspberry Pis via POE HAT
  - Simplifies the wiring and setup, but not totally neccessary.  
  - **If you do not use POE, adjust the BoM (e.g. rack mounted solution will be different, likely)**
- Ethernet cables for hardwired connections
  - WiFi is disabled and not recommended for k3s clusters

### Network Setup
- DHCP static IP assignments for all Raspberry Pis
  - Configured on network switch for centralized management
  - Static IPs required for k3s cluster nodes
- DHCP service range configuration
  - Reserve IPs up to 192.168.1.239
  - Leaves space for MetalLB allocation above this range
  - NOTE - If you are using a different subnet, there is a lot of changes to apply throughout the deployment scripts.  
  `TODO: centralize the subnet in the ansible manifest config.yaml`
- WireGuard (optional)
  - Required only for remote access
  - Provides encrypted tunnels for services like OpenWebUI, PiHole when you are not on your network

### Software Requirements
- SSH enabled on all Raspberry Pis
- AWS account with [Bedrock](https://jrpospos.blog/posts/2024/08/using-amazon-bedrock-with-openwebui-when-working-with-sensitive-data/) API tokens
- Working knowledge of:
  - Docker containers and orchestration
  - Basic AWS services
  - Git and GitHub CLI tools

### Development Environment
- VS Code (recommended) with:
  - Continue Extension
  - SSH Remote Extension
- Alternative: SSH terminal access


# Bill of Materials

| Item | Quantity | Cost per Unit | Total Cost |
|------|----------|--------------|------------|
| [Raspberry Pi 5 8GB](https://www.digikey.com/en/products/detail/raspberry-pi/SC1112/21658257?s=N4IgjCBcpgrAnADiqAxlAZgQwDYGcBTAGhAHsoBtEAJngBYwwB2EAXRIAcAXKEAZS4AnAJYA7AOYgAviQC0dFCHSRs%2BYmUrgAzAAYdW5CUbwmYeGykyamwVjwcARgUGCAngAIOw2BaA) | 4 | $80 | $320 |
| [Raspberry Pi Rack](https://www.amazon.com/gp/product/B09D7RR6NY/ref=ewc_pr_img_2?smid=A2IAB2RW3LLT8D&psc=1) | 1 | $53 | $53 |
| [GPIO Header with shorter standoff](https://www.amazon.com/dp/B084Q4W1PW?ref=ppx_yo2ov_dt_b_fed_asin_title) | 1 | $10 | $10 |
| [Raspberry Pi 5 POE HAT with PCIe](https://www.amazon.com/dp/B0D8JC3MXQ?ref=ppx_yo2ov_dt_b_fed_asin_title) | 4 | $37 | $148 |
| [Crucial P3 4TB NVMe SSD](https://www.newegg.com/crucial-4tb-p3/p/N82E16820156298?Item=9SIA12KJ9P1073) | 3 | $225 | $675 |
| [Crucial P3 500GB NVMe SSD](https://www.newegg.com/crucial-500gb-p3-nvme/p/N82E16820156295) | 1 | $38 | $38 |
| [Nylon Standoff Kit](https://www.amazon.com/gp/product/B06XKWDSPT/ref=ox_sc_act_title_1?smid=A2XXMW1BKOEL72&psc=1) | 1 | $13 | $13 |
| [64GB sdCard](https://www.amazon.com/dp/B08879MG33?ref_=ppx_hzsearch_conn_dt_b_fed_asin_title_13&th=1) | 1 | $25 | $25 |
| **Total Cost (Excludes POE Switch)** | **-** | **-** | **$1282** |

# Get Remote PC ready for Ansible Deployment 
Clone the Ansible tasks to your remote PC to that will manage the k3s cluster
   ```bash
   git clone https://github.com/seadogger/seadogger-homelab.git
   ```

# Raspberry Pi 5 Setup

## POE HAT and Drive install

Install POE HAT with NVMe PCIe adapter on all Raspberry Pi 5s

![Hardware Build](images/Single-Node-Mounted-2.jpeg) 

> **Note**: The BoM includes nylon standoffs.  The solution I found uses an 11mm male standoff with a 2mm nut on the male standoff and a 2mm nylon nut on top with a nylon screw thru to the top nut and into the standoff.  This gives you about 15.5mm of total height between the Pi and the POE HAT.  Less than that and it will not fit over the USB ports.  More than that and the POE transformer hits the top of the rack

![Hardware Build](images/Rack-Mounted-Pi5-Nodes.jpeg)

## NVMe Drive list recommendations

> **Note**: I have not tested all the drives from this list.   The NVMe drives in the latest BoM do work with the HAT and Pi5 

> **Note**:  [This](https://www.amazon.com/gp/product/B08DTP8LG8/ref=ewc_pr_img_1?smid=A2CP9SZGVW0PFE&th=1) NVMe drive has been tested and does not work. **DO NOT BUY this one!**

![NVME Drive List](images/SSD-Compatibility.png)

## [Raspberry Pi Setup](https://youtu.be/x9ceI0_r_Kg)

This setup assumes a Raspberry Pi5 64 bit OS Lite (no desktop) will be setup in a k3s cluster with a single server node and 3 worker nodes with 4TB in each worker node. 

The approach taken to get to here included flashing the Raspberry Pi OS (64-bit, lite) to the storage devices using Raspberry Pi Imager onto a 64GB sdCard.  This was then installed into each Pi and transferred to the NVMe in the previous section.  This should be successful before proceeding into this step.

To make network discovery and integration easier, I edit the advanced configuration in Imager, and set the following options:

  - Set hostname: `node1.local` (set to `2` for node 2, `3` for node 3, etc.)
  - Enable SSH
  - Disable WiFi

After setting all those options, and the hostname is unique to each node (and matches what is in `hosts.ini`), I inserted the microSD cards into the respective Pis, or installed the NVMe SSDs into the correct slots, and booted the cluster.


## SSH connection test

To test the SSH connection from the host or PC you intend to run Ansible from, connect to each server individually, and accepted the hostkey.  This must be done for all nodes so password is not requested by the nodes during the Ansible playbook run:

```
ssh-copy-id pi@node[X].local
ssh pi@192.168.1.[X]
ssh pi@node[X].local
```

This ensures Ansible will also be able to connect via SSH in the following steps. You can test Ansible's connection with:

```
ansible all -m ping
```

It should respond with a 'SUCCESS' message for each node.

## NVMe Boot and 4TB NVMe Drive Setup  

This guide will help you set up and use a **4TB NVMe drive** on a **Raspberry Pi 5**. This process involves partitioning, formatting, cloning partitions, updating `/etc/fstab`, and troubleshooting common issues.

`rpi-clone` seems to reset the partition table to MBR vs. GPT so we lose storage space as MBR is confined to 2TB.  These scripts are very specific the hardware stack choosen in the BoM for partition setup and reformats these partitions and you will lose any data on them.  **Use at your own risk!**

I am using a 64GB sdCard and transitioning the `/boot` and `/` mounts to a `4TB NVMe` using the `52Pi POE w/PCIe HAT`.  This will partition the NVMe just slightly larger than the partitions on the sdCard so the rsync transfers complete without error but we do not waste a ton of space.  

> **Note**: All the sector definitions are based on this size sdCard for gdisk.  If you are using a smaller or larger sdCard you will need to modify the partition tables settings in these scripts.  

### Prepare the 512GB NVMe Drive (Master Node)
```bash
   git clone https://github.com/seadogger/seadogger-homelab.git
   cd seadogger-homelab/useful-scripts
   sudo ./partition_and_boot_NVMe_master_node.sh
```

### Prepare the 4TB NVMe Drive (Worker / Storage Node)
```bash
   git clone https://github.com/seadogger/seadogger-homelab.git
   cd seadogger-homelab/useful-scripts
   sudo ./partition_and_boot_NVMe_worker_node.sh
```
> **Note**:  Rook does not want formatted partitions which is different than Longhorn so the Partitioning and Cloning script leaves the 3rd partition completely alone and unformatted.

> **Note**: Rook and Ceph are more enterprise ready and enables future growth into LakeFS

## Rook-Ceph Storage Configuration

The cluster uses Rook-Ceph for distributed storage with:
- 3 OSDs using NVMe devices
- 1 active MDS with 1 standby
- Erasure-coded data pool (2+1)
- Replicated metadata pool (size 3)

### Important Notes

1. Node Names
   - The configuration uses specific node names (anakin.local, obiwan.local, rey.local)
   - Update these in the values file if node names change

2. Storage Pool Naming
   - Data pool is named "data" in the configuration
   - Ceph automatically prefixes this with the filesystem name (e.g., "ec-fs-data")
   - This is important when referencing pools in storage class configurations

3. Resource Requirements
   - MDS requires at least 512MB memory (4GB recommended)
   - Adjust resource limits based on workload

4. Storage Classes
   - rook-ceph-filesystem-ec: For CephFS with erasure coding
   - ceph-block: For RBD (default)


## Script Summary

1. Partition the NVMe drive using GPT.
2. Format partitions (`vfat` for EFI, `ext4` for root).
3. Clone partitions from the SD card using `rsync`.
4. Update `/etc/fstab`, `/boot/firmware/config.txt`, and `/boot/firmware/cmdline.txt`
5. Cloning the sdCard to the NVMe partition structure
6. Running disk checks on the NVMe `e2fsck` and `fsck.vfat`
7. Reload systemd daemon.
8. A few manual steps after the script runs to get everything ready (Change boot order, shutdown and reboot)

> **Note**: Before you reboot after the above you need to setup for NVMe to boot first in the boot order
- Set the NVMe first in the boot order 
    ```bash
     sudo raspi-config
    ``` 
Under advanced options set the boot order to boot the NVMe first.  
> **Note**: When prompted to reboot **`decline`.  We will reboot in the next step.**

- Shutdown:
   ```bash
   sudo shutdown now
   ```
- Pull the sdCard out and reboot

- Verify partitions are correctly mounted:
   ```bash
   lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
   ```
### Master Node
![Partition Info](images/Partition-Map-NVMe.png)

### Worker / Storage Nodes
![Partition Info](images/Partition-Map-NVMe-worker.png)

# Raspberry Pi Cluster Mangement with Ansible

## Usage

  1. Make sure [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html) is installed on your remote PC (in my case it is a Macbook Air and is attached on the same subnet as my cluster).
  
  2. Copy the `example.hosts.ini` inventory file to `hosts.ini`. Make sure it has the `control_plane` and `node`(s) configured correctly.
  
  3. Copy the `example.config.yml` file to `config.yml`, and modify the variables to your setup.


## Cluster configuration, K3s, App deployment

**This is where the magic of Ansible and ArgoCD take over**

Run the playbook:

```
ansible-playbook main.yml
```

   - Updates apt package cache
   - Configures cgroups are configured correctly in cmdline.txt.
   - Installs necessary packages
   - Enables and starts iscsid service
   - Configures PCIe settings exist in config.txt
   - Loads dm_crypt kernel module
   - Loads rbd kernel module
   - Appends dm_crypt and rbd to /etc/modules
   - Updates Raspberry Pi firmware to rpi-6.6.y
   - Setup/deploy k3s to the control_plane (e.g. server node)
   - Setup/deploy k3s to the worker node(s)

   `NOTE - if you get an error about cgroups you should perform a reboot and run the ansible script again` 

   - TODO - Need to deploy Ceph-Rook separately between these deployments
   - Deploy ArgoCD for GitOps

   - Deploy PODs/Apps thru ArgoCD  

      - MetalLB
      - Rook-Ceph
      - AWS Bedrock
      - PiHole
      - Prometheus and Grafana
      - OpenWeb UI
      - Plex Media Server
      - N8N
      - `TODO - Minecraft Server`

> **Note**: Applications are deployed declaratively through ArgoCD, ensuring GitOps best practices

## Upgrading the cluster

Run the upgrade playbook:

```
ansible-playbook upgrade.yml
```

## Benchmarking the cluster

See the README file within the `benchmarks` folder.  **Credit and Thanks to [Jeff Geerling](https://www.jeffgeerling.com)**

![Benchmark Results](images/IO-Benchmark-2.png)

#### [SDCard Vs. NVMe IO Performance](https://forums.raspberrypi.com/viewtopic.php?t=362903)
![Benchmark Results](images/NVMe-Performance-Compare.png)


## Shutting down the cluster

The safest way to shut down the cluster is to run the following command:

```
ansible all -m community.general.shutdown -b
```

You can reboot all the nodes with:

```
ansible all -m reboot -b
```

# Learning Outcomes

## Technologies
- [Kubernetes (k3s)](https://docs.k3s.io/architecture) architecture and deployment
- [kubectl](https://kubernetes.io/docs/reference/kubectl/) for cluster management
- [Deploying Plex on Kubernetes](https://www.debontonline.com/2021/01/part-14-deploy-plexserver-yaml-with.html)

## Author
The repository was forked from [Jeff Geerling](https://www.jeffgeerling.com)'s Pi-Cluster project and was modified by [seadogger]().
