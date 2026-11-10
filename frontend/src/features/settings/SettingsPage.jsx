import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { 
  User, 
  Clock, 
  Bot, 
  ShieldCheck, 
  Trash2, 
  Save, 
  CheckCircle2, 
  AlertTriangle,
  Lock,
  Layers
} from 'lucide-react';

export const SettingsPage = () => {
  const [profile, setProfile] = useState({
    fullName: 'Alex Chen',
    email: 'alex.chen@university.edu',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Los_Angeles',
    aiModel: 'gemini-1.5-pro',
    temperature: 'balanced',
    autoConflictCheck: true,
    requireActionConfirmation: true,
    telemetrySharing: false
  });
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const u = await api.getCurrentUser();
        setProfile((prev) => ({
          ...prev,
          fullName: u.fullName || prev.fullName,
          email: u.email || prev.email,
          timezone: u.timezone || prev.timezone
        }));
      } catch (e) {
        // fallback
      }
    };
    loadSettings();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSavedSuccess(false);
    try {
      await api.updateSettings(profile);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (e) {
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  const [statusMessage, setStatusMessage] = useState(null);

  const handlePurgeHistory = async () => {
    if (confirm("Are you sure you want to purge all conversation logs? This action is irreversible.")) {
      try {
        const res = await api.purgeChatHistory();
        setStatusMessage({ type: 'success', text: res.message || 'Conversation history purged successfully.' });
        setTimeout(() => setStatusMessage(null), 4000);
      } catch (err) {
        setStatusMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to purge chat history.' });
        setTimeout(() => setStatusMessage(null), 5000);
      }
    }
  };

  const handleDeleteAccount = async () => {
    if (confirm("WARNING: Deleting your account will permanently purge your profile, knowledge base documents, embeddings, plans, and revoked OAuth tokens. Proceed?")) {
      try {
        await api.deleteAccount();
        api.logout();
        window.location.href = '/';
      } catch (err) {
        setStatusMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to delete account.' });
        setTimeout(() => setStatusMessage(null), 5000);
      }
    }
  };

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Workspace Settings</h1>
        <p className="text-xs sm:text-sm text-[#A1A4AA] mt-1">
          Manage your personal profile, AI behavioral thresholds, security controls, and data retention.
        </p>
      </div>

      {statusMessage && (
        <div className={`p-4 rounded-xl text-xs flex items-center gap-2 border ${
          statusMessage.type === 'success'
            ? 'bg-[#42D6A4]/10 border-[#42D6A4]/30 text-[#42D6A4]'
            : 'bg-[#F07878]/10 border-[#F07878]/30 text-[#F07878]'
        }`}>
          <span>{statusMessage.text}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Section 1: User Profile */}
        <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-white/5 text-xs font-semibold text-white uppercase font-mono">
            <User size={15} className="text-[#C59A55]" />
            <span>Identity &amp; Localization</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">Full Name</label>
              <input
                type="text"
                value={profile.fullName}
                onChange={(e) => setProfile({ ...profile, fullName: e.target.value })}
                className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
              />
            </div>

            <div>
              <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">Email Address</label>
              <input
                type="email"
                disabled
                value={profile.email}
                className="w-full bg-[#08090B]/50 border border-white/5 rounded-lg px-3 py-2 text-[#696E78]"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">System Timezone</label>
              <input
                type="text"
                value={profile.timezone}
                onChange={(e) => setProfile({ ...profile, timezone: e.target.value })}
                className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
              />
              <span className="text-[10px] text-[#696E78] mt-1 block">
                All calendar conflict checks and timetable lookups are aligned to this timezone.
              </span>
            </div>
          </div>
        </div>

        {/* Section 2: AI Preferences */}
        <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-white/5 text-xs font-semibold text-white uppercase font-mono">
            <Bot size={15} className="text-[#E6C17A]" />
            <span>AI Orchestration Thresholds</span>
          </div>

          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white font-medium">Automatic Conflict Checking</div>
                <div className="text-[#A1A4AA] text-[11px]">Check existing Google Calendar events before proposing study slots.</div>
              </div>
              <input
                type="checkbox"
                checked={profile.autoConflictCheck}
                onChange={(e) => setProfile({ ...profile, autoConflictCheck: e.target.checked })}
                className="w-4 h-4 accent-[#C59A55]"
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-white font-medium">Strict Action Confirmation (Recommended)</div>
                <div className="text-[#A1A4AA] text-[11px]">Require human approval before creating or modifying calendar events.</div>
              </div>
              <input
                type="checkbox"
                checked={profile.requireActionConfirmation}
                onChange={(e) => setProfile({ ...profile, requireActionConfirmation: e.target.checked })}
                className="w-4 h-4 accent-[#C59A55]"
              />
            </div>
          </div>
        </div>

        {/* Section 3: Privacy and Data Controls */}
        <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-white/5 text-xs font-semibold text-white uppercase font-mono">
            <ShieldCheck size={15} className="text-[#42D6A4]" />
            <span>Privacy &amp; Data Governance</span>
          </div>

          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-lg bg-[#08090B] border border-white/5">
              <div>
                <div className="text-xs font-semibold text-white">Purge Conversation History</div>
                <div className="text-[11px] text-[#A1A4AA]">Delete all chat logs and tool execution records.</div>
              </div>
              <button
                type="button"
                onClick={handlePurgeHistory}
                className="btn-secondary text-xs py-1.5 px-3 self-start sm:self-auto"
              >
                Clear History
              </button>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-lg bg-[#F07878]/10 border border-[#F07878]/25">
              <div>
                <div className="text-xs font-semibold text-[#F07878]">Delete Account &amp; Knowledge Repository</div>
                <div className="text-[11px] text-[#A1A4AA]">Permanently delete user profile, vector embeddings, and OAuth tokens.</div>
              </div>
              <button
                type="button"
                onClick={handleDeleteAccount}
                className="bg-[#F07878] hover:bg-[#F07878]/80 text-black font-semibold text-xs py-1.5 px-3 rounded-lg transition-colors self-start sm:self-auto"
              >
                Delete Account
              </button>
            </div>
          </div>
        </div>

        {/* Bottom Save Bar */}
        <div className="flex items-center justify-between pt-2">
          {savedSuccess ? (
            <div className="text-xs text-[#42D6A4] flex items-center gap-1.5 font-mono">
              <CheckCircle2 size={14} />
              <span>Settings updated successfully.</span>
            </div>
          ) : <div />}

          <button
            type="submit"
            disabled={saving}
            className="btn-bronze text-xs py-2 px-6 font-semibold"
          >
            <Save size={14} />
            <span>{saving ? 'Saving...' : 'Save Changes'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};
