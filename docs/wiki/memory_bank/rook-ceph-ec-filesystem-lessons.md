# Rook-Ceph CephFS with Erasure Coding Lessons

## Issue
When deploying CephFS with erasure coding in Rook-Ceph, several issues were encountered:
1. Filesystem creation failed with "exit status 22"
2. MDS daemons remained in standby state
3. High PG count warning

## Root Causes & Solutions

### 1. Erasure Coding Configuration
**Issue:** CephFS requires explicit permission to use erasure coded pools as data pools.
**Solution:** 
- Add `force_ec_overwrites: "true"` to the data pool parameters
- Use `--force` flag when creating filesystem manually
- Configure in values.yaml:
```yaml
dataPools:
  - parameters:
      force_ec_overwrites: "true"
      allow_ec_overwrites: "true"
```

### 2. PG Count Management
**Issue:** Total PG count exceeded recommended maximum (313 > 250)
**Solution:**
- Reduced `pg_num` from 128 to 64 for the erasure coded data pool
- Keep other pools at lower PG counts (8 for most, 32 for metadata)
- Monitor PG autoscaling progress before proceeding

### 3. Pool Naming Convention
**Issue:** Ansible tasks were looking for incorrect pool names
**Solution:**
- Updated pool name checks in ansible task:
  - From: `ec-fs-data` or `ec-fs-data0`
  - To: `ec-fs-ec-data`
- Always verify actual pool names with `ceph osd pool ls`

## Best Practices

1. **Erasure Coding Setup**
   - Always enable both `force_ec_overwrites` and `allow_ec_overwrites`
   - Use appropriate data/coding chunks ratio (2+1 in our case)
   - Place parameters at correct level in values.yaml

2. **PG Management**
   - Start with conservative PG counts
   - Monitor PG autoscaling
   - Wait for PG counts to stabilize before proceeding

3. **Deployment Process**
   - Verify pool creation before filesystem creation
   - Check MDS status and logs for issues
   - Monitor both Kubernetes resources and Ceph health

4. **Monitoring Points**
   - CephFS status: `ceph fs status <fs_name>`
   - Pool list: `ceph osd pool ls`
   - MDS status: Check for active/standby-replay state
   - PG count: Monitor through `ceph status`

## Configuration Example

```yaml
cephFileSystems:
  - name: ec-fs
    spec:
      metadataPool:
        replicated:
          size: 3
      dataPools:
        - name: ec-data
          failureDomain: host
          erasureCoded:
            dataChunks: 2
            codingChunks: 1
          parameters:
            pg_num: "64"
            allow_ec_overwrites: "true"
            force_ec_overwrites: "true"
            bulk: "true"
      metadataServer:
        activeCount: 1
        activeStandby: true
```

## Troubleshooting Steps

1. Verify pool creation and configuration
2. Check PG count and distribution
3. Monitor MDS state transitions
4. Review operator logs for specific error messages
5. Ensure proper EC configuration at both pool and filesystem levels

## Future Considerations

1. Add PG autoscaling monitoring to ansible tasks
2. Consider adding health checks for MDS state
3. Document EC pool requirements in deployment guide
4. Add validation steps for EC configuration
