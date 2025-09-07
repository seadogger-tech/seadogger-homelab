# Internal PKI and HTTPS Data Flow Architecture
## Date: 2025-08-12

This document outlines the definitive architecture for issuing and using TLS certificates for all internal services within the Kubernetes cluster. It follows the best practice of using a dedicated **Intermediate Certificate Authority (CA)** to sign service certificates, keeping the Root CA offline and secure. All internal services will use the `.local` top-level domain.

### 1. The CA Hierarchy and Full Service List

A two-tier trust chain will be established. The Intermediate CA will sign leaf certificates for the following exhaustive list of services:

```mermaid
graph TD
    A["Root CA<br>(Offline, Highly Secure)"] --> B{"Intermediate CA<br>(Online, in k8s Secret)"};
    B --> openwebui["openwebui.local<br>192.168.1.243"];
    B --> prometheus["prometheus.local<br>192.168.1.244"];
    B --> grafana["grafana.local<br>192.168.1.245"];
    B --> alertmanager["alertmanager.local<br>192.168.1.246"];
    B --> argocd["argocd.local<br>192.168.1.247"];
    B --> ceph["ceph.local<br>192.168.1.248"];
    B --> pihole["pihole.local<br>192.168.1.249"];
    B --> plex["plex.local<br>192.168.1.251"];
    B --> n8n["n8n.local<br>192.168.1.252"];

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#ccf,stroke:#333,stroke-width:2px
```

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

### 3. Issuing All Leaf Certificates

This diagram shows the complete, exhaustive flow for issuing a certificate to every service.

```mermaid
sequenceDiagram
    autonumber
    participant CM as cert-manager
    participant CI as ClusterIssuer(internal-local-issuer)
    participant ING as Ingress (Traefik)

    Note over CM,ING: Process is triggered by Ingress annotations for all .local services.

    CM->>CI: Request sign(openwebui.local)
    CI-->>CM: Cert for openwebui.local
    CM->>ING: Store cert in secret 'openwebui-local-tls'

    CM->>CI: Request sign(prometheus.local)
    CI-->>CM: Cert for prometheus.local
    CM->>ING: Store cert in secret 'prometheus-local-tls'

    CM->>CI: Request sign(grafana.local)
    CI-->>CM: Cert for grafana.local
    CM->>ING: Store cert in secret 'grafana-local-tls'

    CM->>CI: Request sign(alertmanager.local)
    CI-->>CM: Cert for alertmanager.local
    CM->>ING: Store cert in secret 'alertmanager-local-tls'

    CM->>CI: Request sign(argocd.local)
    CI-->>CM: Cert for argocd.local
    CM->>ING: Store cert in secret 'argocd-local-tls'

    CM->>CI: Request sign(ceph.local)
    CI-->>CM: Cert for ceph.local
    CM->>ING: Store cert in secret 'ceph-local-tls'

    CM->>CI: Request sign(pihole.local)
    CI-->>CM: Cert for pihole.local
    CM->>ING: Store cert in secret 'pihole-local-tls'

    CM->>CI: Request sign(plex.local)
    CI-->>CM: Cert for plex.local
    CM->>ING: Store cert in secret 'plex-local-tls'

    CM->>CI: Request sign(n8n.local)
    CI-->>CM: Cert for n8n.local
    CM->>ING: Store cert in secret 'n8n-local-tls'
```

### 4. HTTPS Request Path (Example: `plex.local`)

This flow is identical for all services. The user's browser connects to the single Traefik VIP, which then routes the request to the correct internal service IP.

