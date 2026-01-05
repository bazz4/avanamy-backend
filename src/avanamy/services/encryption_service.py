# src/avanamy/services/encryption_service.py

"""
Encryption service for sensitive data (GitHub tokens, etc.)
"""

import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Service for encrypting/decrypting sensitive data.
    Uses Fernet symmetric encryption.
    """
    
    def __init__(self):
        """Initialize with encryption key from environment."""
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            raise ValueError("ENCRYPTION_KEY environment variable not set")
        
        # Key must be URL-safe base64-encoded 32-byte key
        self.cipher = Fernet(key.encode())
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Encrypted string (base64)
        """
        if not plaintext:
            return ""
        
        encrypted_bytes = self.cipher.encrypt(plaintext.encode())
        return encrypted_bytes.decode()
    
    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt a string.
        
        Args:
            encrypted: Encrypted string (base64)
            
        Returns:
            Decrypted plaintext
        """
        if not encrypted:
            return ""
        
        try:
            decrypted_bytes = self.cipher.decrypt(encrypted.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt: {e}")
            raise ValueError("Failed to decrypt data")


# Global instance
_encryption_service = None


def get_encryption_service() -> EncryptionService:
    """Get global encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service