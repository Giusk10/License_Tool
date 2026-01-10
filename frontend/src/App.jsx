// Importa React per la creazione di componenti
import React from 'react';
// Importa i componenti per il routing dell'applicazione (navigazione tra pagine)
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
// Importa la pagina principale (Home) dove l'utente inserisce i dati del repository
import Home from './pages/Home';
// Importa la pagina di callback che mostra i risultati dell'analisi
import Callback from './pages/Callback';

/**
 * Componente principale dell'applicazione che gestisce il routing tra le diverse pagine.
 *
 * Definisce due rotte:
 * - "/" (root): Pagina iniziale per inserire owner e nome del repository
 * - "/callback": Pagina che mostra i risultati dell'analisi delle licenze
 */
function App() {
  return (
    <Router>
      <Routes>
        {/* Rotta principale - Pagina Home per l'input dei dati */}
        <Route path="/" element={<Home />} />
        {/* Rotta per visualizzare i risultati dell'analisi */}
        <Route path="/callback" element={<Callback />} />
      </Routes>
    </Router>
  );
}

export default App;
