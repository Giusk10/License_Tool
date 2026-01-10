import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import TripleToggleSwitch from '../components/TripleToggleSwitch';
import LicenseSuggestionForm from '../components/LicenseSuggestionForm';
import axios from 'axios';
import {
    CheckCircle,
    XCircle,
    AlertTriangle,
    ArrowLeft,
    GitBranch,
    Search,
    Scale,
    Lightbulb,
    FileText,
    Code,
    RefreshCw,
    ArrowRight,
    Download, HelpCircle
} from 'lucide-react';

// Funzione helper per estrarre le licenze uniche rilevate dai dati di analisi
const extractDetectedLicenses = (analysisData) => {
    if (!analysisData || !analysisData.issues) return [];

    const licenses = new Set();

    // Aggiunge la licenza principale se presente e non sconosciuta
    if (analysisData.main_license &&
        analysisData.main_license !== 'UNKNOWN' &&
        analysisData.main_license !== 'UNLICENSE') {
        licenses.add(analysisData.main_license);
    }

    // Aggiunge tutte le licenze rilevate dai problemi
    analysisData.issues.forEach(issue => {
        if (issue.detected_license &&
            issue.detected_license !== 'Unknown' &&
            issue.detected_license !== 'UNKNOWN' &&
            issue.detected_license !== 'None') {
            licenses.add(issue.detected_license);
        }
    });

    return Array.from(licenses);
};

