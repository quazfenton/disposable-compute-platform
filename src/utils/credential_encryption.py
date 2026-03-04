"""
Credential Encryption for secure storage of sensitive data
Uses Fernet symmetric encryption for credential protection
"""
import os
import json
import logging
import base64
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class CredentialEncryption:
    """Encrypts and decrypts credentials securely"""
    
    def __init__(self, key: Optional[bytes] = None, key_file: Optional[str] = None):
        """
        Initialize credential encryption
        
        Args:
            key: Encryption key (bytes). If None, will load from key_file or generate new
            key_file: Path to key file. If None and key is None, will use default path
        """
        self.key = key
        self.key_file = key_file or os.path.join(
            os.getenv("STORAGE_PATH", "/tmp/disposable-storage"),
            ".credential_key"
        )
        
        # Load or generate key
        if self.key is None:
            self.key = self._load_or_generate_key()
        
        # Initialize Fernet
        self.fernet = Fernet(self.key)
        
        logger.info("CredentialEncryption initialized")
    
    def _load_or_generate_key(self) -> bytes:
        """Load existing key or generate new one"""
        key_path = Path(self.key_file)
        
        # Try to load existing key
        if key_path.exists():
            try:
                with open(key_path, 'rb') as f:
                    key = f.read()
                logger.info(f"Loaded encryption key from {key_path}")
                return key
            except Exception as e:
                logger.error(f"Failed to load key: {e}")
        
        # Generate new key
        key = Fernet.generate_key()
        
        # Save key with restrictive permissions
        try:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write with restrictive permissions (owner read/write only)
            fd = os.open(key_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(key)
            
            logger.info(f"Generated new encryption key at {key_path}")
            
        except Exception as e:
            logger.error(f"Failed to save key: {e}")
            # In development, this is okay - key will be regenerated each run
        
        return key
    
    def encrypt(self, data: Dict[str, Any]) -> str:
        """
        Encrypt credential data
        
        Args:
            data: Dictionary of credential data to encrypt
            
        Returns:
            Encrypted data as base64 string
        """
        try:
            # Add metadata
            data_with_meta = {
                'data': data,
                'encrypted_at': datetime.utcnow().isoformat(),
                'version': '1.0'
            }
            
            # Serialize to JSON
            json_data = json.dumps(data_with_meta).encode('utf-8')
            
            # Encrypt
            encrypted = self.fernet.encrypt(json_data)
            
            # Return as base64 string
            return base64.b64encode(encrypted).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to encrypt credential: {e}")
            raise
    
    def decrypt(self, encrypted_data: str) -> Dict[str, Any]:
        """
        Decrypt credential data
        
        Args:
            encrypted_data: Base64 encoded encrypted data
            
        Returns:
            Decrypted credential data dictionary
        """
        try:
            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_data)
            
            # Decrypt
            decrypted = self.fernet.decrypt(encrypted_bytes)
            
            # Parse JSON
            data_with_meta = json.loads(decrypted.decode('utf-8'))
            
            # Validate version
            version = data_with_meta.get('version', '1.0')
            if version != '1.0':
                logger.warning(f"Unknown encryption version: {version}")
            
            return data_with_meta.get('data', {})
            
        except Exception as e:
            logger.error(f"Failed to decrypt credential: {e}")
            raise
    
    def encrypt_string(self, value: str) -> str:
        """Encrypt a string value"""
        # self.encrypt returns a base64 encoded string
        return self.encrypt({'value': value})
    
    def decrypt_string(self, encrypted_value: str) -> str:
        """Decrypt a string value"""
        # self.decrypt returns the original dictionary
        return self.decrypt(encrypted_value).get('value', '')
    
    def encrypt_password(self, password: str, salt: Optional[str] = None) -> Dict[str, str]:
        """
        Encrypt a password with optional salt
        
        Returns:
            Dictionary with encrypted_password and salt
        """
        import secrets
        
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Combine password with salt
        salted_password = f"{salt}:{password}"
        
        # Encrypt
        encrypted = self.encrypt({'password': salted_password})
        
        return {
            'encrypted_password': encrypted,
            'salt': salt
        }
    
    def decrypt_password(self, encrypted_password: str, salt: str) -> str:
        """Decrypt a password with salt"""
        try:
            decrypted = self.decrypt({'password': encrypted_password})
            salted_password = decrypted.get('password', '')
            
            # Verify salt
            expected_salt = salted_password.split(':')[0]
            if expected_salt != salt:
                logger.error("Salt mismatch during password decryption")
                raise ValueError("Salt mismatch")
            
            # Extract password
            password = salted_password.split(':', 1)[1]
            return password
            
        except Exception as e:
            logger.error(f"Failed to decrypt password: {e}")
            raise


