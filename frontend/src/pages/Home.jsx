// Importa React e hook useState per gestire lo stato del componente
import React, { useState } from 'react';
// Importa hook per la navigazione tra le pagine
import { useNavigate } from 'react-router-dom';
// Importa icone da lucide-react per UI
import { Github, ArrowRight, Upload } from 'lucide-react';
// Importa il logo dell'applicazione
import logo from '../assets/logo-minimal.png';
// Importa axios per le chiamate HTTP al backend
import axios from 'axios';

/**
 * Componente Home - Pagina iniziale dell'applicazione
 *
 * Permette all'utente di:
 * 1. Inserire owner e nome del repository GitHub
 * 2. Clonare un repository da GitHub per l'analisi
 * 3. Caricare un file ZIP contenente il codice sorgente
 *
 * Dopo l'operazione (clone o upload), naviga alla pagina Callback per mostrare i risultati
 */
const Home = () => {
    // Stato per il nome del proprietario del repository
    const [owner, setOwner] = useState('');
    // Stato per il nome del repository
    const [repo, setRepo] = useState('');
    // Stato per indicare se è in corso la clonazione
    const [loading, setLoading] = useState(false);
    // Stato per indicare se è in corso il caricamento di un file ZIP
    const [uploading, setUploading] = useState(false);
    // Hook per la navigazione programmatica
    const navigate = useNavigate();
    // Riferimento all'input file nascosto per il caricamento ZIP
    const fileInputRef = React.useRef(null);

    // Gestisce l'avvio dell'analisi tramite clonazione di un repository GitHub
    const handleAnalyze = async (e) => {
        // Previene il comportamento di default del form
        e.preventDefault();
        // Verifica che owner e repo siano stati inseriti
        if (!owner || !repo) return;

        // Imposta lo stato di caricamento
        setLoading(true);

        try {
            const response = await axios.post('https://licensechecker-license-checker-tool.hf.space/api/clone', {
                owner,
                repo
            });

            // Naviga alla pagina di callback con i dati della clonazione
            navigate('/callback', {
                state: {
                    cloneData: response.data,
                    source: 'clone'
                }
            });
        } catch (error) {
            // Gestisce errori durante la clonazione
            console.error("Cloning failed", error);
            alert("Cloning failed: " + (error.response?.data?.detail || error.message));
            setLoading(false);
        }
    };

    // Attiva il click sull'input file nascosto quando si preme il pulsante di upload
    const handleUploadClick = () => {
        // Verifica che owner e repo siano stati inseriti prima di aprire il selettore file
        if (!owner || !repo) {
            alert("Please enter Owner and Repository name first.");
            return;
        }
        // Simula un click sull'input file nascosto
        fileInputRef.current.click();
    };

    // Gestisce il caricamento e l'invio del file ZIP
    const handleFileChange = async (e) => {
        // Ottiene il file selezionato
        const file = e.target.files[0];
        if (!file) return;

        // Imposta lo stato di caricamento
        setUploading(true);

        // Crea un oggetto FormData per inviare il file
        const formData = new FormData();
        formData.append('owner', owner);
        formData.append('repo', repo);
        formData.append('uploaded_file', file);

        try {
            const response = await axios.post('https://licensechecker-license-checker-tool.hf.space/api/zip', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });

            // Naviga alla pagina di callback con i dati dell'upload
            navigate('/callback', {
                state: {
                    cloneData: response.data,
                    source: 'upload'
                }
            });
        } catch (error) {
            // Gestisce errori durante l'upload
            console.error("Upload failed", error);
            alert("Upload failed: " + (error.response?.data?.detail || error.message));
            setUploading(false);
        }
    };

    // Mostra schermata di caricamento durante operazioni async
    if (uploading || loading) {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
                    {/* Icona animata di caricamento */}
                    <div
                        className="spin"
                        style={{
                            width: 48,
                            height: 48,
                            marginBottom: '1rem'
                        }}
                    />
                    {/* Messaggio dinamico basato sull'operazione in corso */}
                    <h2>{uploading ? 'Uploading Repository...' : 'Cloning Repository...'}</h2>
                    <p>
                        {uploading
                            ? 'Please wait while we upload and process the repository.'
                            : 'Please wait while we clone the repository from GitHub.'}
                    </p>
                </div>
            </div>
        );
    }

    // Render del form principale
    return (
        <div className="container">
            <div className="glass-panel form-group">
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <img
                        src={logo}
                        alt="Logo"
                        style={{ width: '150px', height: '150px' }}
                    />
                </div>
                <h1 style={{ fontSize: '3.5rem', marginBottom: '0.5rem', marginTop: '-1rem'}}>License Checker</h1>
                <p style={{ fontSize: '1.12rem', marginBottom: '2rem' }}>Analyze GitHub repositories for license compatibility.</p>

                {/* Form per l'input dei dati del repository */}
                <form onSubmit={handleAnalyze} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%' }}>
                    {/* Input per il proprietario del repository */}
                    <input
                        type="text"
                        size={13}
                        placeholder="GitHub Owner (e.g. facebook)"
                        value={owner}
                        onChange={(e) => setOwner(e.target.value)}
                        className="glass-input"
                        required
                    />

                    {/* Input per il nome del repository */}
                    <input
                        type="text"
                        size={13}
                        placeholder="Repository Name (e.g. react)"
                        value={repo}
                        onChange={(e) => setRepo(e.target.value)}
                        className="glass-input"
                        required
                    />

                    {/* Input file nascosto per il caricamento ZIP */}
                    <input
                        type="file"
                        ref={fileInputRef}
                        style={{ display: 'none' }}
                        accept=".zip"
                        onChange={handleFileChange}
                    />

                    {/* Container per i pulsanti di azione */}
                    <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                        {/* Pulsante per clonare il repository da GitHub */}
                        <button type="submit" className="glass-button" style={{ flex: 1 }} disabled={loading}>
                            {loading ? 'Cloning...' : (
                                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                                    Clone Repository <ArrowRight size={16} />
                                </span>
                            )}
                        </button>

                        {/* Pulsante per caricare un file ZIP */}
                        <button
                            type="button"
                            onClick={handleUploadClick}
                            className="glass-button"
                            style={{ flex: 1 }}
                            disabled={loading}
                        >
                            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                                Upload Zip <Upload size={16} />
                            </span>
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default Home;

