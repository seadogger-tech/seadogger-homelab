# Velero + rclone Backup Strategy for K3s Homelab - Complete Implementation Guide

## Executive Summary

This document provides the complete implementation guide for a dual-strategy backup system protecting critical applications in a K3s homelab cluster. The solution combines Velero v1.17.0 with Kopia deduplication for frequent incremental backups AND rclone for semi-annual plain file archives, providing both operational recovery and long-term "digital dark age" protection.

**Scope of Protection:**
- **Nextcloud**: 3.3TB - Primary data store (backed up daily + archived semi-annually)
- **OpenWebUI**: ~5GB - User chats and configurations (backed up daily + archived)
- **N8N**: ~1GB - Workflows and credentials (backed up with known encryption issue)
- **Jellyfin**: Media references only - Not backed up (media protected via Nextcloud, erasure coding for hardware protection)
- **PiHole/Portal**: Stateless applications - Not backed up (redeploy via Ansible)

**Key Capabilities:**
- **Dual Strategy:** Velero/Kopia for operational recovery, rclone for plain file archives
- **Disaster Recovery:** Full restoration in 24-48 hours (300Mbps link bottleneck)
- **Ransomware Protection:** Three-tier IAM model prevents deletion, multiple recovery points
- **Cost Effective:** ~$11/month for 3.3TB using Deep Archive
- **Future Proof:** Plain file archives prevent vendor lock-in and "digital dark age"
- **Deduplication:** Kopia reduces storage from potential 330TB to ~3.5TB for 100 backups
- **Automated Testing:** Every 6 hours with Gmail alerting using Kubernetes CRDs
- **Monitored:** Automated backup verification and alerting
- **Encrypted:** AES256 encryption at rest

## Prerequisites

### Required Components Already Installed
- K3s cluster with 4 nodes operational (yoda, anakin, obiwan, rey)
- Nextcloud deployed and running (3.3TB data on CephFS)
- OpenWebUI and N8N deployed
- Velero v1.17.0 installed via Helm with:
  - Kopia uploader configured
  - AWS plugin enabled
  - Node agents deployed (`node-agent-*` pods running)
  - Velero CRDs available in cluster
- Rook-Ceph storage with erasure coding
- AWS account with S3 access
- Gmail account with app password for alerts

### Verify Current Installation
```bash
# Check Velero is running
kubectl get pods -n velero
kubectl get deployment velero -n velero

# Verify node agents are running (should see 4)
kubectl get pods -n velero | grep node-agent

# Check existing configurations
kubectl get backups -n velero
kubectl get schedules -n velero
kubectl get backupstoragelocation -n velero

# Check CRDs are available
kubectl get crd | grep velero
```

## System Architecture

### Complete Backup Architecture Diagram

```mermaid
graph TB
    subgraph K8s["🎯 Kubernetes Cluster (4 Nodes)"]
        direction TB
        
        subgraph VeleroNS["velero namespace"]
            VeleroServer["Velero Server v1.17.0<br/>Schedule Orchestration"]
            VeleroUI["Velero UI<br/>https://velero.seadogger-homelab"]
            TestRunner["Test Executor<br/>CronJob every 6hrs"]
        end

        subgraph NodeAgents["Node Agents (Kopia Uploader)"]
            Agent1["node-agent-yoda"]
            Agent2["node-agent-anakin"]
            Agent3["node-agent-obiwan"]
            Agent4["node-agent-rey"]
        end

        subgraph Protected["✅ Protected Applications"]
            NextcloudPVC["Nextcloud PVC<br/>3.3TB CephFS EC"]
            OpenWebUIPVC["OpenWebUI PVC<br/>5GB RBD"]
            N8NPVC["N8N PVC<br/>1GB RBD"]
        end

        subgraph BackupJobs["Backup Jobs"]
            VeleroSchedules["Daily/Weekly/Monthly<br/>Schedules"]
            RcloneCron["rclone CronJob<br/>Jan 1 & Jul 1"]
        end

        subgraph Storage["Rook-Ceph Storage"]
            CephFS["CephFS EC<br/>Erasure Coded<br/>Single Drive Failure Protection"]
            CephRBD["RBD Block<br/>Replicated"]
        end
    end

    subgraph AWS["☁️ AWS S3 Storage"]
        S3Bucket["seadogger-homelab-backup<br/>us-east-1"]
        
        subgraph Paths["Storage Paths"]
            VeleroPath["/backups/<br/>Kopia Blocks"]
            RclonePath["/nextcloud-plain/<br/>Original Files"]
        end
        
        S3Standard["S3 Standard<br/>Last 7 days<br/>~100GB metadata + recent"]
        DeepArchive["Glacier Deep Archive<br/>After 7 days<br/>~3.3TB Velero + 6.6TB rclone"]
    end

