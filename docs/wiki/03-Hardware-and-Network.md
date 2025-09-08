![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Hardware & Network

![accent-divider.svg](images/accent-divider.svg)
### Hardware Requirements
- Raspberry Pi5 nodes (1 server node and 3 worker nodes)
- POE switch (recommended: Ubiquiti Dream @Machine SE)
  - Powers Raspberry Pis via POE HAT
  - Simplifies the wiring and setup, but not totally neccessary.  
  - **If you do not use POE, adjust the BoM (e.g. rack mounted solution will be different, likely)**
- Ethernet cables for hardwired connections
  - WiFi is disabled and not recommended for k3s clusters

![accent-divider.svg](images/accent-divider.svg)
### Network Setup
- DHCP static IP assignments for all Raspberry Pis
  - Configured on network switch for centralized management
  - Static IPs required for k3s cluster nodes
- DHCP service range configuration
  - Reserve IPs up to 192.168.1.239
  - Leaves space for MetalLB allocation above this range
  - NOTE - If you are using a different subnet, there is a lot of changes to apply throughout the deployment scripts.  
  `TODO: centralize the subnet in the ansible manifest config.yaml`
- WireGuard (optional)
  - Required only for remote access
  - Provides encrypted tunnels for services like OpenWebUI, PiHole when you are not on your network


![accent-divider.svg](images/accent-divider.svg)
### Node Configuration
   - Control Plane: yoda (192.168.1.95)
   - Workers: anakin.local, obiwan.local, rey.local
   - K3s Version: v1.32.6+k3s1
   - OS: Debian GNU/Linux 12 (bookworm)
   - Kernel: 6.6.51+rpt-rpi-2712

![accent-divider.svg](images/accent-divider.svg)

> **Physical Hardware**
![Rack-Mounted-Pi5-Nodes.jpeg](images/Rack-Mounted-Pi5-Nodes.jpeg)
![Single-Node-Mounted-2.jpeg](images/Single-Node-Mounted-2.jpeg)
![SSD-Compatibility.png](images/SSD-Compatibility.png)



![accent-divider.svg](images/accent-divider.svg)
# Bill of Materials

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
| **Total Cost (Excludes POE Switch)** | **-** | **-** | **$1282** |