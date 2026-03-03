# 🔐 HPC Manager Security Guide

**Current Status:** Prototype with HPC password authentication  
**For Production:** Upgrade to Web Auth + SSH Keys (see below)

---

## 📊 Current Implementation (Prototype)

Your app currently uses **HPC password authentication** with these security features:

### ✅ What's Implemented

1. **Password Authentication**
   - Users log in with HPC username/password
   - Password cleared from memory immediately after connection
   - No passwords stored in session state

2. **Rate Limiting**
   - Maximum 3 login attempts
   - 5-minute lockout after failed attempts
   - Prevents brute force attacks

3. **Session Management**
   - 30-minute inactivity timeout
   - Automatic disconnect on timeout
   - Session timer displayed to user

4. **Hostname Whitelist**
   - Only approved HPC clusters allowed
   - Prevents connection to arbitrary hosts
   - Configured in `Home.py`: `ALLOWED_HOSTS`

5. **Dual Authentication Methods**
   - Option 1: Password (simple, for prototyping)
   - Option 2: SSH key (more secure, for power users)

### ⚠️ Current Limitations

- No web application authentication (anyone with URL can access)
- Password transmitted to server (encrypted via HTTPS but visible to Render)
- Single layer of security
- No audit logging
- No user management system

---

## 🏗️ Production Security Architecture

For deployment beyond prototype, implement **two-layer security**:

```
┌─────────────────────────────────────────┐
│  LAYER 1: Web Application Auth          │
│  - Controls WHO can access the app      │
│  - Separate from HPC credentials        │
│  - Implemented with streamlit-auth       │
└─────────────────────────────────────────┘
              ↓ ✅ Web user authenticated
┌─────────────────────────────────────────┐
│  LAYER 2: HPC Authentication            │
│  - Controls WHAT user can do on HPC     │
│  - SSH key (most secure)                │
│  - Or HPC password (acceptable)         │
└─────────────────────────────────────────┘
```

---

## 🚀 Production Upgrade Path

### Option 1: Web Auth + Password (Medium Security)

**Best for:** Small teams, quick deployment

**Implementation:**
```bash
# Add to requirements.txt
streamlit-authenticator>=0.2.3
pyyaml
bcrypt
```

**Files to add:**
- `config.yaml` - Web user credentials (see below)
- Modify `Home.py` - Add web authentication layer

**User workflow:**
1. User logs into web app (web username/password)
2. User enters HPC credentials (HPC username/password)
3. Connect to HPC cluster

**Security level:** 🟡 Medium
- ✅ Two-layer authentication
- ✅ Access control to web app
- ❌ Still uses passwords for HPC

---

### Option 2: Web Auth + SSH Keys (High Security) ⭐ RECOMMENDED

**Best for:** Production deployments, multiple users

**Implementation:**
```bash
# Add to requirements.txt
streamlit-authenticator>=0.2.3
pyyaml
bcrypt
sqlalchemy
psycopg2-binary
cryptography
```

**Files to add:**
- `config.yaml` - Web user credentials
- `database_setup.py` - PostgreSQL schema for encrypted key storage
- Modify `Home.py` - Add web auth + key management

**User workflow:**
1. User logs into web app (web username/password)
2. First time: Upload SSH private key → encrypted & stored in database
3. Subsequent logins: Key automatically retrieved and decrypted
4. Connect to HPC using stored key

**Security level:** 🟢 High
- ✅ Two-layer authentication
- ✅ SSH keys (industry standard)
- ✅ Keys encrypted at rest
- ✅ Per-user audit trail
- ✅ No passwords in memory

**Reference files:**
- `secure_auth_example.py` - Complete implementation
- `database_setup_example.py` - Database schema
- `config.yaml.template` - Configuration template

---

### Option 3: OAuth/SSO Integration (Enterprise)

**Best for:** Organizations with existing identity providers

**Implementation:**
```bash
# Add to requirements.txt
streamlit-oauth
requests
```

**Providers supported:**
- Google Workspace
- Microsoft Azure AD
- GitHub
- Okta
- Custom SAML/OAuth2

**User workflow:**
1. User clicks "Login with Google" (or other provider)
2. Redirected to provider for authentication
3. Returns to app with verified identity
4. Upload SSH key or use stored key
5. Connect to HPC

**Security level:** 🟢 Very High
- ✅ Enterprise SSO
- ✅ MFA from provider
- ✅ Centralized user management
- ✅ Automatic account provisioning/deprovisioning

