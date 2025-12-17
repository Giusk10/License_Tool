import json
from pymongo import MongoClient
from cryptography.fernet import Fernet
# Assicurati che questi import funzionino nel tuo progetto
from app.utility.config import MONGO_URI, DATABASE_NAME, COLLECTION_NAME, ENCRYPTION_KEY

def decripta_dato_singolo(encrypted_data_string):
    """Decrittografa una singola stringa crittografata."""
    if not encrypted_data_string: return ""

    try:
        fernet = Fernet(ENCRYPTION_KEY)
        # Assicuriamoci che sia bytes
        if isinstance(encrypted_data_string, str):
            encrypted_bytes = encrypted_data_string.encode('utf-8')
        else:
            encrypted_bytes = encrypted_data_string

        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        return None

def github_auth_credentials(client_cred: str) -> str | None:
    client = None
    try:
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]

        # Recupera il documento
        doc_id = collection.find_one({"service_name": client_cred})

        if not doc_id:
            return None

        client_credential_cifrato = doc_id.get('encrypted_data')

        # 1. Decifra
        client_credential = decripta_dato_singolo(client_credential_cifrato)

        if not client_credential:
            return None

        # 2. Logica di estrazione intelligente
        try:
            # Proviamo a vedere se è un JSON (es. {"client_id": "xyz"})
            data_json = json.loads(client_credential)

            # Se è un dizionario, estraiamo la chiave
            if isinstance(data_json, dict):
                if client_cred == "CLIENT_ID":
                    return data_json.get("client_id")
                else:
                    return data_json.get("client_secret")
            else:
                return str(data_json)

        except json.JSONDecodeError:
            return client_credential

    except Exception as e:
        return None
    finally:
        if client:
            client.close()

def cripta_credenziali(client_id: str) -> str:
    """
    Prende ID e Secret, crea un JSON, lo cripta e restituisce la stringa cifrata.
    """
    key = "XwbBr7IVVPr0d8kBA48pvzSzX1vVQbaZNzvuu5EZTvE="

    if not key:
        raise ValueError("ENCRYPTION_KEY not found in .env file")

    fernet = Fernet(key)

    # 3. Criptiamo
    encrypted_bytes = fernet.encrypt(client_id.encode('utf-8'))

    # 4. Ritorniamo la stringa (da salvare su Mongo)
    return encrypted_bytes.decode('utf-8')