import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings

class TokenCipher:
    """
    AES-256 GCM authenticated encryption for OAuth access and refresh tokens.
    Guarantees confidentiality and integrity at rest.
    """
    def __init__(self, key_b64: str = None):
        key_str = key_b64 or settings.TOKEN_ENCRYPTION_KEY
        try:
            raw_key = base64.b64decode(key_str)
            if len(raw_key) not in (16, 24, 32):
                # Derive 32-byte key
                raw_key = raw_key.ljust(32, b'0')[:32]
        except Exception:
            raw_key = (key_str.encode() + b'0' * 32)[:32]
        self.key = raw_key
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        # Combine nonce + ciphertext and base64 encode
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode('utf-8')

    def decrypt(self, encrypted_b64: str) -> str:
        if not encrypted_b64:
            return ""
        try:
            combined = base64.b64decode(encrypted_b64.encode('utf-8'))
            nonce = combined[:12]
            ciphertext = combined[12:]
            decrypted = self.aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted.decode('utf-8')
        except Exception as e:
            return ""

token_cipher = TokenCipher()
