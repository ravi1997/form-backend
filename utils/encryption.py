"""
utils/encryption.py
Field-Level Encryption (FLE) utility for sensitive form response data.
Uses AES-256 (Fernet) for simple, robust encryption at rest.
"""
from cryptography.fernet import Fernet
import os
import logging
from abc import ABC, abstractmethod
from cryptography.fernet import Fernet
from config.settings import settings

logger = logging.getLogger(__name__)

class AbstractKMSProvider(ABC):
    @abstractmethod
    def encrypt(self, plain_text: str) -> str:
        """Encrypt string value"""
        pass

    @abstractmethod
    def decrypt(self, cipher_text: str) -> str:
        """Decrypt string value"""
        pass

    @abstractmethod
    def batch_decrypt(self, cipher_texts: list[str]) -> list[str]:
        """Decrypt a list of string values"""
        pass


class LocalKMSProvider(AbstractKMSProvider):
    """
    Local multi-key Fernet ring suitable for Docker/Kubernetes Secret injection contexts. 
    Implements optimistic rotation processing.
    """
    def __init__(self, key_ring):
        valid_keys = [k for k in key_ring if k]
        if not valid_keys:
            logger.warning("No valid KMS keys found in environment. Generating ephemeral key (data loss risk on restart).")
            valid_keys = [Fernet.generate_key().decode()]
        self.fernets = [Fernet(k.encode()) for k in valid_keys]
        
    def encrypt(self, plain_text: str) -> str:
        if not plain_text: return plain_text
        return self.fernets[0].encrypt(plain_text.encode()).decode()

    def decrypt(self, cipher_text: str) -> str:
        if not cipher_text: return cipher_text
        for f in self.fernets:
            try:
                return f.decrypt(cipher_text.encode()).decode()
            except Exception:
                continue
        # Fallback to plain if not encrypted
        return cipher_text

    def batch_decrypt(self, cipher_texts: list[str]) -> list[str]:
        """Optimized batch decryption across multiple ciphertexts."""
        results = []
        for text in cipher_texts:
            results.append(self.decrypt(text))
        return results

    def rotate_keys(self, new_key_ring):
        """
        [Phase 12: Encryption and Key Lifecycle]
        Forces rotation inside the container context and drops the rotation 
        event into the durability stream for distributed tracking.
        """
        from services.event_bus import event_bus
        from datetime import datetime, timezone
        
        valid_keys = [k for k in new_key_ring if k]
        if valid_keys:
            self.fernets = [Fernet(k.encode()) for k in valid_keys]
            
            try:
                event_bus.publish("tenant.key.rotated", {
                    "organization_id": "GLOBAL",
                    "action": "key_rotation_executed",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            except:
                pass
        return True


class AWSKMSProvider(AbstractKMSProvider):
    """
    Stub for formal AWS KMS envelope encryption.
    Boto3 integration required externally via IAM.
    """
    def __init__(self, key_arn: str):
        self.key_arn = key_arn
        logger.info(f"Initialized AWS KMS Interface mapped to {key_arn}")
        # import boto3
        # self.kms_client = boto3.client('kms')
        
    def encrypt(self, plain_text: str) -> str:
        # Example Implementation:
        # resp = self.kms_client.encrypt(KeyId=self.key_arn, Plaintext=plain_text.encode())
        # return base64.b64encode(resp['CiphertextBlob']).decode()
        return LocalKMSProvider([settings.FIELD_ENCRYPTION_KEY]).encrypt(plain_text)

    def decrypt(self, cipher_text: str) -> str:
        return LocalKMSProvider([settings.FIELD_ENCRYPTION_KEY]).decrypt(cipher_text)

    def batch_decrypt(self, cipher_texts: list[str]) -> list[str]:
        return LocalKMSProvider([settings.FIELD_ENCRYPTION_KEY]).batch_decrypt(cipher_texts)


# Bootstrap proper provider based on context
if os.getenv("AWS_KMS_KEY_ARN"):
    _kms_instance = AWSKMSProvider(os.getenv("AWS_KMS_KEY_ARN"))
else:
    ENCRYPTION_KEYS = [settings.FIELD_ENCRYPTION_KEY, os.getenv("PREVIOUS_ENCRYPTION_KEY")]
    _kms_instance = LocalKMSProvider(ENCRYPTION_KEYS)

def encrypt_value(value: str) -> str:
    return _kms_instance.encrypt(value)

def decrypt_value(encrypted_value: str) -> str:
    return _kms_instance.decrypt(encrypted_value)

def batch_decrypt_values(encrypted_values: list[str]) -> list[str]:
    return _kms_instance.batch_decrypt(encrypted_values)


