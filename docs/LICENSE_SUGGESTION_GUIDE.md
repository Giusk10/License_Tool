# Come Usare la Funzionalità di Suggerimento Licenza

## Quando appare il form di suggerimento?

Il form per il suggerimento della licenza appare automaticamente quando:

1. **Nessuna licenza principale rilevata**: Il sistema non trova un file LICENSE o COPYING valido nel repository
2. **Licenze Unknown presenti**: Alcuni file hanno licenze che non possono essere identificate correttamente da ScanCode

## Come usare il form

### Step 1: Compilare le Permissions & Requirements

Seleziona i permessi che desideri per la tua licenza:

- ☑️ **Commercial use allowed**: Il software può essere usato per scopi commerciali
- ☑️ **Modification allowed**: Il codice può essere modificato
- ☑️ **Distribution allowed**: Il software può essere distribuito
- ☐ **Patent grant required**: Include una concessione esplicita di brevetti
- ☐ **Trademark use allowed**: Permette l'uso dei marchi del progetto
- ☐ **Liability protection needed**: Include clausole di esclusione di responsabilità

### Step 2: Scegliere la Copyleft Preference

Seleziona il livello di copyleft desiderato:

- **No Copyleft (Permissive)**: Licenze permissive come MIT, Apache-2.0, BSD
  - Massima libertà per chi usa il codice
  - Nessun obbligo di rilasciare modifiche
  - Esempi: MIT, Apache-2.0, BSD-3-Clause

- **Weak Copyleft (LGPL-style)**: Copyleft debole
  - Le modifiche alla libreria devono essere condivise
  - Il software che la usa può rimanere proprietario
  - Esempi: LGPL-3.0, MPL-2.0

- **Strong Copyleft (GPL-style)**: Copyleft forte
  - Tutto il software derivato deve essere open source
  - Stessa licenza deve essere applicata
  - Esempi: GPL-3.0, AGPL-3.0

### Step 3: Additional Requirements (Opzionale)

Puoi aggiungere requisiti aggiuntivi in testo libero, ad esempio:
- "Il progetto deve essere compatibile con progetti Android"
- "Voglio che le modifiche siano sempre condivise"
- "Necessità di protezione brevettuale"

### Step 4: Get Suggestion

Clicca su "Get Suggestion" e l'AI analizzerà i tuoi requisiti per suggerirti la licenza più adatta.

## Interpretare il risultato

### Recommended License
La licenza principale suggerita basata sui tuoi requisiti.

### Explanation
Una spiegazione dettagliata del perché questa licenza è appropriata per le tue esigenze.

### Alternative Options
Una lista di licenze alternative che potrebbero comunque soddisfare i tuoi requisiti.

## Esempi di scenari

### Scenario 1: Progetto Open Source Aziendale
**Requisiti:**
- ✅ Commercial use
- ✅ Modification
- ✅ Distribution
- ✅ Patent grant
- No Copyleft

**Suggerimento probabile:** Apache-2.0
- Permissiva ma con protezione brevettuale esplicita

### Scenario 2: Libreria Open Source per la Community
**Requisiti:**
- ✅ Commercial use
- ✅ Modification
- ✅ Distribution
- Weak Copyleft

**Suggerimento probabile:** LGPL-3.0
- Modifiche alla libreria condivise, ma progetti che la usano possono rimanere proprietari

### Scenario 3: Software Completamente Libero
**Requisiti:**
- ✅ Commercial use
- ✅ Modification
- ✅ Distribution
- Strong Copyleft
- Additional: "Tutto il codice derivato deve rimanere open source"

**Suggerimento probabile:** GPL-3.0
- Garantisce che tutto il software derivato sia open source

### Scenario 4: Progetto Semplice e Permissivo
**Requisiti:**
- ✅ Commercial use
- ✅ Modification
- ✅ Distribution
- No Copyleft

**Suggerimento probabile:** MIT
- La licenza più semplice e permissiva

## Cosa fare dopo aver ricevuto il suggerimento

1. **Leggi attentamente la spiegazione** per capire le implicazioni della licenza
2. **Considera le alternative** se la licenza suggerita non ti convince completamente
3. **Ricerca ulteriori informazioni** sulla licenza suggerita (es. su choosealicense.com)
4. **Aggiungi un file LICENSE** al tuo repository con il testo della licenza scelta
5. **Aggiorna i file sorgente** con l'intestazione di copyright appropriata

## Note importanti

- ⚠️ Questo è un suggerimento AI, non consulenza legale
- ⚠️ Consulta sempre un avvocato per decisioni legali importanti
- ⚠️ Verifica la compatibilità con le licenze delle dipendenze
- ⚠️ Alcune licenze hanno requisiti specifici (es. file NOTICE, copyright headers)

## Risorse utili

- [Choose a License](https://choosealicense.com/) - Guida visuale alle licenze
- [SPDX License List](https://spdx.org/licenses/) - Lista completa delle licenze standard
- [TLDRLegal](https://tldrlegal.com/) - Spiegazioni semplificate delle licenze
- [GNU License Recommendations](https://www.gnu.org/licenses/license-recommendations.html)

## Supporto

Se hai domande o problemi con il suggerimento della licenza, apri una issue nel repository del progetto.

