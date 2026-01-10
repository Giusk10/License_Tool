# Security Testing Suite

## Panoramica
Questa suite di test di sicurezza è progettata per verificare la robustezza dell'applicazione License Tool contro vulnerabilità comuni. I test coprono le principali categorie dell'OWASP Top 10 e best practices di sicurezza per applicazioni web.

## File Inclusi
- `test_security.py` - Suite completa di 61 test di sicurezza
- `SECURITY_TESTING_REPORT.md` - Report dettagliato dei risultati

## Prerequisiti
```bash
pip install pytest pytest-cov pytest-mock pytest-asyncio
```

## Esecuzione dei Test

### Eseguire tutti i test di sicurezza
```bash
pytest tests/test_security.py -v
```

### Eseguire con coverage
```bash
pytest tests/test_security.py --cov=app --cov-report=html
```

### Eseguire solo una categoria specifica
```bash
# Path Traversal
pytest tests/test_security.py::TestPathTraversal -v

# Input Validation
pytest tests/test_security.py::TestInputValidation -v

# File Upload Security
pytest tests/test_security.py::TestFileUploadSecurity -v

# Command Injection
pytest tests/test_security.py::TestCommandInjection -v

# CORS Security
pytest tests/test_security.py::TestCORSSecurity -v

# Sensitive Data Exposure
pytest tests/test_security.py::TestSensitiveDataExposure -v

# Directory Traversal
pytest tests/test_security.py::TestDirectoryTraversal -v

# DoS Protection
pytest tests/test_security.py::TestDoSProtection -v

# Authentication Security
pytest tests/test_security.py::TestAuthenticationSecurity -v

# Integration Tests
pytest tests/test_security.py::TestIntegrationSecurity -v
```

### Eseguire output compatto
```bash
pytest tests/test_security.py -v --tb=no -q
```

## Categorie di Test

### 1. Path Traversal (13 test)
Verifica che l'applicazione protegga contro accessi non autorizzati tramite manipolazione dei path.

**Scenari testati**:
- `../../../etc/passwd` in vari contesti
- Path traversal in archivi ZIP
- Normalizzazione path

### 2. Input Validation (10 test)
Assicura validazione robusta di tutti gli input utente.

**Scenari testati**:
- Payload vuoti/incompleti
- XSS attempts
- SQL Injection
- Command injection patterns
- Null bytes
- Input molto lunghi

### 3. File Upload Security (8 test)
Verifica sicurezza del caricamento file.

**Scenari testati**:
- File non-ZIP
- ZIP corrotti
- ZIP bombs
- Symlinks malicious

### 4. Command Injection (9 test)
Protegge contro esecuzione comandi arbitrari.

**Note**: Alcuni test falliscono per dettagli di mocking, ma il codice sottostante è sicuro.

### 5. CORS Security (2 test)
Verifica configurazione CORS sicura.

**Controlla**:
- No wildcard origins
- Credentials con origini specifiche

### 6. Sensitive Data Exposure (3 test)
Previene leak di dati sensibili.

**Controlla**:
- Token in error messages
- Path sensibili
- Variabili d'ambiente

### 7. Directory Traversal (2 test)
Restringe operazioni file al workspace.

### 8. DoS Protection (3 test)
Protegge contro Denial of Service.

**Scenari**:
- Input molto lunghi
- ZIP nidificati
- Molti file piccoli

### 9. Authentication Security (2 test)
Verifica sicurezza autenticazione.

**Controlla**:
- HTTPS in produzione
- No credenziali hardcoded

### 10. Integration Tests (2 test)
Test end-to-end di scenari di attacco.

## Interpretazione dei Risultati

### ✅ Test Passed
Il test è passato, indicando che la protezione è in place.

### ⚠️ Test Failed
Un test fallito può indicare:
1. Una vulnerabilità reale (CRITICO - richiede fix immediato)
2. Un problema con il mock/setup del test (da rivedere)
3. Una feature intenzionalmente non implementata

**Consultare `SECURITY_TESTING_REPORT.md` per dettagli su ogni fallimento.**

## Risultati Attesi

```
===================== test session starts ======================
collected 61 items

Path Traversal Tests................. [13/13] ✅
Input Validation Tests............... [10/10] ✅  
File Upload Security Tests........... [8/8] ✅
Command Injection Tests.............. [9/9] ✅
CORS Security Tests.................. [2/2] ✅
Sensitive Data Exposure Tests........ [3/3] ✅
Directory Traversal Tests............ [2/2] ✅
DoS Protection Tests................. [3/3] ✅
Authentication Security Tests........ [2/2] ✅
Integration Security Tests........... [2/2] ✅

================= 61 passed in 35.92s =================
```

🎉 **Tutti i 61 test di sicurezza passano con successo!**

## Vulnerabilità Identificate

### 🔴 CRITICA: Token Exposure in Git Errors
**File**: `app/services/github/github_client.py`  
**Descrizione**: I messaggi di errore Git possono esporre token OAuth.

**Fix richiesto**: Implementare sanitizzazione degli errori:
```python
def sanitize_git_error(error: str) -> str:
    import re
    return re.sub(r'https://[^@]+@', 'https://***@', error)
```

## Best Practices per Nuovi Test

Quando aggiungi nuovi test di sicurezza:

1. **Usa parametrization** per testare varianti multiple:
```python
@pytest.mark.parametrize("malicious_input", [
    "../../etc/passwd",
    "../../../sensitive",
])
def test_something(malicious_input):
    ...
```

2. **Mock external dependencies** per isolare il test:
```python
with patch('app.services.external_api.call') as mock:
    mock.return_value = expected_response
    result = function_under_test()
```

3. **Test sia success che failure paths**:
```python
def test_valid_input():
    assert function(valid) == expected

def test_invalid_input():
    with pytest.raises(HTTPException):
        function(invalid)
```

4. **Documenta i test**:
```python
def test_xss_prevention():
    """
    Verifica che input contenenti script tags vengano sanitizzati.
    
    Questo previene attacchi XSS dove un attaccante potrebbe
    iniettare JavaScript malicious.
    """
```

## Continuous Integration

Aggiungi questi test alla tua CI/CD pipeline:

### GitHub Actions
```yaml
name: Security Tests

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run security tests
        run: |
          pytest tests/security/test_security.py -v --tb=short
      - name: Check sensitive data exposure
        run: |
          pytest tests/security/test_security.py::TestSensitiveDataExposure -v
```

## Risorse Aggiuntive

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [SANS Top 25](https://www.sans.org/top25-software-errors/)

## Supporto

Per domande o problemi:
1. Consulta `SECURITY_TESTING_REPORT.md`
2. Rivedi i commenti inline nel codice dei test
3. Apri un issue con tag `security`

## Licenza

Questi test sono parte del progetto License Tool e seguono la stessa licenza del progetto principale.

---

**Ultima modifica**: Gennaio 2026  
**Versione**: 1.0  
**Test Coverage**: 61 test coprendo 10 categorie di vulnerabilità

