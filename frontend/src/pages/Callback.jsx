import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
    CheckCircle,
    XCircle,
    AlertTriangle,
    ArrowLeft,
    Loader2,
    GitBranch,
    Search,
    Scale,
    Lightbulb,
    FileText,
    Code,
    RefreshCw,
    ArrowRight
} from 'lucide-react';

const Callback = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [status, setStatus] = useState('loading'); // loading, success, error
    const [initialData, setInitialData] = useState(null);
    const [regeneratedData, setRegeneratedData] = useState(null);
    const [isRegenerating, setIsRegenerating] = useState(false);
    const [error, setError] = useState('');

    // Simulated progress state
    const [progressStep, setProgressStep] = useState(0);
    const steps = [
        { label: 'Cloning Repository', icon: GitBranch },
        { label: 'Scanning Files', icon: Search },
        { label: 'Checking Compatibility', icon: Scale },
        { label: 'Generating AI Suggestions', icon: Lightbulb },
        { label: 'Finalizing Report', icon: FileText },
    ];

    useEffect(() => {
        const code = searchParams.get('code');
        const state = searchParams.get('state');

        if (!code || !state) {
            setStatus('error');
            setError('Missing code or state parameters.');
            return;
        }

        // Simulate progress steps for initial scan
        const interval = setInterval(() => {
            setProgressStep((prev) => {
                if (prev < steps.length - 1) return prev + 1;
                return prev;
            });
        }, 2500);

        const fetchData = async () => {
            try {
                // 1. Initial Scan
                const response = await axios.get(`http://localhost:8000/api/callback`, {
                    params: { code, state }
                });
                const data = response.data;
                setInitialData(data);
                setStatus('success');
                setProgressStep(steps.length); // Complete all steps
                clearInterval(interval);

                // 2. Check if regeneration is needed
                const hasIncompatible = data.issues.some(issue => !issue.compatible);
                if (hasIncompatible) {
                    setIsRegenerating(true);

                    // Extract owner and repo from state or response
                    // state is "owner:repo"
                    const [owner, repo] = state.split(':');

                    try {
                        const regenResponse = await axios.post(`http://localhost:8000/api/regenerate`, data);
                        setRegeneratedData(regenResponse.data);
                    } catch (regenErr) {
                        console.error("Regeneration failed:", regenErr);
                        // We don't fail the whole page, just show an error for regeneration
                    } finally {
                        setIsRegenerating(false);
                    }
                }

            } catch (err) {
                console.error(err);
                setStatus('error');
                setError(err.response?.data?.detail || 'An error occurred during analysis.');
                clearInterval(interval);
            }
        };

        fetchData();

        return () => clearInterval(interval);
    }, [searchParams]);

    if (status === 'loading') {
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
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '1rem',
                                    opacity: isActive || isCompleted ? 1 : 0.4,
                                    transition: 'opacity 0.3s'
                                }}>
                                    <div style={{
                                        width: '32px',
                                        height: '32px',
                                        borderRadius: '50%',
                                        background: isCompleted ? '#4caf50' : (isActive ? 'rgba(100, 108, 255, 0.2)' : 'rgba(255, 255, 255, 0.1)'),
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        border: isActive ? '1px solid #646cff' : 'none'
                                    }}>
                                        {isCompleted ? (
                                            <CheckCircle size={18} color="#fff" />
                                        ) : isActive ? (
                                            <Loader2 size={18} className="loading-spinner" style={{ border: 'none', width: '18px', height: '18px' }} />
                                        ) : (
                                            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'rgba(255,255,255,0.3)' }} />
                                        )}
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
                    <h2>Analysis Failed</h2>
                    <p style={{ color: '#ffaaaa' }}>{error}</p>
                    <button onClick={() => navigate('/')} className="glass-button" style={{ marginTop: '1rem' }}>
                        Try Again
                    </button>
                </div>
            </div>
        );
    }

    // Determine which data to show: Regenerated (if available) or Initial
    const displayData = regeneratedData || initialData;
    const isComparisonMode = !!regeneratedData;

    return (
        <div className="container" style={{ justifyContent: 'flex-start', paddingTop: '2rem' }}>
            <div className="glass-panel result-card">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
                    <button onClick={() => navigate('/')} className="glass-button" style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}>
                        <ArrowLeft size={16} style={{ marginRight: '0.5rem' }} /> Back
                    </button>
                    <h2>Analysis Report {isComparisonMode ? '(Regenerated)' : ''}</h2>
                </div>

                {isRegenerating && (
                    <div className="glass-panel" style={{
                        marginBottom: '2rem',
                        background: 'rgba(100, 108, 255, 0.1)',
                        borderColor: '#646cff',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '1rem'
                    }}>
                        <Loader2 size={24} className="loading-spinner" color="#646cff" />
                        <div>
                            <h4 style={{ margin: 0, color: '#646cff' }}>Regenerating Code...</h4>
                            <p style={{ margin: 0, fontSize: '0.9rem', opacity: 0.8 }}>
                                Found incompatible files. Attempting to rewrite them with compatible licenses.
                                The report will update automatically.
                            </p>
                        </div>
                    </div>
                )}

                {displayData && (
                    <div style={{ textAlign: 'left' }}>
                        {/* Header Info */}
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                            gap: '1rem',
                            marginBottom: '2rem'
                        }}>
                            <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                <span style={{ opacity: 0.7, fontSize: '0.9rem' }}>Repository</span>
                                <span style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>{displayData.repository}</span>
                            </div>
                            <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                <span style={{ opacity: 0.7, fontSize: '0.9rem' }}>Main License</span>
                                <span style={{ fontSize: '1.2rem', fontWeight: 'bold', color: '#646cff' }}>{displayData.main_license || 'Unknown'}</span>
                            </div>
                        </div>

                        {/* Pipeline Visualization (Simplified for result view) */}
                        <div style={{ marginBottom: '3rem' }}>
                            <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <GitBranch size={20} /> Execution Pipeline
                            </h3>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                <div className="glass-panel" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', borderColor: '#4caf50' }}>
                                    <CheckCircle size={16} color="#4caf50" /> Initial Scan
                                </div>
                                {isRegenerating && (
                                    <>
                                        <ArrowRight size={16} style={{ opacity: 0.5 }} />
                                        <div className="glass-panel" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', borderColor: '#646cff' }}>
                                            <Loader2 size={16} className="loading-spinner" color="#646cff" /> Regeneration
                                        </div>
                                    </>
                                )}
                                {regeneratedData && (
                                    <>
                                        <ArrowRight size={16} style={{ opacity: 0.5 }} />
                                        <div className="glass-panel" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', borderColor: '#4caf50' }}>
                                            <CheckCircle size={16} color="#4caf50" /> Regeneration Complete
                                        </div>
                                    </>
                                )}
                            </div>
                        </div>

                        {/* Issues List */}
                        <div>
                            <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <AlertTriangle size={20} /> License Issues & Compatibility
                            </h3>

                            {displayData.issues && displayData.issues.length > 0 ? (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                                    {displayData.issues.map((issue, idx) => {
                                        // Find original issue if in comparison mode
                                        const originalIssue = isComparisonMode
                                            ? initialData.issues.find(i => i.file_path === issue.file_path)
                                            : null;

                                        const wasIncompatible = originalIssue && !originalIssue.compatible;
                                        const isNowCompatible = issue.compatible;
                                        const statusChanged = wasIncompatible && isNowCompatible;

                                        return (
                                            <div key={idx} className="glass-panel" style={{
                                                padding: '1.5rem',
                                                borderLeft: `4px solid ${issue.compatible ? '#4caf50' : '#f44336'}`
                                            }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                                                    <div>
                                                        <h4 style={{ margin: 0, fontSize: '1.1rem' }}>{issue.file_path}</h4>

                                                        {isComparisonMode && wasIncompatible ? (
                                                            <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                                                                <span style={{ opacity: 0.6, textDecoration: 'line-through' }}>{originalIssue.detected_license}</span>
                                                                <ArrowRight size={14} />
                                                                <span style={{
                                                                    padding: '0.2rem 0.6rem',
                                                                    borderRadius: '4px',
                                                                    background: 'rgba(76, 175, 80, 0.2)',
                                                                    color: '#4caf50',
                                                                    fontWeight: 'bold'
                                                                }}>
                                                                    {issue.detected_license} (Regenerated)
                                                                </span>
                                                            </div>
                                                        ) : (
                                                            <span style={{
                                                                fontSize: '0.9rem',
                                                                padding: '0.2rem 0.6rem',
                                                                borderRadius: '4px',
                                                                background: 'rgba(255,255,255,0.1)',
                                                                marginTop: '0.5rem',
                                                                display: 'inline-block'
                                                            }}>
                                                                Detected: {issue.detected_license}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <div style={{
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: '0.5rem',
                                                        color: issue.compatible ? '#4caf50' : '#f44336',
                                                        fontWeight: 'bold'
                                                    }}>
                                                        {issue.compatible ? <CheckCircle size={18} /> : <XCircle size={18} />}
                                                        {issue.compatible ? 'Compatible' : 'Incompatible'}
                                                    </div>
                                                </div>

                                                {issue.reason && (
                                                    <p style={{ fontSize: '0.95rem', opacity: 0.8, marginBottom: '1rem' }}>
                                                        {issue.reason}
                                                    </p>
                                                )}

                                                {issue.suggestion && (
                                                    <div style={{
                                                        background: 'rgba(100, 108, 255, 0.1)',
                                                        padding: '1rem',
                                                        borderRadius: '8px',
                                                        marginBottom: '1rem'
                                                    }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: '#646cff' }}>
                                                            <Lightbulb size={16} />
                                                            <span style={{ fontWeight: 'bold', fontSize: '0.9rem' }}>AI Suggestion</span>
                                                        </div>
                                                        <p style={{ margin: 0, fontSize: '0.9rem' }}>{issue.suggestion}</p>
                                                    </div>
                                                )}

                                                {issue.regenerated_code_path && (
                                                    <div style={{ marginTop: '1rem' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                                                            <Code size={16} />
                                                            <span style={{ fontWeight: 'bold', fontSize: '0.9rem' }}>Regenerated Code Available</span>
                                                        </div>
                                                        <pre style={{ maxHeight: '200px', overflowY: 'auto', fontSize: '0.85rem' }}>
                                                            {`Code regenerated at: ${issue.regenerated_code_path}`}
                                                        </pre>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            ) : (
                                <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center', opacity: 0.7 }}>
                                    <CheckCircle size={32} style={{ marginBottom: '1rem' }} />
                                    <p>No license issues found. All files appear to be compatible.</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Callback;
