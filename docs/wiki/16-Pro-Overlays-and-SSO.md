![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)
# Pro Overlays and SSO

This page explains how the Pro layer adds Single Sign-On (SSO), middleware, and overlays on top of the Core stack.

![accent-divider](images/accent-divider.svg)
## What Pro Adds
- Keycloak (IdP) for identity and access management
- oauth2-proxy for OIDC integration
- Traefik `ForwardAuth` middleware to enforce SSO at the edge
- Ingress patches/overlays to attach SSO consistently to app UIs
- Optional portal UI linking all services

![accent-divider](images/accent-divider.svg)
## Hostnames and VIPs
- Traefik VIP: `192.168.1.241`
- Protected hosts (examples):
  - `grafana.seadogger-homelab`
  - `n8n.seadogger-homelab`
  - `openwebui.seadogger-homelab`
  - `prometheus.seadogger-homelab`
  - `alertmanager.seadogger-homelab`
  - `argocd.seadogger-homelab`
  - `ceph.seadogger-homelab`
  - `jellyfin.seadogger-homelab`

![accent-divider](images/accent-divider.svg)
## Deployment Overview (Ansible + ArgoCD)
Pro does not deploy directly with Helm. Instead, Ansible applies ArgoCD Applications which point to the relevant charts/manifests and Pro overlays. ArgoCD then reconciles the desired state.

High-level flow:
- Ansible provisions/updates Core (k3s, cert-manager, ArgoCD, MetalLB, storage).
- Ansible applies ArgoCD Application resources for SSO components (e.g., Keycloak, oauth2-proxy) and Pro overlays.
- ArgoCD syncs these apps into the cluster. IngressRoutes reference the Traefik ForwardAuth middleware to enforce SSO.

To deploy:
1) Ensure ArgoCD is installed via the Core playbooks (`argocd_native_deploy.yml`).
2) Apply Pro ArgoCD Application manifests (via your Pro Ansible tasks) that reference:
   - SSO components (charts/manifests)
   - Overlays (kustomize/patches) that attach ForwardAuth to Ingresses
3) Watch ArgoCD sync status and verify protected hosts resolve at Traefik VIP.

![accent-divider](images/accent-divider.svg)
## Traefik ForwardAuth Pattern
1) Define a Traefik Middleware pointing to oauth2-proxy (ForwardAuth).
2) Reference the Middleware from each Ingress/IngressRoute that requires SSO.
3) Ensure cert-manager issues TLS for all `*.seadogger-homelab` hosts.

Tips:
- Set correct redirect URIs in Keycloak and oauth2-proxy.
- Use an appropriate cookie domain.
- Verify system time sync to avoid token validation issues.
- Mount internal CA trust where components validate TLS internally.
