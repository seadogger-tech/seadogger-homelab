# Rook-Ceph Configuration

## Filesystem Configuration

The cluster is configured with:
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
