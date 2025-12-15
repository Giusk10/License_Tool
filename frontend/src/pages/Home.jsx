import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Github, ArrowRight, Upload } from 'lucide-react';
import axios from 'axios';

const Home = () => {
    const [owner, setOwner] = useState('');
    const [repo, setRepo] = useState('');
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const navigate = useNavigate();
    const fileInputRef = React.useRef(null);

    const handleAnalyze = (e) => {
        e.preventDefault();
        if (!owner || !repo) return;

        setLoading(true);
        // Redirect to backend auth start endpoint
        // Using window.location.href to navigate to the backend URL
        const backendUrl = 'http://localhost:8000/api/auth/start';
        window.location.href = `${backendUrl}?owner=${owner}&repo=${repo}`;
    };

    const handleUploadClick = () => {
        if (!owner || !repo) {
            alert("Please enter Owner and Repository name first.");
            return;
        }
        fileInputRef.current.click();
    };

    const handleFileChange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploading(true);
        const formData = new FormData();
        formData.append('owner', owner);
        formData.append('repo', repo);
        formData.append('uploaded_file', file);

        try {
            const response = await axios.post('http://localhost:8000/api/zip', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });

            navigate('/callback', {
                state: {
                    cloneData: response.data,
                    source: 'upload'
                }
            });
        } catch (error) {
            console.error("Upload failed", error);
            alert("Upload failed: " + (error.response?.data?.detail || error.message));
            setUploading(false);
        }
    };

    if (uploading) {
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
                    <h2>Uploading Repository...</h2>
                    <p>Please wait while we upload and process the repository.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="container">
            <div className="glass-panel form-group">
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0.2rem', marginTop: '1rem' }}>
                    <Github size={62} color="#fff" />
                </div>
                <h1 style={{ fontSize: '3.5rem', marginBottom: '0.5rem' }}>License Checker</h1>
                <p style={{ fontSize: '1.12rem', marginBottom: '2rem' }}>Analyze GitHub repositories for license compatibility.</p>

                <form onSubmit={handleAnalyze} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%' }}>
                    <input
                        type="text"
                        size={13}
                        placeholder="GitHub Owner (e.g. facebook)"
                        value={owner}
                        onChange={(e) => setOwner(e.target.value)}
                        className="glass-input"
                        required
                    />
                    <input
                        type="text"
                        size={13}
                        placeholder="Repository Name (e.g. react)"
                        value={repo}
                        onChange={(e) => setRepo(e.target.value)}
                        className="glass-input"
                        required
                    />

                    <input
                        type="file"
                        ref={fileInputRef}
                        style={{ display: 'none' }}
                        accept=".zip"
                        onChange={handleFileChange}
                    />

                    <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                        <button type="submit" className="glass-button" style={{ flex: 1 }} disabled={loading}>
                            {loading ? 'Redirecting...' : (
                                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                                    Clone Repository <ArrowRight size={16} />
                                </span>
                            )}
                        </button>
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

