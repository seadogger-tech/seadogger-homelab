![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)
# Setting Up n8n Connections to Google Services

This page documents how we configured n8n in our Seadogger Homelab to work with Google APIs (Gmail, Drive, Docs, Sheets, Slides, etc.) from behind a firewall with a private k3s cluster.

![accent-divider](images/accent-divider.svg)
## Key Lessons

- n8n does not use one universal Google credential. Each Google service (Gmail, Drive, Docs, Sheets, Slides, Contacts, Calendar, etc.) requires its own credential.
- OAuth setup works fine in a private cluster using the localhost loopback method with `kubectl port-forward`.
- Once OAuth is finished, n8n stores a refresh token. Day-to-day use continues over the normal ingress at `https://n8n.seadogger-homelab`. No tunnels are required after the first setup.

![accent-divider](images/accent-divider.svg)
## Step-by-Step: Creating Google Credentials

### 1) Port-forward n8n locally
```bash
kubectl -n n8n port-forward deploy/n8n 5678:5678
```

Open the editor at `http://localhost:5678`.

### 2) Create a Google OAuth client in GCP
- APIs & Services → Credentials → Create Credentials → OAuth client ID
- Type: Web application
- Authorized redirect URI:
```
http://localhost:5678/rest/oauth2-credential/callback
```
- Copy the Client ID and Client Secret

### 3) Enable required APIs
Enable in APIs & Services → Library as needed:
- Gmail API, Google Drive API, Google Docs API, Google Sheets API, Google Slides API
- (Plus Contacts, Calendar, or others as required)

### 4) Create credentials in n8n
For each service you want (Gmail, Drive, Docs, Sheets, Slides, etc.):
- In n8n → Credentials → select the specific Google service
- Enter the Client ID/Secret
- n8n pre-defines the correct scopes for each service
- Click Connect → complete OAuth flow in the browser
- Google redirects back to `http://localhost:5678/...`, which reaches the pod through the port-forward

### 5) Verify
- Credential shows Connected in n8n
- Service node (e.g., Gmail, Google Drive, Google Docs) now works in workflows

![accent-divider](images/accent-divider.svg)
## Example Credentials We Configured
- Gmail account
- Google Drive account
- Google Docs account
- Google Sheets account + trigger
- Google Slides account
- Google Contacts account
- Google Calendar account

Each is an independent credential in n8n.

![accent-divider](images/accent-divider.svg)
## After Setup
- Port-forward is only required during credential creation.
- Normal use continues at:
```
https://n8n.seadogger-homelab
```
- Tokens refresh automatically in the background — no re-auth required unless scopes change or the credential is deleted.

![accent-divider](images/accent-divider.svg)
## Troubleshooting

### `invalid_scope` error
- Check that the required APIs are enabled in your Google Cloud project.
- Make sure scopes are space-separated, not comma-separated.
- If the project is in Testing mode, add your Google account under OAuth Consent Screen → Test Users.
- Example valid scope string (for Gmail + Drive + Docs + Sheets + Slides):
```
https://mail.google.com/ https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/presentations
```

### Secure cookie error when using port-forward
If you see this message:
```
Your n8n server is configured to use a secure cookie,
however you are either visiting this via an insecure URL...
```
Set this once in your Helm values (or equivalent env vars):
```yaml
main:
  extraEnvVars:
    N8N_SECURE_COOKIE: "false"
```
Then re-sync. This only affects port-forward sessions — your ingress URL continues to work normally.

### Consent screen never shows permissions
- Check the OAuth Client is type Web application, not Desktop or Other.
- Confirm the redirect URI matches exactly what n8n shows (`http://localhost:5678/rest/oauth2-credential/callback`).

### Tokens not refreshing
- Ensure `N8N_ENCRYPTION_KEY` is set so credentials are stored securely.
- If tokens stop refreshing (rare), re-run the port-forward OAuth flow to reconnect.

![accent-divider](images/accent-divider.svg)
## Notes
This recipe enables secure OAuth credential creation for n8n inside a private homelab without exposing the editor publicly.

