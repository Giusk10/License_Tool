# ⚖️ License Tool

**License Tool** è una piattaforma avanzata per il controllo della conformità delle licenze software. Il sistema permette agli sviluppatori di analizzare interi repository o caricare archivi localmente per identificare conflitti legali tra la licenza principale del progetto e le licenze dei singoli file.

Sviluppato da: **Riccio Giuseppe, Simeone Lucia, Medugno Vittoria, Capone Antonella, Liparulo Elisa**.

## 📂 Struttura del Progetto

Il progetto è organizzato in una struttura modulare che separa nettamente il backend (FastAPI), il frontend (React) e la suite di test:

```text
License_Tool-Lucia2/
├── .github/workflows/      # Pipeline di CI/CD per test automatizzati
├── app/                    # Core del Backend (FastAPI)
│   ├── controllers/        # Definizione degli endpoint API e gestione rotte
│   ├── models/             # Schemi Pydantic per la validazione dei dati
│   ├── services/           # Logica di business e workflow di analisi
│   │   ├── compatibility/  # Algoritmi per il calcolo della compatibilità licenze
│   │   ├── downloader/     # Servizi per il download dei repository processati
│   │   ├── github/         # Client per l'integrazione con le API GitHub e OAuth
│   │   ├── llm/            # Moduli per l'interazione con Ollama e rigenerazione codice
│   │   └── scanner/        # Integrazione con ScanCode Toolkit e filtraggio risultati
│   └── utility/            # Gestione configurazioni, variabili d'ambiente e helper
├── frontend/               # Interfaccia Utente (React + Vite)
│   ├── public/             # Asset statici pubblici
│   └── src/                # Codice sorgente dell'applicazione React
│       ├── components/     # Componenti UI (es. Toggle Switch, Dashboard)
│       └── pages/          # Definizione delle viste principali (Home, Callback)
├── tests/                  # Suite di test unitari e di integrazione
├── pyproject.toml          # Metadata del progetto e configurazione build system
├── requirements.txt        # Elenco dipendenze Python per installazione rapida
├── LICENSE                 # Testo della Licenza MIT del progetto
└── THRID_PART_NOTICE       # Documentazione obbligatoria per componenti di terze parti

```

## 🚀 Panoramica del Sistema

Il tool implementa un workflow completo di analisi e correzione:

1. **Acquisizione**: Il codice viene acquisito tramite **GitHub OAuth** o tramite upload di un archivio **.zip**.
2. **Scansione (ScanCode) - Rilevamento Licenze**: Utilizza *ScanCode Toolkit* per estrarre le licenze dichiarate in ogni file.
3. **Analisi di Compatibilità**: Un motore interno confronta le licenze trovate con la licenza target, identificando incompatibilità.
4. **Enrichment AI (Ollama)**: I risultati vengono arricchiti da un LLM che spiega il conflitto e suggerisce soluzioni.
5. **Rigenerazione del Codice**: ossibilità di riscrivere automaticamente i file che presentano conflitti di licenza (es. file Copyleft in progetti permissivi) mantenendo la logica originale.

🛠️ Architettura e API
Il backend è basato su FastAPI e si articola sui seguenti endpoint principali:

* Autenticazione:
  * `GET /api/auth/start`: Avvia il flusso OAuth 2.0 con GitHub.
  * `GET /api/callback`: Gestisce il ritorno da GitHub, scambia il codice con un token ed esegue la clonazione della repo.

* Gestione File:
  * `POST /api/zip`: Permette l'analisi tramite caricamento manuale di un file .zip.
  * `POST /api/download`: Permette di scaricare il repository analizzato (ed eventualmente corretto) come archivio zip.

* Analisi e Correzione:
  * `POST /api/analyze`: Avvia la scansione e il controllo di compatibilità sulla repo locale.
  * `POST /api/regenerate`: Riceve i risultati di un'analisi precedente e avvia la rigenerazione tramite AI dei file problematici.

## 📦 Gestione delle Dipendenze

Il progetto utilizza un doppio sistema di gestione delle dipendenze per massimizzare la compatibilità:

### 1. `pyproject.toml` (Standard Moderno)

Questo file gestisce la configurazione secondo gli standard **PEP 517/518**:

* **Metadata**: Elenca gli autori, la versione (0.1.0) e la descrizione del tool.
* **Build System**: Configura `setuptools` per la creazione del pacchetto, isolando il backend dal frontend.
* **Testing**: Centralizza le opzioni di **Pytest**, definendo i percorsi di test e la copertura del codice (`--cov=app`).

### 2. `requirements.txt` (Installazione Rapida)

Elenca le librerie necessarie per l'ambiente operativo:

