# ⚖️ License Tool

**License Tool** è una piattaforma avanzata per il controllo della conformità delle licenze software. Il sistema permette agli sviluppatori di analizzare interi repository o caricare archivi localmente per identificare conflitti legali tra la licenza principale del progetto e le licenze dei singoli file.

Sviluppato da: **Riccio Giuseppe, Simeone Lucia, Medugno Vittoria, Capone Antonella, Liparulo Elisa**.

---

## 📂 Struttura del Progetto

Il progetto è organizzato in una struttura modulare che separa nettamente il backend (FastAPI), il frontend (React) e la suite di test:

```text
License_Tool/
├── .github/workflows/      # Pipeline di CI/CD per test automatizzati
├── app/                    # Core del Backend (FastAPI)
│   ├── controllers/        # Definizione degli endpoint API e gestione rotte
│   ├── models/             # Schemi Pydantic per la validazione dei dati
│   ├── services/           # Logica di business e workflow di analisi
│   │   ├── compatibility/  # Algoritmi compatibilità, matrice e parser SPDX
│   │   ├── downloader/     # Servizi per il download e creazione archivi ZIP
│   │   ├── github/         # Client per operazioni Git e integrazione GitHub
│   │   ├── llm/            # Integrazione Ollama per suggerimenti e codice
│   │   └── scanner/        # Logica di rilevamento licenze e filtraggio file
│   └── utility/            # Configurazione app e variabili d'ambiente
├── docs/                   # Documentazione tecnica, guide e note legali
├── frontend/               # Interfaccia Utente (React + Vite)
├── tests/                  # Suite di test unitari e di integrazione
├── pyproject.toml          # Configurazione build system e metadati progetto
├── requirements.txt        # Elenco dipendenze Python per installazione rapida
├── start-all-services.ps1  # Script PowerShell per l'avvio rapido dei servizi
└── LICENSE                 # Testo della Licenza del progetto
```

## 🚀 Panoramica del Sistema

Il tool implementa un workflow completo di analisi e correzione:

1.  **Acquisizione**: Il codice viene acquisito tramite **GitHub OAuth** o tramite upload manuale di un archivio **.zip**.
2.  **Scansione (ScanCode)**: Utilizza *ScanCode Toolkit* per estrarre le licenze dichiarate e i copyright in ogni file.
3.  **Analisi di Compatibilità**: Un motore interno confronta le licenze rilevate con la licenza target del progetto, identificando eventuali conflitti legali.
4.  **Enrichment AI (Ollama)**: I risultati vengono arricchiti da un LLM che spiega il conflitto e suggerisce soluzioni pratiche.
5.  **Rigenerazione del Codice**: Possibilità di riscrivere automaticamente i file che presentano conflitti (es. file con licenza Copyleft in progetti permissivi) mantenendo la logica originale ma rimuovendo il codice problematico.
6.  **Suggerimento Licenza**: In caso di Licenza principale non specificata, tramite un form dove vengono specificati requisisti e costraint [LICENSE SUGGESTION GUIDE](docs/LICENSE_SUGGESTION_GUIDE.md), raccomanda la licenza utilizzare utilizzando un LLM 

---

## ⚙️ Prerequisiti e Configurazione

Prima di installare il progetto, assicurati di avere i seguenti componenti installati e attivi sulla tua macchina:

1.  **Python 3.10-3.13**
2.  **Node.js & npm** (per il frontend)
3.  **Ollama**: Deve essere installato e in esecuzione con i modelli necessari scaricati (es. `llama3`, `codellama`).
4.  **ScanCode Toolkit**: Deve essere installato localmente. Il percorso dell'eseguibile dovrà essere specificato nel file di configurazione.

### Configurazione Variabili d'Ambiente (.env)

Il backend richiede un file `.env` nella root del progetto (`License_Tool/`) per funzionare correttamente.

Crea un file chiamato `.env` e compilalo seguendo questo template (adatta i percorsi al tuo OS):

