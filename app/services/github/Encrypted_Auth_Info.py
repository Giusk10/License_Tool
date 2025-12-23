"""
Encrypted Credentials Manager.

This module handles the retrieval, decryption, and encryption of sensitive
GitHub credentials (such as Client IDs and Secrets) stored in MongoDB.
It uses Fernet symmetric encryption to ensure data security at rest.
"""

import json
import logging
from typing import Optional, Union

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from cryptography.fernet import Fernet, InvalidToken

from app.utility.config import (
    MONGO_URI,
    DATABASE_NAME,
    COLLECTION_NAME,
    ENCRYPTION_KEY
)

logger = logging.getLogger(__name__)


def decripta_dato_singolo(encrypted_data: Union[str, bytes]) -> str:
    """
    Decrypts a single piece of encrypted data.

    Args:
        encrypted_data (Union[str, bytes]): The encrypted string or bytes sequence.

    Returns:
        str: The decrypted plaintext string. Returns an empty string if
        decryption fails or the input is empty.
    """
    if not encrypted_data:
        return ""

    try:
        fernet = Fernet(ENCRYPTION_KEY)

        # Ensure input is bytes before passing to Fernet
        if isinstance(encrypted_data, str):
            encrypted_bytes = encrypted_data.encode('utf-8')
        else:
            encrypted_bytes = encrypted_data

        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode('utf-8')

    except (InvalidToken, ValueError, TypeError):
        # Log a warning for data issues (corruption, wrong key) without crashing
        logger.warning("Decryption failed: invalid token, wrong key, or corrupted data.")
        return ""


def _parse_json_credential(decrypted_text: str, credential_type: str) -> Optional[str]:
    """
    Helper to extract the specific credential from the decrypted text.

    It handles two storage formats:
    1. JSON Object: {"client_id": "...", "client_secret": "..."}
    2. Raw String: "some-secret-value" (Legacy or simple storage)

    Args:
        decrypted_text (str): The cleartext resulting from decryption.
        credential_type (str): The key to extract ("CLIENT_ID" or "CLIENT_SECRET").

    Returns:
        Optional[str]: The extracted credential value.
    """
    try:
        # Attempt to parse as JSON
        data_json = json.loads(decrypted_text)

        # If it's a dictionary, extract the specific field
        if isinstance(data_json, dict):
            if credential_type == "CLIENT_ID":
                return data_json.get("client_id")
            # Default to client_secret for any other request
            return data_json.get("client_secret")

        # If valid JSON but not a dict, return as string
        return str(data_json)

    except json.JSONDecodeError:
        # Not JSON? Return the raw decrypted text
        return decrypted_text


def github_auth_credentials(credential_type: str) -> Optional[str]:
    """
    Retrieves and decrypts a specific GitHub credential from the database.

    Args:
        credential_type (str): The identifier for the credential to retrieve.
            Typically "CLIENT_ID" or "CLIENT_SECRET".

    Returns:
        Optional[str]: The decrypted credential, or None if not found or if an error occurs.
    """
    try:
        # Use context manager to ensure the connection is closed
        with MongoClient(MONGO_URI) as client:
            db = client[DATABASE_NAME]
            collection = db[COLLECTION_NAME]

            # Find the document by service name (stored key)
            doc = collection.find_one({"service_name": credential_type})

            if not doc:
                return None

            encrypted_value = doc.get('encrypted_data')

            # 1. Decrypt
            decrypted_value = decripta_dato_singolo(encrypted_value)

            if not decrypted_value:
                return None

            # 2. Parse and Extract
            return _parse_json_credential(decrypted_value, credential_type)

    except PyMongoError:
        logger.exception("Database error while retrieving GitHub credentials.")
        return None
    except ValueError:
        logger.exception("Value error while processing GitHub credentials.")
        return None


def cripta_credenziali(plaintext: str) -> str:
    """
    Encrypts a plaintext string using the configured encryption key.

    Args:
        plaintext (str): The raw credential string (ID or Secret) to encrypt.

    Returns:
        str: The encrypted data as a UTF-8 string, ready for storage.

    Raises:
        ValueError: If ENCRYPTION_KEY is not defined in the configuration.
    """
    if not ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY not found in configuration.")

    fernet = Fernet(ENCRYPTION_KEY)

    # Encrypt
    encrypted_bytes = fernet.encrypt(plaintext.encode('utf-8'))

    # Return as string
    return encrypted_bytes.decode('utf-8')