* **Framework**: `fastapi`, `uvicorn`.
* **Analisi**: `license-expression` per la gestione degli identificatori SPDX.
* **Sicurezza e Dati**: `cryptography` e `pymongo`.

## 🛠️ Stack Tecnologico

### Backend
* Framework: FastAPI.
* Scansione: ScanCode Toolkit.
* AI/LLM: Integrazione con l'API di Ollama.
* Linguaggio: Python 3.13.

### Frontend
* Framework: React 19 con Vite. 
* Routing: React Router DOM. 
* Icone: Lucide React. 
* HTTP Client: Axios.

### Requisiti

* Python 3.13
* Node.js & npm
* Istanza di **Ollama** attiva
* Token GitHub OAuth (opzionale, per clonazione repository privati/limiti API)
* MongoDB
* ScanCode Toolkit installato e disponibile nel percorso di sistema

## 🔧 Installazione e Avvio

### Procedura

1. **Backend**:
```bash
# Entra nella cartella del progetto
cd License_Tool

# Installa le dipendenze
pip install -r requirements.txt

# Avvia il server (porta di default 8000)
uvicorn app.main:app --reload
```

2. **Frontend**:
```bash
# Entra nella cartella frontend
cd frontend

# Installa le dipendenze
npm install

# Avvia l'ambiente di sviluppo
npm run dev

```
Il frontend sarà accessibile di default su http://localhost:5173.
## ⚖️ Licenza e Conformità Legale

Questa sezione fornisce chiarezza sulle licenze che governano questo strumento e i suoi componenti.

### 1. Licenza del Tool (MIT)

Questo progetto (il codice sorgente originale) è rilasciato sotto la **Licenza MIT**.

Vedi il file [LICENSE](LICENSE) per il testo completo.

### 2. Dipendenza ScanCode (Apache-2.0 / CC-BY-4.0)

Questo strumento utilizza il **ScanCode Toolkit** per l'analisi delle licenze. ScanCode è soggetto alle seguenti licenze:

* **Software ScanCode:** Apache License 2.0.
* **Dati ScanCode (e.g., set per il rilevamento delle licenze):** CC-BY-4.0 (Creative Commons Attribuzione 4.0 Internazionale).

**Obbligo di Avviso:** Come richiesto dalla Licenza Apache 2.0, tutti gli avvisi di copyright e le licenze dei componenti di terze parti di ScanCode sono documentati tramite i file `.ABOUT` e sono inclusi e distribuiti nel file **[THIRD_PART_NOTICE](THRID_PART_NOTICE)**, il quale riproduce il contenuto del file `NOTICE` di ScanCode.

**Attribuzione Dati ScanCode (CC-BY-4.0):**
L'uso dei set di dati di ScanCode richiede la seguente attribuzione preferita:
> Copyright (c) nexB Inc. e altri. Tutti i diritti riservati. ScanCode è un marchio di nexB Inc. SPDX-License-Identifier: CC-BY-4.0. Vedi https://creativecommons.org/licenses/by/4.0/legalcode per il testo della licenza. Vedi https://github.com/nexB/scancode-toolkit per supporto o download.

---

## ⚠️ Avviso Legale Importante e Dipendenze Esterne

Questo strumento interagisce con servizi esterni e scarica codice che ha licenze proprie.

### Dipendenze Esterne e Servizi

Questo tool si basa sui seguenti servizi esterni, il cui utilizzo è regolato dai rispettivi termini e condizioni:

* **GitHub API e Accesso al Repository:**
    * Il tool scarica repository (codice e metadati) tramite l'API di GitHub.
    * L'uso di questa funzionalità è soggetto ai **Termini di Servizio e ai Termini d'uso delle API di GitHub**.
    * **Attenzione:** Si prega di rispettare rigorosamente i limiti di frequenza (rate limits) di GitHub.

* **Ollama API:**
    * Il tool interagisce con un'istanza Ollama. L'uso di Ollama è soggetto alla sua licenza (MIT).

### Declino di Responsabilità per la Rigenerazione del Codice

Il tool include funzionalità che permettono la **rigenerazione o la modifica** del codice scaricato per l'analisi.

**Si prega di notare che ogni codice scaricato e/o rigenerato mantiene la sua licenza originale.**

Se il codice analizzato è coperto da una licenza **Copyleft (come GPL)**, l'integrazione o la distribuzione del codice rigenerato in un nuovo progetto **potrebbe sottoporre il progetto risultante ai requisiti Copyleft** di tale licenza.

L'utente è l'unico responsabile della conformità legale all'uso, alla modifica e alla distribuzione del codice generato o analizzato con questo strumento. L'autore di questo strumento (sotto Licenza MIT) declina ogni responsabilità per l'uso improprio o per le violazioni delle licenze di terze parti.
