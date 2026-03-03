"""
Database setup for storing encrypted SSH keys (Optional - Most Secure Method)
Use this if you want to store users' SSH keys securely in a database
"""

from sqlalchemy import create_engine, Column, Integer, String, LargeBinary, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from cryptography.fernet import Fernet
import os

Base = declarative_base()

# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(Base):
    """Web application user with encrypted SSH key storage"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    web_username = Column(String(100), unique=True, nullable=False)
    web_password_hash = Column(String(255), nullable=False)  # bcrypt hash
    email = Column(String(255), unique=True)
    
    # HPC credentials
    hpc_username = Column(String(100))
    encrypted_ssh_private_key = Column(LargeBinary)  # Encrypted SSH key
    ssh_key_uploaded_at = Column(DateTime)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)

# ============================================================================
# DATABASE CONNECTION (Use Render PostgreSQL)
# ============================================================================

def get_database_engine():
    """
    Get database connection.
    In Render, set DATABASE_URL environment variable to your PostgreSQL URL
    """
    database_url = os.environ.get(
        'DATABASE_URL',
        'postgresql://user:password@localhost:5432/hpc_manager'
    )
    
    return create_engine(database_url)

def init_database():
    """Initialize database tables"""
    engine = get_database_engine()
    Base.metadata.create_all(engine)
    print("✅ Database tables created")

# ============================================================================
# KEY ENCRYPTION/DECRYPTION
# ============================================================================

def get_encryption_key():
    """
    Get master encryption key from environment.
    Generate with: from cryptography.fernet import Fernet; Fernet.generate_key()
    Store in Render environment variables as: SSH_KEY_ENCRYPTION_KEY
    """
    key = os.environ.get('SSH_KEY_ENCRYPTION_KEY')
    if not key:
        raise ValueError("SSH_KEY_ENCRYPTION_KEY not set in environment!")
    return key.encode()

def encrypt_ssh_key(private_key_content: str) -> bytes:
    """Encrypt SSH private key for storage"""
    f = Fernet(get_encryption_key())
    return f.encrypt(private_key_content.encode())

def decrypt_ssh_key(encrypted_key: bytes) -> str:
    """Decrypt SSH private key for use"""
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted_key).decode()

# ============================================================================
# USER SSH KEY MANAGEMENT
# ============================================================================

def save_user_ssh_key(web_username: str, private_key_content: str, hpc_username: str = None):
    """
    Save encrypted SSH key for a user.
    
    Args:
        web_username: Web app username
        private_key_content: SSH private key content (plain text)
        hpc_username: Optional HPC username
    """
    engine = get_database_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Find user
        user = session.query(User).filter_by(web_username=web_username).first()
        if not user:
            raise ValueError(f"User {web_username} not found")
        
        # Encrypt key
        encrypted_key = encrypt_ssh_key(private_key_content)
        
        # Update user record
        user.encrypted_ssh_private_key = encrypted_key
        user.ssh_key_uploaded_at = datetime.utcnow()
        if hpc_username:
            user.hpc_username = hpc_username
        
        session.commit()
        print(f"✅ SSH key saved for {web_username}")
        
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_user_ssh_key(web_username: str) -> tuple:
    """
    Retrieve and decrypt user's SSH key.
    
    Returns:
        tuple: (decrypted_key_content, hpc_username) or (None, None)
    """
    engine = get_database_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        user = session.query(User).filter_by(web_username=web_username).first()
        
        if not user or not user.encrypted_ssh_private_key:
            return None, None
        
        # Decrypt key
        decrypted_key = decrypt_ssh_key(user.encrypted_ssh_private_key)
        
        return decrypted_key, user.hpc_username
        
    finally:
        session.close()

def delete_user_ssh_key(web_username: str):
    """Delete stored SSH key for security"""
    engine = get_database_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        user = session.query(User).filter_by(web_username=web_username).first()
        if user:
            user.encrypted_ssh_private_key = None
            user.ssh_key_uploaded_at = None
            session.commit()
            print(f"✅ SSH key deleted for {web_username}")
    finally:
        session.close()

# ============================================================================
# EXAMPLE USAGE IN STREAMLIT
# ============================================================================

def streamlit_key_vault_integration():
    """Example of how to integrate with Streamlit app"""
    import streamlit as st
    import tempfile
    
    # After web authentication succeeds...
    web_username = st.session_state.get('web_username')
    
    # Check if user has stored key
    stored_key, hpc_username = get_user_ssh_key(web_username)
    
    if stored_key:
        st.success("✅ Using your stored SSH key")
        
        # Write to temp file for SSH client
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.key') as tmp:
            tmp.write(stored_key)
            tmp_key_path = tmp.name
            os.chmod(tmp_key_path, 0o600)
        
        # Use with HPC client
        from hpc_client_ssh import HPCSSHClient
        client = HPCSSHClient('login.hpc.edu', hpc_username, key_path=tmp_key_path)
        
        # Remember to clean up
        os.unlink(tmp_key_path)
        
    else:
        st.info("Upload your SSH key (one-time setup)")
        
        uploaded_key = st.file_uploader("SSH Private Key", type=["pem", "key"])
        hpc_user = st.text_input("HPC Username")
        
        if uploaded_key and hpc_user and st.button("Save Key"):
            key_content = uploaded_key.read().decode()
            save_user_ssh_key(web_username, key_content, hpc_user)
            st.success("✅ Key saved! Refresh to use it.")
            st.rerun()

# ============================================================================
# SETUP INSTRUCTIONS
# ============================================================================

if __name__ == "__main__":
    print("""
    🔐 Database Setup for Secure SSH Key Storage
    
    1. Generate encryption key:
       python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    
    2. Set environment variable in Render:
       SSH_KEY_ENCRYPTION_KEY=<generated_key>
    
    3. Set Render PostgreSQL URL:
       DATABASE_URL=<from_render_dashboard>
    
    4. Initialize database:
       python database_setup_example.py --init
    
    5. Add to requirements.txt:
       sqlalchemy
       psycopg2-binary
       cryptography
    """)
    
    import sys
    if '--init' in sys.argv:
        init_database()
