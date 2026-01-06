import React, { useState } from 'react';
import { Lightbulb, X, CheckCircle, ArrowRight } from 'lucide-react';
import axios from 'axios';

const LicenseSuggestionForm = ({ owner, repo, detectedLicenses = [], onClose, onSuggestionReceived }) => {
    const [loading, setLoading] = useState(false);
    const [suggestion, setSuggestion] = useState(null);

    const [formData, setFormData] = useState({
        owner: owner,
        repo: repo,
        commercial_use: true,
        modification: true,
        distribution: true,
        patent_grant: false,
        trademark_use: false,
        liability: false,
        copyleft: 'none',
        additional_requirements: '',
        detected_licenses: detectedLicenses
    });

    const handleCheckboxChange = (field) => {
        setFormData(prev => ({
            ...prev,
            [field]: !prev[field]
        }));
    };

    const handleCopyleftChange = (value) => {
        setFormData(prev => ({
            ...prev,
            copyleft: value
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);

        try {
            const response = await axios.post('http://localhost:8000/api/suggest-license', formData);
            setSuggestion(response.data);
            if (onSuggestionReceived) {
                onSuggestionReceived(response.data);
            }
        } catch (error) {
            console.error("License suggestion failed", error);
            alert("Failed to get license suggestion: " + (error.response?.data?.detail || error.message));
        } finally {
            setLoading(false);
        }
    };

    if (suggestion) {
        return (
            <div style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(0, 0, 0, 0.8)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
                padding: '2rem'
            }}>
                <div className="glass-panel" style={{
                    maxWidth: '600px',
                    width: '100%',
                    padding: '2rem',
                    position: 'relative',
                    maxHeight: '90vh',
                    overflowY: 'auto',
                    boxSizing: 'border-box',
                    overflowX: 'hidden'
                }}>
                    <button
                        onClick={onClose}
                        style={{
                            position: 'absolute',
                            top: '1rem',
                            right: '1rem',
                            background: 'transparent',
                            border: 'none',
                            cursor: 'pointer',
                            color: '#fff'
                        }}
                    >
                        <X size={24} />
                    </button>

                    <div style={{ textAlign: 'center', marginBottom: '2rem'}}>
                        <CheckCircle size={64} color="#219625ff" style={{ marginBottom: '1rem' }} />
                        <h2>License Suggestion</h2>
                    </div>

                    <div className="glass-panel" style={{
                        background: 'rgba(100, 108, 255, 0.1)',
                        borderColor: '#646cff',
                        padding: '1.5rem',
                        marginBottom: '1.5rem'
                    }}>
                        <h3 style={{ color: '#646cff', marginBottom: '0.5rem' }}>Recommended License</h3>
                        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '1rem' }}>
                            {suggestion.suggested_license}
                        </div>
                    </div>

                    <div style={{ marginBottom: '1.5rem' }}>
                        <h4 style={{ marginBottom: '0.5rem' }}>Explanation</h4>
                        <p style={{ opacity: 0.9, lineHeight: '1.6' }}>
                            {suggestion.explanation}
                        </p>
                    </div>

                    {suggestion.alternatives && suggestion.alternatives.length > 0 && (
                        <div style={{ marginBottom: '2rem' }}>
                            <h4 style={{ marginBottom: '0.5rem' }}>Alternative Options</h4>
                            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                {suggestion.alternatives.map((alt, idx) => (
                                    <span key={idx} className="glass-panel" style={{
                                        padding: '0.4rem 0.8rem',
                                        fontSize: '0.9rem',
                                        background: 'rgba(255, 255, 255, 0.05)'
                                    }}>
                                        {alt}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    <button
                        onClick={onClose}
                        className="glass-button"
                        style={{ width: '100%', padding: '1rem' }}
                    >
                        Close
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '2rem'
        }}>
            <div className="glass-panel" style={{
                maxWidth: '700px',
                width: '100%',
                padding: '2rem',
                position: 'relative',
                maxHeight: '90vh',
                overflowY: 'auto',
                boxSizing: 'border-box',
                overflowX: 'hidden'
            }}>
                <button
                    onClick={onClose}
                    style={{
                        position: 'absolute',
                        top: '1rem',
                        right: '1rem',
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        color: '#fff'
                    }}
                >
                    <X size={24} />
                </button>

                <div style={{ textAlign: 'center', marginBottom: '1rem'}}>
                    <Lightbulb size={64} color="#646cff" style={{ marginBottom: '0.3rem', marginTop: '0.5rem' }} />
                    <h2>License Recommendation</h2>
                    <p style={{ opacity: 0.8, marginTop: '0.5rem' }}>
                        No main license detected or unknown licenses found.
                        Please specify your requirements to get AI-powered license suggestions.
                    </p>
                </div>

                {/* Display detected licenses if any */}
                {detectedLicenses && detectedLicenses.length > 0 && (
                    <div className="glass-panel" style={{
                        background: 'rgba(100, 108, 255, 0.1)',
                        borderColor: '#646cff',
                        padding: '1rem',
                        marginBottom: '1.5rem'
                    }}>
                        <h4 style={{ marginBottom: '0.5rem', fontSize: '1.3rem', color: '#646cff', marginTop: '0.5rem'}}>
                            Existing Licenses Detected in Project
                        </h4>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                            {detectedLicenses.map((license, idx) => (
                                <span key={idx} style={{
                                    padding: '0.3rem 0.6rem',
                                    fontSize: '0.95rem',
                                    background: 'rgba(100, 108, 255, 0.2)',
                                    borderRadius: '4px',
                                    border: '1px solid rgba(100, 108, 255, 0.3)'
                                }}>
                                    {license}
                                </span>
                            ))}
                        </div>
                        <p style={{ fontSize: '0.9rem', opacity: 0.7, marginTop: '0.5rem', marginBottom: 0 }}>
                            The AI will recommend a license compatible with these existing licenses.
                        </p>
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div style={{ marginBottom: '2rem' }}>
                        <h3 style={{ marginBottom: '1rem', fontSize: '1.3rem' }}>Permissions & Requirements</h3>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={formData.commercial_use}
                                    onChange={() => handleCheckboxChange('commercial_use')}
                                    className="glass-checkbox"
                                />
                                <span>Commercial use allowed</span>
                            </label>

                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={formData.modification}
                                    onChange={() => handleCheckboxChange('modification')}
                                    className="glass-checkbox"
                                />
                                <span>Modification allowed</span>
                            </label>

                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={formData.distribution}
                                    onChange={() => handleCheckboxChange('distribution')}
                                    className="glass-checkbox"
                                />
                                <span>Distribution allowed</span>
                            </label>

                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={formData.patent_grant}
                                    onChange={() => handleCheckboxChange('patent_grant')}
                                    className="glass-checkbox"
                                />
                                <span>Patent grant required</span>
                            </label>

                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={formData.trademark_use}
                                    onChange={() => handleCheckboxChange('trademark_use')}
                                    className="glass-checkbox"
                                />
                                <span>Trademark use allowed</span>
                            </label>

                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={formData.liability}
                                    onChange={() => handleCheckboxChange('liability')}
                                    className="glass-checkbox"
                                />
                                <span>Liability protection needed</span>
                            </label>
                        </div>
                    </div>

                    <div style={{ marginBottom: '2rem' }}>
                        <h3 style={{ marginBottom: '1rem', fontSize: '1.3rem' }}>Copyleft Preference</h3>

                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                            {['none', 'weak', 'strong'].map((option) => (
                                <button
                                    key={option}
                                    type="button"
                                    onClick={() => handleCopyleftChange(option)}
                                    className="glass-button"
                                    style={{
                                        flex: 1,
                                        minWidth: '150px',
                                        background: formData.copyleft === option
                                            ? 'rgba(100, 108, 255, 0.3)'
                                            : 'rgba(255, 255, 255, 0.05)',
                                        borderColor: formData.copyleft === option ? '#646cff' : 'rgba(255, 255, 255, 0.1)'
                                    }}
                                >
                                    {option === 'none' && 'No Copyleft (Permissive)'}
                                    {option === 'weak' && 'Weak Copyleft (LGPL-style)'}
                                    {option === 'strong' && 'Strong Copyleft (GPL-style)'}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div style={{ marginBottom: '2rem' }}>
                        <h3 style={{ marginBottom: '1rem', fontSize: '1.2rem' }}>Additional Requirements (Optional)</h3>
                        <textarea
                            value={formData.additional_requirements}
                            onChange={(e) => setFormData(prev => ({ ...prev, additional_requirements: e.target.value }))}
                            placeholder="Any additional constraints or preferences..."
                            className="glass-input"
                            style={{
                                width: '94%',
                                minHeight: '100px',
                                resize: 'vertical',
                                fontFamily: 'inherit'
                            }}
                        />
                    </div>

                    <div style={{ display: 'flex', gap: '1rem' }}>
                        <button
                            type="button"
                            onClick={onClose}
                            className="glass-button"
                            style={{ flex: 1, background: 'rgba(255, 255, 255, 0.05)' }}
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="glass-button"
                            style={{ flex: 1 }}
                            disabled={loading}
                        >
                            {loading ? (
                                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                                    <div className="spin" style={{ width: 20, height: 20 }} />
                                    Getting Suggestion...
                                </span>
                            ) : (
                                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                                    Get Suggestion <ArrowRight size={20} />
                                </span>
                            )}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default LicenseSuggestionForm;