---

## 📁 Reference Implementation Files

The following files demonstrate production security patterns:

### 1. `secure_auth_example.py`
Complete working example showing all three SSH key methods:
- **Method A:** Upload key each session
- **Method B:** Paste key content
- **Method C:** Encrypted vault storage

### 2. `database_setup_example.py`
PostgreSQL schema and functions for:
- User management
- Encrypted SSH key storage
- Key encryption/decryption
- Audit logging

### 3. `config.yaml.template`
Web authentication configuration:
```yaml
credentials:
  usernames:
    alice:
      email: alice@university.edu
      name: Alice Smith
      password: $2b$12$hashed_password
      hpc_username: asmith
```

---

## 🔧 How to Upgrade from Prototype to Production

### Step 1: Choose Your Security Level

| Current Use Case | Recommended Upgrade |
|------------------|---------------------|
| Personal/Lab testing | Stay with current (password) |
| Small team (5-10 users) | Web Auth + Password |
| Department-wide (10-50 users) | Web Auth + SSH Keys |
| Organization-wide (50+ users) | OAuth/SSO + SSH Keys |

### Step 2: Set Up Web Authentication

```bash
# Install dependencies
pip install streamlit-authenticator pyyaml bcrypt

# Create config.yaml
cp config.yaml.template config.yaml

# Generate password hashes
python -c "import streamlit_authenticator as stauth; print(stauth.Hasher(['password123']).generate())"
```

Add to `config.yaml`:
```yaml
credentials:
  usernames:
    user1:
      email: user1@example.com
      name: User One
      password: <paste_generated_hash>

cookie:
  name: hpc_manager_cookie
  key: <generate_random_key>
  expiry_days: 0
```

Modify `Home.py` to require web login before showing HPC connection form.

### Step 3: (Optional) Add SSH Key Vault

```bash
# Install database dependencies
pip install sqlalchemy psycopg2-binary cryptography

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set environment variable in Render
SSH_KEY_ENCRYPTION_KEY=<generated_key>

# Initialize database
python database_setup_example.py --init
```

Add key management UI to `Home.py` (see `secure_auth_example.py` for reference).

### Step 4: Deploy to Render

```bash
# Environment variables to set in Render dashboard:
SSH_KEY_ENCRYPTION_KEY=<your_key>
DATABASE_URL=<postgres_url_from_render>
ALLOWED_HPC_HOSTS=login1.nan.kcl.ac.uk,login2.nan.kcl.ac.uk
SECRET_KEY=<random_secret>
```

Add PostgreSQL addon in Render dashboard.

---

## 🛡️ Security Best Practices

### For Current Prototype

✅ **Do:**
- Use HTTPS (Render provides automatically)
- Keep `ALLOWED_HOSTS` whitelist updated
- Monitor for suspicious connection attempts
- Use strong passwords
- Log out when finished

❌ **Don't:**
- Share the app URL publicly
- Use the same password for web app and HPC
- Leave sessions open unattended
- Connect from public WiFi without VPN

### For Production

✅ **Additional Do's:**
- Enable audit logging
- Rotate secrets every 90 days
- Use PostgreSQL (not SQLite)
- Set up monitoring/alerts
- Regular security audits
- Document security incidents
- Train users on security practices

❌ **Additional Don'ts:**
- Never commit `config.yaml` to git
- Never log passwords
- Never store unencrypted keys
- Never disable HTTPS
- Never skip input validation

---

## 🔍 Security Checklist

### Pre-Deployment

- [ ] Web authentication configured
- [ ] SSH keys used (not passwords)
- [ ] Database set up for key storage
- [ ] All secrets in environment variables
- [ ] `config.yaml` in `.gitignore`
- [ ] HTTPS enforced
- [ ] Session timeout configured
- [ ] Rate limiting enabled
- [ ] Input validation added
- [ ] Audit logging implemented

### Post-Deployment

- [ ] Test all authentication flows
- [ ] Verify session timeout works
- [ ] Check rate limiting triggers
- [ ] Monitor logs for errors
- [ ] Set up alerts for failed logins
- [ ] Document user onboarding process
- [ ] Create incident response plan
- [ ] Schedule security reviews

---

## 🔐 Secrets Management

### Current (Prototype)
No secrets stored persistently - passwords only in memory during active session.

### Production Requirements

