"""
Package `app.services.compatibility`

Questo package fornisce gli strumenti per valutare la compatibilità delle licenze dei
file rispetto alla licenza principale di un progetto usando una matrice professionale.

API pubblica:
- check_compatibility(main_license: str, file_licenses: Dict[str, str]) -> dict

Nota: la logica è suddivisa in moduli separati:
- compat_utils: normalizzazione simboli e parsing di base
- matrix: caricamento/normalizzazione della matrice professionale
- parser_spdx: parser semplice per espressioni SPDX (AND/OR/WITH)
- evaluator: valutazione tri-stato dell'albero (yes/no/conditional/unknown)
- checker: funzione pubblica che orchestri il controllo per file
"""

from .checker import check_compatibility

__all__ = ["check_compatibility"]


"""
Perché in questo package l'`init` espone un'API pubblica: 
viene fatto il re-export di check_compatibility così chi usa il package può fare from app.services.compatibility import check_compatibility. 
Se l'`init` è vuoto l'import fallisce e devi importare il sottomodulo direttamente. 
Inoltre __all__ controlla cosa viene esportato con from ... import * e aiuta l'IDE a risolvere i nomi
"""