const Callback = () => {
    const navigate = useNavigate();
    const location = useLocation();

    // Stati
    const [status, setStatus] = useState('loading'); // loading, cloned, analyzing, success, error
    const [cloneData, setCloneData] = useState(null); // { owner, repo, local_path }
    const [analysisData, setAnalysisData] = useState(null);
    const [regeneratedData, setRegeneratedData] = useState(null);
    const [isRegenerating, setIsRegenerating] = useState(false);
    const [error, setError] = useState('');
    const [source, setSource] = useState('clone'); // clone or upload
    const [filterState, setFilterState] = useState(2); // 1: Compatible, 2: All, 3: Incompatible
    const [showLicenseSuggestionForm, setShowLicenseSuggestionForm] = useState(false);
    const [licenseSuggestion, setLicenseSuggestion] = useState(null);

    // Progresso simulato per l'analisi
    const [progressStep, setProgressStep] = useState(0);
    const steps = [
        { label: 'Scanning Files', icon: Search },
        { label: 'Checking Compatibility', icon: Scale },
        { label: 'Generating AI Suggestions', icon: Lightbulb },
        { label: 'Finalizing Report', icon: FileText },
    ];

    // 1. Clonazione Iniziale al Mount
    React.useRef(false);
    useEffect(() => {
        // Controlla se i dati sono stati passati tramite navigazione (es. da Upload Zip o Clone)
        if (location.state?.cloneData) {
            setCloneData(location.state.cloneData);
            setStatus('cloned');
            if (location.state.source) {
                setSource(location.state.source);
            }
        } else {
            // Se non sono presenti dati, reindirizza alla Home
            setStatus('error');
            setError('No repository data found. Please start from the Home page.');
            // Opzionale: Auto-redirect dopo un ritardo
            // setTimeout(() => navigate('/'), 3000);
        }
    }, [location.state]);

    // 2. Gestione Click Analizza
    const handleAnalyze = async () => {
        if (!cloneData) return;

        setStatus('analyzing');
        setProgressStep(0);

        // Simulazione progresso
        const interval = setInterval(() => {
            setProgressStep((prev) => {
                if (prev < steps.length - 1) return prev + 1;
                return prev;
            });
        }, 2000);

        try {
            const response = await axios.post(`https://licensechecker-license-checker-tool.hf.space/api/analyze`, {
                owner: cloneData.owner,
                repo: cloneData.repo
            });

            setAnalysisData(response.data);
            setStatus('success');
            clearInterval(interval);

            // Controlla se è necessario un suggerimento di licenza
            // REMOVED AUTO OPEN: if (response.data.needs_license_suggestion) {
            //     setShowLicenseSuggestionForm(true);
            // }

            // Controlla le necessità di rigenerazione immediatamente dopo l'analisi
            // REMOVED AUTO REGENERATION: checkAndRegenerate(response.data, cloneData.owner, cloneData.repo);

        } catch (err) {
            console.error(err);
            clearInterval(interval);
            setStatus('error');
            setError(err.response?.data?.detail || 'Analysis failed.');
        }
    };

    // 3. Logica di Controllo e Rigenerazione
    const handleRegenerate = async () => {
        if (!analysisData) return;

        setIsRegenerating(true);
        try {
            const regenResponse = await axios.post(`https://licensechecker-license-checker-tool.hf.space/api/regenerate`, analysisData);
            setRegeneratedData(regenResponse.data);
        } catch (regenErr) {
            console.error("Regeneration failed:", regenErr);
        } finally {
            setIsRegenerating(false);
        }
    };

    // 4. Gestione Download
    const handleDownload = async () => {
        if (!cloneData) return;
        try {
            const response = await axios.post('https://licensechecker-license-checker-tool.hf.space/api/download', {
                owner: cloneData.owner,
                repo: cloneData.repo
            }, { responseType: 'blob' });

            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `${cloneData.owner}_${cloneData.repo}.zip`);
            document.body.appendChild(link);
            link.click();
            link.remove();
        } catch (err) {
            console.error("Download failed:", err);
            // Opzionalmente imposta uno stato di errore o un avviso
        }
    };

    // --- RENDER CONDIZIONALI BASATI SULLO STATO ---

    /**
     * Stato LOADING - Visualizzato durante il caricamento iniziale
     * Mostra un'icona di caricamento animata e un messaggio
     */
    if (status === 'loading') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
                    {/* Spinner animato */}
                    <div
                        className="spin"
                        style={{
                            width: 48,
                            height: 48,
                            marginBottom: '1rem'
                        }}
                    />
                    <h2>Cloning Repository...</h2>
                    <p>Please wait while we fetch the repository from GitHub.</p>
                </div>
            </div>
        );
    }

    /**
     * Stato CLONED - Repository clonato/caricato con successo
     * Mostra i dettagli del repository e permette di:
     * - Avviare l'analisi
     * - Scaricare il repository
     */
    if (status === 'cloned') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', width: '100%', maxWidth: '600px', textAlign: 'center' }}>
                    {/* Icona di successo */}
                    <div style={{ marginBottom: '1rem', marginTop: '0.5.rem' }}>
                        <GitBranch size={70} color="#219625ff" />
                    </div>
                    {/* Titolo dinamico basato sulla sorgente (upload o clone) */}
                    <h2 style={{ marginBottom: '1rem' }}>
                        {source === 'upload' ? 'Repository Uploaded Successfully!' : 'Repository Cloned Successfully!'}
                    </h2>

                    {/* Pannello con i dettagli del repository */}
                    <div className="glass-panel" style={{
                        background: 'rgba(49, 24, 82, 0.2)',
                        borderColor: '#444bcc3f',
                        padding: '1.5rem',
                        marginBottom: '2.6rem',
                        textAlign: 'left'
                    }}>
                        <p><strong>Owner :</strong> {cloneData.owner}</p>
                        <p><strong>Repository :</strong> {cloneData.repo}</p>
                        <p><strong>Local Path :</strong> <span style={{ fontSize: '0.9rem', opacity: 0.9 }}>{cloneData.local_path}</span></p>
                    </div>

                    {/* Pulsanti di azione */}
                    <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
                        {/* Pulsante per avviare l'analisi */}
                        <button onClick={handleAnalyze} className="glass-button" style={{ fontSize: '1.1rem', padding: '1rem 2rem' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                Analyze Repository <ArrowRight size={20} />
                            </span>
                        </button>
                        {/* Pulsante per scaricare il repository */}
                        <button onClick={handleDownload} className="glass-button" style={{ fontSize: '1.1rem', padding: '1rem 2rem', background: 'rgba(255, 255, 255, 0.1)' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                Download <Download size={20} />
                            </span>
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    /**
     * Stato ANALYZING - Analisi in corso
     * Mostra una barra di progresso con gli step dell'analisi:
     * 1. Scansione file
     * 2. Controllo compatibilità
     * 3. Generazione suggerimenti AI
     * 4. Finalizzazione report
     */
    if (status === 'analyzing') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', width: '100%', maxWidth: '600px' }}>
                    <h2 style={{ marginBottom: '2rem' }}>Analyzing Repository</h2>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', alignItems: 'flex-start' }}>
                        {/* Mappa ogni step mostrando icona e stato (completato/attivo/in attesa) */}
                        {steps.map((step, index) => {
                            const Icon = step.icon;
                            const isActive = index === progressStep;  // Step corrente
                            const isCompleted = index < progressStep;  // Step già completati
                            return (
                                <div key={index} style={{
                                    display: 'flex', alignItems: 'center', gap: '1rem',
                                    opacity: isActive || isCompleted ? 1 : 0.4,  // Opacità ridotta per step futuri
                                    transition: 'opacity 0.3s'
                                }}>
                                    {/* Icona circolare dello step con colore basato sullo stato */}
                                    <div style={{
                                        width: '32px', height: '32px', borderRadius: '50%',
                                        background: isCompleted ? '#219625ff' : (isActive ? 'rgba(100, 108, 255, 0.2)' : 'rgba(255, 255, 255, 0.1)'),
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        border: isActive ? '1px solid #646cff' : 'none'
                                    }}>
                                        {/* Check per completati, spinner per attivo, dot per futuri */}
                                        {isCompleted ? <CheckCircle size={20} color="#fff" /> :
                                            isActive ? <div className="spin" style={{ width: 20, height: 20 }} /> :
                                                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'rgba(255,255,255,0.3)' }} />}
                                    </div>
                                    {/* Label e icona dello step */}
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <Icon size={20} />
                                        <span style={{ fontSize: '1.1rem', fontWeight: isActive ? 'bold' : 'normal' }}>{step.label}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        );
    }

    /**
     * Stato ERROR - Errore durante una delle operazioni
     * Mostra il messaggio di errore e permette di tornare alla home
     */
    if (status === 'error') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', borderColor: '#ff4444' }}>
                    {/* Icona di errore */}
                    <XCircle size={48} color="#ff4444" style={{ marginBottom: '1rem' }} />
                    <h2>Operation Failed</h2>
                    {/* Messaggio di errore specifico */}
                    <p style={{ color: '#ffaaaa' }}>{error}</p>
                    {/* Pulsante per tornare alla home */}
                    <button onClick={() => navigate('/')} className="glass-button" style={{ marginTop: '1rem' }}>
                        Try Again
                    </button>
                </div>
            </div>
        );
    }

    // STATO DI SUCCESSO (Visualizza Risultati)
    const displayData = regeneratedData || analysisData;
    const isComparisonMode = !!regeneratedData;

    return (
        <div className="container" style={{ justifyContent: 'flex-start', paddingTop: '2rem' }}>
            <div className="glass-panel result-card">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
                    <button onClick={() => navigate('/')} className="glass-button" style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}>
                        <ArrowLeft size={16} style={{ marginRight: '0.5rem' }} /> Back
                    </button>
                    <h2>Analysis Report {isComparisonMode ? '(Regenerated)' : ''}</h2>
                    <div style={{ display: 'flex', gap: '1rem' }}>
                        {displayData.issues.some(i =>
                            displayData.main_license !== 'UNKNOWN' &&
                            !i.compatible &&
                            !/(\.(md|txt|rst)|THIRD_PARTY_NOTICE|NOTICE)$/i.test(i.file_path)) && (
                            <button onClick={handleRegenerate} className="glass-button" style={{ padding: '0.5rem 1rem', fontSize: '0.9rem', background: 'rgba(100, 108, 255, 0.2)' }}>
                                <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <RefreshCw size={16} /> Regenerate
                                </span>
                            </button>
                        )}
                        <button onClick={handleDownload} className="glass-button" style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <Download size={16} /> Download
                            </span>
                        </button>
                    </div>
                </div>

                {isRegenerating && (
                    <div className="glass-panel" style={{
                        marginBottom: '2rem',
                        background: 'rgba(100, 108, 255, 0.1)',
                        borderColor: '#646cff',
                        display: 'flex', alignItems: 'center', gap: '1rem'
                    }}>
                        <div className="spin" style={{ width: 24, height: 24, marginLeft: '1.3rem' }} />
                        <div>
                            <h4 style={{ margin: 0, color: '#646cff' }}>Regenerating Code...</h4>
                            <p style={{ margin: 0, fontSize: '0.9rem', opacity: 0.8 }}>
                                Found incompatible files. Attempting to rewrite them...
                            </p>
                        </div>
                    </div>
                )}


                {displayData && (
                    <div style={{ textAlign: 'left' }}>
                        {/* Header Info */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
                            <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', background:'rgba(21, 28, 51, 0.18)' }}>
                                <span style={{ opacity: 0.7, fontSize: '1rem' }}>Repository</span>
                                <span style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>{displayData.repository}</span>
                            </div>
                            <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', background: 'rgba(21, 28, 51, 0.18)', position: 'relative' }}>
                                <span style={{ opacity: 0.7, fontSize: '1rem' }}>Main License</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                                    <span style={{ fontSize: '1.2rem', fontWeight: 'bold', color: '#646cff' }}>
                                        {displayData.main_license === 'UNKNOWN' ? 'UNLICENSE' : displayData.main_license}
                                    </span>
                                    {displayData.needs_license_suggestion && (
                                        <button
                                            onClick={() => setShowLicenseSuggestionForm(true)}
                                            className="glass-button"
                                            style={{
                                                padding: '0.3rem 0.6rem',
                                                fontSize: '0.75rem',
                                                background: 'rgba(255, 193, 7, 0.2)',
                                                borderColor: '#ffc107',
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '0.3rem'
                                            }}
                                        >
                                            <Lightbulb size={16} /> Get Suggestion
                                        </button>
                                    )}
                                    {licenseSuggestion && (
                                        <span style={{
                                            padding: '0.3rem 0.6rem',
                                            fontSize: '0.75rem',
                                            background: 'rgba(33, 150, 37, 0.2)',
                                            borderRadius: '4px',
                                            color: '#219625ff',
                                            border: '1px solid rgba(33, 150, 37, 0.3)'
                                        }}>
                                            Suggested: {licenseSuggestion.suggested_license}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Issues List */}
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                                <h3 style={{ marginLeft: 3, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <AlertTriangle size={25} /> License Issues & Compatibility
                                </h3>

                                <div className="toggle-wrapper" style={{ minWidth: '300px', height: '60px', position: 'relative' }}>
                                    <TripleToggleSwitch
                                        labels={{
                                            left: { title: "✓", value: "left" },
                                            center: { title: "All", value: "center" },
                                            right: { title: "✗", value: "right" }
                                        }}
                                        value={filterState === 1 ? 'left' : filterState === 3 ? 'right' : 'center'}
                                        onChange={(val) => {
                                            if (val === 'left') setFilterState(1);
                                            if (val === 'center') setFilterState(2);
                                            if (val === 'right') setFilterState(3);
                                        }}
                                    />
                                </div>
                            </div>

                            {/* Filter Logic */}
                            {(() => {
                                const issuesToRender = displayData.issues.filter(issue => {
                                    if (filterState === 1) return issue.compatible; // Stato 1: Mostra solo Compatibili
                                    if (filterState === 3) return !issue.compatible;  // Stato 3: Mostra solo Incompatibili
                                    return true; // Stato 2: Mostra tutti
                                });

                                if (issuesToRender.length > 0) {
                                    return (
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                                            {issuesToRender.map((issue, idx) => {
                                                const originalIssue = isComparisonMode
                                                    ? analysisData.issues.find(i => i.file_path === issue.file_path)
                                                    : null;
                                                const wasIncompatible = originalIssue && !originalIssue.compatible;

                                                return (
                                                    <div key={idx} className="glass-panel" style={{
                                                        background: 'rgba(21, 28, 51, 0.18)',
                                                        padding: '1.5rem',
                                                        borderLeft: `4px solid ${issue.compatible === true ? '#219625ff' : (issue.compatible === false ? '#f44336' : '#ffab00')}`
                                                    }}>
                                                        {/* Container Flex principale */}
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>

                                                            <div style={{ flex: 1, minWidth: 0, marginRight: '1rem' }}>
                                                                <h4 style={{
                                                                    margin: 0,
                                                                    fontSize: '1.1rem',
                                                                    // MODIFICA QUI: Forza il testo ad andare a capo
                                                                    wordBreak: 'break-all',
                                                                    overflowWrap: 'anywhere'
                                                                }}>
                                                                    {issue.file_path}
                                                                </h4>

                                                                {isComparisonMode && wasIncompatible ? (
                                                                    <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                                                                        <span style={{ opacity: 0.6, textDecoration: 'line-through' }}>{originalIssue.detected_license}</span>
                                                                        <ArrowRight size={14} />
                                                                        <span style={{ padding: '0.2rem 0.6rem', borderRadius: '4px', background: 'rgba(76, 175, 80, 0.2)', color: '#219625ff', fontWeight: 'bold' }}>
                                                                            {issue.detected_license} (Regenerated)
                                                                        </span>
                                                                    </div>
                                                                ) : (
                                                                    <span style={{ fontSize: '0.9rem', padding: '0.2rem 0.6rem', borderRadius: '4px', background: 'rgba(255,255,255,0.1)', marginTop: '0.5rem', display: 'inline-block' }}>
                                                                        Detected: {issue.detected_license}
                                                                    </span>
                                                                )}
                                                            </div>

                                                            {/* Parte destra (Icona e Status) - Aggiunto 'flexShrink: 0' per evitare che si schiacci */}
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: issue.compatible === true ? '#219625ff' : (issue.compatible === false ? '#f44336' : '#ffab00'), fontWeight: 'bold', flexShrink: 0 }}>
                                                                {issue.compatible === true && <CheckCircle size={22} />}
                                                                {issue.compatible === false && <XCircle size={22} />}
                                                                {(issue.compatible === null || issue.compatible === undefined) && <HelpCircle size={22} />}
                                                                {issue.compatible === true ? 'Compatible' : (issue.compatible === false ? 'Incompatible' : 'Unknown')}
                                                            </div>
                                                        </div>
                                                        {issue.reason && (
                                                            <ul style={{
                                                                fontSize: '0.95rem',
                                                                opacity: 0.8,
                                                                marginBottom: '1rem',
                                                                paddingLeft: '1.5rem' // Aggiunto per l'indentazione dei punti
                                                            }}>
                                                                {issue.reason.split(';').map((item, index) => {
                                                                    // Rimuoviamo spazi bianchi extra e saltiamo stringhe vuote
                                                                    const text = item.trim();
                                                                    if (!text) return null;

                                                                    return (
                                                                        <li key={index} style={{ marginBottom: '0.25rem' }}>
                                                                            {text}
                                                                        </li>
                                                                    );
                                                                })}
                                                            </ul>
                                                        )}
                                                        {issue.suggestion && (
                                                            <div style={{ background: 'rgba(100, 108, 255, 0.05)', padding: '1rem', borderRadius: '8px', marginBottom: '1rem', border: '1px solid rgba(100, 108, 255, 0.2)' }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', color: '#646cff' }}>
                                                                    <Lightbulb size={22} />
                                                                    <span style={{ fontWeight: 'bold', fontSize: '1rem' }}>AI Suggestions</span>
                                                                </div>

                                                                {issue.suggestion
                                                                    // 1. SPLIT CORRETTO: Cerca numero seguito da parentesi ")"
                                                                    // Suddivide il testo in base ai numeri seguiti da "§"
                                                                    .split(/(?=\d+§)/)

                                                                    .filter(line => line && line.trim() !== '')
                                                                    .map((line, index) => (

                                                                        <ul key={index} style={{
                                                                            margin: 0,
                                                                            marginBottom: '0.8rem',
                                                                            paddingLeft: '0.5rem',
                                                                            fontSize: '1rem',
                                                                            color: '#e0e0e0',
                                                                            listStyleType: 'none'
                                                                        }}>
                                                                            <li style={{ display: 'flex', alignItems: 'flex-start' }}>

                                                                                {/* Renderizza il numero progressivo visivo: 1) 2) ... */}
                                                                                <span style={{
                                                                                    marginRight: '0.5rem',
                                                                                    fontWeight: 'bold',
                                                                                    color: '#646cff',
                                                                                    flexShrink: 0
                                                                                }}>{index + 1})
                                                                                </span>

                                                                                <div style={{ whiteSpace: 'pre-wrap' }}>
                                                                                    {/* 2. PULIZIA TESTO: Rimuove "1§", "2§" originali dall'inizio della stringa */}
                                                                                    {/* Nota il \) che indica la parentesi chiusa */}
                                                                                    {line.replace(/^\d+§\s*/, '').trim()}
                                                                                </div>
                                                                            </li>
                                                                        </ul>
                                                                    ))
                                                                }
                                                            </div>
                                                        )}
                                                        {issue.regenerated_code_path && (
                                                            <div style={{ marginTop: '1rem' }}>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                                                                    <Code size={16} /><span style={{ fontWeight: 'bold', fontSize: '0.9rem' }}>Regenerated Code Available</span>
                                                                </div>
                                                                <pre style={{ maxHeight: '200px', overflowY: 'auto', fontSize: '0.85rem' }}>{`Code regenerated at: ${issue.regenerated_code_path}`}</pre>
                                                            </div>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    );
                                } else {
                                    return (
                                        <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center', opacity: 0.7, background: 'rgba(21, 28, 51, 0.18)' }}>
                                            <CheckCircle size={32} style={{ marginBottom: '1rem' }} />
                                            <p>No issues found matching the selected filter. </p>
                                        </div>
                                    );
                                }
                            })()}
                        </div>
                    </div>
                )}
            </div>

            {/* License Suggestion Form Modal */}
            {showLicenseSuggestionForm && cloneData && (
                <LicenseSuggestionForm
                    owner={cloneData.owner}
                    repo={cloneData.repo}
                    detectedLicenses={analysisData ? extractDetectedLicenses(analysisData) : []}
                    onClose={() => setShowLicenseSuggestionForm(false)}
                    onSuggestionReceived={(suggestion) => {
                        setLicenseSuggestion(suggestion);
                    }}
                />
            )}
        </div>
    );
};

export default Callback;
