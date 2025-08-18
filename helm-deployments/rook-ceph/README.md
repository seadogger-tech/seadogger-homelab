# Rook-Ceph Configuration

## Filesystem Configuration

The cluster is configured with:
- 3 OSDs using NVMe devices
- 1 active MDS with 1 standby
- Erasure-coded data pool (2+1)
- Replicated metadata pool (size 3)

### Important Notes

- STORAGE DIRECTIONS
    - CEPH Block Storage (Note: The filesystem name is added as a prefix of the pool names by helm automatically).
        - filesytem name
            - ceph-block
        - pools 
            - Called ceph-block-data
        - storage classes 
            - Called ceph-block-data (Note: This should default storage class for all PVCs, this storage class is tied to ceph-block-data pool)

    - CEPH FileSystems Storage (Note: The filesystem name is added as a prefix of the pool names by helm automatically).
        - filesytem name
            - ceph-fs
        - pools 
            - ceph-fs-metadata (Replicated)
            - ceph-fs-data-replicated (Replicated data storage class.  IMPORTANT:  Helm deployment will fail if there is not at least one replicated storage class)
            - ceph-fs-data-ec (Erasure encoded data storage class) 
        - storage classes
            - ceph-fs-data-replicated (Storage class is tied to the ceph-fs-data-replicated data pool)
            - ceph-fs-data-ec (Storage class is tied to the ceph-fs-data-ec data pool)
