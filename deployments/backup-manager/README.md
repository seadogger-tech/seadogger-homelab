# Backup Manager

Simple web UI for managing K8up backups and restores.

## Features

- View all snapshots for Nextcloud, N8N, and Jellyfin
- One-click restore with confirmation dialog
- Automatic application stop/start during restore
- Real-time restore progress monitoring

## Deployment

### Build and Deploy

```bash
# Build image on cluster node
cd deployments/backup-manager
docker build -t backup-manager:latest .

# Deploy to cluster
kubectl apply -f deployment.yaml
kubectl apply -f ingressroute.yaml
```

### Access

URL: https://backups.seadogger-homelab

## Usage

1. Select namespace tab (Nextcloud, N8N, or Jellyfin)
2. View list of available snapshots with dates
3. Click "Restore" button for desired snapshot
4. Confirm the restore operation
5. Wait for restore to complete (progress shown on page)
6. Application automatically restarts with restored data

## Security

- No authentication (internal network only)
- Service account has minimal RBAC:
  - Read snapshots
  - Create restore jobs
  - Scale deployments (to stop/start apps during restore)

## API Endpoints

- `GET /` - Web UI
- `GET /api/snapshots/<namespace>` - List snapshots
- `POST /api/restore/<namespace>/<snapshot_id>` - Create restore
- `GET /api/restore/<namespace>/<restore_name>/status` - Check restore status
