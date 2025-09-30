![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Benchmarking

This page documents performance benchmarks for the Seadogger Homelab infrastructure.

**Credit and Thanks:** Benchmarking methodology and tools from [Jeff Geerling](https://www.jeffgeerling.com)

![accent-divider.svg](images/accent-divider.svg)
## Storage Performance Benchmarks

### NVMe vs SD Card Performance

![Benchmark Results](images/IO-Benchmark-2.png)

**Key Findings:**
- NVMe SSDs provide dramatically better I/O performance than SD cards
- Sequential read/write speeds exceed SD card performance by 10-20x
- Random I/O performance critical for Kubernetes workloads

### Detailed Comparison

![NVMe Performance Comparison](images/NVMe-Performance-Compare.png)

**Reference:** [SDCard Vs. NVMe IO Performance Discussion](https://forums.raspberrypi.com/viewtopic.php?t=362903)

![accent-divider.svg](images/accent-divider.svg)
## Storage Configuration

### Worker Node Partition Layout

![Partition Map - NVMe Worker](images/Partition-Map-NVMe-worker.png)

**Worker nodes use:**
- Full 4TB NVMe for Rook-Ceph OSD storage
- No OS partitions on NVMe (boot from SD card initially)
- Dedicated storage for distributed Ceph cluster

### Control Plane Partition Layout

![Partition Map - NVMe Control Plane](images/Partition-Map-NVMe.png)

**Control plane uses:**
- 500GB NVMe for OS and system storage
- Smaller capacity sufficient for control plane workload
- etcd snapshots stored on NVMe for fast backup/restore

![accent-divider.svg](images/accent-divider.svg)
## Performance Metrics

### I/O Performance Summary

![IO Benchmark Results](images/IO-Benchmark-2.png)

**Test Conditions:**
- Raspberry Pi 5 (8GB RAM)
- NVMe SSD via PCIe HAT
- Debian GNU/Linux 12 (bookworm)
- K3s v1.32.6+k3s1

**Tools Used:**
- fio (Flexible I/O tester)
- iozone
- dd benchmarks

![accent-divider.svg](images/accent-divider.svg)
## Running Your Own Benchmarks

See the `benchmarks/` directory in the repository for:
- Benchmark scripts
- Test configurations
- Result analysis tools
- Detailed methodology

**Quick benchmark:**
```bash
# Navigate to benchmarks directory
cd benchmarks/

# Run storage benchmark
./run-storage-benchmark.sh

# Results saved to results/
```

![accent-divider.svg](images/accent-divider.svg)
## See Also

- [[03-Hardware-and-Network]] - Hardware specifications and configuration
- [[06-Storage-Rook-Ceph]] - Storage architecture and Rook-Ceph deployment
- [Jeff Geerling's Raspberry Pi Benchmarks](https://github.com/geerlingguy/raspberry-pi-pcie-devices)