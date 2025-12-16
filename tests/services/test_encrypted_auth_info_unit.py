"""
test: services/github/Encrypted_Auth_Info.py
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet
from app.services.github.Encrypted_Auth_Info import decripta_dato_singolo, github_auth_credentials, cripta_credenziali


class TestDecriptaDatoSingolo:
    """Test per la funzione decripta_dato_singolo"""

    def test_decripta_dato_singolo_success(self):
        """Test decrittazione riuscita di una stringa"""
        # Genera una chiave di test
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        # Crittografa un dato di test
        original_data = "test_secret_value"
        encrypted_bytes = fernet.encrypt(original_data.encode('utf-8'))
        encrypted_string = encrypted_bytes.decode('utf-8')

        # Mock della chiave di encryption
        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo(encrypted_string)

            # Verifica il risultato
            assert result == original_data

    def test_decripta_dato_singolo_invalid_token(self):
        """Test con token non valido (restituisce None)"""
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo("invalid_encrypted_data")
            assert result is None

    def test_decripta_dato_singolo_empty_string(self):
        """Test con stringa vuota"""
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo("")
            assert result == ""

    def test_decripta_dato_singolo_special_characters(self):
        """Test decrittazione con caratteri speciali"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        # Dato con caratteri speciali
        original_data = "test@#$%^&*()_+-={}[]|\\:;\"'<>,.?/"
        encrypted_bytes = fernet.encrypt(original_data.encode('utf-8'))
        encrypted_string = encrypted_bytes.decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo(encrypted_string)
            assert result == original_data

    def test_decripta_dato_singolo_unicode_characters(self):
        """Test decrittazione con caratteri unicode"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        # Dato con caratteri unicode
        original_data = "Café € 中文 🔐"
        encrypted_bytes = fernet.encrypt(original_data.encode('utf-8'))
        encrypted_string = encrypted_bytes.decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo(encrypted_string)
            assert result == original_data


class TestGithubAuthCredentials:
    """Test per la funzione github_auth_credentials"""

    def test_github_auth_credentials_client_id_success(self):
        """Test recupero CLIENT_ID con successo"""
        # Prepara dati di test
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        client_data = json.dumps({"client_id": "test_client_id_123", "client_secret": "secret"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        # Mock della collection MongoDB
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": encrypted_data
        }

        # Mock del client MongoDB
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            result = github_auth_credentials("CLIENT_ID")

            # Verifica il risultato
            assert result == "test_client_id_123"
            mock_collection.find_one.assert_called_once_with({"service_name": "CLIENT_ID"})
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_client_secret_success(self):
        """Test recupero CLIENT_SECRET con successo"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        client_data = json.dumps({"client_id": "id", "client_secret": "test_secret_456"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_SECRET",
            "encrypted_data": encrypted_data
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            result = github_auth_credentials("CLIENT_SECRET")

            assert result == "test_secret_456"
            mock_collection.find_one.assert_called_once_with({"service_name": "CLIENT_SECRET"})
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_document_not_found(self):
        """Test quando il documento non viene trovato in MongoDB"""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client):
            result = github_auth_credentials("CLIENT_ID")

            assert result is None
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_connection_error(self):
        """Test gestione errore di connessione a MongoDB"""
        mock_client = MagicMock()
        mock_client.__getitem__.side_effect = Exception("Connection failed")

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client):
            result = github_auth_credentials("CLIENT_ID")

            assert result is None
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_decryption_error(self):
        """Test gestione errore durante la decrittazione"""
        test_key = Fernet.generate_key()

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": "invalid_encrypted_data"
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            result = github_auth_credentials("CLIENT_ID")

            assert result is None
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_invalid_json(self):
        """Test gestione JSON non valido nei dati decrittati"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        # Crittografa una stringa che non è JSON valido
        invalid_data = "not a json string"
        encrypted_data = fernet.encrypt(invalid_data.encode('utf-8')).decode('utf-8')

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": encrypted_data
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            result = github_auth_credentials("CLIENT_ID")

            assert result == "not a json string"
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_missing_key_in_json(self):
        """Test quando il JSON non contiene la chiave richiesta"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        # JSON senza client_id o client_secret
        client_data = json.dumps({"other_field": "value"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": encrypted_data
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            result = github_auth_credentials("CLIENT_ID")

            # get() restituisce None se la chiave non esiste
            assert result is None

    def test_github_auth_credentials_closes_connection_on_success(self):
        """Test che la connessione MongoDB venga chiusa anche in caso di successo"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        client_data = json.dumps({"client_id": "test_id", "client_secret": "secret"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": encrypted_data
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            github_auth_credentials("CLIENT_ID")

            # Verifica che close() sia stato chiamato
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_uses_correct_database_and_collection(self):
        """Test che vengano usati il database e la collection corretti"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        client_data = json.dumps({"client_id": "test_id", "client_secret": "secret"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": encrypted_data
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        test_db_name = "test_database"
        test_collection_name = "test_collection"

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key), \
                patch("app.services.github.Encrypted_Auth_Info.DATABASE_NAME", test_db_name), \
                patch("app.services.github.Encrypted_Auth_Info.COLLECTION_NAME", test_collection_name):

            github_auth_credentials("CLIENT_ID")

            # Verifica che il database e la collection corretti siano stati accessati
            mock_client.__getitem__.assert_called_once_with(test_db_name)
            mock_db.__getitem__.assert_called_once_with(test_collection_name)

    def test_github_auth_credentials_missing_encrypted_data(self):
        """Test quando il documento esiste ma manca la chiave 'encrypted_data'"""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID"
            # encrypted_data mancante
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client):
            result = github_auth_credentials("CLIENT_ID")

            assert result is None
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_decryption_returns_empty(self):
        """Test quando la decrittazione restituisce una stringa vuota"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        # Crittografa una stringa vuota
        empty_data = ""
        encrypted_data = fernet.encrypt(empty_data.encode('utf-8')).decode('utf-8')

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": encrypted_data
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            result = github_auth_credentials("CLIENT_ID")

            assert result is None
            mock_client.close.assert_called_once()

    def test_github_auth_credentials_valid_json_not_dict(self):
        """Test quando il JSON è valido ma non è un dizionario (es. lista)"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        # JSON valido ma lista
        json_data = json.dumps(["client_id", "secret"])
        encrypted_data = fernet.encrypt(json_data.encode('utf-8')).decode('utf-8')

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "service_name": "CLIENT_ID",
            "encrypted_data": encrypted_data
        }

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.close = MagicMock()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient", return_value=mock_client), \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):

            result = github_auth_credentials("CLIENT_ID")

            assert result == str(["client_id", "secret"])
            mock_client.close.assert_called_once()