```ini
# --- Integrazione ScanCode ---
# Percorso assoluto dell'eseguibile di ScanCode (es. su Linux/Mac o Windows)
SCANCODE_BIN="/path/to/scancode-toolkit/scancode"

# --- Integrazione AI (Ollama) ---
OLLAMA_URL="http://localhost:11434"
# Modello usato per la rigenerazione del codice (es. codellama, deepseek-coder)
OLLAMA_CODING_MODEL="qwen2.5-coder:1.5b"
# Modello usato per spiegazioni generiche (es. llama3, mistral)
OLLAMA_GENERAL_MODEL="deepseek-r1:1.5b"
# (Opzionali) Metadati per il versioning dei modelli
OLLAMA_HOST_VERSION="0.1.0"
OLLAMA_HOST_TAGS="latest"

# --- Autenticazione GitHub ---
# URL dove il frontend riceve il codice di callback da GitHub
CALLBACK_URL="http://localhost:5173/callback"

# --- Percorsi File System ---
CLONE_BASE_DIR="./temp_clones"
OUTPUT_BASE_DIR="./output"
MINIMAL_JSON_BASE_DIR="./output/minimal_scans"
```
## 🛠️ Stack Tecnologico

Il progetto utilizza tecnologie moderne per garantire scalabilità, sicurezza e una user experience fluida.

