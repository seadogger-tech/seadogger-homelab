# Active Context: seadogger-homelab

This document tracks the current work focus, recent changes, and next steps for the `seadogger-homelab` project.

## Current Focus

The primary focus is on deploying an application to manage media files and provide access to other systems on the network. The leading candidate is Ganesha NFS, which is part of CephFS. However, we are facing challenges with macOS clients due to issues with NFSv4 and newer.

## Recent Changes

*   Initialized the `memory-bank` directory and its core documentation.

## Next Steps

1.  **Resolve NFS Issues:** Investigate and resolve the compatibility problems between Ganesha NFS and macOS clients.
2.  **Deploy Plex Media Server:** Once the media file sharing is stable, deploy Plex Media Server as a follow-on enhancement.
3.  **Fix Monitoring Stack:** Address issues with the Prometheus and Grafana deployments to ensure proper metrics collection and cluster status visibility.
4.  **Remote Ceph Storage:** Implement a solution to connect the local Ceph cluster to remote storage for backup or tiering.
5.  **Complete Core Documentation:** Create the `progress.md` file to finalize the initial `memory-bank` scaffold.
