import React, { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../../services/api';
import { BrandLogo } from '../../components/BrandLogo';
import { Loader2, CheckCircle, AlertCircle } from 'lucide-react';

export const AuthCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('processing');
  const [errorMessage, setErrorMessage] = useState(null);
  const hasRunRef = useRef(false);

  useEffect(() => {
    if (hasRunRef.current) return;
    hasRunRef.current = true;

    const handleOAuthCallback = async () => {
      const ticket = searchParams.get('ticket');
      const token = searchParams.get('token');
      const code = searchParams.get('code');
      const state = searchParams.get('state');
      const error = searchParams.get('error');

      // Immediately scrub parameters from the browser address bar to prevent replay on refresh
      window.history.replaceState({}, document.title, window.location.pathname);

      if (error) {
        setStatus('error');
        setErrorMessage(decodeURIComponent(error));
        return;
      }

      // Case 1: Received single-use authorization ticket (secure ticket exchange pattern)
      if (ticket) {
        try {
          const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
          const response = await fetch(`${baseUrl}/auth/exchange-ticket`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ ticket })
          });
          if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Failed to exchange authorization ticket.");
          }
          const data = await response.json();
          api.setToken(data.token);
          localStorage.setItem('aurelia_user', JSON.stringify(data.user));

          setStatus('success');
          setTimeout(() => {
            if (data.user?.onboardingComplete) {
              navigate('/app');
            } else {
              navigate('/onboarding');
            }
          }, 1200);
          return;
        } catch (err) {
          setStatus('error');
          setErrorMessage(err.message || "Failed to exchange ticket for session.");
          return;
        }
      }

      // Case 2: Direct session token fallback
      if (token) {
        try {
          api.setToken(token);
          const user = await api.getCurrentUser();
          localStorage.setItem('aurelia_user', JSON.stringify(user));
          setStatus('success');
          setTimeout(() => {
            if (user?.onboardingComplete) {
              navigate('/app');
            } else {
              navigate('/onboarding');
            }
          }, 1200);
          return;
        } catch (err) {
          setStatus('error');
          setErrorMessage(err.message || "Failed to establish user session.");
          return;
        }
      }

      // Case 3: Frontend received code to exchange with backend
      if (code) {
        try {
          const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
          const response = await fetch(`${baseUrl}/auth/google/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state || '')}`, {
            headers: {
              'Accept': 'application/json'
            }
          });
          if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Failed to exchange authorization code.");
          }
          const data = await response.json();
          api.setToken(data.token);
          localStorage.setItem('aurelia_user', JSON.stringify(data.user));
          setStatus('success');
          setTimeout(() => {
            if (data.user?.onboardingComplete) {
              navigate('/app');
            } else {
              navigate('/onboarding');
            }
          }, 1200);
        } catch (err) {
          setStatus('error');
          setErrorMessage(err.message || "OAuth processing failed.");
        }
        return;
      }

      setStatus('error');
      setErrorMessage("No authorization code or session ticket provided in callback.");
    };

    handleOAuthCallback();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-[#08090B] text-[#F5F3EE] flex items-center justify-center p-6 bg-grid">
      <div className="card-dark max-w-md w-full p-8 rounded-2xl bg-[#121418] border border-white/10 text-center space-y-6 shadow-2xl">
        <BrandLogo size="md" className="justify-center" />

        {status === 'processing' && (
          <div className="py-6 space-y-4">
            <Loader2 size={36} className="text-[#C59A55] animate-spin mx-auto" />
            <h2 className="text-lg font-semibold text-white">Validating Google Authorization...</h2>
            <p className="text-xs text-[#A1A4AA]">
              Verifying cryptographic state and retrieving user profile.
            </p>
          </div>
        )}

        {status === 'success' && (
          <div className="py-6 space-y-4 animate-in fade-in">
            <CheckCircle size={36} className="text-[#42D6A4] mx-auto" />
            <h2 className="text-lg font-semibold text-white">Identity Verified</h2>
            <p className="text-xs text-[#A1A4AA]">
              Launching your workspace...
            </p>
          </div>
        )}

        {status === 'error' && (
          <div className="py-6 space-y-4 animate-in fade-in">
            <AlertCircle size={36} className="text-[#F07878] mx-auto" />
            <h2 className="text-lg font-semibold text-white">Authentication Failed</h2>
            <p className="text-xs text-[#F07878] leading-relaxed">
              {errorMessage}
            </p>
            <div className="pt-4 flex justify-center">
              <button
                onClick={() => navigate('/auth')}
                className="btn-secondary text-xs"
              >
                Return to Sign In
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
