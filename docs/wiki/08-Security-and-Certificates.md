![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Security & Certificates

![accent-divider.svg](images/accent-divider.svg)
# Internal PKI and HTTPS Data Flow Architecture

This document outlines the definitive architecture for issuing and using TLS certificates for all internal services within the Kubernetes cluster. It follows the best practice of using a dedicated **Intermediate Certificate Authority (CA)** to sign service certificates, keeping the Root CA offline and secure. All internal services use the `*.seadogger-homelab` internal domain.

![accent-divider.svg](images/accent-divider.svg)
### 1. The CA Hierarchy and Full Service List

A two-tier trust chain will be established. The Intermediate CA will sign leaf certificates for the following exhaustive list of services:

```mermaid
graph TD
    A["Root CA<br>(Offline, Highly Secure)"] --> B{"Intermediate CA<br>(Online, in k8s Secret)"};
    B --> prometheus["prometheus.seadogger-homelab<br>192.168.1.244"];
    B --> grafana["grafana.seadogger-homelab<br>192.168.1.245"];
    B --> alertmanager["alertmanager.seadogger-homelab<br>192.168.1.246"];
    B --> openwebui["openwebui.seadogger-homelab"];
    B --> argocd["argocd.seadogger-homelab"];
    B --> ceph["ceph.seadogger-homelab"];
    B --> pihole["pihole.seadogger-homelab"];
    B --> jellyfin["jellyfin.seadogger-homelab"];
    B --> n8n["n8n.seadogger-homelab"];

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#ccf,stroke:#333,stroke-width:2px
```

![accent-divider.svg](images/accent-divider.svg)
### 2. Bootstrap the Private CA Hierarchy

This is a one-time setup process performed on `yoda.local` (192.168.1.95).

#### Certificate Generation and Secret Management

**Secret Names:**
- Root CA Secret: `internal-root-ca-secret`
- Intermediate CA Secret: `internal-intermediate-ca-secret`
- ClusterIssuer Name: `internal-local-issuer`

**Certificate Generation Parameters**

To ensure broad compatibility and security, the following certificate generation parameters have been standardized:

1. **Root CA**
   - Key Type: RSA
   - Key Length: 4096 bits
   - Validity Period: 10 years
   - Signature Algorithm: SHA-256
   - Secret Name: `internal-root-ca-secret`

2. **Intermediate CA**
   - Key Type: RSA
   - Key Length: 2048 bits
   - Validity Period: 2 years
   - Signature Algorithm: SHA-256
   - Secret Name: `internal-intermediate-ca-secret`

3. **Leaf Certificates**
   - Key Type: RSA
   - Key Length: 2048 bits
   - Validity Period: 1 year
   - Signature Algorithm: SHA-256
   - Secret Name Pattern: `{service-name}-local-tls`

These parameters ensure:
- Compatibility with modern browsers (Safari, Chrome)
- Strong cryptographic security
- Manageable certificate rotation cycles

```mermaid
sequenceDiagram
    autonumber
    participant Admin as You on yoda.local (192.168.1.95)
    participant RootCA as Root CA (Offline)
    participant IntCA as Intermediate CA (Online)
    participant CM as cert-manager
    participant CI as ClusterIssuer

    Admin->>RootCA: Generate Root Keypair (root-ca.key, root-ca.crt)
    Note right of RootCA: The root-ca.key is now stored offline securely.

    Admin->>IntCA: Generate Intermediate Keypair (intermediate-ca.key, intermediate-ca.csr)
    Admin->>RootCA: Sign Intermediate CSR with Root Key
    RootCA-->>Admin: Return signed Intermediate Certificate (intermediate-ca.crt)

    Admin->>CM: Create k8s Secret 'internal-intermediate-ca-secret'<br>with Intermediate CA keypair in cert-manager ns
    Admin->>CI: Apply ClusterIssuer 'internal-local-issuer'<br>pointing to 'internal-intermediate-ca-secret'
    Admin->>Admin: Install root-ca.crt into all client devices' trust stores
```

![accent-divider.svg](images/accent-divider.svg)
### 3. Issuing All Leaf Certificates

This diagram shows the complete, exhaustive flow for issuing a certificate to every service.

```mermaid
sequenceDiagram
    autonumber
    participant CM as cert-manager
    participant CI as ClusterIssuer(internal-local-issuer)
    participant ING as Ingress (Traefik)

    Note over CM,ING: Process is triggered by Ingress annotations for all *.seadogger-homelab services.

    CM->>CI: Request sign(openwebui.seadogger-homelab)
    CI-->>CM: Cert for openwebui.seadogger-homelab
    CM->>ING: Store cert in secret 'openwebui-local-tls'

    CM->>CI: Request sign(prometheus.seadogger-homelab)
    CI-->>CM: Cert for prometheus.seadogger-homelab
    CM->>ING: Store cert in secret 'prometheus-local-tls'

    CM->>CI: Request sign(grafana.seadogger-homelab)
    CI-->>CM: Cert for grafana.seadogger-homelab
    CM->>ING: Store cert in secret 'grafana-local-tls'

    CM->>CI: Request sign(alertmanager.seadogger-homelab)
    CI-->>CM: Cert for alertmanager.seadogger-homelab
    CM->>ING: Store cert in secret 'alertmanager-local-tls'

    CM->>CI: Request sign(argocd.seadogger-homelab)
    CI-->>CM: Cert for argocd.seadogger-homelab
    CM->>ING: Store cert in secret 'argocd-local-tls'

    CM->>CI: Request sign(ceph.seadogger-homelab)
    CI-->>CM: Cert for ceph.seadogger-homelab
    CM->>ING: Store cert in secret 'ceph-local-tls'

    CM->>CI: Request sign(pihole.seadogger-homelab)
    CI-->>CM: Cert for pihole.seadogger-homelab
    CM->>ING: Store cert in secret 'pihole-local-tls'

    CM->>CI: Request sign(jellyfin.seadogger-homelab)
    CI-->>CM: Cert for jellyfin.seadogger-homelab
    CM->>ING: Store cert in secret 'jellyfin-local-tls'

    CM->>CI: Request sign(n8n.seadogger-homelab)
    CI-->>CM: Cert for n8n.seadogger-homelab
    CM->>ING: Store cert in secret 'n8n-local-tls'
```

![accent-divider.svg](images/accent-divider.svg)
### 4. HTTPS Request Path (Example: `jellyfin.seadogger-homelab`)

This flow is identical for all services. The user's browser connects to the single Traefik VIP, which then routes the request to the correct internal service IP.

```mermaid
sequenceDiagram
    autonumber
    participant U as User Browser (trusts Root CA)
    participant DNS as PiHole DNS (192.168.1.250)
    participant LB as Traefik VIP (192.168.1.241)
    participant TR as Traefik Ingress
    participant KS as Secret (jellyfin-local-tls)
    participant POD as JellyFin Pod (at jellyfin.seadogger-homelab)

    U->>DNS: Resolve jellyfin.seadogger-homelab
    DNS-->>U: 192.168.1.241 (Traefik VIP)
    U->>LB: TCP :443
    LB->>TR: Forward stream
    U->>TR: TLS ClientHello (SNI=jellyfin.seadogger-homelab)
    TR->>KS: Load cert/key for jellyfin.seadogger-homelab
    KS-->>TR: Leaf cert + chain
    TR-->>U: ServerHello + Certificate
    U-->>U: Verify certificate chain up to the trusted Root CA
    U->>TR: Encrypted GET /
    TR->>POD: Decrypted HTTP request to Plex Service
    POD-->>TR: HTTP response
    TR-->>U: Encrypted HTTPS response
```

![accent-divider.svg](images/accent-divider.svg)
# Next Steps: SSO Implementation Plan

This section outlines the plan for implementing Single Sign-On (SSO) using Keycloak as the Identity Provider (IdP), enforced at the edge by `oauth2-proxy` and Traefik's `ForwardAuth` middleware.

![accent-divider.svg](images/accent-divider.svg)
## Goal

Centralize login with Keycloak, enforce it uniformly at the edge with `oauth2-proxy` + Traefik, and pass user identity to backend applications via HTTP headers.

![accent-divider.svg](images/accent-divider.svg)
## Architecture and Hostnames

*   **Keycloak (IdP):** `idp.seadogger-homelab` (will be assigned a new VIP, e.g., 192.168.1.253)
*   **oauth2-proxy:** `auth.seadogger-homelab` (internal service, no dedicated VIP)
*   **Traefik (Ingress):** `192.168.1.241` (existing VIP)
*   **Protected Applications:** `grafana.seadogger-homelab`, `n8n.seadogger-homelab`, `openwebui.seadogger-homelab`, `prometheus.seadogger-homelab`, `alertmanager.seadogger-homelab`, `argocd.seadogger-homelab`, `ceph.seadogger-homelab`.

![accent-divider.svg](images/accent-divider.svg)
## Secrets & Credentials

- Do not commit real credentials to git. Store sensitive values with Ansible Vault (e.g., `ansible-vault encrypt_string`) and use GitHub Actions secrets for CI (e.g., `WIKI_TOKEN`). If any secrets were committed previously, rotate them immediately (create new credentials, update Vault/CI, disable the old ones).

![accent-divider.svg](images/accent-divider.svg)
## Client Trust: Export and Install the Root CA

To avoid browser “untrusted site” warnings when accessing the portal and other internal services, install your internal Root CA on your devices.

### 1) Export the Root CA (and optional Intermediate)
Get the Root CA PEM (the trust anchor to install on devices):
```
kubectl -n cert-manager get secret internal-root-ca-secret \
  -o jsonpath='{.data.root-ca\.crt}' | base64 -d > seadogger-rootCA.pem
```

Optional — export the Intermediate CA (for inspection/chain debugging):
```
kubectl -n cert-manager get secret internal-intermediate-ca-secret \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > seadogger-intermediateCA.pem
```

### 2) Install on Devices
- iPhone / iPad (iOS & iPadOS)
  - AirDrop or email `seadogger-rootCA.pem` to the device
  - Tap to install: Settings > General > VPN & Device Management > Profiles
  - Then: Settings > General > About > Certificate Trust Settings → enable “Full Trust” for “SeaDogger Root CA”

- Mac (macOS)
  - Double‑click `seadogger-rootCA.pem` → opens in Keychain Access
  - Install into the System keychain
  - Right‑click the certificate → Get Info → Trust → set to “Always Trust”

- Chrome
  - Uses the OS trust store
  - On macOS: inherits Keychain trust (works after steps above)
  - On iOS/iPadOS: uses system trust (works after enabling “Full Trust”)

After installation, your browser will trust certificates issued for `*.seadogger-homelab` by your internal CA.

![accent-divider.svg](images/accent-divider.svg)
### SSO Component Block Diagram

This diagram shows the high-level relationship between the components and explicitly lists all applications that will be protected.

```mermaid
graph LR
    subgraph "User's Browser"
        U(User)
    end

    subgraph "Kubernetes Cluster"
        T[Traefik Ingress]
        O[oauth2-proxy]
        K[Keycloak]
        subgraph "SSO-Protected Apps"
            A1[grafana.seadogger-homelab]
            A2[n8n.seadogger-homelab]
            A3[openwebui.seadogger-homelab]
            A4[prometheus.seadogger-homelab]
            A5[alertmanager.seadogger-homelab]
            A6[argocd.seadogger-homelab]
            A7[ceph.seadogger-homelab]
        end
    end

    U -- "Request App" --> T
    T -- "ForwardAuth Check" --> O
    O -- "Redirect for Login" --> U
    U -- "Authenticates" --> K
    K -- "Redirect w/ Code" --> U
    U -- "Callback to Proxy" --> O
    O -- "Sets Session Cookie" --> U
    U -- "Authenticated Request" --> T
    
    T -- "Forwards to" --> A1
    T -- "Forwards to" --> A2
    T -- "Forwards to" --> A3
    T -- "Forwards to" --> A4
    T -- "Forwards to" --> A5
    T -- "Forwards to" --> A6
    T -- "Forwards to" --> A7

    style T fill:#89cff0
    style O fill:#f9e79f
    style K fill:#f5b7b1
```
![accent-divider.svg](images/accent-divider.svg)
## SSO Login Flow (First Time Access)

This diagram shows a user accessing a protected application (`grafana.seadogger-homelab`) for the first time.

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Traefik as Traefik Ingress (192.168.1.241)
    participant OAuth2Proxy as oauth2-proxy (auth.seadogger-homelab)
    participant Keycloak as Keycloak (idp.seadogger-homelab)
    participant Grafana as Grafana App

    User->>Traefik: GET https://grafana.seadogger-homelab
    Traefik->>OAuth2Proxy: ForwardAuth: Is user authenticated?
    OAuth2Proxy-->>Traefik: No (401 Unauthorized)
    Traefik-->>User: Redirect to login page
    User->>OAuth2Proxy: GET /oauth2/start
    OAuth2Proxy-->>User: Redirect to Keycloak login
    User->>Keycloak: User enters credentials
    Keycloak-->>User: Login success, redirect back to proxy with auth code
    User->>OAuth2Proxy: GET /oauth2/callback?code=...
    OAuth2Proxy->>Keycloak: Exchange auth code for tokens
    Keycloak-->>OAuth2Proxy: ID, Access, Refresh Tokens
    OAuth2Proxy-->>User: Set session cookie, redirect to original URL (grafana.seadogger-homelab)
    User->>Traefik: GET https://grafana.seadogger-homelab (with session cookie)
    Traefik->>OAuth2Proxy: ForwardAuth: Is user authenticated?
    OAuth2Proxy-->>Traefik: Yes (200 OK) + sets X-Forwarded-User header
    Traefik->>Grafana: Forward request with user identity header
    Grafana-->>Traefik: App content
    Traefik-->>User: App content
```
![accent-divider.svg](images/accent-divider.svg)
## Authenticated Request Flow

Once the user has a valid session cookie, every subsequent request is validated quickly at the edge.

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Traefik as Traefik Ingress (192.168.1.241)
    participant OAuth2Proxy as oauth2-proxy (auth.seadogger-homelab)
    participant N8N as n8n App

    User->>Traefik: GET https://n8n.seadogger-homelab (with session cookie)
    Traefik->>OAuth2Proxy: ForwardAuth: Validate cookie
    OAuth2Proxy-->>Traefik: OK (200) + X-Forwarded-User header
    Traefik->>N8N: Forward request with identity
    N8N-->>Traefik: App content
    Traefik-->>User: App content
```
![accent-divider.svg](images/accent-divider.svg)
## Global Logout Flow

This shows how logging out from one application logs the user out of the entire SSO session.

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Traefik as Traefik Ingress (192.168.1.241)
    participant OAuth2Proxy as oauth2-proxy (auth.seadogger-homelab)
    participant Keycloak as Keycloak (idp.seadogger-homelab)

    User->>Traefik: GET https://auth.seadogger-homelab/oauth2/sign_out
    Note over User, Traefik: (This link would be present in the UI of Grafana, n8n, etc.)
    Traefik->>OAuth2Proxy: Forward request to sign_out endpoint
    OAuth2Proxy-->>User: Clear session cookie
    OAuth2Proxy->>Keycloak: RP-Initiated Logout: Invalidate user session
    Keycloak-->>OAuth2Proxy: Logout successful
    OAuth2Proxy-->>User: Redirect to a post-logout page
```

![accent-divider.svg](images/accent-divider.svg)
## See Also

- **[[07-Networking-and-Ingress]]** - Traefik TLS termination
- **[[04-Bootstrap-and-Cold-Start]]** - Internal PKI deployment
- **[[02-Architecture]]** - C4 Network & Security diagram
- **[[21-Deployment-Dependencies]]** - Cert-manager dependency analysis

**Related Issues:**
- [#42 - Document encryption strategy](https://github.com/seadogger-tech/seadogger-homelab/issues/42) - Encryption ADR
- [#25 - Encryption verification](https://github.com/seadogger-tech/seadogger-homelab/issues/25) - End-to-end encryption checks
- [#48 - Deployment Dependencies](https://github.com/seadogger-tech/seadogger-homelab/issues/48) - Simplify PKI bootstrap
