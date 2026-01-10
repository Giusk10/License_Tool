// Importa React in modalità Strict per evidenziare potenziali problemi
import { StrictMode } from 'react'
// Importa la funzione per creare la root dell'applicazione React
import { createRoot } from 'react-dom/client'
// Importa gli stili globali dell'applicazione
import './index.css'
// Importa il componente principale dell'applicazione
import App from './App.jsx'

// Crea la root dell'applicazione e la renderizza nell'elemento DOM con id 'root'
// StrictMode attiva controlli e avvisi aggiuntivi in modalità sviluppo
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