class SecureCredentialStore:
    """Secure store for credentials with encryption and TTL"""
    
    def __init__(self, storage_path: str, encryption: CredentialEncryption = None):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.encryption = encryption or CredentialEncryption()
        
        # In-memory cache of credentials
        self._credentials: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"SecureCredentialStore initialized at {storage_path}")
    
    def _credential_file(self, credential_id: str) -> Path:
        """Get path to credential file"""
        # Sanitize credential_id to prevent path traversal
        safe_id = credential_id.replace('/', '_').replace('\\', '_').replace('..', '_')
        return self.storage_path / f"{safe_id}.cred"
    
    def store_credential(
        self,
        credential_id: str,
        credential_data: Dict[str, Any],
        ttl_minutes: Optional[int] = None
    ) -> str:
        """
        Store encrypted credential
        
        Args:
            credential_id: Unique identifier for credential
            credential_data: Dictionary of credential data
            ttl_minutes: Time-to-live in minutes (optional)
            
        Returns:
            credential_id
        """
        try:
            # Add TTL if specified
            if ttl_minutes:
                credential_data['expires_at'] = (
                    datetime.utcnow() + timedelta(minutes=ttl_minutes)
                ).isoformat()
            
            # Encrypt credential data
            encrypted = self.encryption.encrypt(credential_data)
            
            # Create credential record
            credential = {
                'id': credential_id,
                'encrypted_data': encrypted,
                'created_at': datetime.utcnow().isoformat(),
                'ttl_minutes': ttl_minutes
            }
            
            # Save to file
            cred_file = self._credential_file(credential_id)
            
            # Write with restrictive permissions
            fd = os.open(cred_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                json.dump(credential, f)
            
            # Cache in memory
            self._credentials[credential_id] = credential
            
            logger.info(f"Stored credential {credential_id}")
            
            return credential_id
            
        except Exception as e:
            logger.error(f"Failed to store credential: {e}")
            raise
    
    def retrieve_credential(self, credential_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve and decrypt credential
        
        Args:
            credential_id: Credential identifier
            
        Returns:
            Decrypted credential data or None if not found/expired
        """
        try:
            # Check cache first
            if credential_id in self._credentials:
                credential = self._credentials[credential_id]
                
                # Check expiration
                if 'expires_at' in credential.get('encrypted_data', {}):
                    expires_at = datetime.fromisoformat(credential['expires_at'])
                    if datetime.utcnow() > expires_at:
                        logger.info(f"Credential {credential_id} expired")
                        self.delete_credential(credential_id)
                        return None
                
                # Decrypt and return
                encrypted_data = credential['encrypted_data']
                return self.encryption.decrypt(encrypted_data)
            
            # Load from file
            cred_file = self._credential_file(credential_id)
            
            if not cred_file.exists():
                logger.info(f"Credential {credential_id} not found")
                return None
            
            with open(cred_file, 'r') as f:
                credential = json.load(f)
            
            # Check expiration
            expires_at_str = credential.get('expires_at')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.utcnow() > expires_at:
                    logger.info(f"Credential {credential_id} expired")
                    self.delete_credential(credential_id)
                    return None
            
            # Decrypt and return
            encrypted_data = credential['encrypted_data']
            decrypted = self.encryption.decrypt(encrypted_data)
            
            # Cache for next time
            self._credentials[credential_id] = credential
            
            return decrypted
            
        except Exception as e:
            logger.error(f"Failed to retrieve credential: {e}")
            return None
    
    def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential"""
        try:
            # Remove from cache
            if credential_id in self._credentials:
                del self._credentials[credential_id]
            
            # Remove from disk
            cred_file = self._credential_file(credential_id)
            
            if cred_file.exists():
                cred_file.unlink()
                logger.info(f"Deleted credential {credential_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete credential: {e}")
            return False
    
    def list_credentials(self) -> list:
        """List all credential IDs"""
        credentials = []
        
        for cred_file in self.storage_path.glob("*.cred"):
            credential_id = cred_file.stem
            credentials.append(credential_id)
        
        return credentials
    
    def cleanup_expired(self) -> int:
        """Clean up expired credentials"""
        cleaned = 0
        
        for credential_id in self.list_credentials():
            credential = self.retrieve_credential(credential_id)
            if credential is None:
                # Either expired or error - already deleted if expired
                cleaned += 1
        
        return cleaned


# Global credential encryption instance
_credential_encryption: Optional[CredentialEncryption] = None


def get_credential_encryption() -> CredentialEncryption:
    """Get global credential encryption instance"""
    global _credential_encryption
    if _credential_encryption is None:
        _credential_encryption = CredentialEncryption()
    return _credential_encryption


def init_credential_encryption(key: Optional[bytes] = None, key_file: Optional[str] = None) -> CredentialEncryption:
    """Initialize global credential encryption"""
    global _credential_encryption
    _credential_encryption = CredentialEncryption(key, key_file)
    return _credential_encryption
