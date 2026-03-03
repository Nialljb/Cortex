"""
Example: Web Auth + SSH Keys Architecture
This demonstrates the recommended secure approach for deployment
"""

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import os
import tempfile
from datetime import datetime, timedelta

# ============================================================================
# LAYER 1: WEB AUTHENTICATION
# ============================================================================

def init_web_auth():
    """Initialize web application authentication"""
    
    # Load user database (in production, use PostgreSQL)
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
    
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )
    
    return authenticator

def require_web_login(authenticator):
    """Require user to log into web application"""
    
    name, authentication_status, username = authenticator.login('Login', 'main')
    
    if authentication_status == False:
        st.error('❌ Username/password is incorrect')
        st.stop()
    elif authentication_status == None:
        st.warning('👤 Please enter your username and password')
        st.info("""
        **New User?**
        Contact admin to create account.
        
        **Security Note:**
        This is your WEB application login, separate from your HPC credentials.
        """)
        st.stop()
    
    return username

# ============================================================================
# LAYER 2: HPC KEY MANAGEMENT
# ============================================================================

def ssh_key_upload_method(authenticator):
    """Method 1: User uploads their SSH key each session"""
    
    st.sidebar.header("🔐 HPC Connection")
    
    uploaded_key = st.sidebar.file_uploader(
        "Upload SSH Private Key",
        type=["pem", "key", ""],
        help="Upload your ~/.ssh/id_rsa or similar private key file"
    )
    
    if uploaded_key:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.key', mode='wb') as tmp:
            tmp.write(uploaded_key.read())
            tmp_key_path = tmp.name
            os.chmod(tmp_key_path, 0o600)  # Secure permissions
        
        st.sidebar.success("✅ Key uploaded")
        
        # Store in session for cleanup
        if 'temp_keys' not in st.session_state:
            st.session_state.temp_keys = []
        st.session_state.temp_keys.append(tmp_key_path)
        
        return tmp_key_path
    
    return None

def ssh_key_paste_method():
    """Method 2: User pastes their SSH key content"""
    
    st.sidebar.header("🔐 HPC Connection")
    
    key_content = st.sidebar.text_area(
        "Paste SSH Private Key",
        height=150,
        help="Paste the content of your private key file",
        type="password"  # Hide content
    )
    
    if key_content and st.sidebar.button("Use This Key"):
        # Write to temp file
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.key') as tmp:
            tmp.write(key_content)
            tmp_key_path = tmp.name
            os.chmod(tmp_key_path, 0o600)
        
        st.sidebar.success("✅ Key loaded")
        
        if 'temp_keys' not in st.session_state:
            st.session_state.temp_keys = []
        st.session_state.temp_keys.append(tmp_key_path)
        
        return tmp_key_path
    
    return None

def ssh_key_vault_method(web_username):
    """Method 3: Retrieve encrypted key from database (most secure)"""
    
    from cryptography.fernet import Fernet
    import database  # Your DB module
    
    # Get master encryption key from environment
    MASTER_KEY = os.environ.get('SSH_KEY_ENCRYPTION_KEY').encode()
    f = Fernet(MASTER_KEY)
    
    # Retrieve encrypted key from database
    encrypted_key = database.get_user_ssh_key(web_username)
    
    if encrypted_key:
        # Decrypt
        decrypted_key = f.decrypt(encrypted_key).decode()
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.key') as tmp:
            tmp.write(decrypted_key)
            tmp_key_path = tmp.name
            os.chmod(tmp_key_path, 0o600)
        
        st.sidebar.success("✅ Using stored SSH key")
        
        if 'temp_keys' not in st.session_state:
            st.session_state.temp_keys = []
        st.session_state.temp_keys.append(tmp_key_path)
        
        return tmp_key_path
    else:
        st.sidebar.info("📤 Please upload your SSH key (one-time setup)")
        return ssh_key_upload_method(None)

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def cleanup_temp_keys():
    """Delete temporary key files on session end"""
    if 'temp_keys' in st.session_state:
        for key_path in st.session_state.temp_keys:
            try:
                if os.path.exists(key_path):
                    os.unlink(key_path)
            except:
                pass
        st.session_state.temp_keys = []

