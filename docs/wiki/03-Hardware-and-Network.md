![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Hardware & Network

This page captures the practical hardware and network plan that the Ansible playbooks assume, without repeating the full setup guides.

![accent-divider.svg](images/accent-divider.svg)
## Network Plan (what Ansible expects)
- Nodes use `.local` hostnames for provisioning:
  - Control plane: `yoda.local` (e.g., 192.168.1.95)
  - Workers: `anakin.local`, `obiwan.local`, `rey.local` (static DHCP reservations)
- Application hosts use `*.seadogger-homelab` and resolve to the Traefik VIP via Pi-hole DNS overrides.
- Configure your subnet once in `ansible/config.yml`:
  - `ipv4_subnet_prefix`, `ipv4_gateway`, `dns4_servers`
- MetalLB pool and VIPs: see [[07-Networking-and-Ingress]] for the authoritative address ranges and service VIP table.
- Pi-hole host overrides: see `core/deployments/pihole/pihole-values.yaml` for the `address=/.../192.168.1.241` entries pointing at Traefik.

![accent-divider.svg](images/accent-divider.svg)
## Hardware Summary
- Raspberry Pi 5 nodes (1 control plane + 3 workers)
- PoE switch (recommended) to power PoE HATs and simplify wiring
- NVMe storage on each node (workers sized for Rook‑Ceph data)
- Hard‑wired Ethernet (Wi‑Fi disabled for k3s stability)

![accent-divider.svg](images/accent-divider.svg)
## Node Configuration (example)
- K3s: v1.32.6+k3s1
- OS: Debian GNU/Linux 12 (bookworm)
- Kernel: 6.6.51+rpt-rpi-2712

![accent-divider.svg](images/accent-divider.svg)
## Bill of Materials (BoM)

| Item | Quantity | Cost per Unit | Total Cost |
|------|----------|--------------|------------|
| [Raspberry Pi 5 8GB](https://www.digikey.com/en/products/detail/raspberry-pi/SC1112/21658257?s=N4IgjCBcpgrAnADiqAxlAZgQwDYGcBTAGhAHsoBtEAJngBYwwB2EAXRIAcAXKEAZS4AnAJYA7AOYgAviQC0dFCHSRs%2BYmUrgAzAAYdW5CUbwmYeGykyamwVjwcARgUGCAngAIOw2BaA) | 4 | $80 | $320 |
| [Raspberry Pi Rack](https://www.amazon.com/gp/product/B09D7RR6NY/ref=ewc_pr_img_2?smid=A2IAB2RW3LLT8D&psc=1) | 1 | $53 | $53 |
| [GPIO Header with shorter standoff](https://www.amazon.com/dp/B084Q4W1PW?ref=ppx_yo2ov_dt_b_fed_asin_title) | 1 | $10 | $10 |
| [Raspberry Pi 5 POE HAT with PCIe](https://www.amazon.com/dp/B0D8JC3MXQ?ref=ppx_yo2ov_dt_b_fed_asin_title) | 4 | $37 | $148 |
| [Crucial P3 4TB NVMe SSD](https://www.newegg.com/crucial-4tb-p3/p/N82E16820156298?Item=9SIA12KJ9P1073) | 3 | $225 | $675 |
| [Crucial P3 500GB NVMe SSD](https://www.newegg.com/crucial-500gb-p3-nvme/p/N82E16820156295) | 1 | $38 | $38 |
| [Nylon Standoff Kit](https://www.amazon.com/gp/product/B06XKWDSPT/ref=ox_sc_act_title_1?smid=A2XXMW1BKOEL72&psc=1) | 1 | $13 | $13 |
| [64GB sdCard](https://www.amazon.com/dp/B08879MG33?ref_=ppx_hzsearch_conn_dt_b_fed_asin_title_13&th=1) | 1 | $25 | $25 |
| **Total (excludes PoE switch)** | **-** | **-** | **$1282** |

> Physical reference
> ![Rack-Mounted-Pi5-Nodes.jpeg](images/Rack-Mounted-Pi5-Nodes.jpeg)
> ![Single-Node-Mounted-2.jpeg](images/Single-Node-Mounted-2.jpeg)
> ![SSD-Compatibility.png](images/SSD-Compatibility.png)

![accent-divider.svg](images/accent-divider.svg)
## Next
- Bootstrap and cold‑start flow: [[04-Bootstrap-and-Cold-Start]]
- VIPs and ingress hostnames: [[07-Networking-and-Ingress]]
