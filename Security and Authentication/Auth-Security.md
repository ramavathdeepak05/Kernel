# ALIS Master Architecture & Authentication Strategy

**Version**: 1.0
**Philosophy**: "Local-First Compute, Cloud-First Security."

## 1. High-Level Architecture (Hub & Spoke)
We use a **Multi-Tenant, Distributed** model.
- **The Hub (Cloudflare)**: Single control plane for DNS and Identity.
- **The Spokes (Local Servers)**: Physical servers at each client site running ALIS.

```mermaid
graph TD
    subgraph "The Hub (Cloudflare Zero Trust)"
        DNS[Wildcard DNS: *.alis.quaicu.org]
        Access[Identity Gateway (SSO + Policy)]
    end

    subgraph "Client A (University)"
        TunnelA[Tunnel: woxsen.alis.quaicu.org]
        ServerA[Local Server (Air-Gapped Logic)]
        AuthA[ALIS Auth (Layer 2 OTP)]
    end

    subgraph "Client B (Corporate)"
        TunnelB[Tunnel: corp.alis.quaicu.org]
        ServerB[Local Server (Air-Gapped Logic)]
        AuthB[ALIS Auth (Layer 2 OTP)]
    end

    User -->|HTTPS| DNS
    DNS -->|Layer 1 Auth| Access
    Access -->|Secure Tunnel| TunnelA
    TunnelA --> ServerA
    ServerA -->|Layer 2 Auth| AuthA
```

---

## 2. Authentication Strategy: "The Hybrid Double-Lock"
We combine **Convenience** (SSO) with **Independence** (ALIS OTP).

### Gate 1: Cloudflare Access (Network Layer)
- **Mechanism**: **Google / Microsoft SSO**.
- **User Action**: Logs in with their existing institutional email (`user@woxsen.edu`).
- **Benefit**: No new passwords. If the institution disables their email, they lose access instantly.
- **Result**: User is tunneled to the local ALIS server.

### Gate 2: ALIS Application (App Layer)
- **Mechanism**: **ALIS OTP** (One-Time Password).
- **User Action**: ALIS detects the user (via headers) and challenges them: *"Enter the code sent to your mobile ending in 88."*
- **Benefit**: Protects against compromised institutional accounts. Even if a hacker has the Google password, they cannot enter ALIS without the phone.

---

## 3. User Provisioning (The Cycle)
ALIS acts as the **Identity Master**.

1.  **Onboarding**: Admin creates user in ALIS Wizard.
2.  **Provisioning**: ALIS (via API) creates the user's **Outlook/Google Account** and assigns licenses.
3.  **Sync**: The user can now use those Outlook credentials to pass **Gate 1**.
4.  **Offboarding**: Admin disables user in ALIS. ALIS revokes their Outlook access and Cloudflare session.

---

## 4. Cloudflare Tunnel Setup Guide

**Objective**: Securely expose the ALIS Frontend/Backend to `alis.quaicu.org` without opening inbound ports.

### Prerequisites
- A Cloudflare account with `quaicu.org` active.
- Access to the ALIS Server (Windows).
- Administrator privileges (PowerShell).

### Step 1: Install `cloudflared`
Run the following in **PowerShell (Admin)**:

```powershell
# Create directory
New-Item -ItemType Directory -Force -Path "C:\Cloudflare"
Set-Location "C:\Cloudflare"

# Download the executable
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile "cloudflared.exe"

# Verify version
.\cloudflared.exe --version
```

### Step 2: Authenticate
This links the server to your Cloudflare account.

```powershell
.\cloudflared.exe tunnel login
```
- A browser window will open. Select `quaicu.org`.
- Once authorized, a certificate file (`cert.pem`) will be saved.

### Step 3: Create the Tunnel
Create a named tunnel (e.g., `alis-production`).

```powershell
.\cloudflared.exe tunnel create alis-production
```
- This generates a **Tunnel ID** (UUID) and a credentials file. Save the UUID.

### Step 4: Configure the Tunnel
Create `C:\Cloudflare\config.yml`:

```yaml
tunnel: <Your-Tunnel-UUID>
credentials-file: C:\Users\<Username>\.cloudflared\<Tunnel-UUID>.json

ingress:
  # Frontend (Next.js)
  - hostname: alis.quaicu.org
    service: http://localhost:3000

  # Catch-all (404 for anything else)
  - service: http_status:404
```

### Step 5: Route DNS
Route the public domain to this tunnel.

```powershell
.\cloudflared.exe tunnel route dns alis-production alis.quaicu.org
```

### Step 6: Run as Service
Install `cloudflared` as a Windows Service so it starts automatically on reboot.

```powershell
.\cloudflared.exe service install
Start-Service cloudflared
```

---

## 5. Identity Provider (IdP) Integration Guide

**Objective**: Connect Woxsen's Email System (Microsoft/Google) to Cloudflare so users can log in with institutional credentials.

### Azure AD (Microsoft Entra ID) Setup

1.  **In Azure Portal (portal.azure.com)**:
    - Go to **Microsoft Entra ID** > **App registrations** > **New registration**.
    - Name: `Cloudflare Access`.
    - Redirect URI (Web): `https://<your-team-domain>.cloudflareaccess.com/cdn-cgi/access/callback`.
    - Register and copy **Application (client) ID** and **Directory (tenant) ID**.
    - Go to **Certificates & secrets** > **New client secret**. Copy the **Value**.
    - Go to **API permissions** > **Add a permission** > **Microsoft Graph** > **User.Read** (Grant Admin Consent).

2.  **In Cloudflare Zero Trust Dashboard**:
    - Go to **Settings** > **Authentication** > **Add new**.
    - Select **Azure AD**.
    - Paste the **Client ID**, **Tenant ID**, and **Client Secret**.
    - Click **Save**.

### Google Workspace Setup

1.  **In Google Cloud Console (console.cloud.google.com)**:
    - Create a new project: `Cloudflare Access`.
    - Go to **APIs & Services** > **OAuth consent screen**. Set User Type to **Internal**.
    - Go to **Credentials** > **Create Credentials** > **OAuth client ID** > **Web application**.
    - Authorized redirect URIs: `https://<your-team-domain>.cloudflareaccess.com/cdn-cgi/access/callback`.
    - Copy **Client ID** and **Client Secret**.

2.  **In Cloudflare Zero Trust Dashboard**:
    - Go to **Settings** > **Authentication** > **Add new**.
    - Select **Google Workspace**.
    - Paste the **Client ID** and **Client Secret**.
    - Enter your Google Workspace Domain (e.g., `woxsen.edu`).
    - Click **Save**.

### Final Step: Test Login
- Visit your Access App URL (e.g., `woxsen.alis.quaicu.org`).
- You should see a button: **"Login with Azure AD"** or **"Login with Google"**.
