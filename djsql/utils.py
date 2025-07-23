import os
from cryptography.fernet import Fernet
import logging
from django.conf import settings # Import settings to access BASE_DIR

logger = logging.getLogger(__name__)

# Define the path for the encryption key file
KEY_FILE_PATH = settings.BASE_DIR / '.encryption_key'

# Load the encryption key
ENCRYPTION_KEY = os.environ.get('MY_ENC_KEY')

if not ENCRYPTION_KEY:
    if KEY_FILE_PATH.exists():
        try:
            with open(KEY_FILE_PATH, 'rb') as key_file:
                ENCRYPTION_KEY = key_file.read().decode()
            logger.info(f"Encryption key loaded from {KEY_FILE_PATH}")
        except Exception as e:
            logger.error(f"Failed to read encryption key from {KEY_FILE_PATH}: {e}")
            ENCRYPTION_KEY = None # Fallback to generating if read fails
    
    if not ENCRYPTION_KEY:
        logger.warning("MY_ENC_KEY environment variable not set and key file not found. Generating a new key for development. DO NOT USE IN PRODUCTION!")
        ENCRYPTION_KEY = Fernet.generate_key().decode()
        try:
            with open(KEY_FILE_PATH, 'wb') as key_file:
                key_file.write(ENCRYPTION_KEY.encode())
            logger.info(f"New encryption key generated and saved to {KEY_FILE_PATH}")
        except Exception as e:
            logger.error(f"Failed to save generated encryption key to {KEY_FILE_PATH}: {e}")
            # If saving fails, the key will still be used in memory for this session,
            # but a new one will be generated next time if not set in env.

try:
    if ENCRYPTION_KEY:
        cipher_suite = Fernet(ENCRYPTION_KEY.encode())
    else:
        cipher_suite = None
        logger.error("No encryption key available. Cipher suite not initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Fernet cipher suite with provided or generated key: {e}")
    cipher_suite = None # Ensure cipher_suite is None if initialization fails

def encrypt_data(data):
    if not cipher_suite:
        logger.error("Cipher suite not initialized. Cannot encrypt data.")
        return data # Return original data or raise an error
    if not data:
        return ""
    try:
        encrypted_data = cipher_suite.encrypt(data.encode()).decode()
        return encrypted_data
    except Exception as e:
        logger.error(f"Error encrypting data: {e}")
        return data # Return original data or raise an error

def decrypt_data(encrypted_data):
    if not cipher_suite:
        logger.error("Cipher suite not initialized. Cannot decrypt data.")
        return encrypted_data # Return original data or raise an error
    if not encrypted_data:
        return ""

    # Check if data looks like it's already encrypted (Fernet tokens are base64 and have specific format)
    # Fernet tokens are always base64 encoded and have a specific structure
    try:
        # Try to decode as base64 first - if this fails, it's likely plain text
        import base64
        base64.urlsafe_b64decode(encrypted_data.encode())

        # If base64 decode succeeds, try Fernet decryption
        decrypted_data = cipher_suite.decrypt(encrypted_data.encode()).decode()
        return decrypted_data
    except Exception as e:
        # If decryption fails, it's likely plain text - return as is
        # Only log as debug to avoid spam, since this is expected for plain text passwords
        logger.debug(f"Data appears to be plain text (decryption failed): {str(e)[:50]}...")
        return encrypted_data # Return original data (likely plain text)
