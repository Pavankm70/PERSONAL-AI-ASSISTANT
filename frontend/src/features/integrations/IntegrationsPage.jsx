import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../../services/api';
import {
  Mail,
  Calendar,
  HardDrive,
  Search,
  CloudSun,
  Database,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Lock,
  ChevronDown,
  ChevronUp,
  Zap,
  ZapOff,
  ExternalLink
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────────────── */
/* Tiny toggle switch                                                   */
/* ─────────────────────────────────────────────────────────────────── */
const ToggleSwitch = ({ enabled, onChange, disabled }) => (
  <button
    type="button"
    role="switch"
    aria-checked={enabled}
    disabled={disabled}
    onClick={() => !disabled && onChange(!enabled)}
    className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
      enabled ? 'bg-[#C59A55]' : 'bg-[#2A2D35]'
    } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
  >
    <span
      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 ease-in-out ${
        enabled ? 'translate-x-4' : 'translate-x-0'
      }`}
    />
  </button>
);

/* ─────────────────────────────────────────────────────────────────── */
/* Status badge                                                         */
/* ─────────────────────────────────────────────────────────────────── */
const StatusBadge = ({ status }) => {
  const variants = {
    connected:     'bg-[#42D6A4]/10 text-[#42D6A4] border-[#42D6A4]/25',
    expired:       'bg-[#E6C17A]/10 text-[#E6C17A] border-[#E6C17A]/25',
    error:         'bg-[#F07878]/10 text-[#F07878] border-[#F07878]/25',
    not_connected: 'bg-[#181B20] text-[#696E78] border-white/5'
  };
  const labels = { connected: 'CONNECTED', expired: 'EXPIRED', error: 'ERROR', not_connected: 'NOT CONNECTED' };
  const dotColors = { connected: 'bg-[#42D6A4]', expired: 'bg-[#E6C17A]', error: 'bg-[#F07878]', not_connected: 'bg-[#696E78]' };
  const v = status in variants ? status : 'not_connected';
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-mono text-[10px] border ${variants[v]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotColors[v]}`} />
      {labels[v]}
    </span>
  );
};

/* ─────────────────────────────────────────────────────────────────── */
/* Provider icon                                                        */
/* ─────────────────────────────────────────────────────────────────── */
const ProviderIcon = ({ provider }) => {
  const icons = {
    gmail:      <Mail size={18} className="text-[#C59A55]" />,
    calendar:   <Calendar size={18} className="text-[#E6C17A]" />,
    drive:      <HardDrive size={18} className="text-[#82AFFF]" />,
    web_search: <Search size={18} className="text-[#42D6A4]" />,
    weather:    <CloudSun size={18} className="text-[#E6C17A]" />,
    rag:        <Database size={18} className="text-[#C59A55]" />,
    google:     <ShieldCheck size={18} className="text-[#C59A55]" />
  };
  return icons[provider] || <ShieldCheck size={18} className="text-[#C59A55]" />;
};

/* ─────────────────────────────────────────────────────────────────── */
/* Capability row                                                        */
/* ─────────────────────────────────────────────────────────────────── */
const CapabilityRow = ({ cap, onToggle, saving }) => (
  <div className="flex items-start gap-3 py-3 border-b border-white/5 last:border-0">
    <div className="flex-1 min-w-0">
      <p className="text-xs font-semibold text-white leading-tight">{cap.label}</p>
      <p className="text-[11px] text-[#696E78] mt-0.5 leading-relaxed">{cap.description}</p>
    </div>
    <ToggleSwitch enabled={cap.enabled} onChange={(val) => onToggle(cap.key, val)} disabled={saving} />
  </div>
);

