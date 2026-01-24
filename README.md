# ⚖️ License Checker

**License Checker** is an advanced platform for software license compliance checking. The system allows developers to analyze entire repositories or upload archives locally to identify legal conflicts between the project's main license and the licenses of individual files. It also offers the possibility of receiving suggestions on which license to use within one's project if it is missing one.

Developed by: **Riccio Giuseppe, Simeone Lucia, Medugno Vittoria, Capone Antonella, Liparulo Elisa**.

---

## 📂 Project Structure

The project is organized into a modular structure that clearly separates the backend (FastAPI), the frontend (React), and the test suite:

```text
License_Tool/
├── .github/workflows/      # CI/CD pipeline for automated testing
├── app/                    # Backend Core (FastAPI)
│   ├── controllers/        # API endpoint definition and route management
│   ├── models/             # Pydantic schemata for data validation
│   ├── services/           # Business logic and analysis workflows
│   │   ├── compatibility/  # Compatibility algorithms, matrix, and SPDX parser
│   │   ├── downloader/     # Services for downloading and creating ZIP archives
│   │   ├── github/         # Client for Git operations and GitHub integration
│   │   ├── llm/            # Ollama integration for suggestions and code
│   │   └── scanner/        # License detection logic and file filtering
│   └── utility/            # App configuration and environment variables
├── docs/                   # Technical documentation, guides, and legal notes
├── frontend/               # User Interface (React + Vite)
│   ├── src/                # Frontend Core
│   │   ├──  assets         # Images and Logo
│   │   ├──  components     # Graphic components for pages and Suggestion Form
│   │   └──  pages          # Application pages
├── tests/                  # Unit and integration test suite
├── pyproject.toml          # Build system configuration and project metadata
├── requirements.txt        # List of Python dependencies for quick installation
├── Dockerfile              # Instructions for building the image and setting up the runtime environment
├── start-container.sh      # Entrypoint script for initialization and starting services
└── LICENSE                 # Project License Text
```

## 🚀 System Overview

The tool implements a complete workflow for analysis, correction, and suggestions:

1.  **Acquisition**: Code is acquired via **GitHub** or via manual upload of a **.zip** archive.
2.  **Scanning (ScanCode)**: Uses *ScanCode Toolkit* to extract declared licenses and copyrights in each file.
3.  **Compatibility Analysis**: An internal engine that compares detected licenses with the project's target license, identifying potential legal conflicts.
4.  **Enrichment AI (Ollama)**: Results are enriched by an LLM that explains the conflict and suggests practical solutions.
5.  **Code Regeneration**: Capability to automatically rewrite files presenting conflicts (e.g., files with Copyleft licenses in permissive projects) while maintaining original logic, removing problematic code.
6.  **License Suggestion**: An LLM-assisted workflow for identifying the ideal license, based on requirements and constraints specified by the user via a dedicated form. Details in [LICENSE SUGGESTION GUIDE](docs/LICENSE_SUGGESTION_GUIDE.md).

---

## 🛠️ Technology Stack

The project uses modern technologies to ensure scalability, security, and a smooth user experience.

