# ⚖️ License Tool

**License Tool** è una piattaforma avanzata per il controllo della conformità delle licenze software. Il sistema permette agli sviluppatori di analizzare interi repository o caricare archivi localmente per identificare conflitti legali tra la licenza principale del progetto e le licenze dei singoli file. Con la possibilità di avere suggerimenti sulla licenza da adoperare all'interno del proprio progetto nell'eventualità che ne sia sprovvisto.

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
│   ├── src/                # Core del Frontend
│   │   ├──  assets         # Immagini e Logo
│   │   ├──  components     # Componenti grafici per pagine e Form di suggerimento
│   │   └──  pages          # Pagine di collegamento
├── tests/                  # Suite di test unitari e di integrazione
├── pyproject.toml          # Configurazione build system e metadati progetto
├── requirements.txt        # Elenco dipendenze Python per installazione rapida
├── Dockerfile              # Istruzioni di build dell'immagine e setup dell'ambiente runtime
├── start-container.sh      # Script di entrypoint per l'inizializzazione e l'avvio dei servizi
└── LICENSE                 # Testo della Licenza del progetto
```

## 🚀 Panoramica del Sistema

Il tool implementa un workflow completo di analisi, correzione e suggerimenti:

1.  **Acquisizione**: Il codice viene acquisito tramite **GitHub** o tramite upload manuale da un archivio **.zip**.
2.  **Scansione (ScanCode)**: Utilizza *ScanCode Toolkit* per estrarre le licenze dichiarate e i copyright in ogni file.
3.  **Analisi di Compatibilità**: Un motore interno che confronta le licenze rilevate con la licenza target del progetto identificando eventuali conflitti legali.
4.  **Enrichment AI (Ollama)**: I risultati vengono arricchiti da un LLM che spiega il conflitto e suggerisce soluzioni pratiche.
5.  **Rigenerazione del Codice**: Possibilità di riscrivere automaticamente i file che presentano conflitti (es. file con licenza Copyleft in progetti permissivi) mantenendo la logica originale, rimuovendo il codice problematico.
6.  **Suggerimento Licenza**: Workflow assistito da LLM per l'individuazione della licenza ideale, basata sui requisiti e vincoli specificati dall'utente tramite form dedicato. Dettagli in [LICENSE SUGGESTION GUIDE](docs/LICENSE_SUGGESTION_GUIDE.md).

---

## 🛠️ Stack Tecnologico

Il progetto utilizza tecnologie moderne per garantire scalabilità, sicurezza e una user experience fluida.

### Backend (Python)
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) - Scelto per le alte prestazioni e la generazione automatica della documentazione OpenAPI.
* **Analisi Licenze:** [ScanCode Toolkit](https://github.com/nexB/scancode-toolkit) - Engine leader del settore per il rilevamento di licenze e copyright.
* **AI Integration:** [Ollama](https://ollama.com/) - Orchestrazione di LLM in cloud per l'analisi semantica, la rigenerazione del codice e il suggerimento della Licenza.

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

## ☁️ Deployment

Il **Backend** è ospitato su **Hugging Face Spaces** (via Docker SDK) per gestire l'elaborazione e i modelli LLM, mentre il **Frontend** è distribuito su Vercel per garantire performance ottimali e delivery globale.

## 🔧 Avvio

L'interfaccia web sarà accessibile all'indirizzo **https://license-tool-nine.vercel.app/**.

---

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
