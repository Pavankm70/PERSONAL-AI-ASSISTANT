import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { BrandLogo } from '../../components/BrandLogo';
import { BRAND_CONFIG } from '../../config/brand';
import { api } from '../../services/api';
import { ShieldCheck, ArrowRight, Loader2, Sparkles, AlertCircle } from 'lucide-react';

export const AuthPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const mode = searchParams.get('mode') || 'signin';

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [demoEmail, setDemoEmail] = useState('alex.chen@university.edu');
  const [demoName, setDemoName] = useState('Alex Chen');

  const handleGoogleSignIn = () => {
    setLoading(true);
    setError(null);
    try {
      // Start real backend Google OAuth flow
      const url = api.getGoogleOAuthUrl('identity');
      window.location.href = url;
    } catch (err) {
      setError("Unable to initiate Google OAuth. You can use the Quick Development Sign-In below.");
      setLoading(false);
    }
  };

  const handleDevLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.devLogin(demoEmail, demoName);
      navigate('/onboarding');
    } catch (err) {
      setError(err.message || 'Dev login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#08090B] text-[#F5F3EE] flex flex-col justify-between p-6 bg-grid relative overflow-hidden">
      {/* Ambient background glow */}
      <div className="ambient-glow top-1/4 left-1/2 -translate-x-1/2 opacity-70" />

      {/* Top Header */}
      <div className="container mx-auto flex items-center justify-between z-10">
        <button
          onClick={() => navigate('/')}
          className="bg-transparent border-0 cursor-pointer"
        >
          <BrandLogo size="md" />
        </button>
        <button
          onClick={() => navigate('/')}
          className="btn-ghost text-xs"
        >
          Back to overview
        </button>
      </div>

      {/* Center Auth Card */}
      <div className="container mx-auto max-w-md w-full my-12 z-10">
        <div className="card-dark p-8 rounded-2xl bg-[#121418] border border-white/10 shadow-2xl space-y-6">
          <div className="text-center space-y-2">
            <div className="w-12 h-12 rounded-xl bg-[#181B20] border border-[#C59A55]/30 flex items-center justify-center mx-auto text-[#E6C17A]">
              <Sparkles size={22} />
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Welcome to your workspace
            </h1>
            <p className="text-xs text-[#A1A4AA]">
              {mode === 'signup'
                ? "Request access to your personal intelligence ecosystem."
                : "Sign in with your Google account to access your assistant."}
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-[#F07878]/10 border border-[#F07878]/30 text-xs text-[#F07878] flex items-center gap-2">
              <AlertCircle size={15} className="flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Primary Action: Google OAuth Button */}
          <button
            onClick={handleGoogleSignIn}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-xl bg-[#181B20] hover:bg-[#22262D] border border-white/15 text-white font-medium text-sm transition-all shadow-sm hover:border-[#C59A55]/40"
          >
            {/* Google Icon */}
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.4 7.36 24 12 24Z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15Z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.36 0 3.26 2.6 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98Z"
              />
            </svg>
            <span>Continue with Google</span>
          </button>

          <div className="relative flex py-2 items-center">
            <div className="flex-grow border-t border-white/10" />
            <span className="flex-shrink mx-3 text-[10px] font-mono text-[#696E78] uppercase">
              Or Local / Dev Preview
            </span>
            <div className="flex-grow border-t border-white/10" />
          </div>

          {/* Quick Dev Preview Sign-In (No real credentials required to test) */}
          <form onSubmit={handleDevLogin} className="space-y-3">
            <div>
              <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">
                Demo User Name
              </label>
              <input
                type="text"
                value={demoName}
                onChange={(e) => setDemoName(e.target.value)}
                className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">
                Demo Email
              </label>
              <input
                type="email"
                value={demoEmail}
                onChange={(e) => setDemoEmail(e.target.value)}
                className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-bronze w-full py-2.5 text-xs font-semibold justify-center"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Entering Workspace...</span>
                </>
              ) : (
                <>
                  <span>Enter Application</span>
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </form>

          {/* Privacy and Least Privilege Notice */}
          <div className="pt-2 border-t border-white/5 space-y-2 text-[11px] text-[#696E78] leading-normal">
            <div className="flex items-start gap-2">
              <ShieldCheck size={14} className="text-[#C59A55] mt-0.5 flex-shrink-0" />
              <span>
                Initial sign-in verifies identity only. Additional Gmail, Calendar, and Drive permissions are requested via explicit consent during onboarding.
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Footer */}
      <div className="container mx-auto text-center text-xs text-[#696E78] z-10">
        <span>{BRAND_CONFIG.name} — Protected by server-side token encryption</span>
      </div>
    </div>
  );
};
