import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../../services/api';
import { 
  Bot, 
  Send, 
  Sparkles, 
  CheckCircle2, 
  FileText, 
  Calendar, 
  Mail, 
  ExternalLink, 
  Paperclip, 
  Loader2, 
  AlertCircle,
  Clock,
  ShieldCheck,
  Check,
  Plus,
  MessageSquare,
  ChevronDown,
  ArrowDown,
  Square
} from 'lucide-react';

export const ChatPage = () => {
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get('q') || '';

  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(() => {
    return localStorage.getItem('aurelia_active_conv_id') || null;
  });

  const [messages, setMessages] = useState([
    {
      id: 'm_welcome',
      role: 'assistant',
      content: "Good evening. What would you like to organize today? I can review your inbox, check your schedule, extract facts from your uploaded documents, or assemble a study plan.",
      createdAt: new Date().toISOString()
    }
  ]);
  const [input, setInput] = useState(initialQuery);
  const [loading, setLoading] = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const [chatError, setChatError] = useState(null);
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const messagesEndRef = useRef(null);
  const chatContainerRef = useRef(null);
  const isAtBottomRef = useRef(true);
  const abortControllerRef = useRef(null);

  const suggestedPrompts = [
    "Summarize my uploaded resume.",
    "What is on my calendar tomorrow?",
    "Find my next MSc class in my notes.",
    "Help me plan my study week.",
    "What is the weather in Bengaluru today?"
  ];

  const scrollToBottom = (behavior = 'smooth') => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior });
    }
    isAtBottomRef.current = true;
    setShowJumpToLatest(false);
  };

  const handleScroll = () => {
    const container = chatContainerRef.current;
    if (!container) return;
    const threshold = 80;
    const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const atBottom = distanceToBottom <= threshold;
    isAtBottomRef.current = atBottom;
    if (atBottom) {
      setShowJumpToLatest(false);
    } else {
      setShowJumpToLatest(true);
    }
  };

  const handleJumpToLatest = () => {
    isAtBottomRef.current = true;
    setShowJumpToLatest(false);
    scrollToBottom('smooth');
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
    setActiveTool(null);
  };

  // Follow incoming responses only when user is already near bottom
  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollToBottom('smooth');
    }
  }, [messages, activeTool]);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Load user's conversations and restore active conversation history
  const loadConversations = async (targetIdToSelect = null) => {
    try {
      const convList = await api.getConversations();
      setConversations(convList);

      const targetId = targetIdToSelect || activeConversationId || (convList.length > 0 ? convList[0].id : null);
      if (targetId) {
        const found = convList.find(c => c.id === targetId);
        if (found || targetIdToSelect) {
          try {
            const convData = await api.getConversation(targetId);
            if (convData && convData.messages && convData.messages.length > 0) {
              setMessages(convData.messages);
              setActiveConversationId(targetId);
              localStorage.setItem('aurelia_active_conv_id', targetId);
              return;
            }
          } catch (e) {
            // fallback
          }
        } else {
          setActiveConversationId(null);
          localStorage.removeItem('aurelia_active_conv_id');
        }
      }
    } catch (e) {
      // offline / unauthenticated
    }
  };

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (initialQuery) {
      handleSendMessage(initialQuery);
    }
  }, []);

  const handleSelectConversation = async (convId) => {
    try {
      setLoading(true);
      const convData = await api.getConversation(convId);
      if (convData && convData.messages) {
        setMessages(convData.messages.length > 0 ? convData.messages : [
          {
            id: 'm_welcome',
            role: 'assistant',
            content: `Conversation "${convData.title}" loaded. How can I assist you?`,
            createdAt: new Date().toISOString()
          }
        ]);
        setActiveConversationId(convId);
        localStorage.setItem('aurelia_active_conv_id', convId);
      }
    } catch (err) {
      // ignore
    } finally {
      setLoading(false);
      setShowHistoryDrawer(false);
    }
  };

  const handleStartNewChat = () => {
    setActiveConversationId(null);
    localStorage.removeItem('aurelia_active_conv_id');
    setMessages([
      {
        id: `m_welcome_${Date.now()}`,
        role: 'assistant',
        content: "New conversation started. Ask me about your uploaded documents, schedule, emails, or academic targets.",
        createdAt: new Date().toISOString()
      }
    ]);
    setShowHistoryDrawer(false);
  };

  const handleSendMessage = async (textToSend) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    setChatError(null);
    setInput('');
    const userMsg = {
      id: `usr_${Date.now()}`,
      role: 'user',
      content: query,
      createdAt: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    // Automatically follow user submission to the bottom
    isAtBottomRef.current = true;
    setShowJumpToLatest(false);
    setTimeout(() => scrollToBottom('smooth'), 50);

    const lower = query.toLowerCase();
    if (lower.includes('email') || lower.includes('inbox') || lower.includes('mail')) {
      setActiveTool("Querying authorized Gmail stream...");
    } else if (lower.includes('calendar') || lower.includes('schedule') || lower.includes('tomorrow')) {
      setActiveTool("Retrieving Google Calendar events & conflict checking...");
    } else if (lower.includes('class') || lower.includes('timetable') || lower.includes('msc')) {
      setActiveTool("Querying structured timetable records & document chunks...");
    } else if (lower.includes('weather') || lower.includes('temperature')) {
      setActiveTool("Fetching real-time Open-Meteo weather telemetry...");
    } else if (lower.includes('resume') || lower.includes('document') || lower.includes('pdf') || lower.includes('notes')) {
      setActiveTool("Analyzing Knowledge Base document chunks...");
    } else {
      setActiveTool("Consulting personal knowledge vector index...");
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await api.sendMessage(query, activeConversationId, { signal: controller.signal });
      setActiveTool(null);
      setMessages((prev) => [...prev, response]);

      if (response.conversationId && response.conversationId !== activeConversationId) {
        setActiveConversationId(response.conversationId);
        localStorage.setItem('aurelia_active_conv_id', response.conversationId);
        // Refresh conversations list
        api.getConversations().then(setConversations).catch(() => {});
      }
    } catch (err) {
      if (err.name === 'AbortError' || controller.signal.aborted) {
        // Request cancelled by user via Stop button — clean exit without error toast
        return;
      }
      setActiveTool(null);
      // DO NOT persist or display the error as a successful assistant message!
      let msg = err.message || 'Service temporarily unavailable.';
      if (!msg || msg === 'Failed to fetch' || msg.toLowerCase().includes('failed to fetch')) {
        msg = 'Unable to connect to Aurelia backend server. Please verify the backend is running on port 8000.';
      }
      setChatError({
        message: msg,
        query: query
      });
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setLoading(false);
      setActiveTool(null);
    }
  };

  const handleConfirmAction = async (msgId) => {
    // Find the message with the pending suggestedAction
    const msg = messages.find((m) => m.id === msgId);
    if (!msg || !msg.suggestedAction) return;

    // Prevent repeated submission if already in progress or confirmed
    if (msg.suggestedAction.status === 'approved' || msg.suggestedAction.status === 'confirmed') {
      return;
    }

    const actionType = msg.suggestedAction.actionType;
    const details = msg.suggestedAction.details || {};

    if (actionType === 'delete_plan') {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, suggestedAction: { ...m.suggestedAction, status: 'approved', confirmationError: null } }
            : m
        )
      );

      try {
        await api.deletePlan(details.planId);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'confirmed',
                    confirmationResult: { success: true, message: 'Plan deleted successfully.' },
                  },
                }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'failed',
                    confirmationError: err.message || 'Failed to delete plan. Please try again.',
                  },
                }
              : m
          )
        );
      }
      return;
    }

    if (actionType === 'sync_plan_calendar') {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, suggestedAction: { ...m.suggestedAction, status: 'approved', confirmationError: null } }
            : m
        )
      );

      try {
        const res = await api.syncPlanToCalendar(details.planId, details.studyBlocks, details.selectedBlockIds);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'confirmed',
                    confirmationResult: res,
                  },
                }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'failed',
                    confirmationError: err.message || 'Failed to sync study sessions to Google Calendar. Please try again.',
                  },
                }
              : m
          )
        );
      }
      return;
    }

    if (actionType === 'delete_event') {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, suggestedAction: { ...m.suggestedAction, status: 'approved', confirmationError: null } }
            : m
        )
      );

      try {
        await api.deleteCalendarEvent(details.eventId);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'confirmed',
                    confirmationResult: { success: true, message: 'Event cancelled from calendar.' },
                  },
                }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'failed',
                    confirmationError: err.message || 'Failed to cancel event. Please try again.',
                  },
                }
              : m
          )
        );
      }
      return;
    }

    if (actionType === 'create_draft') {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, suggestedAction: { ...m.suggestedAction, status: 'approved', confirmationError: null } }
            : m
        )
      );

      try {
        const res = await api.createEmailDraft(details.to, details.subject, details.body);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'confirmed',
                    confirmationResult: res,
                  },
                }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'failed',
                    confirmationError: err.message || 'Failed to save email draft. Please try again.',
                  },
                }
              : m
          )
        );
      }
      return;
    }

    if (actionType === 'send_email') {
      const confirmationToken = msg.suggestedAction.confirmationToken;
      if (!confirmationToken) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'failed',
                    confirmationError: 'No send confirmation token found. Please try requesting the action again.',
                  },
                }
              : m
          )
        );
        return;
      }

      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, suggestedAction: { ...m.suggestedAction, status: 'approved', confirmationError: null } }
            : m
        )
      );

      try {
        const res = await api.confirmSendEmail(confirmationToken);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'confirmed',
                    confirmationResult: res,
                  },
                }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  suggestedAction: {
                    ...m.suggestedAction,
                    status: 'failed',
                    confirmationError: err.message || 'Failed to send email. Please try again.',
                  },
                }
              : m
          )
        );
      }
      return;
    }

    // confirmationToken lives at the TOP LEVEL of suggestedAction (not inside details)
    const confirmationToken = msg.suggestedAction.confirmationToken;
    if (!confirmationToken) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                suggestedAction: {
                  ...m.suggestedAction,
                  status: 'failed',
                  confirmationError: 'No confirmation token found. Please try requesting the action again.',
                },
              }
            : m
        )
      );
      return;
    }

    // Set status to 'approved' (loading/in-progress) while the API call is running
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId
          ? { ...m, suggestedAction: { ...m.suggestedAction, status: 'approved', confirmationError: null } }
          : m
      )
    );

    try {
      // Build event details from user-facing details object
      const eventDetails = msg.suggestedAction.details || {};
      const actionId = msg.suggestedAction.id;
      const result = await api.confirmCalendarEvent(confirmationToken, eventDetails, actionId);

      // On success: mark as confirmed and store the result
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                suggestedAction: {
                  ...m.suggestedAction,
                  status: 'confirmed',
                  confirmationResult: result,
                },
              }
            : m
        )
      );
    } catch (err) {
      // On failure: mark as failed and store the honest error message
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                suggestedAction: {
                  ...m.suggestedAction,
                  status: 'failed',
                  confirmationError: err.message || 'Failed to create event. Please try again.',
                },
              }
            : m
        )
      );
    }
  };

  const renderMessageContent = (m) => {
    if (m.role === 'user') {
      return <div className="whitespace-pre-wrap">{m.content}</div>;
    }

    const content = m.content || '';
    const sourcesHeaderIdx = content.indexOf('**Grounded Evidentiary Sources:**');

    if (sourcesHeaderIdx !== -1) {
      const rawAnswerPart = content.substring(0, sourcesHeaderIdx).trim();
      const rawSourcesPart = content.substring(sourcesHeaderIdx + '**Grounded Evidentiary Sources:**'.length).trim();
      
      const cleanAnswer = rawAnswerPart.startsWith('**Answer:**')
        ? rawAnswerPart.substring('**Answer:**'.length).trim()
        : (rawAnswerPart.startsWith('Answer:') ? rawAnswerPart.substring('Answer:'.length).trim() : rawAnswerPart);

      // Split distinct source blocks
      const sourceBlocks = rawSourcesPart
        .split(/\n\n(?=[^\n>]+\s\((?:Page\s\d+|Page\s*unavailable)\))/g)
        .filter(b => b.trim());

      return (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <div className="text-[10px] font-mono uppercase text-[#C59A55] font-semibold tracking-wider flex items-center gap-1.5">
              <Sparkles size={12} className="text-[#E6C17A]" />
              <span>Direct Answer</span>
            </div>
            <div className="text-white text-xs sm:text-sm leading-relaxed whitespace-pre-wrap pl-0.5 font-sans">
              {cleanAnswer}
            </div>
          </div>

          <div className="pt-3 border-t border-white/10 space-y-2.5">
            <div className="text-[11px] font-mono uppercase text-[#A1A4AA] flex items-center gap-1.5 font-semibold">
              <ShieldCheck size={13} className="text-[#42D6A4]" />
              <span className="text-white">Grounded Evidentiary Sources:</span>
            </div>

            <div className="space-y-2">
              {sourceBlocks.map((blk, idx) => {
                const lines = blk.trim().split('\n');
                const headerLine = lines[0] || '';
                const quoteLines = lines.slice(1).join('\n').replace(/^>\s*/gm, '').trim();

                return (
                  <div
                    key={idx}
                    className="p-3 rounded-xl bg-[#08090B] border border-white/10 space-y-1.5 shadow-sm"
                  >
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
                      <FileText size={13} className="text-[#C59A55] flex-shrink-0" />
                      <span>{headerLine}</span>
                    </div>
                    {quoteLines && (
                      <blockquote className="border-l-2 border-[#C59A55] pl-3 py-1 bg-white/[0.02] rounded-r text-[11px] font-serif text-[#ECEFF1] italic leading-relaxed whitespace-pre-wrap">
                        "{quoteLines}"
                      </blockquote>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      );
    }

    // Direct answer with persistent DB citations (from reload or other tools)
    const isDirectAnswerFormat = content.startsWith('**Answer:**') || content.startsWith('Answer:');
    const displayAnswer = isDirectAnswerFormat
      ? (content.startsWith('**Answer:**') ? content.substring('**Answer:**'.length).trim() : content.substring('Answer:'.length).trim())
      : content;

    return (
      <div className="space-y-3">
        {isDirectAnswerFormat ? (
          <div className="space-y-1.5">
            <div className="text-[10px] font-mono uppercase text-[#C59A55] font-semibold tracking-wider flex items-center gap-1.5">
              <Sparkles size={12} className="text-[#E6C17A]" />
              <span>Direct Answer</span>
            </div>
            <div className="text-white text-xs sm:text-sm leading-relaxed whitespace-pre-wrap pl-0.5">
              {displayAnswer}
            </div>
          </div>
        ) : (
          <div className="whitespace-pre-wrap">{content}</div>
        )}

        {/* Citations preserved in database across reloads */}
        {m.citations && m.citations.length > 0 && (() => {
          // Determine contextual header label based on citation source types present
          const types = [...new Set(m.citations.map(c => c.sourceType || 'document'))];
          let citHeader = 'Grounded Evidentiary Sources';
          let CitIcon = ShieldCheck;
          let citIconClass = 'text-[#42D6A4]';
          if (types.length === 1) {
            if (types[0] === 'calendar') { citHeader = 'Calendar Events Referenced'; CitIcon = Calendar; citIconClass = 'text-[#E6C17A]'; }
            else if (types[0] === 'email') { citHeader = 'Emails Referenced'; CitIcon = Mail; citIconClass = 'text-[#42D6A4]'; }
          }
          return (
          <div className="mt-3 pt-3 border-t border-white/10 space-y-2">
            <div className="text-[11px] font-mono uppercase text-[#A1A4AA] flex items-center gap-1.5 font-semibold">
              <CitIcon size={13} className={citIconClass} />
              <span className="text-white">{citHeader}:</span>
            </div>
            <div className="grid grid-cols-1 gap-2">
              {m.citations.map((c) => (
                <div
                  key={c.id || Math.random()}
                  className="p-3 rounded-xl bg-[#08090B] border border-white/10 space-y-1.5 text-xs shadow-sm"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold text-white flex items-center gap-1.5">
                      {c.sourceType === 'document' && <FileText size={13} className="text-[#C59A55]" />}
                      {c.sourceType === 'calendar' && <Calendar size={13} className="text-[#E6C17A]" />}
                      {c.sourceType === 'email' && <Mail size={13} className="text-[#42D6A4]" />}
                      <span>{c.title}</span>
                      {c.sourceType === 'document' && (
                        <span className="text-[10px] text-[#A1A4AA] font-mono bg-white/5 px-1.5 py-0.5 rounded border border-white/5">
                          {c.page ? `Page ${c.page}` : 'Page unavailable'}
                        </span>
                      )}
                    </div>
                    {c.url && (
                      <a
                        href={c.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[#C59A55] hover:underline flex-shrink-0"
                      >
                        <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                  {c.snippet && (
                    <blockquote className="border-l-2 border-[#C59A55] pl-3 py-1 bg-white/[0.02] rounded-r text-[11px] font-serif text-[#ECEFF1] italic leading-relaxed">
                      "{c.snippet}"
                    </blockquote>
                  )}
                </div>
              ))}
            </div>
          </div>
          );
        })()}
      </div>
    );
  };

  const activeConvTitle = conversations.find(c => c.id === activeConversationId)?.title || "Current Session";

  return (
    <div className="flex flex-col h-full bg-[#08090B]">
      {/* Session Top Bar */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-2.5 border-b border-white/5 bg-[#0D0F12] text-xs">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHistoryDrawer(!showHistoryDrawer)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-white font-medium border border-white/10 transition-colors"
          >
            <MessageSquare size={13} className="text-[#C59A55]" />
            <span className="truncate max-w-[200px]">{activeConvTitle}</span>
            <ChevronDown size={12} className="text-[#696E78]" />
          </button>
          <span className="text-[10px] font-mono text-[#696E78] hidden sm:inline">
            Persisted in SQLite database
          </span>
        </div>

        <button
          onClick={handleStartNewChat}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg btn-bronze text-[11px]"
          title="Start fresh conversation"
        >
          <Plus size={13} />
          <span>New Session</span>
        </button>
      </div>

      {/* History Drawer Modal / Dropdown */}
      {showHistoryDrawer && (
        <div className="p-4 bg-[#121418] border-b border-white/10 space-y-2 z-10">
          <div className="flex items-center justify-between text-xs font-semibold text-[#A1A4AA] pb-1 border-b border-white/5">
            <span>SAVED CONVERSATIONS ({conversations.length})</span>
            <button onClick={() => setShowHistoryDrawer(false)} className="text-[#696E78] hover:text-white">✕</button>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {conversations.length > 0 ? (
              conversations.map((c) => (
                <div
                  key={c.id}
                  onClick={() => handleSelectConversation(c.id)}
                  className={`p-2 rounded-lg text-xs flex items-center justify-between cursor-pointer transition-colors ${
                    c.id === activeConversationId
                      ? 'bg-[#C59A55]/15 text-[#E6C17A] border border-[#C59A55]/30'
                      : 'hover:bg-white/5 text-[#A1A4AA] hover:text-white'
                  }`}
                >
                  <span className="truncate max-w-sm">{c.title}</span>
                  <span className="text-[10px] font-mono text-[#696E78]">
                    {c.updatedAt ? new Date(c.updatedAt).toLocaleDateString() : ''}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-xs text-[#696E78] py-2">No prior conversations found.</div>
            )}
          </div>
        </div>
      )}

      {/* Messages Canvas Wrapper with Intelligent Scroll & Jump Button */}
      <div className="relative flex-1 min-h-0 flex flex-col">
        <div 
          ref={chatContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-4 sm:p-8 space-y-6 max-w-4xl mx-auto w-full"
        >
        {messages.map((m) => {
          const isUser = m.role === 'user';
          return (
            <div
              key={m.id}
              className={`flex gap-3 sm:gap-4 ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              {!isUser && (
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#E6C17A] to-[#8C6928] flex items-center justify-center flex-shrink-0 text-black shadow-sm mt-1">
                  <Bot size={16} />
                </div>
              )}

              <div
                className={`max-w-2xl rounded-2xl p-4 text-xs sm:text-sm leading-relaxed ${
                  isUser
                    ? 'bg-[#C59A55]/15 border border-[#C59A55]/30 text-white rounded-tr-none'
                    : 'bg-[#121418] border border-white/10 text-[#ECEFF1] rounded-tl-none shadow-md'
                }`}
              >
                {renderMessageContent(m)}

                {/* Consequential Action Confirmation Preview */}
                {!isUser && m.suggestedAction && (() => {
                  const sa = m.suggestedAction;
                  const statusLabel = {
                    pending: 'Awaiting Confirmation',
                    approved: 'Processing...',
                    confirmed: 'Confirmed',
                    failed: 'Failed',
                    rejected: 'Dismissed',
                  }[sa.status] || sa.status;

                  const statusColor =
                    sa.status === 'confirmed' ? 'bg-[#42D6A4]/20 text-[#42D6A4]' :
                    sa.status === 'approved'  ? 'bg-[#C59A55]/20 text-[#E6C17A]' :
                    sa.status === 'failed'    ? 'bg-[#F07878]/20 text-[#F07878]' :
                    sa.status === 'rejected'  ? 'bg-white/10 text-[#696E78]' :
                                                'bg-[#C59A55]/20 text-[#E6C17A]';

                  return (
                    <div className="mt-4 p-3.5 rounded-xl bg-[#08090B] border border-[#C59A55]/40 space-y-3">
                      <div className="flex items-center justify-between text-xs font-semibold text-[#E6C17A]">
                        <span className="flex items-center gap-1.5">
                          <AlertCircle size={14} className="text-[#E6C17A]" />
                          <span>Action Required: {sa.title}</span>
                        </span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${statusColor}`}>
                          {statusLabel}
                        </span>
                      </div>

                      {/* Explicit allowlist for user-facing fields only — never exposes confirmationToken, raw args, or internal data */}
                      {(() => {
                        const d = sa.details || {};
                        const isAllDay = d.isAllDay || d.type === 'All-Day Personal Leave' || String(d.type || '').toLowerCase().includes('all-day');
                        let userFacingRows = [];

                        if (sa.actionType === 'delete_plan') {
                          userFacingRows = [
                            { label: 'Action', value: 'Permanently Delete Study Plan' },
                            { label: 'Plan', value: d.planTitle },
                            { label: 'Tasks', value: d.taskCount },
                            { label: 'Google Calendar', value: d.calendar },
                            { label: 'Warning', value: d.warning }
                          ];
                        } else if (sa.actionType === 'sync_plan_calendar') {
                          userFacingRows = [
                            { label: 'Action', value: 'Add Study Sessions to Google Calendar' },
                            { label: 'Plan', value: d.planTitle },
                            { label: 'Sessions', value: d.sessionCount },
                            { label: 'Date Range', value: d.dateRange },
                            { label: 'Timezone', value: d.timezone },
                            { label: 'Calendar', value: d.calendar || 'Primary Google Calendar' },
                          ];
                        } else if (sa.actionType === 'delete_event') {
                          userFacingRows = [
                            { label: 'Action', value: 'Cancel Calendar Event' },
                            { label: 'Event', value: d.title },
                            { label: 'Time', value: d.time },
                            { label: 'Calendar', value: d.calendar || 'Primary Google Calendar' },
                            { label: 'Warning', value: d.warning }
                          ];
                        } else if (sa.actionType === 'send_email') {
                          userFacingRows = [
                            { label: 'Action', value: 'Send Email via Gmail' },
                            { label: 'To', value: d.to },
                            { label: 'Subject', value: d.subject },
                            { label: 'Preview', value: d.bodyPreview },
                            { label: 'Note', value: d.note }
                          ];
                        } else if (sa.actionType === 'create_draft') {
                          userFacingRows = [
                            { label: 'Action', value: 'Create Gmail Draft' },
                            { label: 'To', value: d.to },
                            { label: 'Subject', value: d.subject },
                            { label: 'Preview', value: d.body ? (d.body.length > 150 ? d.body.substring(0, 150) + '...' : d.body) : '' },
                            { label: 'Service', value: d.service }
                          ];
                        } else {
                          userFacingRows = [
                            { label: 'Event', value: d.title || sa.title },
                            { label: 'Date', value: d.date },
                            { label: 'Time', value: d.time || (d.startTime ? d.startTime.replace('T', ' ').substring(0, 16) : null) },
                            { label: 'Timezone', value: d.timezone },
                            { label: 'Duration', value: d.duration },
                            { label: 'Location', value: d.location },
                            { label: 'Calendar', value: d.calendar || 'Primary Google Calendar' },
                          ];
                        }

                        userFacingRows = userFacingRows.filter(r => Boolean(r.value));

                        return (
                          <div className="text-[11px] text-[#A1A4AA] space-y-1 font-mono">
                            {userFacingRows.map((row) => (
                              <div key={row.label} className="flex justify-between border-b border-white/5 pb-0.5">
                                <span className="text-[#696E78]">{row.label}:</span>
                                <span className="text-white text-right max-w-xs truncate">
                                  {row.value}
                                </span>
                              </div>
                            ))}
                          </div>
                        );
                      })()}

                      {/* Status-specific action / result area */}
                      {sa.status === 'pending' && (
                        <div className="flex gap-2 pt-1">
                          <button
                            onClick={() => handleConfirmAction(m.id)}
                            className="btn-bronze text-xs py-1.5 px-3 flex-1 flex items-center justify-center gap-1"
                          >
                            <Check size={14} />
                            <span>Confirm &amp; Commit Action</span>
                          </button>
                          <button
                            onClick={() => {
                              setMessages((prev) =>
                                prev.map((item) =>
                                  item.id === m.id
                                    ? { ...item, suggestedAction: { ...item.suggestedAction, status: 'rejected' } }
                                    : item
                                )
                              );
                            }}
                            className="btn-secondary text-xs py-1.5 px-3"
                          >
                            Dismiss
                          </button>
                        </div>
                      )}

                      {sa.status === 'approved' && (
                        <div className="text-[11px] text-[#E6C17A] flex items-center gap-1.5 font-medium animate-pulse">
                          <Loader2 size={13} className="animate-spin" />
                          <span>
                            {sa.actionType === 'delete_plan' ? 'Deleting study plan...' :
                             sa.actionType === 'sync_plan_calendar' ? 'Synchronizing study sessions to Google Calendar...' :
                             sa.actionType === 'delete_event' ? 'Cancelling event from Google Calendar...' :
                             sa.actionType === 'send_email' ? 'Dispatching email via Gmail...' :
                             sa.actionType === 'create_draft' ? 'Saving draft to Gmail...' :
                             'Writing to Google Calendar...'}
                          </span>
                        </div>
                      )}

                      {sa.status === 'confirmed' && (() => {
                        const r = sa.confirmationResult || {};
                        const d = sa.details || {};
                        if (sa.actionType === 'delete_plan') {
                          return (
                            <div className="text-[11px] text-[#42D6A4] space-y-1">
                              <div className="flex items-center gap-1.5 font-medium">
                                <CheckCircle2 size={14} className="flex-shrink-0 text-[#42D6A4]" />
                                <span>The study plan &quot;{d.planTitle}&quot; and its tasks have been deleted from your workspace.</span>
                              </div>
                            </div>
                          );
                        }
                        if (sa.actionType === 'sync_plan_calendar') {
                          return (
                            <div className="text-[11px] text-[#42D6A4] space-y-1">
                              <div className="flex items-center gap-1.5 font-medium">
                                <CheckCircle2 size={14} className="flex-shrink-0 text-[#42D6A4]" />
                                <span>{r.message || 'Study sessions have been added to your Google Calendar.'}</span>
                              </div>
                              {r.successCount !== undefined && (
                                <div className="text-[#696E78] font-mono text-[10px]">
                                  {r.successCount} synced, {r.failedCount || 0} failed.
                                </div>
                              )}
                            </div>
                          );
                        }
                        if (sa.actionType === 'delete_event') {
                          return (
                            <div className="text-[11px] text-[#42D6A4] space-y-1">
                              <div className="flex items-center gap-1.5 font-medium">
                                <CheckCircle2 size={14} className="flex-shrink-0 text-[#42D6A4]" />
                                <span>The event &quot;{d.title}&quot; has been cancelled and removed from your Google Calendar.</span>
                              </div>
                            </div>
                          );
                        }
                        if (sa.actionType === 'send_email') {
                          return (
                            <div className="text-[11px] text-[#42D6A4] space-y-1">
                              <div className="flex items-center gap-1.5 font-medium">
                                <CheckCircle2 size={14} className="flex-shrink-0 text-[#42D6A4]" />
                                <span>Email successfully dispatched to {d.to} via Gmail.</span>
                              </div>
                              {r.messageId && (
                                <div className="text-[#696E78] font-mono text-[10px]">Message ID: {r.messageId}</div>
                              )}
                            </div>
                          );
                        }
                        if (sa.actionType === 'create_draft') {
                          return (
                            <div className="text-[11px] text-[#42D6A4] space-y-1">
                              <div className="flex items-center gap-1.5 font-medium">
                                <CheckCircle2 size={14} className="flex-shrink-0 text-[#42D6A4]" />
                                <span>Email draft &quot;{d.subject}&quot; saved to your Gmail drafts folder.</span>
                              </div>
                              {r.draftId && (
                                <div className="text-[#696E78] font-mono text-[10px]">Draft ID: {r.draftId}</div>
                              )}
                            </div>
                          );
                        }
                        const isAllDay = d.isAllDay || d.type === 'All-Day Personal Leave' || r.isAllDay;
                        return (
                          <div className="text-[11px] text-[#42D6A4] space-y-1">
                            <div className="flex items-center gap-1.5 font-medium">
                              <CheckCircle2 size={14} className="flex-shrink-0 text-[#42D6A4]" />
                              <span>
                                Your {d.title || 'Personal Leave / Sick Day'} event has been added to your Google Calendar
                                {d.date ? ` for ${d.date}` : ''}
                                {isAllDay ? ', as an all-day event.' : '.'}
                              </span>
                            </div>
                            {r.id && (
                              <div className="text-[#696E78] font-mono text-[10px]">Event ID: {r.id}</div>
                            )}
                          </div>
                        );
                      })()}

                      {sa.status === 'failed' && (
                        <div className="space-y-2 pt-1">
                          <div className="text-[11px] text-[#F07878] flex items-center gap-1.5 font-medium">
                            <AlertCircle size={13} className="flex-shrink-0" />
                            <span>{sa.confirmationError || 'Could not create event. Please try again.'}</span>
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleConfirmAction(m.id)}
                              className="btn-bronze text-xs py-1 px-2.5 flex-1 flex items-center justify-center gap-1"
                            >
                              <Check size={13} />
                              <span>Retry Confirmation</span>
                            </button>
                            <button
                              onClick={() => {
                                setMessages((prev) =>
                                  prev.map((item) =>
                                    item.id === m.id
                                      ? { ...item, suggestedAction: { ...item.suggestedAction, status: 'rejected' } }
                                      : item
                                  )
                                );
                              }}
                              className="btn-secondary text-xs py-1 px-2.5"
                            >
                              Dismiss
                            </button>
                          </div>
                        </div>
                      )}

                      {sa.status === 'rejected' && (
                        <div className="text-[11px] text-[#696E78] flex items-center gap-1 font-medium">
                          <span>Action dismissed.</span>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>
          );
        })}

        {/* Real-time Tool Execution Progress Indicator with Stop Action */}
        {activeTool && (
          <div className="flex items-center justify-between gap-3 p-3 rounded-lg bg-[#121418] border border-[#C59A55]/20 text-xs text-[#E6C17A] max-w-md shadow-sm">
            <div className="flex items-center gap-2 animate-pulse truncate">
              <Loader2 size={14} className="animate-spin text-[#C59A55] flex-shrink-0" />
              <span className="truncate">{activeTool}</span>
            </div>
            <button
              type="button"
              onClick={handleStopGeneration}
              className="flex items-center gap-1 px-2 py-0.5 rounded bg-white/5 hover:bg-red-500/20 text-[#A1A4AA] hover:text-red-300 border border-white/10 hover:border-red-500/30 text-[11px] flex-shrink-0 transition-colors"
              title="Stop Generation"
            >
              <Square size={10} className="fill-current text-red-400" />
              <span>Stop</span>
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Floating Jump to Latest Button */}
      {showJumpToLatest && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 pointer-events-none">
          <button
            type="button"
            onClick={handleJumpToLatest}
            className="pointer-events-auto flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-[#181B20]/95 hover:bg-[#22262E] border border-[#C59A55]/50 text-xs font-medium text-white shadow-xl backdrop-blur transition-all hover:scale-105 active:scale-95 cursor-pointer"
          >
            <ArrowDown size={13} className="text-[#C59A55]" />
            <span>Jump to latest</span>
          </button>
        </div>
      )}
    </div>

      {/* Suggested Prompts Pill Carousel */}
      {messages.length <= 2 && (
        <div className="px-4 py-2 max-w-4xl mx-auto w-full flex items-center gap-2 overflow-x-auto no-scrollbar">
          <Sparkles size={14} className="text-[#C59A55] flex-shrink-0" />
          {suggestedPrompts.map((p, idx) => (
            <button
              key={idx}
              onClick={() => handleSendMessage(p)}
              className="text-xs bg-[#121418] hover:bg-white/5 border border-white/10 hover:border-[#C59A55]/40 text-[#A1A4AA] hover:text-white px-3 py-1.5 rounded-full whitespace-nowrap transition-colors"
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {/* Error Banner with Honest Error Message and Retry Action */}
      {chatError && (
        <div className="max-w-4xl mx-auto w-full px-4 mb-3 animate-in fade-in">
          <div className="p-3.5 rounded-xl bg-[#F07878]/10 border border-[#F07878]/30 text-xs text-[#F07878] flex items-center justify-between gap-3 shadow-sm">
            <div className="flex items-center gap-2">
              <AlertCircle size={16} className="text-[#F07878] flex-shrink-0" />
              <span className="leading-relaxed">{chatError.message}</span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={() => {
                  const retryQuery = chatError.query;
                  setChatError(null);
                  handleSendMessage(retryQuery);
                }}
                className="px-2.5 py-1 bg-[#F07878]/20 hover:bg-[#F07878]/30 text-white rounded text-[11px] font-medium transition-colors cursor-pointer"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={() => setChatError(null)}
                className="text-[#A1A4AA] hover:text-white font-bold px-1.5 cursor-pointer"
                title="Dismiss"
              >
                ✕
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Composer Bottom Area */}
      <div className="p-4 sm:p-6 border-t border-white/5 bg-[#0D0F12]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          className="max-w-4xl mx-auto flex items-end gap-2 bg-[#121418] border border-white/10 rounded-xl p-2 focus-within:border-[#C59A55]/50 transition-colors"
        >
          <button
            type="button"
            className="p-2 text-[#696E78] hover:text-[#C59A55] transition-colors rounded"
            title="Upload documents via Knowledge Base"
            onClick={() => window.location.href = '/knowledge'}
          >
            <Paperclip size={18} />
          </button>

          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            placeholder="Ask anything across your inbox, calendar, documents, or plans..."
            className="w-full bg-transparent text-xs sm:text-sm text-white resize-none focus:outline-none py-2 px-1 placeholder:text-[#696E78] max-h-32"
          />

          {loading ? (
            <button
              type="button"
              onClick={handleStopGeneration}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 border border-red-500/40 text-red-300 text-xs font-medium flex-shrink-0 transition-colors shadow-sm cursor-pointer"
              title="Stop Generation"
            >
              <Square size={13} className="fill-current text-red-400" />
              <span className="hidden sm:inline font-mono">Stop</span>
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className={`btn-bronze text-xs p-2.5 rounded-lg flex-shrink-0 ${
                !input.trim() ? 'opacity-40 cursor-not-allowed' : ''
              }`}
              title="Send message"
            >
              <Send size={16} />
            </button>
          )}
        </form>

        <div className="text-center mt-2 text-[10px] font-mono text-[#696E78]">
          Grounded with strict user tenancy • External and uploaded documents treated as untrusted data
        </div>
      </div>
    </div>
  );
};
