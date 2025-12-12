import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom';
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
    Download
} from 'lucide-react';

const Callback = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const location = useLocation();

    // States
    const [status, setStatus] = useState('loading'); // loading, cloned, analyzing, success, error
    const [cloneData, setCloneData] = useState(null); // { owner, repo, local_path }
    const [analysisData, setAnalysisData] = useState(null);
    const [regeneratedData, setRegeneratedData] = useState(null);
    const [isRegenerating, setIsRegenerating] = useState(false);
    const [error, setError] = useState('');
    const [source, setSource] = useState('clone'); // clone or upload
    const [filterState, setFilterState] = useState(2); // 1: Incompatible, 2: All, 3: Compatible

    // Simulated progress for analysis
    const [progressStep, setProgressStep] = useState(0);
    const steps = [
        { label: 'Scanning Files', icon: Search },
        { label: 'Checking Compatibility', icon: Scale },
        { label: 'Generating AI Suggestions', icon: Lightbulb },
        { label: 'Finalizing Report', icon: FileText },
    ];

    // 1. Initial Clone on Mount
    const hasCalledRef = React.useRef(false);

    useEffect(() => {
        // Check if data was passed via navigation (e.g. from Upload Zip)
        if (location.state?.cloneData) {
            setCloneData(location.state.cloneData);
            setStatus('cloned');
            if (location.state.source) {
                setSource(location.state.source);
            }
            return;
        }

        const code = searchParams.get('code');
        const state = searchParams.get('state');

        if (!code || !state) {
            setStatus('error');
            setError('Missing code or state parameters.');
            return;
        }

        if (hasCalledRef.current) return;
        hasCalledRef.current = true;

        const performClone = async () => {
            try {
                const response = await axios.get(`http://localhost:8000/api/callback`, {
                    params: { code, state }
                });
                // Response: { status: "cloned", owner, repo, local_path }
                setCloneData(response.data);
                setStatus('cloned');
            } catch (err) {
                console.error(err);
                setStatus('error');
                setError(err.response?.data?.detail || 'Cloning failed.');
            }
        };

        performClone();
    }, [searchParams, location.state]);

    // 2. Handle Analyze Click
    const handleAnalyze = async () => {
        if (!cloneData) return;

        setStatus('analyzing');
        setProgressStep(0);

        // Progress simulation
        const interval = setInterval(() => {
            setProgressStep((prev) => {
                if (prev < steps.length - 1) return prev + 1;
                return prev;
            });
        }, 2000);

        try {
            const response = await axios.post(`http://localhost:8000/api/analyze`, {
                owner: cloneData.owner,
                repo: cloneData.repo
            });

            setAnalysisData(response.data);
            setStatus('success');
            clearInterval(interval);

            // Check for regeneration needs immediately after analysis
            // REMOVED AUTO REGENERATION: checkAndRegenerate(response.data, cloneData.owner, cloneData.repo);

        } catch (err) {
            console.error(err);
            clearInterval(interval);
            setStatus('error');
            setError(err.response?.data?.detail || 'Analysis failed.');
        }
    };

    // 3. Check and Regenerate Logic
    // 3. Check and Regenerate Logic
    const handleRegenerate = async () => {
        if (!analysisData) return;

        setIsRegenerating(true);
        try {
            const regenResponse = await axios.post(`http://localhost:8000/api/regenerate`, analysisData);
            setRegeneratedData(regenResponse.data);
        } catch (regenErr) {
            console.error("Regeneration failed:", regenErr);
        } finally {
            setIsRegenerating(false);
        }
    };

    // 4. Handle Download
    const handleDownload = async () => {
        if (!cloneData) return;
        try {
            const response = await axios.post('http://localhost:8000/api/download', {
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
            // Optionally set an error state or alert
        }
    };


    // --- RENDER HELPERS ---

    if (status === 'loading') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
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

    if (status === 'cloned') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', width: '100%', maxWidth: '600px', textAlign: 'center' }}>
                    <div style={{ marginBottom: '2rem' }}>
                        <GitBranch size={64} color="#4caf50" />
                    </div>
                    <h2 style={{ marginBottom: '1rem' }}>
                        {source === 'upload' ? 'Repository Uploaded Successfully!' : 'Repository Cloned Successfully!'}
                    </h2>

                    <div className="glass-panel" style={{
                        padding: '1.5rem',
                        marginBottom: '2rem',
                        textAlign: 'left'
                    }}>
                        <p><strong>Owner:</strong> {cloneData.owner}</p>
                        <p><strong>Repository:</strong> {cloneData.repo}</p>
                        <p><strong>Local Path:</strong> <span style={{ fontSize: '0.85rem', opacity: 0.7 }}>{cloneData.local_path}</span></p>
                    </div>

                    <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
                        <button onClick={handleAnalyze} className="glass-button" style={{ fontSize: '1.1rem', padding: '1rem 2rem' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                Analyze Repository <ArrowRight size={20} />
                            </span>
                        </button>
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

    if (status === 'analyzing') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', width: '100%', maxWidth: '600px' }}>
                    <h2 style={{ marginBottom: '2rem' }}>Analyzing Repository</h2>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', alignItems: 'flex-start' }}>
                        {steps.map((step, index) => {
                            const Icon = step.icon;
                            const isActive = index === progressStep;
                            const isCompleted = index < progressStep;
                            return (
                                <div key={index} style={{
                                    display: 'flex', alignItems: 'center', gap: '1rem',
                                    opacity: isActive || isCompleted ? 1 : 0.4,
                                    transition: 'opacity 0.3s'
                                }}>
                                    <div style={{
                                        width: '32px', height: '32px', borderRadius: '50%',
                                        background: isCompleted ? '#4caf50' : (isActive ? 'rgba(100, 108, 255, 0.2)' : 'rgba(255, 255, 255, 0.1)'),
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        border: isActive ? '1px solid #646cff' : 'none'
                                    }}>
                                        {isCompleted ? <CheckCircle size={18} color="#fff" /> :
                                            isActive ? <div className="spin" style={{ width: 18, height: 18 }} /> :
                                                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'rgba(255,255,255,0.3)' }} />}
                                    </div>
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

    if (status === 'error') {
        return (
            <div className="container">
                <div className="glass-panel" style={{ padding: '3rem', borderColor: '#ff4444' }}>
                    <XCircle size={48} color="#ff4444" style={{ marginBottom: '1rem' }} />
                    <h2>Operation Failed</h2>
                    <p style={{ color: '#ffaaaa' }}>{error}</p>
                    <button onClick={() => navigate('/')} className="glass-button" style={{ marginTop: '1rem' }}>
                        Try Again
                    </button>
                </div>
            </div>
        );
    }

    // SUCCESS STATE (Display Results)
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
                        {!isComparisonMode && displayData.issues.some(i => !i.compatible && !/\.(md|txt|rst)$/i.test(i.file_path)) && (
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
                            <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                <span style={{ opacity: 0.7, fontSize: '0.9rem' }}>Repository</span>
                                <span style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>{displayData.repository}</span>
                            </div>
                            <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                <span style={{ opacity: 0.7, fontSize: '0.9rem' }}>Main License</span>
                                <span style={{ fontSize: '1.2rem', fontWeight: 'bold', color: '#646cff' }}>{displayData.main_license || 'Unknown'}</span>
                            </div>
                        </div>

                        {/* Issues List */}
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                                <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <AlertTriangle size={20} /> License Issues & Compatibility
                                </h3>

                                <div className="toggle-wrapper" style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
                                    <span style={{
                                        fontSize: '0.8rem',
                                        opacity: filterState === 1 ? 1 : 0.5,
                                        color: filterState === 1 ? '#f44336' : 'inherit',
                                        fontWeight: filterState === 1 ? 'bold' : 'normal'
                                    }}>Incompatible</span>

                                    <input
                                        type="range"
                                        min="1"
                                        max="3"
                                        step="1"
                                        value={filterState}
                                        onChange={(e) => setFilterState(parseInt(e.target.value))}
                                        className={`tgl-def state-${filterState}`}
                                    />

                                    <span style={{
                                        fontSize: '0.8rem',
                                        opacity: filterState === 3 ? 1 : 0.5,
                                        color: filterState === 3 ? '#4caf50' : 'inherit',
                                        fontWeight: filterState === 3 ? 'bold' : 'normal'
                                    }}>Compatible</span>
                                </div>
                            </div>

                            {/* Filter Logic */}
                            {(() => {
                                const issuesToRender = displayData.issues.filter(issue => {
                                    if (filterState === 1) return !issue.compatible; // Show only incompatible
                                    if (filterState === 3) return issue.compatible;  // Show only compatible
                                    return true; // Show all (State 2)
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
                                                        padding: '1.5rem',
                                                        borderLeft: `4px solid ${issue.compatible ? '#4caf50' : '#f44336'}`
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
                                                                        <span style={{ padding: '0.2rem 0.6rem', borderRadius: '4px', background: 'rgba(76, 175, 80, 0.2)', color: '#4caf50', fontWeight: 'bold' }}>
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
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: issue.compatible ? '#4caf50' : '#f44336', fontWeight: 'bold', flexShrink: 0 }}>
                                                                {issue.compatible ? <CheckCircle size={18} /> : <XCircle size={18} />}
                                                                {issue.compatible ? 'Compatible' : 'Incompatible'}
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
                                                                    <Lightbulb size={18} />
                                                                    <span style={{ fontWeight: 'bold', fontSize: '0.95rem' }}>Suggerimenti di Risoluzione</span>
                                                                </div>

                                                                {issue.suggestion
                                                                    // 1. SPLIT CORRETTO: Cerca numero seguito da parentesi ")"
                                                                    // La regex (?=\d+\)) usa un "lookahead" per trovare "1)", "2)" ecc.
                                                                    .split(/(?=\d+\))/)

                                                                    .filter(line => line && line.trim() !== '')
                                                                    .map((line, index) => (

                                                                        <ul key={index} style={{
                                                                            margin: 0,
                                                                            marginBottom: '0.8rem',
                                                                            paddingLeft: '0.5rem',
                                                                            fontSize: '0.9rem',
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
                                                                                    {/* 2. PULIZIA TESTO: Rimuove "1)", "2)" originali dall'inizio della stringa */}
                                                                                    {/* Nota il \) che indica la parentesi chiusa */}
                                                                                    {line.replace(/^\d+\)\s*/, '').trim()}
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
                                        <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center', opacity: 0.7 }}>
                                            <CheckCircle size={32} style={{ marginBottom: '1rem' }} />
                                            <p>No issues found matching the selected filter.</p>
                                        </div>
                                    );
                                }
                            })()}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Callback;
