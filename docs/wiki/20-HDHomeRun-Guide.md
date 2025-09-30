![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# HDHomeRun Guide Utility

A Python utility that fetches the HDHomeRun XMLTV guide using the network device's DeviceAuth code to query the HDHomeRun API. The guide is saved locally for use with Jellyfin or other media applications.

![accent-divider.svg](images/accent-divider.svg)
## Overview

This script automates the process of downloading EPG (Electronic Program Guide) data from HDHomeRun devices, making it easy to integrate live TV guide information into your homelab media server.

**Use Cases:**
- Jellyfin live TV guide integration
- Automated EPG updates for media servers
- Offline TV guide storage

![accent-divider.svg](images/accent-divider.svg)
## Features

- **Configurable discovery endpoint** – Point the script at any HDHomeRun device on your network
- **Configurable target** – Write the XML to any local file path
- **No external dependencies** – Uses only Python standard library (`urllib`, `argparse`)
- **Automated scheduling** – Can be run as a cron job for regular updates

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

![accent-divider.svg](images/accent-divider.svg)
## Installation

### Manual Installation

```bash
# Copy the script to your preferred location
cp fetch_hdhomerun_guide.py /usr/local/bin/

# Make it executable
chmod +x /usr/local/bin/fetch_hdhomerun_guide.py
```

### For Jellyfin Integration

```bash
# Create directory for guide data
mkdir -p /media/data/HomeMedia/files/Live_TV_Guide/

# Set permissions
chown -R jellyfin:jellyfin /media/data/HomeMedia/files/Live_TV_Guide/
```

![accent-divider.svg](images/accent-divider.svg)
## Usage

### Basic Usage (Default Output)

The simplest usage saves the guide as `xmltv.xml` in the current directory:

```bash
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json
```

**Output:** Guide saved to `./xmltv.xml`

### Custom Output Path

Specify a custom location for the guide file:

```bash
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json \
    --target /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
```

### For Jellyfin

Configure Jellyfin to use the downloaded guide:

```bash
# Fetch guide to Jellyfin's expected location
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json \
    --target /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
```

Then in Jellyfin:
1. Navigate to **Dashboard** → **Live TV** → **TV Guide Data Providers**
2. Select **XMLTV**
3. Point to: `/media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml`

![accent-divider.svg](images/accent-divider.svg)
## Automated Updates

### Using Cron

Set up automatic guide updates every 6 hours:

```bash
# Edit crontab
crontab -e

# Add this line (update every 6 hours)
0 */6 * * * /usr/local/bin/fetch_hdhomerun_guide.py --discover-url http://192.168.1.70/discover.json --target /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
```

### Using Kubernetes CronJob

Deploy as a CronJob in your cluster:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: hdhomerun-guide-fetch
  namespace: jellyfin
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: fetch-guide
            image: python:3.11-slim
            command:
            - python
            - /scripts/fetch_hdhomerun_guide.py
            - --discover-url
            - http://192.168.1.70/discover.json
            - --target
            - /data/xmltv.xml
            volumeMounts:
            - name: guide-data
              mountPath: /data
            - name: script
              mountPath: /scripts
          volumes:
          - name: guide-data
            persistentVolumeClaim:
              claimName: jellyfin-media
          - name: script
            configMap:
              name: hdhomerun-script
          restartPolicy: OnFailure
```

![accent-divider.svg](images/accent-divider.svg)
## Command-Line Options

Run with `--help` to see all available options:

```bash
./fetch_hdhomerun_guide.py --help
```

**Available Options:**
- `--discover-url` - URL to HDHomeRun device's discover.json endpoint (required)
- `--target` - Output file path (optional, defaults to `./xmltv.xml`)

![accent-divider.svg](images/accent-divider.svg)
## Troubleshooting

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

3. Check network connectivity:
   ```bash
   ping 192.168.1.70
   ```

### Permission Denied Writing Output File

**Error:** `PermissionError: [Errno 13] Permission denied`

**Solutions:**
```bash
# Check directory permissions
ls -la /media/data/HomeMedia/files/Live_TV_Guide/

# Fix permissions
sudo chown $USER:$USER /media/data/HomeMedia/files/Live_TV_Guide/

# Or run with sudo (not recommended)
sudo ./fetch_hdhomerun_guide.py --discover-url ...
```

### Guide Not Updating in Jellyfin

**Solutions:**
1. Refresh guide data in Jellyfin:
   - **Dashboard** → **Scheduled Tasks** → **Live TV Guide** → **Run Now**

2. Verify file path in Jellyfin matches script output

3. Check Jellyfin logs:
   ```bash
   kubectl logs -n jellyfin deploy/jellyfin --tail=100 | grep -i "guide"
   ```

![accent-divider.svg](images/accent-divider.svg)
## Script Details

### How It Works

1. **Discover Device:** Queries the HDHomeRun device's `/discover.json` endpoint
2. **Extract DeviceAuth:** Parses the device's authentication code from the response
3. **Fetch Guide:** Uses DeviceAuth to authenticate to HDHomeRun's API and download XMLTV data
4. **Save Locally:** Writes the XML guide data to the specified file path

### Dependencies

**Python stdlib only:**
- `urllib.request` - HTTP requests
- `urllib.parse` - URL handling
- `argparse` - Command-line argument parsing
- `json` - JSON parsing

**No pip install required!**

![accent-divider.svg](images/accent-divider.svg)
## See Also

- [[09-Apps]] - Applications deployed in the homelab
- [HDHomeRun Official Docs](https://www.silicondust.com/support/)
- [Jellyfin Live TV Guide](https://jellyfin.org/docs/general/server/live-tv/)
- [XMLTV Format Specification](http://wiki.xmltv.org/index.php/Main_Page)

![accent-divider.svg](images/accent-divider.svg)
## License

This script is provided under the MIT License. Feel free to modify and adapt it to your needs.