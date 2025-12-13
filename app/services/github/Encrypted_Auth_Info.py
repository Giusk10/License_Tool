import json
from pymongo import MongoClient
from cryptography.fernet import Fernet
from app.utility.config import MONGO_URI, DATABASE_NAME, COLLECTION_NAME, ENCRYPTION_KEY

def decripta_dato_singolo(encrypted_data_string):
    """Decrittografa una singola stringa crittografata."""
    fernet = Fernet(ENCRYPTION_KEY)
    encrypted_bytes = encrypted_data_string.encode('utf-8')
    decrypted_bytes = fernet.decrypt(encrypted_bytes)
    return decrypted_bytes.decode('utf-8')

def github_auth_credentials(client_cred : str) -> str | None:

    client = None
    try:
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]

        # Recupera il CLIENT_ID o CLIENT_SECRET
        doc_id = collection.find_one({"service_name": client_cred})
        if not doc_id: return None
        client_credential_cifrato = doc_id['encrypted_data']
        client_credential = decripta_dato_singolo(client_credential_cifrato)
        cred = json.loads(client_credential).get("client_id") if client_cred == "CLIENT_ID" else json.loads(client_credential).get("client_secret")

        return cred

    except Exception as e:
        print(f"Errore durante il recupero: {e}")
        return None
    finally:
        if client:
            client.close()