class TestCriptaCredenziali:
    """Test per la funzione cripta_credenziali"""

    def test_cripta_credenziali_success(self):
        """Test crittografia riuscita di una stringa"""
        original_data = "test_client_id_123"

        result = cripta_credenziali(original_data)

        # Verifica che restituisca una stringa
        assert isinstance(result, str)
        assert len(result) > 0

        # Verifica che possa essere decrittata con la stessa chiave
        key = "XwbBr7IVVPr0d8kBA48pvzSzX1vVQbaZNzvuu5EZTvE="
        fernet = Fernet(key)
        decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
        assert decrypted == original_data

    def test_cripta_credenziali_empty_string(self):
        """Test crittografia di una stringa vuota"""
        original_data = ""

        result = cripta_credenziali(original_data)

        assert isinstance(result, str)

        # Decrittazione
        key = "XwbBr7IVVPr0d8kBA48pvzSzX1vVQbaZNzvuu5EZTvE="
        fernet = Fernet(key)
        decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
        assert decrypted == original_data

    def test_cripta_credenziali_special_characters(self):
        """Test crittografia con caratteri speciali"""
        original_data = "test@#$%^&*()_+-={}[]|\\:;\"'<>,.?/"

        result = cripta_credenziali(original_data)

        assert isinstance(result, str)

        # Decrittazione
        key = "XwbBr7IVVPr0d8kBA48pvzSzX1vVQbaZNzvuu5EZTvE="
        fernet = Fernet(key)
        decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
        assert decrypted == original_data

    def test_cripta_credenziali_unicode_characters(self):
        """Test crittografia con caratteri unicode"""
        original_data = "Café € 中文 🔐"

        result = cripta_credenziali(original_data)

        assert isinstance(result, str)

        # Decrittazione
        key = "XwbBr7IVVPr0d8kBA48pvzSzX1vVQbaZNzvuu5EZTvE="
        fernet = Fernet(key)
        decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
        assert decrypted == original_data

