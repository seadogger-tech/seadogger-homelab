![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Networking & Ingress

![accent-divider.svg](images/accent-divider.svg)
## MetalLB Address Pools
> Update to match your subnet.
- `192.168.1.241 - 192.168.1.254`

![accent-divider.svg](images/accent-divider.svg)
## Networking
The cluster assumes static node IPs and a dedicated MetalLB pool. If you change the subnet, update the Ansible inventory, MetalLB `IPAddressPool`, and any VIPs referenced in manifests.

![accent-divider.svg](images/accent-divider.svg)
### VIP L2 Advertisements (MetalLB)
| VIP            | Purpose            |
|----------------|--------------------|
| `192.168.1.241` | Traefik (ingress)  |
| `192.168.1.242` | Bedrock Gateway    |
| `192.168.1.244` | Prometheus         |
| `192.168.1.245` | Grafana            |
| `192.168.1.246` | Alertmanager       |
| `192.168.1.250` | Pi-hole DNS        |

![accent-divider.svg](images/accent-divider.svg)
### Ingress Hosts (TLS terminates at Traefik `192.168.1.241`) via PiHole DNS 
- `openwebui.seadogger-homelab`
- `argocd.seadogger-homelab`
- `ceph.seadogger-homelab`
- `pihole.seadogger-homelab`
- `jellyfin.seadogger-homelab`
- `n8n.seadogger-homelab`