**Never hardcode these:**
- Database passwords
- Encryption keys
- API tokens
- Cookie secrets
- SSH keys

**Use Render environment variables:**
```bash
# In Render Dashboard > Environment
DATABASE_URL=postgresql://...
SSH_KEY_ENCRYPTION_KEY=abc123...
SECRET_KEY=xyz789...
COOKIE_KEY=def456...
```

**Access in code:**
```python
import os
DB_PASSWORD = os.environ.get('DATABASE_URL')
ENCRYPTION_KEY = os.environ.get('SSH_KEY_ENCRYPTION_KEY')
```

---

## 📊 Security Comparison Matrix

| Feature | Current (Prototype) | Web Auth + Password | Web Auth + Keys | OAuth + Keys |
|---------|---------------------|---------------------|-----------------|--------------|
| **Web app access control** | ❌ | ✅ | ✅ | ✅ |
| **HPC authentication** | Password | Password | SSH Key | SSH Key |
| **Two-factor security** | ❌ | ✅ | ✅ | ✅ |
| **Audit trail** | ❌ | ✅ | ✅ | ✅ |
| **Key encryption** | N/A | N/A | ✅ | ✅ |
| **SSO integration** | ❌ | ❌ | ❌ | ✅ |
| **Setup complexity** | 🟢 Simple | 🟡 Medium | 🟠 Complex | 🔴 Advanced |
| **Maintenance** | 🟢 Low | 🟡 Medium | 🟠 High | 🔴 High |
| **Security level** | 🟡 Basic | 🟡 Medium | 🟢 High | 🟢 Very High |
| **Cost** | Free | Free | Postgres addon | Free + Provider |

---

## 🚨 Incident Response

### If You Suspect Compromise

1. **Immediate actions:**
   - Disable the app (stop Render service)
   - Reset all passwords
   - Revoke all SSH keys
   - Check audit logs

2. **Investigation:**
   - Review access logs
   - Check for unauthorized jobs
   - Verify no data exfiltration
   - Document findings

3. **Recovery:**
   - Rotate all secrets
   - Update security policies
   - Re-deploy with enhanced security
   - Notify affected users

4. **Prevention:**
   - Implement missing security controls
   - Add monitoring/alerting
   - Schedule security training
   - Document lessons learned

---

## 📚 Additional Resources

### Documentation
- Streamlit Authentication: https://github.com/mkhorasani/Streamlit-Authenticator
- Paramiko SSH: https://www.paramiko.org/
- Cryptography: https://cryptography.io/
- Render Security: https://render.com/docs/security

### Security Standards
- NIST Password Guidelines: https://pages.nist.gov/800-63-3/
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- CIS Controls: https://www.cisecurity.org/controls

### Tools
- Password strength checker
- Secret scanner (for git repos)
- Vulnerability scanner
- Penetration testing services

---

## 🤝 Getting Help

### For Security Issues
- **DO NOT** post security issues publicly
- Email: your-security-contact@example.com
- Use encrypted communication

### For Implementation Help
- Review `secure_auth_example.py`
- Check Streamlit documentation
- Community forums (for non-security questions)

---

## 📝 Version History

| Version | Date | Changes | Security Level |
|---------|------|---------|----------------|
| 1.0 | 2026-02-09 | Initial prototype with HPC password auth | 🟡 Basic |
| 2.0 | TBD | Add web authentication | 🟡 Medium |
| 3.0 | TBD | Add SSH key vault | 🟢 High |
| 4.0 | TBD | Add OAuth/SSO | 🟢 Very High |

---

## 🎯 Quick Start for Production Upgrade

**When you're ready to move from prototype to production:**

1. **Choose upgrade path** (see comparison matrix above)
2. **Review reference files:**
   - `secure_auth_example.py`
   - `database_setup_example.py`
   - `config.yaml.template`
3. **Install dependencies** (see requirements for your chosen path)
4. **Configure authentication** (web auth or OAuth)
5. **Set up database** (if using key vault)
6. **Configure Render environment variables**
7. **Test thoroughly** (all authentication flows)
8. **Deploy incrementally** (test with small group first)
9. **Monitor closely** (first 24 hours)
10. **Document for users** (onboarding guide)

---

**Remember:** Security is a journey, not a destination. Start with what works for your current needs, and upgrade as your requirements grow.

For questions about this guide, contact your security team or refer to the example files included in this repository.
