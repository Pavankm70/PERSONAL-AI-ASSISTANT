import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { 
  Mail, 
  Search, 
  Filter, 
  ExternalLink, 
  Sparkles, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  RefreshCw,
  Star,
  ChevronRight,
  Paperclip,
  Send
} from 'lucide-react';
import { formatDateForDisplay, getEffectiveTimezone } from '../../utils/dateUtils';

export const InboxPage = () => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [connected, setConnected] = useState(true);
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [summarizing, setSummarizing] = useState(false);
  const [timezone, setTimezone] = useState('UTC');

  useEffect(() => {
    api.getCurrentUser().then((u) => {
      if (u?.timezone) setTimezone(u.timezone);
    }).catch(() => {});
  }, []);

  const fetchMessages = async () => {
    setLoading(true);
    try {
      const data = await api.getGmailMessages(filter);
      setMessages(data);
      setConnected(true);
      if (data.length > 0 && !selectedMessage) {
        setSelectedMessage(data[0]);
      }
    } catch (err) {
      // Check if integration is not connected
      setConnected(false);
      setMessages([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMessages();
  }, [filter]);

  const handleSummarize = async (msgId) => {
    setSummarizing(true);
    try {
      const result = await api.summarizeThread(msgId);
      setSelectedMessage((prev) => ({
        ...prev,
        summary: result.summary,
        actionItems: result.actionItems
      }));
    } catch (e) {
      setSelectedMessage((prev) => ({
        ...prev,
        summary: `Unable to summarize email: ${e.message || 'Please check your connection and try again.'}`,
        actionItems: []
      }));
    } finally {
      setSummarizing(false);
    }
  };

  const filteredMessages = messages.filter((m) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      m.subject.toLowerCase().includes(q) ||
      m.fromName.toLowerCase().includes(q) ||
      m.snippet.toLowerCase().includes(q)
    );
  });

  if (!connected && !loading) {
    return (
      <div className="p-8 max-w-2xl mx-auto my-12 text-center space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-[#121418] border border-white/10 flex items-center justify-center mx-auto text-[#C59A55]">
          <Mail size={32} />
        </div>
        <div className="space-y-2">
          <h2 className="text-xl font-bold text-white">Gmail Integration Not Connected</h2>
          <p className="text-xs sm:text-sm text-[#A1A4AA] max-w-md mx-auto">
            Authorize your Google account to grant read-only intelligence access to your emails. Aurelia will extract priority messages and action items.
          </p>
        </div>
        <div className="flex justify-center gap-3">
          <a
            href={api.getGoogleOAuthUrl('gmail')}
            className="btn-bronze text-xs py-2.5 px-6"
          >
            Connect Authorized Gmail Account
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#08090B]">
      {/* Top Filter and Search Bar */}
      <div className="p-4 border-b border-white/5 bg-[#0D0F12] flex flex-wrap items-center justify-between gap-4">
        {/* Search */}
        <div className="flex items-center gap-2 bg-[#121418] border border-white/10 rounded-lg px-3 py-1.5 w-full sm:w-72">
          <Search size={14} className="text-[#696E78]" />
          <input
            type="text"
            placeholder="Search email threads..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-transparent text-xs text-white focus:outline-none"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full">
          {[
            { id: 'all', label: 'All' },
            { id: 'today', label: 'Today' },
            { id: 'unread', label: 'Unread' },
            { id: 'read', label: 'Read' },
            { id: 'starred', label: 'Starred' },
            { id: 'important', label: 'Important' },
            { id: 'attachments', label: 'Attachments' },
            { id: 'sent', label: 'Sent' },
            { id: 'week', label: 'This Week' },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                filter === f.id
                  ? 'bg-[#C59A55] text-black font-semibold'
                  : 'bg-[#121418] border border-white/10 text-[#A1A4AA] hover:text-white'
              }`}
            >
              {f.label}
            </button>
          ))}
          <button
            onClick={fetchMessages}
            className="p-1.5 rounded-lg text-[#696E78] hover:text-white transition-colors"
            title="Refresh inbox"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Main Inbox 2-Pane View */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-12 overflow-hidden">
        {/* Message List */}
        <div className="md:col-span-5 border-r border-white/5 overflow-y-auto divide-y divide-white/5">
          {loading ? (
            <div className="p-8 text-center text-xs text-[#696E78]">
              Retrieving inbox intelligence...
            </div>
          ) : filteredMessages.length === 0 ? (
            <div className="p-8 text-center text-xs text-[#696E78]">
              No messages found matching "{filter}".
            </div>
          ) : (
            filteredMessages.map((msg) => {
              const isSelected = selectedMessage?.id === msg.id;
              return (
                <div
                  key={msg.id}
                  onClick={() => setSelectedMessage(msg)}
                  className={`p-4 cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-[#181B20] border-l-2 border-[#C59A55]'
                      : 'hover:bg-[#121418]'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-semibold text-white truncate max-w-[160px]">
                      {msg.fromName}
                    </span>
                    <span className="text-[10px] font-mono text-[#696E78]">
                      {formatDateForDisplay(msg.date, timezone, 'short')}
                    </span>
                  </div>

                  <div className="text-xs text-white font-medium truncate mb-1">
                    {msg.subject}
                  </div>

                  <div className="text-[11px] text-[#A1A4AA] line-clamp-2">
                    {msg.snippet}
                  </div>

                  <div className="mt-2 flex items-center gap-2">
                    {msg.isImportant && (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#E6C17A]/15 text-[#E6C17A] border border-[#E6C17A]/30">
                        Gmail Important
                      </span>
                    )}
                    {msg.aiPriority === 'high' && (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#42D6A4]/15 text-[#42D6A4] border border-[#42D6A4]/30 flex items-center gap-1">
                        <Sparkles size={9} />
                        AI Priority
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Selected Message Detail & AI Summary View */}
        <div className="md:col-span-7 bg-[#08090B] p-6 overflow-y-auto">
          {selectedMessage ? (
            <div className="space-y-6 max-w-2xl">
              {/* Header */}
              <div className="space-y-2 pb-4 border-b border-white/5">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-mono text-[#C59A55]">
                    THREAD ID: {selectedMessage.threadId || selectedMessage.id}
                  </div>
                  {selectedMessage.gmailLink && (
                    <a
                      href={selectedMessage.gmailLink}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-[#82AFFF] hover:underline flex items-center gap-1"
                    >
                      <span>Open in Gmail</span>
                      <ExternalLink size={12} />
                    </a>
                  )}
                </div>

                <h2 className="text-lg font-bold text-white">
                  {selectedMessage.subject}
                </h2>

                <div className="text-xs text-[#A1A4AA] flex items-center justify-between">
                  <div>
                    From: <span className="text-white font-medium">{selectedMessage.fromName}</span> &lt;{selectedMessage.fromEmail}&gt;
                  </div>
                  <div className="font-mono text-[11px] text-[#696E78]">
                    {formatDateForDisplay(selectedMessage.date, timezone, 'long')}
                  </div>
                </div>
              </div>

              {/* AI Summary Card */}
              <div className="p-4 rounded-xl bg-[#121418] border border-[#C59A55]/30 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#E6C17A]">
                    <Sparkles size={15} />
                    <span>Aurelia Email Intelligence</span>
                  </div>
                  <button
                    onClick={() => handleSummarize(selectedMessage.id)}
                    disabled={summarizing}
                    className="text-[10px] font-mono text-[#C59A55] hover:underline"
                  >
                    {summarizing ? 'Analyzing...' : 'Re-summarize'}
                  </button>
                </div>

                <p className="text-xs sm:text-sm text-[#F5F3EE] leading-relaxed">
                  {selectedMessage.summary || selectedMessage.snippet}
                </p>

                {selectedMessage.actionItems && selectedMessage.actionItems.length > 0 && (
                  <div className="pt-2 border-t border-white/5 space-y-1">
                    <div className="text-[10px] font-mono uppercase text-[#42D6A4]">Action Items Detected:</div>
                    {selectedMessage.actionItems.map((item, idx) => (
                      <div key={idx} className="flex items-start gap-2 text-xs text-[#A1A4AA]">
                        <CheckCircle2 size={12} className="text-[#42D6A4] mt-0.5 flex-shrink-0" />
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Message Content Snippet */}
              <div className="p-5 rounded-xl bg-[#0D0F12] border border-white/5 text-xs sm:text-sm text-[#A1A4AA] leading-relaxed space-y-3">
                <div className="text-[10px] font-mono uppercase text-[#696E78]">Original Snippet:</div>
                <p className="text-white">{selectedMessage.snippet}</p>
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-[#696E78]">
              Select an email from the left pane to view intelligence.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
