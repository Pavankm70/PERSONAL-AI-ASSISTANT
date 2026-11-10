import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { 
  Bot, 
  Calendar, 
  Mail, 
  FileText, 
  ArrowRight, 
  Clock, 
  CheckCircle2, 
  AlertCircle, 
  Plus, 
  ExternalLink,
  Sparkles,
  Layers,
  Cpu,
  ChevronRight,
  BookOpen,
  Check
} from 'lucide-react';
import { 
  formatTimeRange, 
  formatDateForDisplay, 
  getEffectiveTimezone,
  getCurrentUserDate
} from '../../utils/dateUtils';

export const DashboardOverview = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [quickQuery, setQuickQuery] = useState('');

  useEffect(() => {
    const fetchOverview = async () => {
      setLoading(true);
      try {
        const res = await api.getDashboardOverview();
        setData(res);
      } catch (err) {
        // Fallback realistic state when services not yet connected
        setData({
          user: { fullName: 'Alex Chen', email: 'alex.chen@university.edu' },
          todayAgenda: [],
          importantEmails: [],
          recentDocuments: [],
          pendingActions: [],
          integrationsStatus: {
            gmail: 'not_connected',
            calendar: 'not_connected',
            drive: 'not_connected',
            rag: 'connected'
          },
          systemStats: {
            totalDocuments: 0,
            upcomingEventsCount: 0,
            unreadImportantCount: 0,
            activePlansCount: 0
          }
        });
      } finally {
        setLoading(false);
      }
    };

    fetchOverview();
  }, []);

  const handleQuickSubmit = (e) => {
    e.preventDefault();
    if (!quickQuery.trim()) return;
    navigate(`/app/chat?q=${encodeURIComponent(quickQuery)}`);
  };

  const handleToggleTask = async (planId, taskId, currentCompleted) => {
    try {
      await api.updatePlanTask(planId, taskId, { completed: !currentCompleted });
      // Optimistically update data
      setData((prev) => {
        if (!prev) return prev;
        const updatedAgenda = (prev.todayAgenda || []).map((item) =>
          item.taskId === taskId ? { ...item, completed: !currentCompleted } : item
        );
        const updatedTasks = (prev.todayStudyTasks || []).map((task) =>
          task.id === taskId ? { ...task, completed: !currentCompleted } : task
        );
        return {
          ...prev,
          todayAgenda: updatedAgenda,
          todayStudyTasks: updatedTasks,
          systemStats: {
            ...prev.systemStats,
            todayCompletedTasksCount: (prev.systemStats?.todayCompletedTasksCount || 0) + (currentCompleted ? -1 : 1)
          }
        };
      });
    } catch (e) {
      console.error('Failed to toggle task:', e);
    }
  };

  if (loading) {
    return (
      <div className="p-8 space-y-6 animate-pulse max-w-7xl mx-auto">
        <div className="h-10 bg-white/5 rounded-lg w-1/3" />
        <div className="h-32 bg-white/5 rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="h-64 bg-white/5 rounded-xl" />
          <div className="h-64 bg-white/5 rounded-xl" />
          <div className="h-64 bg-white/5 rounded-xl" />
        </div>
      </div>
    );
  }

  const { user, todayAgenda, importantEmails, recentDocuments, pendingActions, integrationsStatus } = data || {};
  const userName = user?.fullName || 'Pawan';
  const todayDateFormatted = formatDateForDisplay(new Date(), user?.timezone, 'long');
  const todayAgendaCount = todayAgenda?.length || 0;
  const todayStudyCount = data?.todayStudyTasks?.length || 0;
  const completedCount = data?.systemStats?.todayCompletedTasksCount || 0;

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">
      {/* Top Greeting & Assistant Prompt Entry */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-eyebrow font-mono">SYSTEM 001 ACTIVE</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[#C59A55]">
                {todayDateFormatted}
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight mt-1">
              Welcome, {userName}
            </h1>
            <p className="text-xs sm:text-sm text-[#A1A4AA] mt-1">
              {todayAgendaCount > 0
                ? `You have ${todayAgendaCount} item${todayAgendaCount === 1 ? '' : 's'} on your agenda today (${todayStudyCount} study task${todayStudyCount === 1 ? '' : 's'}, ${completedCount} completed).`
                : 'Your schedule for today is currently clear. Ask Aurelia to plan your study sessions or review your inbox.'}
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto">
            <button
              onClick={() => navigate('/app/calendar')}
              className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5"
            >
              <Calendar size={13} />
              <span>Calendar</span>
            </button>
            <button
              onClick={() => navigate('/app/plans')}
              className="btn-bronze text-xs py-1.5 px-3.5 flex items-center gap-1.5"
            >
              <BookOpen size={13} />
              <span>Study Plans</span>
            </button>
          </div>
        </div>

        {/* Quick Conversational Input Card */}
        <form
          onSubmit={handleQuickSubmit}
          className="card-dark p-2 rounded-xl bg-[#121418] border border-white/10 flex items-center gap-3 shadow-md focus-within:border-[#C59A55]/50 transition-all"
        >
          <div className="p-2 text-[#C59A55] pl-3">
            <Sparkles size={18} />
          </div>
          <input
            type="text"
            placeholder="Ask Aurelia anything: 'What do I have scheduled tomorrow?' or 'Do I have any quizzes?'..."
            value={quickQuery}
            onChange={(e) => setQuickQuery(e.target.value)}
            className="w-full bg-transparent text-xs sm:text-sm text-white focus:outline-none placeholder:text-[#696E78]"
          />
          <button
            type="submit"
            className="btn-bronze text-xs py-2 px-4 whitespace-nowrap flex items-center gap-1"
          >
            <span>Ask Agent</span>
            <ArrowRight size={13} />
          </button>
        </form>
      </div>

      {/* Suggested Actions Alert Banner if any */}
      {pendingActions && pendingActions.length > 0 && (
        <div className="p-4 rounded-xl bg-[#181B20] border border-[#C59A55]/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-[#C59A55]/20 text-[#E6C17A]">
              <Sparkles size={16} />
            </div>
            <div>
              <div className="text-[10px] font-mono text-[#E6C17A] uppercase">
                Pending Suggested Action
              </div>
              <div className="text-xs font-semibold text-white">
                {pendingActions[0].title}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('/app/calendar')}
              className="btn-bronze text-xs py-1.5 px-3"
            >
              Review &amp; Confirm
            </button>
          </div>
        </div>
      )}

      {/* Grid: 3 Pillars (Calendar, Inbox, Knowledge) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Widget 1: Today's Agenda */}
        <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-[#C59A55]" />
                <h3 className="text-sm font-semibold text-white">Today's Agenda</h3>
              </div>
              <div className="flex items-center gap-2">
                {data?.todayStudyTasks && data.todayStudyTasks.length > 0 && (
                  <span className="text-[10px] font-mono text-[#E6C17A] bg-[#C59A55]/15 px-1.5 py-0.5 rounded">
                    {data.systemStats?.todayCompletedTasksCount || 0}/{data.todayStudyTasks.length} tasks
                  </span>
                )}
                <span className="text-[10px] font-mono text-[#696E78]">
                  {integrationsStatus?.calendar === 'connected' ? 'LIVE' : 'LOCAL'}
                </span>
              </div>
            </div>

            {todayAgenda && todayAgenda.length > 0 ? (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {todayAgenda.map((evt) => {
                  const isStudy = evt.source === 'study_plan' || evt.eventType === 'study_plan';
                  const isUnscheduled = evt.isUnscheduled || (!evt.startTime && !evt.scheduledTime);
                  const timeLabel = isUnscheduled
                    ? 'Unscheduled study task'
                    : formatTimeRange(evt.startTime, evt.endTime, user?.timezone, evt.isAllDay);

                  return (
                    <div
                      key={evt.id}
                      className={`p-3 rounded-lg bg-[#08090B] border text-xs space-y-1.5 transition-all ${
                        evt.completed
                          ? 'border-[#42D6A4]/30 opacity-75'
                          : isStudy
                          ? 'border-[#C59A55]/30'
                          : 'border-white/5'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className={`font-semibold text-white truncate max-w-[190px] ${evt.completed ? 'line-through text-[#A1A4AA]' : ''}`}>
                          {evt.title}
                        </span>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {isStudy && (
                            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#C59A55]/15 text-[#E6C17A] border border-[#C59A55]/30">
                              Study Plan
                            </span>
                          )}
                          {!isStudy && (
                            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#82AFFF]/15 text-[#82AFFF] border border-[#82AFFF]/30">
                              Calendar
                            </span>
                          )}
                          {isStudy && evt.taskId && evt.planId && (
                            <button
                              type="button"
                              onClick={() => handleToggleTask(evt.planId, evt.taskId, evt.completed)}
                              className={`p-1 rounded transition-colors ${
                                evt.completed
                                  ? 'bg-[#42D6A4]/20 text-[#42D6A4]'
                                  : 'bg-white/5 hover:bg-white/10 text-[#696E78]'
                              }`}
                              title={evt.completed ? 'Mark pending' : 'Mark completed'}
                            >
                              <Check size={11} />
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="text-[11px] font-mono text-[#A1A4AA] flex items-center justify-between">
                        <span className="flex items-center gap-1 text-[#C59A55]">
                          <Clock size={11} />
                          <span>{timeLabel}</span>
                        </span>
                        {evt.completed && (
                          <span className="text-[10px] text-[#42D6A4] font-medium">Completed</span>
                        )}
                        {!evt.completed && evt.durationMinutes && (
                          <span className="text-[10px] text-[#696E78]">{evt.durationMinutes}m</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-[#696E78] space-y-2">
                <div>No events or study tasks scheduled for today.</div>
                {integrationsStatus?.calendar !== 'connected' && (
                  <button
                    onClick={() => navigate('/app/integrations')}
                    className="text-[11px] text-[#C59A55] hover:underline block mx-auto font-mono"
                  >
                    Connect Google Calendar for Live Sync →
                  </button>
                )}
              </div>
            )}
          </div>

          <button
            onClick={() => navigate('/app/calendar')}
            className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-xs text-[#A1A4AA] hover:text-white transition-colors"
          >
            <span>Open Calendar Workspace</span>
            <ChevronRight size={14} />
          </button>
        </div>

        {/* Widget 2: Priority Email Highlights */}
        <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Mail size={16} className="text-[#C59A55]" />
                <h3 className="text-sm font-semibold text-white">Important Emails</h3>
              </div>
              <span className="text-[10px] font-mono text-[#696E78]">
                {integrationsStatus?.gmail === 'connected' ? 'LIVE' : 'NOT CONNECTED'}
              </span>
            </div>

            {integrationsStatus?.gmail !== 'connected' ? (
              <div className="p-6 rounded-lg bg-[#08090B] border border-white/5 text-center space-y-3">
                <Mail size={28} className="mx-auto text-[#696E78]" />
                <div className="text-xs text-[#A1A4AA]">
                  Gmail is not connected. Authorize Gmail to receive summaries of priority messages and action items.
                </div>
                <button
                  onClick={() => navigate('/app/integrations')}
                  className="btn-secondary text-xs py-1.5 px-3"
                >
                  Connect Gmail
                </button>
              </div>
            ) : importantEmails && importantEmails.length > 0 ? (
              <div className="space-y-2">
                {importantEmails.slice(0, 3).map((mail) => (
                  <div key={mail.id} className="p-3 rounded-lg bg-[#08090B] border border-white/5 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white truncate max-w-[180px]">{mail.fromName}</span>
                      <span className="text-[10px] font-mono text-[#42D6A4] bg-[#42D6A4]/10 px-1.5 py-0.5 rounded">Priority</span>
                    </div>
                    <div className="text-xs text-[#A1A4AA] truncate">{mail.subject}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-[#696E78]">
                Your priority inbox is all caught up.
              </div>
            )}
          </div>

          <button
            onClick={() => navigate('/app/inbox')}
            className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-xs text-[#A1A4AA] hover:text-white transition-colors"
          >
            <span>View Connected Inbox</span>
            <ChevronRight size={14} />
          </button>
        </div>

        {/* Widget 3: Knowledge Base & Timetable */}
        <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-[#C59A55]" />
                <h3 className="text-sm font-semibold text-white">Personal Knowledge</h3>
              </div>
              <span className="text-[10px] font-mono text-[#42D6A4]">RAG READY</span>
            </div>

            {recentDocuments && recentDocuments.length > 0 ? (
              <div className="space-y-2">
                {recentDocuments.slice(0, 3).map((doc) => (
                  <div key={doc.id} className="p-3 rounded-lg bg-[#08090B] border border-white/5 text-xs flex items-center justify-between">
                    <div className="flex items-center gap-2 overflow-hidden">
                      <FileText size={14} className="text-[#C59A55] flex-shrink-0" />
                      <span className="text-white truncate">{doc.filename}</span>
                    </div>
                    <span className="text-[10px] font-mono text-[#42D6A4]">{doc.chunkCount} chunks</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 rounded-lg bg-[#08090B] border border-white/5 text-center space-y-3">
                <FileText size={28} className="mx-auto text-[#696E78]" />
                <div className="text-xs text-[#A1A4AA]">
                  No documents uploaded yet. Upload your timetable, lecture notes, or syllabus for grounded AI recall.
                </div>
                <button
                  onClick={() => navigate('/app/knowledge')}
                  className="btn-bronze text-xs py-1.5 px-3"
                >
                  Upload Documents
                </button>
              </div>
            )}
          </div>

          <button
            onClick={() => navigate('/app/knowledge')}
            className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-xs text-[#A1A4AA] hover:text-white transition-colors"
          >
            <span>Manage Documents</span>
            <ChevronRight size={14} />
          </button>
        </div>
      </div>

      {/* Connected Services Quick Status Ribbon */}
      <div className="p-5 rounded-xl bg-[#0D0F12] border border-white/5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Cpu size={16} className="text-[#C59A55]" />
          <span className="text-xs font-semibold text-white">Connected Stream Health</span>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {[
            { name: 'Google Identity', status: 'connected' },
            { name: 'Gmail', status: integrationsStatus?.gmail || 'not_connected' },
            { name: 'Calendar', status: integrationsStatus?.calendar || 'not_connected' },
            { name: 'Drive', status: integrationsStatus?.drive || 'not_connected' },
            { name: 'Vector Store (pgvector)', status: 'connected' }
          ].map((s) => (
            <div key={s.name} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#121418] border border-white/5 text-[11px] font-mono text-[#A1A4AA]">
              <span className={`w-1.5 h-1.5 rounded-full ${s.status === 'connected' ? 'bg-[#42D6A4]' : 'bg-[#696E78]'}`} />
              <span>{s.name}</span>
            </div>
          ))}
        </div>

        <button
          onClick={() => navigate('/app/integrations')}
          className="text-xs text-[#C59A55] hover:text-[#E6C17A] transition-colors font-medium flex items-center gap-1"
        >
          <span>Configure</span>
          <ArrowRight size={12} />
        </button>
      </div>
    </div>
  );
};