def check_session_timeout(timeout_minutes=30):
    """Auto-logout after inactivity"""
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = datetime.now()
    
    time_elapsed = datetime.now() - st.session_state.last_activity
    
    if time_elapsed > timedelta(minutes=timeout_minutes):
        # Cleanup
        cleanup_temp_keys()
        if st.session_state.get('client'):
            st.session_state.client.close()
        
        # Reset session
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        
        st.warning("⏱️ Session expired due to inactivity")
        st.rerun()
    
    # Update activity timestamp
    st.session_state.last_activity = datetime.now()

# ============================================================================
# MAIN APPLICATION FLOW
# ============================================================================

def main():
    st.set_page_config(page_title="Secure HPC Manager", page_icon="🔐")
    
    # Initialize web authentication
    authenticator = init_web_auth()
    
    # LAYER 1: Require web login
    web_username = require_web_login(authenticator)
    
    # User is authenticated to WEB APP
    st.sidebar.success(f"👤 Logged in as: {web_username}")
    
    # Check session timeout
    check_session_timeout(timeout_minutes=30)
    
    # Add logout button
    if st.sidebar.button("Logout from Web App"):
        cleanup_temp_keys()
        if st.session_state.get('client'):
            st.session_state.client.close()
        authenticator.logout('Logout', 'sidebar')
        st.rerun()
    
    st.sidebar.divider()
    
    # LAYER 2: HPC Connection with SSH Key
    if not st.session_state.get('hpc_connected'):
        st.title("🔐 Connect to HPC Cluster")
        
        st.info("""
        **Two-Factor Security:**
        1. ✅ You're logged into the web app (Layer 1)
        2. 🔑 Now provide your SSH key for HPC access (Layer 2)
        """)
        
        # Choose method for SSH key
        key_method = st.radio(
            "How do you want to provide your SSH key?",
            [
                "Upload key file",
                "Paste key content", 
                "Use stored key (if previously saved)"
            ]
        )
        
        key_path = None
        
        if key_method == "Upload key file":
            key_path = ssh_key_upload_method(authenticator)
        elif key_method == "Paste key content":
            key_path = ssh_key_paste_method()
        else:
            key_path = ssh_key_vault_method(web_username)
        
        if key_path:
            # Get HPC connection details
            ALLOWED_HOSTS = ["login1.nan.kcl.ac.uk", "login2.nan.kcl.ac.uk"]
            hostname = st.selectbox("HPC Cluster", ALLOWED_HOSTS)
            hpc_username = st.text_input(
                "HPC Username",
                help="This may be different from your web app username"
            )
            
            if st.button("Connect to HPC Cluster"):
                try:
                    from hpc_client_ssh import HPCSSHClient
                    
                    with st.spinner("Connecting to HPC..."):
                        client = HPCSSHClient(hostname, hpc_username, key_path=key_path)
                        
                        st.session_state.client = client
                        st.session_state.hpc_connected = True
                        st.session_state.hostname = hostname
                        st.session_state.hpc_username = hpc_username
                    
                    st.success(f"✅ Connected to {hostname} as {hpc_username}")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Connection failed: {e}")
                    # Clean up failed key
                    if key_path and os.path.exists(key_path):
                        os.unlink(key_path)
    
    else:
        # User is connected to both web app AND HPC
        st.title("🎯 HPC Job Manager")
        st.success(f"""
        **Connected:**
        - Web User: {web_username}
        - HPC: {st.session_state.hpc_username}@{st.session_state.hostname}
        """)
        
        if st.sidebar.button("Disconnect from HPC"):
            cleanup_temp_keys()
            st.session_state.client.close()
            st.session_state.hpc_connected = False
            st.rerun()
        
        # Your existing HPC management interface here...
        st.info("Your HPC management interface goes here...")

if __name__ == "__main__":
    main()
