"""
test: services/github/Encrypted_Auth_Info.py
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet
# Aggiungiamo l'import dell'errore specifico
from pymongo.errors import PyMongoError
from app.services.github.Encrypted_Auth_Info import decripta_dato_singolo, github_auth_credentials, cripta_credenziali


class TestDecriptaDatoSingolo:
    """Test per la funzione decripta_dato_singolo"""

    def test_decripta_dato_singolo_success(self):
        """Test decrittazione riuscita di una stringa"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        original_data = "test_secret_value"
        encrypted_bytes = fernet.encrypt(original_data.encode('utf-8'))
        encrypted_string = encrypted_bytes.decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo(encrypted_string)
            assert result == original_data

    def test_decripta_dato_singolo_invalid_token(self):
        """Test con token non valido (restituisce stringa vuota)"""
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo("invalid_encrypted_data")
            assert result == ""

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
        original_data = "Café € 中文 🔐"
        encrypted_bytes = fernet.encrypt(original_data.encode('utf-8'))
        encrypted_string = encrypted_bytes.decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = decripta_dato_singolo(encrypted_string)
            assert result == original_data


class TestGithubAuthCredentials:
    """Test per la funzione github_auth_credentials"""

    def _setup_mongo_mock(self, mock_mongo_client_cls, find_one_result):
        """Helper per configurare il mock di MongoDB con Context Manager"""
        mock_client_instance = MagicMock()

        # Setup del context manager
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None

        mock_db = MagicMock()
        mock_collection = MagicMock()

        mock_client_instance.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.find_one.return_value = find_one_result

        mock_mongo_client_cls.return_value = mock_client_instance

        return mock_client_instance, mock_db, mock_collection

    def test_github_auth_credentials_client_id_success(self):
        """Test recupero CLIENT_ID con successo"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        client_data = json.dumps({"client_id": "test_client_id_123", "client_secret": "secret"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            _, _, mock_collection = self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": encrypted_data
            })

            result = github_auth_credentials("CLIENT_ID")

            assert result == "test_client_id_123"
            mock_collection.find_one.assert_called_once_with({"service_name": "CLIENT_ID"})

    def test_github_auth_credentials_client_secret_success(self):
        """Test recupero CLIENT_SECRET con successo"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        client_data = json.dumps({"client_id": "id", "client_secret": "test_secret_456"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            _, _, _ = self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_SECRET",
                "encrypted_data": encrypted_data
            })

            result = github_auth_credentials("CLIENT_SECRET")
            assert result == "test_secret_456"

    def test_github_auth_credentials_document_not_found(self):
        """Test quando il documento non viene trovato in MongoDB"""
        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls:
            self._setup_mongo_mock(mock_mongo_cls, None)

            result = github_auth_credentials("CLIENT_ID")
            assert result is None

    def test_github_auth_credentials_connection_error(self):
        """Test gestione errore di connessione a MongoDB"""
        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls:
            # CORREZIONE: Simuliamo l'errore specifico che il codice cattura (PyMongoError)
            # invece di una Exception generica.
            mock_mongo_cls.side_effect = PyMongoError("Connection failed")

            result = github_auth_credentials("CLIENT_ID")
            assert result is None

    def test_github_auth_credentials_decryption_error(self):
        """Test gestione errore durante la decrittazione"""
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": "invalid_encrypted_data"
            })

            result = github_auth_credentials("CLIENT_ID")
            assert result is None

    def test_github_auth_credentials_invalid_json(self):
        """Test gestione JSON non valido nei dati decrittati (ritorna stringa raw)"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        invalid_data = "not a json string"
        encrypted_data = fernet.encrypt(invalid_data.encode('utf-8')).decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": encrypted_data
            })

            result = github_auth_credentials("CLIENT_ID")
            assert result == "not a json string"

    def test_github_auth_credentials_closes_connection_on_success(self):
        """
        Test che il context manager venga usato correttamente.
        """
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)
        client_data = json.dumps({"client_id": "test", "client_secret": "test"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            mock_client, _, _ = self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": encrypted_data
            })

            github_auth_credentials("CLIENT_ID")

            mock_client.__enter__.assert_called_once()
            mock_client.__exit__.assert_called_once()

    def test_github_auth_credentials_uses_correct_database_and_collection(self):
        """Test che vengano usati il database e la collection corretti"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)
        client_data = json.dumps({"client_id": "test", "client_secret": "test"})
        encrypted_data = fernet.encrypt(client_data.encode('utf-8')).decode('utf-8')

        test_db_name = "test_database"
        test_collection_name = "test_collection"

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key), \
                patch("app.services.github.Encrypted_Auth_Info.DATABASE_NAME", test_db_name), \
                patch("app.services.github.Encrypted_Auth_Info.COLLECTION_NAME", test_collection_name):
            mock_client, mock_db, _ = self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": encrypted_data
            })

            github_auth_credentials("CLIENT_ID")

            mock_client.__getitem__.assert_called_once_with(test_db_name)
            mock_db.__getitem__.assert_called_once_with(test_collection_name)

    def test_github_auth_credentials_missing_encrypted_data(self):
        """Test quando il documento esiste ma il campo encrypted_data è None"""
        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls:
            self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": None
            })

            result = github_auth_credentials("CLIENT_ID")
            assert result is None

    def test_github_auth_credentials_decryption_returns_empty(self):
        """Test quando la decrittazione restituisce una stringa vuota"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)
        encrypted_data = fernet.encrypt(b"").decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": encrypted_data
            })

            result = github_auth_credentials("CLIENT_ID")
            assert result is None

    def test_github_auth_credentials_valid_json_not_dict(self):
        """Test quando il JSON è valido ma non è un dizionario (es. lista)"""
        test_key = Fernet.generate_key()
        fernet = Fernet(test_key)

        json_data = json.dumps(["client_id", "secret"])
        encrypted_data = fernet.encrypt(json_data.encode('utf-8')).decode('utf-8')

        with patch("app.services.github.Encrypted_Auth_Info.MongoClient") as mock_mongo_cls, \
                patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            self._setup_mongo_mock(mock_mongo_cls, {
                "service_name": "CLIENT_ID",
                "encrypted_data": encrypted_data
            })

            result = github_auth_credentials("CLIENT_ID")
            assert result == str(["client_id", "secret"])


class TestCriptaCredenziali:
    """Test per la funzione cripta_credenziali"""

    def test_cripta_credenziali_success(self):
        """Test crittografia riuscita di una stringa con chiave patchata"""
        original_data = "test_client_id_123"
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = cripta_credenziali(original_data)

            assert isinstance(result, str)
            assert len(result) > 0

            # Verifica usando LA STESSA chiave
            fernet = Fernet(test_key)
            decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
            assert decrypted == original_data

    def test_cripta_credenziali_empty_string(self):
        """Test crittografia di una stringa vuota"""
        original_data = ""
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = cripta_credenziali(original_data)
            assert isinstance(result, str)

            fernet = Fernet(test_key)
            decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
            assert decrypted == original_data

    def test_cripta_credenziali_special_characters(self):
        original_data = "test@#$%^&*()_+-={}[]|\\:;\"'<>,.?/"
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = cripta_credenziali(original_data)

            fernet = Fernet(test_key)
            decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
            assert decrypted == original_data

    def test_cripta_credenziali_unicode_characters(self):
        original_data = "Café € 中文 🔐"
        test_key = Fernet.generate_key()

        with patch("app.services.github.Encrypted_Auth_Info.ENCRYPTION_KEY", test_key):
            result = cripta_credenziali(original_data)

            fernet = Fernet(test_key)
            decrypted = fernet.decrypt(result.encode('utf-8')).decode('utf-8')
            assert decrypted == original_data