```mermaid
sequenceDiagram
    autonumber
    participant U as User Browser (trusts Root CA)
    participant DNS as PiHole DNS (192.168.1.250)
    participant LB as Traefik VIP (192.168.1.241)
    participant TR as Traefik Ingress
    participant KS as Secret (plex-local-tls)
    participant POD as Plex Pod (at 192.168.1.251)

    U->>DNS: Resolve plex.local
    DNS-->>U: 192.168.1.241 (Traefik VIP)
    U->>LB: TCP :443
    LB->>TR: Forward stream
    U->>TR: TLS ClientHello (SNI=plex.local)
    TR->>KS: Load cert/key for plex.local
    KS-->>TR: Leaf cert + chain
    TR-->>U: ServerHello + Certificate
    U-->>U: Verify certificate chain up to the trusted Root CA
    U->>TR: Encrypted GET /
    TR->>POD: Decrypted HTTP request to Plex Service
    POD-->>TR: HTTP response
    TR-->>U: Encrypted HTTPS response
```

---
# Next Steps: SSO Implementation Plan

This section outlines the plan for implementing Single Sign-On (SSO) using Keycloak as the Identity Provider (IdP), enforced at the edge by `oauth2-proxy` and Traefik's `ForwardAuth` middleware.

## Goal

Centralize login with Keycloak, enforce it uniformly at the edge with `oauth2-proxy` + Traefik, and pass user identity to backend applications via HTTP headers.

## Architecture and Hostnames

*   **Keycloak (IdP):** `idp.local` (will be assigned a new VIP, e.g., 192.168.1.253)
*   **oauth2-proxy:** `auth.local` (internal service, no dedicated VIP)
*   **Traefik (Ingress):** `192.168.1.241` (existing VIP)
*   **Protected Applications:** `grafana.local`, `n8n.local`, `openwebui.local`, `prometheus.local`, `alertmanager.local`, `argocd.local`, `ceph.local`.

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
            A1[grafana.local]
            A2[n8n.local]
            A3[openwebui.local]
            A4[prometheus.local]
            A5[alertmanager.local]
            A6[argocd.local]
            A7[ceph.local]
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

## SSO Login Flow (First Time Access)

This diagram shows a user accessing a protected application (`grafana.local`) for the first time.

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Traefik as Traefik Ingress (192.168.1.241)
    participant OAuth2Proxy as oauth2-proxy (auth.local)
    participant Keycloak as Keycloak (idp.local)
    participant Grafana as Grafana App

    User->>Traefik: GET https://grafana.local
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
    OAuth2Proxy-->>User: Set session cookie, redirect to original URL (grafana.local)
    User->>Traefik: GET https://grafana.local (with session cookie)
    Traefik->>OAuth2Proxy: ForwardAuth: Is user authenticated?
    OAuth2Proxy-->>Traefik: Yes (200 OK) + sets X-Forwarded-User header
    Traefik->>Grafana: Forward request with user identity header
    Grafana-->>Traefik: App content
    Traefik-->>User: App content
```

## Authenticated Request Flow

Once the user has a valid session cookie, every subsequent request is validated quickly at the edge.

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Traefik as Traefik Ingress (192.168.1.241)
    participant OAuth2Proxy as oauth2-proxy (auth.local)
    participant N8N as n8n App

    User->>Traefik: GET https://n8n.local (with session cookie)
    Traefik->>OAuth2Proxy: ForwardAuth: Validate cookie
    OAuth2Proxy-->>Traefik: OK (200) + X-Forwarded-User header
    Traefik->>N8N: Forward request with identity
    N8N-->>Traefik: App content
    Traefik-->>User: App content
```

## Global Logout Flow

This shows how logging out from one application logs the user out of the entire SSO session.

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Traefik as Traefik Ingress (192.168.1.241)
    participant OAuth2Proxy as oauth2-proxy (auth.local)
    participant Keycloak as Keycloak (idp.local)

    User->>Traefik: GET https://auth.local/oauth2/sign_out
    Note over User, Traefik: (This link would be present in the UI of Grafana, n8n, etc.)
    Traefik->>OAuth2Proxy: Forward request to sign_out endpoint
    OAuth2Proxy-->>User: Clear session cookie
    OAuth2Proxy->>Keycloak: RP-Initiated Logout: Invalidate user session
    Keycloak-->>OAuth2Proxy: Logout successful
    OAuth2Proxy-->>User: Redirect to a post-logout page
```
