![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# HDHomeRun Guide Utility

A Python utility that fetches the HDHomeRun XMLTV guide using the network device's DeviceAuth code to query the HDHomeRun API. The guide is saved to Nextcloud storage for use with Jellyfin.

> **⚠️ Important:** The guide file **must** be written to Nextcloud storage (not `/media`). Jellyfin's `/media` mount is **read-only**. Use the Kubernetes CronJob method below for automated updates.

![accent-divider.svg](images/accent-divider.svg)
## Overview

This script automates the process of downloading EPG (Electronic Program Guide) data from HDHomeRun devices, making it easy to integrate live TV guide information into Jellyfin via Nextcloud.

**Use Cases:**
- Jellyfin live TV guide integration
- Automated EPG updates for media servers
- Offline TV guide storage

**Storage Architecture:**
- **Nextcloud** owns the data at `/media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml` (www-data UID:33)
- **Jellyfin** reads the file via read-only `/media` mount
- **Updates** must write to Nextcloud namespace with proper permissions

![accent-divider.svg](images/accent-divider.svg)
## Features

- **Configurable discovery endpoint** – Point the script at any HDHomeRun device on your network
- **Configurable target** – Write the XML to any writable file path
- **No external dependencies** – Uses only Python standard library (`urllib`, `argparse`)
- **Kubernetes CronJob ready** – Designed for automated scheduling in the cluster

![accent-divider.svg](images/accent-divider.svg)
## Location

The script is located in the repository at:

```
seadogger-homelab-pro/core/useful_scripts/fetch_hdhomerun_guide.py
```

![accent-divider.svg](images/accent-divider.svg)
## Prerequisites

- Python 3.8+ (uses `urllib` and `argparse` from stdlib)
- HDHomeRun device on your network
- Network access to HDHomeRun device
- Write access to Nextcloud storage (for automated updates)

![accent-divider.svg](images/accent-divider.svg)
## Automated Updates (Recommended)

### Using Kubernetes CronJob

Deploy as a CronJob that writes to Nextcloud storage (accessible to Jellyfin):

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: hdhomerun-guide-fetch
  namespace: nextcloud
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          securityContext:
            runAsUser: 33      # www-data user
            runAsGroup: 33     # www-data group
            fsGroup: 33
          containers:
          - name: fetch-guide
            image: python:3.11-slim
            command:
            - python
            - /scripts/fetch_hdhomerun_guide.py
            - --discover-url
            - http://192.168.1.70/discover.json
            - --target
            - /nextcloud/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
            volumeMounts:
            - name: nextcloud-data
              mountPath: /nextcloud/data
            - name: script
              mountPath: /scripts
          volumes:
          - name: nextcloud-data
            persistentVolumeClaim:
              claimName: nextcloud-nextcloud
          - name: script
            configMap:
              name: hdhomerun-script
          restartPolicy: OnFailure
```

**Key Configuration:**
- **Namespace:** `nextcloud` (has write access to Nextcloud PVC)
- **User/Group:** `33` (www-data) to match Nextcloud file permissions
- **Mount Path:** `/nextcloud/data` (Nextcloud PVC root)
- **Target File:** `/nextcloud/data/HomeMedia/files/Live_TV_Guide/xmltv.xml`
- **PVC:** `nextcloud-nextcloud` (Nextcloud's storage)

### Creating the ConfigMap

Before deploying the CronJob, create a ConfigMap with the script:

```bash
# From the repository root
kubectl create configmap hdhomerun-script \
  --from-file=fetch_hdhomerun_guide.py=./useful_scripts/fetch_hdhomerun_guide.py \
  -n nextcloud

# Verify it was created
kubectl get configmap hdhomerun-script -n nextcloud -o yaml
```

### Deploying the CronJob

```bash
# Save the CronJob manifest to a file
kubectl apply -f hdhomerun-cronjob.yaml

# Verify it's scheduled
kubectl get cronjob -n nextcloud

# Check job execution
kubectl get jobs -n nextcloud

# View logs from most recent job
kubectl logs -n nextcloud -l job-name=hdhomerun-guide-fetch-<id>
```

![accent-divider.svg](images/accent-divider.svg)
## Jellyfin Configuration

Once the CronJob is running and updating the guide file, configure Jellyfin to use it:

### In Jellyfin UI:
1. Navigate to **Dashboard** → **Live TV** → **TV Guide Data Providers**
2. Select **XMLTV**
3. Set the guide path to: `/media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml`
4. Set refresh interval: **6 hours** (to match CronJob schedule)

**Path Explanation:**
- Jellyfin sees path as: `/media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml` (read-only mount)
- CronJob writes to: `/nextcloud/data/HomeMedia/files/Live_TV_Guide/xmltv.xml` (Nextcloud PVC)
- They're the same file on the underlying CephFS storage

![accent-divider.svg](images/accent-divider.svg)
## Manual Testing (Local Development Only)

For local testing outside the cluster:

### Basic Usage

```bash
# Test script locally (saves to current directory)
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json
```

**Output:** Guide saved to `./xmltv.xml`

### Custom Output Path (Local Testing)

```bash
# Specify custom local path
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json \
    --target /tmp/xmltv.xml
```

> **Note:** These manual commands are for **testing only**. For production updates in the cluster, use the Kubernetes CronJob method above.

![accent-divider.svg](images/accent-divider.svg)
## Command-Line Options

```bash
./fetch_hdhomerun_guide.py --help
```

**Available Options:**
- `--discover-url` - URL to HDHomeRun device's discover.json endpoint (required)
- `--target` - Output file path (optional, defaults to `./xmltv.xml`)

![accent-divider.svg](images/accent-divider.svg)
## Troubleshooting

### CronJob Not Running

**Check CronJob status:**
```bash
kubectl get cronjob -n nextcloud hdhomerun-guide-fetch
kubectl describe cronjob -n nextcloud hdhomerun-guide-fetch
```

**Check recent jobs:**
```bash
kubectl get jobs -n nextcloud
```

**View job logs:**
```bash
# Get the most recent job pod
kubectl get pods -n nextcloud -l job-name --sort-by=.metadata.creationTimestamp

# View logs
kubectl logs -n nextcloud <pod-name>
```

### Cannot Connect to HDHomeRun Device

**Error:** Connection refused or timeout

**Solutions:**
1. Verify HDHomeRun device IP address:
   ```bash
   # Find HDHomeRun on network
   nmap -p 80 192.168.1.0/24 | grep -B 4 "HDHomeRun"
   ```

2. Test discover endpoint:
   ```bash
   curl http://192.168.1.70/discover.json
   ```

3. Check network connectivity from cluster:
   ```bash
   kubectl run -n nextcloud test-curl --rm -it --restart=Never \
     --image=curlimages/curl -- curl http://192.168.1.70/discover.json
   ```

### Permission Denied Writing File

**Error:** `PermissionError: [Errno 13] Permission denied`

**Cause:** CronJob not running as correct user/group

**Solution:** Verify `securityContext` in CronJob manifest:
```yaml
securityContext:
  runAsUser: 33      # www-data
  runAsGroup: 33     # www-data
  fsGroup: 33
```

**Check file ownership:**
```bash
kubectl exec -n nextcloud deploy/nextcloud -- \
  ls -la /var/www/html/data/HomeMedia/files/Live_TV_Guide/
```

Should show owner as `www-data` (UID:33).

### Guide Not Updating in Jellyfin

**Solutions:**

1. **Verify file exists and is readable:**
   ```bash
   kubectl exec -n jellyfin deploy/jellyfin -- \
     ls -la /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
   ```

2. **Check file modification time:**
   ```bash
   kubectl exec -n jellyfin deploy/jellyfin -- \
     stat /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
   ```
   Should update every 6 hours based on CronJob schedule.

3. **Force refresh in Jellyfin:**
   - **Dashboard** → **Scheduled Tasks** → **Live TV Guide** → **Run Now**

4. **Check Jellyfin logs:**
   ```bash
   kubectl logs -n jellyfin deploy/jellyfin --tail=100 | grep -i "guide\|xmltv"
   ```

### ConfigMap Not Found

**Error:** `configmap "hdhomerun-script" not found`

**Solution:** Create the ConfigMap first:
```bash
kubectl create configmap hdhomerun-script \
  --from-file=fetch_hdhomerun_guide.py=./useful_scripts/fetch_hdhomerun_guide.py \
  -n nextcloud
```

![accent-divider.svg](images/accent-divider.svg)
## Script Details

### How It Works

1. **Discover Device:** Queries the HDHomeRun device's `/discover.json` endpoint
2. **Extract DeviceAuth:** Parses the device's authentication code from the response
3. **Fetch Guide:** Uses DeviceAuth to authenticate to HDHomeRun's API and download XMLTV data
4. **Save to Nextcloud:** Writes the XML guide data to Nextcloud storage (accessible to Jellyfin)

### Dependencies

**Python stdlib only:**
- `urllib.request` - HTTP requests
- `urllib.parse` - URL handling
- `argparse` - Command-line argument parsing
- `json` - JSON parsing

**No pip install required!**

### Storage Flow

```
HDHomeRun Device (192.168.1.70)
    ↓
CronJob Pod (nextcloud namespace, UID:33)
    ↓
Nextcloud PVC: /nextcloud/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
    ↓ (same file, different mount)
Jellyfin Pod (read-only): /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
```

![accent-divider.svg](images/accent-divider.svg)
## See Also

- **[[09-Apps]]** - Jellyfin and Nextcloud application details
- **[[06-Storage-Rook-Ceph]]** - CephFS storage architecture
- [HDHomeRun Official Docs](https://www.silicondust.com/support/)
- [Jellyfin Live TV Guide](https://jellyfin.org/docs/general/server/live-tv/)
- [XMLTV Format Specification](http://wiki.xmltv.org/index.php/Main_Page)

![accent-divider.svg](images/accent-divider.svg)
## License

This script is provided under the MIT License. Feel free to modify and adapt it to your needs.