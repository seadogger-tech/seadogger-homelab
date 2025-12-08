![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# HDHomeRun Guide Integration

Integration of HDHomeRun XMLTV guide data with Jellyfin using an in-cluster HTTP proxy that works around Jellyfin's gzip decompression bug.

> **⚠️ Important:** Jellyfin cannot parse gzip-compressed XMLTV data from the HDHomeRun API. We use an in-cluster proxy that serves uncompressed XMLTV to Jellyfin.

![accent-divider.svg](images/accent-divider.svg)
## Overview

This system provides automated EPG (Electronic Program Guide) data from HDHomeRun devices to Jellyfin using a lightweight HTTP proxy deployed in the Jellyfin namespace.

**Architecture:**
- **XMLTV Proxy** runs in the `jellyfin` namespace
- **Fetches** from HDHomeRun API with `Accept-Encoding: identity` (no gzip)
- **Serves** uncompressed XMLTV to Jellyfin at `http://xmltv-proxy.jellyfin/xmltv.xml`
- **Credentials** stored in Kubernetes Secret (managed via Ansible)

**Why a Proxy?**
Jellyfin has a bug where it sends `Accept-Encoding: gzip` to XMLTV URLs but fails to decompress the response. The HDHomeRun API returns gzip-compressed data by default, causing Jellyfin to fail with "Data at the root level is invalid" errors. The proxy solves this by explicitly requesting uncompressed data.

![accent-divider.svg](images/accent-divider.svg)
## Features

- **Gzip workaround** – Explicitly requests uncompressed XMLTV data
- **Lightweight** – Python HTTP server in a 20MB Alpine container
- **Always fresh** – Fetches latest guide data on each Jellyfin request
- **Credential management** – Stored in Kubernetes Secret via Ansible
- **Low resources** – 50m CPU / 64Mi RAM requests

![accent-divider.svg](images/accent-divider.svg)
## Components

### 1. XMLTV Proxy Deployment
**Location:** `deployments/jellyfin/xmltv-proxy.yaml`

- **ConfigMap:** Python HTTP server script
- **Deployment:** Single replica pod running `python:3.11-alpine`
- **Service:** ClusterIP at `xmltv-proxy.jellyfin` on port 80
- **Environment:** Credentials loaded from `hdhomerun-credentials` Secret

### 2. Credentials Management
**Location:** `ansible/tasks/jellyfin_secrets.yml`

Creates the `hdhomerun-credentials` Secret from `ansible/config.yml` variables:
- `hdhomerun_email` - HDHomeRun account email
- `hdhomerun_device_ids` - Comma-separated device IDs


![accent-divider.svg](images/accent-divider.svg)
## Deployment

### Step 1: Configure Credentials

Add your HDHomeRun credentials to `ansible/config.yml`:

```yaml
# --- HDHomeRun Credentials (for Jellyfin XMLTV Proxy) ---
hdhomerun_email: "your-email@example.com"
hdhomerun_device_ids: "YOUR_DEVICE_ID"
```

> **Note:** Find your Device ID on the [HDHomeRun website](https://my.hdhomerun.com/) or on the device label.

### Step 2: Create Kubernetes Secret

Run the Ansible playbook to create the Secret in the jellyfin namespace:

```bash
cd ansible
ansible-playbook -i hosts.ini main.yml --tags jellyfin
```

This creates the `hdhomerun-credentials` Secret with your email and device IDs.

### Step 3: Deploy XMLTV Proxy

The proxy deployment is managed by ArgoCD from the repository:

```bash
# Check if deployment exists
kubectl get deployment -n jellyfin xmltv-proxy

# View proxy logs
kubectl logs -n jellyfin -l app=xmltv-proxy --tail=20

# Check service
kubectl get svc -n jellyfin xmltv-proxy
```

**Expected Output:**
```
XMLTV Proxy server running on port 8080
Proxying: https://api.hdhomerun.com/api/xmltv?Email=...&DeviceIDs=...
```

### Step 4: Test the Proxy

Verify the proxy returns valid XMLTV data:

```bash
# From within the cluster
kubectl exec -n jellyfin deployment/jellyfin -- \
  curl -s http://xmltv-proxy.jellyfin/xmltv.xml | head -20
```

**Expected Output:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<tv source-info-url="https://www.hdhomerun.com/" source-info-name="HDHomeRun">
  <channel id="US26588.hdhomerun.com">
    <display-name>WKCFDT</display-name>
    ...
```

![accent-divider.svg](images/accent-divider.svg)
## Jellyfin Configuration

Configure Jellyfin to use the XMLTV proxy:

### In Jellyfin UI:
1. Navigate to **Dashboard** → **Live TV** → **TV Guide Data Providers**
2. Click **Add** → Select **XMLTV**
3. Set the **File or URL** to: `http://xmltv-proxy.jellyfin/xmltv.xml`
4. Set **Refresh interval**: **Daily** (guide data is fetched fresh on each request)
5. Click **Save**

### Trigger Initial Load
After saving the configuration:
1. Navigate to **Dashboard** → **Scheduled Tasks**
2. Find **Refresh Guide** task
3. Click **Run Now**

### Verify Guide Data
- Check **Dashboard** → **Live TV** → **Guide** to see program listings
- The guide should populate with 14 days of program data (HDHomeRun DVR subscription required)

![accent-divider.svg](images/accent-divider.svg)
## Troubleshooting

### Proxy Not Running

**Check deployment status:**
```bash
kubectl get deployment -n jellyfin xmltv-proxy
kubectl get pods -n jellyfin -l app=xmltv-proxy
```

**View proxy logs:**
```bash
kubectl logs -n jellyfin -l app=xmltv-proxy --tail=50
```

**Expected log output:**
```
XMLTV Proxy server running on port 8080
Proxying: https://api.hdhomerun.com/api/xmltv?Email=...&DeviceIDs=...
```

### Secret Not Found Error

**Error:** `secret "hdhomerun-credentials" not found`

**Solution:** Create the Secret via Ansible:
```bash
cd ansible
ansible-playbook -i hosts.ini main.yml --tags jellyfin
```

**Verify Secret exists:**
```bash
kubectl get secret -n jellyfin hdhomerun-credentials
```

### Proxy Returns Error

**Check proxy logs for errors:**
```bash
kubectl logs -n jellyfin -l app=xmltv-proxy | grep -i error
```

**Common errors:**
- **"HDHOMERUN_EMAIL and HDHOMERUN_DEVICE_IDS environment variables must be set"**
  - Solution: Ensure Secret is created and mounted correctly
- **"Failed to fetch XMLTV"**
  - Solution: Check network connectivity to HDHomeRun API
  - Test: `curl https://api.hdhomerun.com/api/xmltv?Email=...&DeviceIDs=...`

### Guide Not Loading in Jellyfin

**Error:** "Data at the root level is invalid. Line 1, position 1"

**This error indicates:**
- Jellyfin is receiving gzip-compressed data (the proxy workaround isn't working)
- Or Jellyfin cannot reach the proxy

**Solutions:**

1. **Verify proxy is accessible from Jellyfin:**
   ```bash
   kubectl exec -n jellyfin deployment/jellyfin -- \
     curl -I http://xmltv-proxy.jellyfin/xmltv.xml
   ```

   Should return: `HTTP/1.0 200 OK` with `Content-Type: application/xml`

2. **Check first bytes of response:**
   ```bash
   kubectl exec -n jellyfin deployment/jellyfin -- \
     curl -s http://xmltv-proxy.jellyfin/xmltv.xml | head -c 100
   ```

   Should start with: `<?xml version="1.0" encoding="utf-8"?>`

3. **Force refresh in Jellyfin:**
   - **Dashboard** → **Scheduled Tasks** → **Refresh Guide** → **Run Now**

4. **Check Jellyfin logs:**
   ```bash
   kubectl logs -n jellyfin deployment/jellyfin --tail=100 | grep -i "xmltv\|guide\|error"
   ```

### Proxy Performance Issues

**Check proxy resource usage:**
```bash
kubectl top pod -n jellyfin -l app=xmltv-proxy
```

**Restart proxy if needed:**
```bash
kubectl rollout restart deployment/xmltv-proxy -n jellyfin
```

![accent-divider.svg](images/accent-divider.svg)
## Technical Details

### How It Works

1. **Jellyfin Request:** Jellyfin sends HTTP request to `http://xmltv-proxy.jellyfin/xmltv.xml`
2. **Proxy Fetch:** Proxy fetches from HDHomeRun API with `Accept-Encoding: identity` (no gzip)
3. **Uncompressed Response:** HDHomeRun API returns uncompressed XMLTV (10+ MB)
4. **Pass Through:** Proxy serves the XML directly to Jellyfin with `Content-Encoding: identity`

### Architecture Flow

```
Jellyfin Pod (jellyfin namespace)
    ↓ HTTP GET /xmltv.xml
XMLTV Proxy Pod (jellyfin namespace)
    ↓ Fetch with Accept-Encoding: identity
HDHomeRun API (api.hdhomerun.com)
    ↓ Returns uncompressed XMLTV
XMLTV Proxy Pod
    ↓ Serve uncompressed XML
Jellyfin Pod (parses successfully)
```

### Proxy Implementation

**Language:** Python 3.11 (stdlib only, no dependencies)
**Base Image:** `python:3.11-alpine` (20MB)
**HTTP Server:** `http.server.HTTPServer` (Python stdlib)
**Configuration:** Environment variables from Kubernetes Secret

**Key Code:**
- Explicitly requests uncompressed: `req.add_header('Accept-Encoding', 'identity')`
- Sets response header: `Content-Encoding: identity`
- No caching - always fetches fresh data

![accent-divider.svg](images/accent-divider.svg)
## See Also

- **[[09-Apps]]** - Jellyfin application details
- **[[08-Security-and-Certificates]]** - Kubernetes Secrets management
- [HDHomeRun Official Docs](https://www.silicondust.com/support/)
- [Jellyfin Live TV Guide](https://jellyfin.org/docs/general/server/live-tv/)
- [XMLTV Format Specification](http://wiki.xmltv.org/index.php/Main_Page)
- [HDHomeRun XMLTV API](https://www.silicondust.com/support/hdhomerun/guide-data/)