### Backend (Python)
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) - Scelto per le alte prestazioni e la generazione automatica della documentazione OpenAPI.
* **Analisi Licenze:** [ScanCode Toolkit](https://github.com/nexB/scancode-toolkit) - Engine leader del settore per il rilevamento di licenze e copyright.
* **AI Integration:** [Ollama](https://ollama.com/) - Orchestrazione di LLM locali (es. Llama 3, CodeLlama) per l'analisi semantica e la rigenerazione del codice.
* **Database:** MongoDB (tramite driver `pymongo`) - Per l'archiviazione flessibile dei risultati di scansione JSON.
* **Sicurezza:** Libreria `cryptography` per la cifratura a riposo dei token OAuth.

### Frontend (React)
* **Core:** React 19 + [Vite](https://vitejs.dev/) - Per un ambiente di sviluppo rapido e build ottimizzate.
* **Routing:** React Router DOM - Gestione della navigazione SPA (Single Page Application).
* **Networking:** Axios - Gestione delle chiamate HTTP verso le API del backend.
* **UI/UX:** CSS Modules e [Lucide React](https://lucide.dev/) per un set di icone coerente e leggero.

---

## 📦 Gestione delle Dipendenze

Il progetto adotta un approccio ibrido per la gestione delle dipendenze, garantendo sia standardizzazione che rapidità di setup:

### 1. `pyproject.toml` (Standard PEP 517/518)
È il file di configurazione principale per il build system moderno.
* **Metadata**: Definisce versione (`0.1.0`), autori e descrizione.
* **Build**: Isola le dipendenze di build.
* **Testing**: Centralizza la configurazione di **Pytest** e della coverage (`--cov=app`).

### 2. `requirements.txt` (Deploy Rapido)
È utilizzato per l'installazione immediata dell'ambiente operativo (es. in CI/CD o sviluppo locale veloce). Include librerie essenziali come:
* **Core**: `fastapi`, `uvicorn`.
* **Analisi Legale**: `license-expression` (SPDX).
* **Sicurezza**: `cryptography`, `pymongo`.

## 🔧 Installazione e Avvio

Segui questa procedura per configurare e avviare sia il backend che il frontend.

### 1. Configurazione Backend

Il backend richiede la creazione di un file di configurazione per connettersi ai servizi esterni (MongoDB, Ollama, ScanCode).

1.  **Installa le dipendenze:**
    ```bash
    # Entra nella root del progetto
    cd License_Tool

    # Installa i pacchetti Python richiesti
    pip install -r requirements.txt
    ```

2.  **Configura l'ambiente:**
    Assicurati di aver creato il file `.env` come descritto nella sezione **Configurazione Variabili d'Ambiente**.
   3.  **Scarica i modelli AI:**
       Scarica e installa Ollama dal sito ufficiale: [ollama.ai/download](https://ollama.ai/download).
       Aprii un terminale e scarica i modelli definiti nel tuo `.env`:
       ```bash
       ollama pull deepseek-r1:1.5b
       ollama pull qwen2.5-coder:1.5b
       ```
4.  **Avvia il Server:**
    ```bash
    uvicorn app.main:app --reload
    ```
    Il backend sarà attivo su `http://localhost:8000`.

### 2. Configurazione Frontend

In un nuovo terminale:

```bash
# Spostati nella cartella del frontend
cd frontend

# Installa le dipendenze Node.js
npm install

# Avvia il server di sviluppo
npm run dev
```

L'interfaccia web sarà accessibile all'indirizzo **http://localhost:5173**.

---

## ⚡ Quick Start (Windows)
Prima di procedere con una delle opzioni seguenti, bisogna aver scaricato e installato i modelli Ollama richiesti.

#### Opzione 1 - Script Automatico (CONSIGLIATO)
Se hai configurato lo script di automazione (opzionale), puoi avviare tutto con un comando.
```powershell
.\start-all-services.ps1
```
Lo script automatizza l'intero processo:
* ✅ Verifica che Ollama sia installato
* ✅ Avvia il servizio Ollama in background
* ✅ Verifica la presenza dei modelli AI necessari
* ✅ Avvia il Backend FastAPI
* ✅ Avvia il Frontend React

#### Opzione 2 - Manuale (3 Terminali)

**Terminal 1: Ollama**
```bash
ollama serve
```
*(⚠️ Non chiudere questa finestra)*

**Terminal 2: Backend**
```bash
uvicorn app.main:app --reload
```
**Terminal 3: Frontend**
```bash
cd frontend
npm run dev
```
**Apri il browser:** http://localhost:5173/

### 📚 Guide dettagliate
* [HOW-TO-USE-SUGGEST-LICENSE.md](docs/LICENSE_SUGGESTION_GUIDE.md) - Guida al suggerimento licenze

## 🆘 Troubleshooting: Errore connessione AI

### Problema Comune
Se durante l'utilizzo o l'avvio visualizzi questo errore:
```text
503 Service Unavailable for url: http://localhost:11434/api/generate
```
Significa semplicemente che **Ollama non è in esecuzione** o non è raggiungibile.

**Soluzione:**
1. Apri un terminale dedicato. 
2. Digita ollama serve. 
3. Lascia la finestra aperta e riprova l'operazione nel tool.

Assicurati anche di aver scaricato i modelli corretti.
```bash
ollama list
```

## ⚖️ Licenza e Conformità Legale

Questa sezione fornisce chiarezza sulle licenze che governano questo strumento e i suoi componenti.

### 1. Licenza del Tool (AGPL-3.0)
Il codice sorgente di questo progetto è rilasciato sotto la **Licenza AGPL v3.0**.
Vedi il file [LICENSE](LICENSE) per il testo completo.

### 2. Dipendenza ScanCode (Apache-2.0 / CC-BY-4.0)
Questo strumento integra il **ScanCode Toolkit** per l'analisi delle licenze. L'uso di ScanCode è soggetto alle seguenti condizioni:

* **Software ScanCode:** Apache License 2.0.
* **Dati di Rilevamento (Dataset):** CC-BY-4.0 (Creative Commons Attribuzione 4.0 Internazionale).

**Obbligo di Avviso:**
Come richiesto dalla Licenza Apache 2.0, tutti gli avvisi di copyright e le licenze dei componenti di terze parti di ScanCode sono documentati e distribuiti nel file **[THIRD_PARTY_NOTICE](docs/THIRD_PARTY_NOTICE)**.

**Attribuzione Dati ScanCode:**
> Copyright (c) nexB Inc. e altri. Tutti i diritti riservati. ScanCode è un marchio di nexB Inc. SPDX-License-Identifier: CC-BY-4.0. Vedi https://creativecommons.org/licenses/by/4.0/legalcode per il testo della licenza. Vedi https://github.com/nexB/scancode-toolkit per supporto o download.

---

## ⚠️ Avviso Legale Importante e Servizi Esterni

Questo strumento interagisce con servizi esterni e scarica codice soggetto a licenze proprie.

### Dipendenze Esterne
L'utilizzo di questo tool comporta l'interazione con i seguenti servizi, regolati dai rispettivi termini:

* **GitHub API:** Il download dei repository è soggetto ai *Termini di Servizio* e ai *Termini d'uso delle API* di GitHub. Si raccomanda di rispettare rigorosamente i limiti di frequenza (rate limits).
* **Ollama API:** L'interazione con i modelli AI locali è soggetta alla licenza MIT di Ollama.

### 🛑 Declino di Responsabilità: Rigenerazione del Codice

Il tool include funzionalità sperimentali per la **rigenerazione o modifica automatica** del codice tramite AI.

**Punti Critici da Considerare:**
1.  **Persistenza della Licenza:** Ogni codice scaricato o rigenerato mantiene la sua licenza originale.
2.  **Rischio "Virale" (Copyleft):** Se il codice analizzato è coperto da una licenza Copyleft (es. GPL), l'integrazione del codice rigenerato in un nuovo progetto potrebbe estendere i requisiti Copyleft all'intero progetto derivato.
3.  **Responsabilità Utente:** L'autore di questo strumento declina ogni responsabilità per l'uso improprio, violazioni di copyright o incompatibilità legali derivanti dall'uso del codice generato.

**L'utente è l'unico responsabile della verifica della conformità legale finale.**