/* ─────────────────────────────────────────────────────────────────── */
/* Integration card                                                     */
/* ─────────────────────────────────────────────────────────────────── */
const IntegrationCard = ({ item, onToggleConnect, actionLoading }) => {
  const [expanded, setExpanded] = useState(false);
  const [capSaving, setCapSaving] = useState(false);
  const [localCaps, setLocalCaps] = useState(item.supportedCapabilities || []);
  const [capError, setCapError] = useState(null);

  const hasCapabilities = localCaps.length > 0;
  const isConnected = item.status === 'connected';
  const isLoading = actionLoading === item.provider;
  const enabledCount = localCaps.filter(c => c.enabled).length;

  const handleToggleCap = useCallback(async (key, val) => {
    const prevCaps = [...localCaps];
    setLocalCaps(prev => prev.map(c => c.key === key ? { ...c, enabled: val } : c));
    setCapSaving(true);
    setCapError(null);
    try {
      const payload = {};
      localCaps.forEach(c => { payload[c.key] = c.key === key ? val : c.enabled; });
      await api.updateCapabilities(item.provider, payload);
    } catch {
      setLocalCaps(prevCaps);
      setCapError('Failed to save capability. Please try again.');
    } finally {
      setCapSaving(false);
    }
  }, [localCaps, item.provider]);

  return (
    <div className={`rounded-xl border flex flex-col transition-all duration-200 ${
      isConnected ? 'bg-[#0E1014] border-white/10 hover:border-white/20' : 'bg-[#0C0D11] border-white/5'
    }`}>
      {/* Card header */}
      <div className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="p-2.5 rounded-lg bg-[#08090B] border border-white/5">
            <ProviderIcon provider={item.provider} />
          </div>
          <StatusBadge status={item.status} />
        </div>
        <h3 className="text-base font-semibold text-white">{item.name}</h3>
        <p className="text-xs text-[#A1A4AA] mt-1 leading-relaxed">{item.description}</p>
        {item.accountEmail && (
          <div className="mt-3 text-[11px] font-mono text-[#696E78]">
            Authenticated as <span className="text-[#E6C17A]">{item.accountEmail}</span>
          </div>
        )}
        {item.errorMessage && (
          <div className="mt-3 p-2.5 rounded-lg bg-[#F07878]/10 border border-[#F07878]/25 text-[11px] text-[#F07878] flex items-start gap-1.5">
            <AlertCircle size={13} className="flex-shrink-0 mt-0.5" />
            <span>{item.errorMessage}</span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 pb-4 flex items-center justify-between border-t border-white/5 pt-3 mt-auto">
        {hasCapabilities && isConnected ? (
          <button
            onClick={() => setExpanded(e => !e)}
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[#A1A4AA] hover:text-white transition-colors"
          >
            {expanded ? <ZapOff size={12} /> : <Zap size={12} />}
            {enabledCount}/{localCaps.length} permissions
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        ) : (
          <span className="text-[10px] font-mono text-[#696E78] uppercase">
            {item.scopes?.[0]?.split('/').pop() || 'OAuth Scoped'}
          </span>
        )}

        {item.provider !== 'google' && item.provider !== 'rag' && (
          <button
            onClick={() => onToggleConnect(item.provider, item.status)}
            disabled={isLoading}
            className={`text-xs py-1.5 px-3 rounded-lg font-semibold transition-all ${
              isConnected
                ? 'bg-[#1E2028] text-[#A1A4AA] hover:bg-[#2A2D35] hover:text-white border border-white/10'
                : 'bg-[#C59A55] text-[#08090B] hover:bg-[#D4AA65]'
            }`}
          >
            {isLoading ? <RefreshCw size={13} className="animate-spin" /> : isConnected ? 'Disconnect' : 'Connect'}
          </button>
        )}
      </div>

      {/* Capability panel */}
      {expanded && hasCapabilities && isConnected && (
        <div className="px-5 pb-5 border-t border-white/5">
          <div className="mt-3 mb-1 flex items-center justify-between">
            <p className="text-[11px] font-semibold text-[#696E78] uppercase tracking-widest">Fine-Grained Permissions</p>
            {capSaving && <RefreshCw size={11} className="animate-spin text-[#C59A55]" />}
          </div>
          {localCaps.map(cap => (
            <CapabilityRow key={cap.key} cap={cap} onToggle={handleToggleCap} saving={capSaving} />
          ))}
          {capError && <p className="text-[11px] text-[#F07878] mt-2">{capError}</p>}
          <p className="text-[10px] text-[#696E78] mt-3 leading-relaxed">
            Toggles restrict what Aurelia AI may do within this session—they do not revoke your Google OAuth grant.
          </p>
        </div>
      )}
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────── */
/* Main page                                                            */
/* ─────────────────────────────────────────────────────────────────── */
export const IntegrationsPage = () => {
  const [searchParams] = useSearchParams();
  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [bannerMessage, setBannerMessage] = useState(null);
  const [bannerType, setBannerType] = useState('success');

  const fetchIntegrations = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getIntegrations();
      setIntegrations(data);
    } catch {
      setIntegrations([
        { id: 'int_google',   provider: 'google',     name: 'Google Identity',        description: 'Primary OAuth identity for authentication.', status: 'connected',     scopes: ['openid'],          accountEmail: 'user@example.com', capabilities: {}, supportedCapabilities: [] },
        { id: 'int_gmail',    provider: 'gmail',       name: 'Gmail Service',          description: 'Email reading, summarization, and secure sending.',   status: 'not_connected', scopes: ['gmail.readonly'],    capabilities: {}, supportedCapabilities: [] },
        { id: 'int_calendar', provider: 'calendar',    name: 'Google Calendar',        description: 'Agenda retrieval and confirmed event scheduling.',      status: 'not_connected', scopes: ['calendar.events'],   capabilities: {}, supportedCapabilities: [] },
        { id: 'int_drive',    provider: 'drive',       name: 'Google Drive',           description: 'Access and read documents in authorized Drive folders.', status: 'not_connected', scopes: ['drive.readonly'],    capabilities: {}, supportedCapabilities: [] },
        { id: 'int_rag',      provider: 'rag',         name: 'Personal Knowledge Base',description: 'Tenant-isolated vector store for uploaded documents.',   status: 'connected',     scopes: ['internal_pgvector'], capabilities: {}, supportedCapabilities: [] },
        { id: 'int_web',      provider: 'web_search',  name: 'Live Web Intelligence',  description: 'Fact retrieval and citation grounding from the web.',    status: 'connected',     scopes: ['tavily_search'],     capabilities: {}, supportedCapabilities: [] },
        { id: 'int_weather',  provider: 'weather',     name: 'Weather Telemetry',      description: 'Forecast data for scheduling and outdoor planning.',     status: 'connected',     scopes: ['openmeteo'],         capabilities: {}, supportedCapabilities: [] }
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIntegrations();
    const statusParam = searchParams.get('status');
    const providerParam = searchParams.get('provider');
    if (statusParam === 'connected' && providerParam) {
      setBannerType('success');
      setBannerMessage(`Successfully connected ${providerParam.toUpperCase()}.`);
      setTimeout(() => setBannerMessage(null), 5000);
    } else if (statusParam === 'error') {
      setBannerType('error');
      setBannerMessage(searchParams.get('message') || 'Connection failed. Please try again.');
      setTimeout(() => setBannerMessage(null), 8000);
    }
  }, [searchParams, fetchIntegrations]);

  const handleToggleConnect = async (provider, currentStatus) => {
    setActionLoading(provider);
    if (currentStatus === 'connected') {
      try {
        await api.disconnectIntegration(provider);
        setBannerType('success');
        setBannerMessage(`${provider.toUpperCase()} disconnected.`);
        setTimeout(() => setBannerMessage(null), 4000);
        await fetchIntegrations();
      } catch {
        setBannerType('error');
        setBannerMessage('Could not disconnect. Please try again.');
        setTimeout(() => setBannerMessage(null), 5000);
      }
      setActionLoading(null);
    } else {
      if (['gmail', 'calendar', 'drive', 'google'].includes(provider)) {
        window.location.href = api.getGoogleConnectUrl(provider);
        return;
      }
      setActionLoading(null);
    }
  };

  const connectedCount = integrations.filter(i => i.status === 'connected').length;
  const googleServices = integrations.filter(i => ['gmail', 'calendar', 'drive'].includes(i.provider));
  const googleConnected = googleServices.filter(i => i.status === 'connected').length;
  const needsAction = integrations.filter(i => i.errorMessage).length;

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Connected Integrations &amp; Permissions
          </h1>
          <p className="text-xs sm:text-sm text-[#A1A4AA] mt-1">
            Every external connection requires explicit authorization. Toggle individual capabilities anytime.
          </p>
        </div>
        <button
          onClick={fetchIntegrations}
          disabled={loading}
          className="p-2 rounded-lg border border-white/10 text-[#A1A4AA] hover:text-white hover:border-white/20 transition-colors"
          title="Refresh status"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Banner */}
      {bannerMessage && (
        <div className={`p-4 rounded-xl border text-xs sm:text-sm flex items-center gap-3 ${
          bannerType === 'success'
            ? 'bg-[#42D6A4]/10 border-[#42D6A4]/30 text-[#42D6A4]'
            : 'bg-[#F07878]/10 border-[#F07878]/30 text-[#F07878]'
        }`}>
          {bannerType === 'success'
            ? <CheckCircle2 size={18} className="flex-shrink-0" />
            : <AlertCircle size={18} className="flex-shrink-0" />}
          <span>{bannerMessage}</span>
        </div>
      )}

      {/* Stats */}
      {!loading && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Total Active',     value: connectedCount, suffix: `/ ${integrations.length}` },
            { label: 'Google Services',  value: googleConnected, suffix: `/ ${googleServices.length}` },
            { label: 'Requiring Action', value: needsAction,     suffix: null }
          ].map(s => (
            <div key={s.label} className="bg-[#0E1014] border border-white/8 rounded-xl p-4">
              <p className="text-[11px] font-mono text-[#696E78] uppercase tracking-widest">{s.label}</p>
              <p className="text-2xl font-bold text-white mt-1">
                {s.value}
                {s.suffix && <span className="text-sm text-[#696E78] font-normal"> {s.suffix}</span>}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Security notice */}
      <div className="p-4 rounded-xl bg-[#0E1014] border border-white/8 flex items-center gap-3 text-xs text-[#A1A4AA]">
        <Lock size={15} className="text-[#C59A55] flex-shrink-0" />
        <span>
          OAuth tokens are encrypted with AES-256-GCM at rest. Client secrets are never sent to the browser.
          Capability toggles restrict what Aurelia AI may do without revoking your Google authorization.
        </span>
      </div>

      {/* Cards */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-white/5 bg-[#0C0D11] h-44 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {integrations.map(item => (
            <IntegrationCard
              key={item.id}
              item={item}
              onToggleConnect={handleToggleConnect}
              actionLoading={actionLoading}
            />
          ))}
        </div>
      )}

      {/* Google hint */}
      {!loading && googleConnected < googleServices.length && (
        <div className="p-4 rounded-xl bg-[#0E1014] border border-[#C59A55]/20 flex items-start gap-3 text-xs text-[#A1A4AA]">
          <ExternalLink size={15} className="text-[#C59A55] flex-shrink-0 mt-0.5" />
          <span>
            Connect Gmail, Calendar, and Drive to unlock the full Aurelia AI experience — manage your schedule,
            emails, and documents through natural conversation.
          </span>
        </div>
      )}
    </div>
  );
};