### Backend (Python)
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) - Chosen for high performance and automatic OpenAPI documentation generation.
* **License Analysis:** [ScanCode Toolkit](https://github.com/nexB/scancode-toolkit) - Industry-leading engine for license and copyright detection.
* **AI Integration:** [Ollama](https://ollama.com/) - Orchestration of LLMs in the cloud for semantic analysis, code regeneration, and License suggestion.

### Frontend (React)
* **Core:** React 19 + [Vite](https://vitejs.dev/) - For a rapid development environment and optimized builds.
* **Routing:** React Router DOM - SPA (Single Page Application) navigation management.
* **Networking:** Axios - Handling HTTP calls to backend APIs.
* **UI/UX:** CSS Modules and [Lucide React](https://lucide.dev/) for a consistent and lightweight icon set.

---

## 📦 Dependency Management

The project adopts a hybrid approach for dependency management, ensuring both standardization and rapid setup:

### 1. `pyproject.toml` (Standard PEP 517/518)
This is the main configuration file for the modern build system.
* **Metadata**: Defines version (`0.1.0`), authors, and description.
* **Build**: Isolates build dependencies.
* **Testing**: Centralizes configuration for **Pytest** and coverage (`--cov=app`).

### 2. `requirements.txt` (Fast Deploy)
Used for immediate installation of the operating environment (e.g., in CI/CD or fast local development). Includes essential libraries such as:
* **Core**: `fastapi`, `uvicorn`.
* **Legal Analysis**: `license-expression` (SPDX).

## ☁️ Deployment

The **Backend** is hosted on **Hugging Face Spaces** (via Docker SDK) to manage processing and LLM models, while the **Frontend** is distributed on Vercel to ensure optimal performance and global delivery.

## 🔧 Startup

The web interface will be accessible at **https://license-tool-nine.vercel.app/**.

---

## ⚖️ License and Legal Compliance

This section provides clarity on the licenses governing this tool and its components.

### 1. Tool License (AGPL-3.0)
The source code of this project is released under the **AGPL v3.0 License**.
See the [LICENSE](LICENSE) file for the full text.

### 2. ScanCode Dependency (Apache-2.0 / CC-BY-4.0)
This tool integrates the **ScanCode Toolkit** for license analysis. The use of ScanCode is subject to the following conditions:

* **ScanCode Software:** Apache License 2.0.
* **Detection Data (Dataset):** CC-BY-4.0 (Creative Commons Attribution 4.0 International).

**Notice Obligation:**
As required by the Apache 2.0 License, all copyright notices and licenses of third-party ScanCode components are documented and distributed in the file **[THIRD_PARTY_NOTICE](docs/THIRD_PARTY_NOTICE)**.

**ScanCode Data Attribution:**
> Copyright (c) nexB Inc. and others. All rights reserved. ScanCode is a trademark of nexB Inc. SPDX-License-Identifier: CC-BY-4.0. See https://creativecommons.org/licenses/by/4.0/legalcode for the license text. See https://github.com/nexB/scancode-toolkit for support or download.

---

## ⚠️ Important Legal Notice and External Services

This tool interacts with external services and downloads code subject to its own licenses.

### External Dependencies
Using this tool involves interaction with the following services, governed by their respective terms:

* **GitHub API:** Download of repositories is subject to GitHub's *Terms of Service* and *API Terms of Use*. It is recommended to strictly adhere to rate limits.
* **Ollama API:** Interaction with local AI models is subject to Ollama's MIT license.
  
### AI Models & Inference Notice

This tool leverages external Large Language Models (LLMs) to perform code analysis and reasoning. Specifically, it is configured to utilize:

* DeepSeek-V3 (by DeepSeek-AI) - Licensed under MIT License.
* Qwen-Coder (by Alibaba Cloud) - Licensed under Apache 2.0 License.

**Data Privacy Warning:** Usage of "Cloud" versions of these models implies that code snippets and analysis data are transmitted to remote inference endpoints. Users are responsible for verifying that their code can be securely transmitted to third-party inference providers in compliance with their own data privacy policies.

### 🛑 Disclaimer: Code Regeneration

The tool includes experimental features for **automatic regeneration or modification** of code via AI.

**Critical Points to Consider:**
1.  **License Persistence:** Any downloaded or regenerated code retains its original license.
2.  **"Viral" Risk (Copyleft):** If the analyzed code is covered by a Copyleft license (e.g., GPL), integrating the regenerated code into a new project could extend Copyleft requirements to the entire derivative project.
3.  **User Responsibility:** The author of this tool declines any responsibility for misuse, copyright violations, or legal incompatibilities arising from the use of the generated code.

**The user is solely responsible for verifying final legal compliance.**

