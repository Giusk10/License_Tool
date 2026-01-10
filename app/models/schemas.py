"""
Schemas Module.

Questo modulo definisce i modelli Pydantic utilizzati per la validazione dei dati
nelle richieste e risposte API. Include schemi per le richieste di analisi,
la segnalazione di problemi relativi alle licenze e i risultati della clonazione dei repository.
"""

from typing import List, Optional
from pydantic import BaseModel

# ------------------------------------------------------------------
# REQUEST MODELS
# ------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """
    Rappresenta il payload di richiesta per l'analisi di un repository.

    Attributes:
        owner (str): Il nome utente o nome dell'organizzazione del proprietario del repository.
        repo (str): Il nome del repository.
    """
    owner: str
    repo: str


# ------------------------------------------------------------------
# COMPONENT MODELS
# ------------------------------------------------------------------

class LicenseIssue(BaseModel):
    """
    Rappresenta un singolo problema di compatibilità o violazione di licenza all'interno di un file.

    Attributes:
        file_path (str): Il percorso relativo al file contenente il problema.
        detected_license (str): L'identificatore della licenza rilevata nel file.
        compatible (bool): Indica se la licenza del file è compatibile con il progetto.
        reason (Optional[str]): Spiegazione del motivo per cui la licenza è incompatibile.
        suggestion (Optional[str]): Suggerimento generato dall'AI per risolvere il problema.
        licenses (Optional[str]): Dettagli aggiuntivi della licenza o stringhe di identificazione grezze.
        regenerated_code_path (Optional[str]): Percorso a un file generato localmente con correzioni.
    """
    file_path: str
    detected_license: str
    compatible: bool | None
    reason: Optional[str] = None
    suggestion: Optional[str] = None
    licenses: Optional[str] = None
    regenerated_code_path: Optional[str] = None


# ------------------------------------------------------------------
# RESPONSE MODELS
# ------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    """
    Rappresenta il payload di risposta principale per l'endpoint di analisi.

    Attributes:
        repository (str): Il nome completo del repository (es. "owner/repo").
        main_license (str): La licenza principale identificata per il progetto.
        issues (List[LicenseIssue]): Un elenco di problemi di compatibilità dettagliati trovati.
        needs_license_suggestion (bool): Indica se dovrebbe essere mostrato un modulo di suggerimento licenza.
    """
    repository: str
    main_license: str
    issues: List[LicenseIssue]
    needs_license_suggestion: bool = False


# ------------------------------------------------------------------
# INTERNAL MODELS
# ------------------------------------------------------------------

class CloneResult(BaseModel):
    """
    Modello interno per tracciare il risultato di un'operazione di clonazione del repository.

    Utilizzato sia per la clonazione GitHub che per il caricamento ZIP.

    Attributes:
        success (bool): True se l'operazione è riuscita, False altrimenti.
        repo_path (Optional[str]): Il percorso del file system locale al repository clonato/caricato.
        error (Optional[str]): Messaggio di errore se l'operazione è fallita.
    """
    success: bool
    repo_path: Optional[str] = None
    error: Optional[str] = None


# ------------------------------------------------------------------
# LICENSE SUGGESTION MODELS
# ------------------------------------------------------------------

class LicenseRequirementsRequest(BaseModel):
    """
    Rappresenta i requisiti e i vincoli dell'utente per il suggerimento della licenza.

    Attributes:
        owner (str): Il proprietario del repository.
        repo (str): Il nome del repository.
        commercial_use (bool): Se è richiesto l'uso commerciale.
        modification (bool): Se è consentita la modifica.
        distribution (bool): Se è consentita la distribuzione.
        patent_grant (bool): Se è necessaria la concessione di brevetti.
        trademark_use (bool): Se è necessario l'uso del marchio.
        liability (bool): Se è necessaria la protezione dalla responsabilità.
        copyleft (Optional[str]): Preferenza copyleft: "strong", "weak", "none", o None.
        additional_requirements (Optional[str]): Eventuali requisiti aggiuntivi in testo libero.
        detected_licenses (Optional[List[str]]): Elenco delle licenze già rilevate nel progetto.
    """
    owner: str
    repo: str
    commercial_use: bool = True
    modification: bool = True
    distribution: bool = True
    patent_grant: bool = False
    trademark_use: bool = False
    liability: bool = False
    copyleft: Optional[str] = None  # "strong", "weak", "none"
    additional_requirements: Optional[str] = None
    detected_licenses: Optional[List[str]] = None


class LicenseSuggestionResponse(BaseModel):
    """
    Rappresenta la risposta di suggerimento licenza generata dall'AI.

    Attributes:
        suggested_license (str): L'identificatore della licenza raccomandata.
        explanation (str): Spiegazione del motivo per cui è stata suggerita questa licenza.
        alternatives (Optional[List[str]]): Opzioni di licenza alternative.
    """
    suggested_license: str
    explanation: str
    alternatives: Optional[List[str]] = None

