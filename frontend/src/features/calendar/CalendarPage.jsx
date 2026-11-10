import React, { useState, useEffect, useMemo } from 'react';
import { api } from '../../services/api';
import { 
  Calendar as CalendarIcon, 
  Clock, 
  Sparkles, 
  AlertTriangle, 
  CheckCircle2, 
  Loader2,
  Check,
  Trash2,
  BookOpen,
  Link2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Filter,
  Search,
  Plus,
  RefreshCw,
  Edit2,
  X,
  CalendarCheck,
  Layers,
  List
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { 
  formatTimeRange, 
  formatDateForDisplay, 
  getEffectiveTimezone,
  getCurrentUserDate,
  getStartOfDay,
  getEndOfDay,
  getWeekRange,
  getMonthRange,
  formatYearMonthDay,
  isSameDay,
  isToday,
  parseDateSafe
} from '../../utils/dateUtils';

export const CalendarPage = () => {
  const navigate = useNavigate();

  // Core Data
  const [events, setEvents] = useState([]);
  const [studyTasks, setStudyTasks] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [checkingGoogleCal, setCheckingGoogleCal] = useState(true);
  const [connected, setConnected] = useState(false);
  const [timezone, setTimezone] = useState('UTC');

  // Navigation & Filtering
  const [view, setView] = useState('week'); // 'day' | 'week' | 'month' | 'schedule'
  const [currentDate, setCurrentDate] = useState(new Date());
  const [typeFilter, setTypeFilter] = useState('all'); // 'all' | 'study_plan' | 'google_calendar' | 'personal'
  const [searchQuery, setSearchQuery] = useState('');

  // Natural Language Dispatcher State
  const [nlQuery, setNlQuery] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewError, setPreviewError] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState(null);

  // Sync to Google Calendar Modal State
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [selectedSyncTaskIds, setSelectedSyncTaskIds] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  // Event Details / Edit Modal State
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ title: '', date: '', startTime: '', endTime: '' });
  const [savingEdit, setSavingEdit] = useState(false);

  // Quick Manual Create Event Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: '',
    date: getCurrentUserDate(),
    startTime: '10:00',
    endTime: '11:00',
    isStudySession: false,
    planId: ''
  });
  const [creatingEvent, setCreatingEvent] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setCheckingGoogleCal(true);

    // 1. Run user timezone, study plans, and Google Calendar fetches concurrently
    const [userRes, plansRes, calRes] = await Promise.allSettled([
      api.getCurrentUser(),
      api.getPlans(),
      api.getCalendarEvents()
    ]);

    // Apply user timezone
    if (userRes.status === 'fulfilled' && userRes.value?.timezone) {
      setTimezone(userRes.value.timezone);
    }

    // Apply persistent study plans
    if (plansRes.status === 'fulfilled') {
      const plansData = plansRes.value;
      setPlans(Array.isArray(plansData) ? plansData : []);
      const scheduled = [];
      if (Array.isArray(plansData)) {
        for (const p of plansData) {
          for (const t of (p.tasks || [])) {
            if (t.scheduledDate || t.startTime || t.scheduledTime) {
              scheduled.push({
                ...t,
                planId: p.id,
                planTitle: p.title
              });
            }
          }
        }
      }
      setStudyTasks(scheduled);
    } else {
      setStudyTasks([]);
      setPlans([]);
    }

    // Apply Google Calendar events
    if (calRes.status === 'fulfilled') {
      const calData = calRes.value;
      setEvents(Array.isArray(calData) ? calData : []);
      setConnected(true);
    } else {
      setEvents([]);
      setConnected(false);
    }

    setCheckingGoogleCal(false);
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  // --- UNIFIED EVENT COLLECTION & DEDUPLICATION ---
  const unifiedEvents = useMemo(() => {
    const list = [];
    const linkedEventIds = new Set();

    // Map study tasks by googleCalendarEventId
    const taskByEventId = new Map();
    for (const task of studyTasks) {
      if (task.googleCalendarEventId) {
        taskByEventId.set(task.googleCalendarEventId, task);
      }
    }

    // 1. Process Google Calendar events
    for (const evt of events) {
      const linkedTask = taskByEventId.get(evt.id);
      if (linkedTask) {
        // Unified Study Session synced to Calendar
        linkedEventIds.add(evt.id);
        list.push({
          id: `task_${linkedTask.id}`,
          rawId: linkedTask.id,
          eventId: evt.id,
          googleCalendarEventId: evt.id,
          title: linkedTask.title || evt.title,
          planId: linkedTask.planId,
          planTitle: linkedTask.planTitle,
          eventType: 'study_plan',
          isSynced: true,
          completed: Boolean(linkedTask.completed),
          durationMinutes: linkedTask.durationMinutes || 45,
          startTime: evt.startTime || linkedTask.startTime,
          endTime: evt.endTime || linkedTask.endTime,
          scheduledDate: linkedTask.scheduledDate || (evt.startTime ? evt.startTime.slice(0, 10) : ''),
          location: evt.location || linkedTask.planTitle || 'Academic Study',
          isAllDay: Boolean(evt.isAllDay),
          source: 'unified_study'
        });
      } else {
        // Pure Google Calendar Event
        const isAcademicOrStudy = /study|exam|course|quiz|lecture|assignment|homework/i.test(evt.title || '');
        list.push({
          id: `cal_${evt.id}`,
          rawId: evt.id,
          eventId: evt.id,
          googleCalendarEventId: evt.id,
          title: evt.title,
          eventType: 'google_calendar',
          isPersonal: !isAcademicOrStudy,
          isSynced: true,
          completed: false,
          durationMinutes: null,
          startTime: evt.startTime,
          endTime: evt.endTime,
          scheduledDate: evt.startTime ? evt.startTime.slice(0, 10) : '',
          location: evt.location || 'Calendar',
          isAllDay: Boolean(evt.isAllDay),
          source: 'google_calendar'
        });
      }
    }

    // 2. Add un-synced Study Tasks
    for (const task of studyTasks) {
      if (!task.googleCalendarEventId || !linkedEventIds.has(task.googleCalendarEventId)) {
        let taskStart = task.startTime;
        let taskEnd = task.endTime;
        if (!taskStart && task.scheduledDate && task.scheduledTime) {
          taskStart = `${task.scheduledDate}T${task.scheduledTime.length === 5 ? task.scheduledTime + ':00' : task.scheduledTime}`;
        }
        list.push({
          id: `task_${task.id}`,
          rawId: task.id,
          taskId: task.id,
          googleCalendarEventId: null,
          title: task.title,
          planId: task.planId,
          planTitle: task.planTitle,
          eventType: 'study_plan',
          isSynced: false,
          completed: Boolean(task.completed),
          durationMinutes: task.durationMinutes || 45,
          startTime: taskStart,
          endTime: taskEnd,
          scheduledDate: task.scheduledDate || '',
          location: task.planTitle || 'Study Plan',
          isAllDay: false,
          source: 'study_plan'
        });
      }
    }

    return list;
  }, [events, studyTasks]);

  // --- DATE RANGE & FILTER CALCULATIONS ---
  const { currentRangeLabel, filteredEvents } = useMemo(() => {
    let startLimit = null;
    let endLimit = null;
    let rangeLabel = '';

    if (view === 'day') {
      const sod = getStartOfDay(currentDate, timezone);
      const eod = getEndOfDay(currentDate, timezone);
      startLimit = sod;
      endLimit = eod;
      rangeLabel = formatDateForDisplay(currentDate, timezone, 'long');
    } else if (view === 'week') {
      const wk = getWeekRange(currentDate, timezone, 1);
      startLimit = wk.start;
      endLimit = wk.end;
      rangeLabel = `${formatDateForDisplay(wk.start, timezone, 'short')} – ${formatDateForDisplay(wk.end, timezone, 'medium')}`;
    } else if (view === 'month') {
      const mo = getMonthRange(currentDate, timezone);
      startLimit = mo.start;
      endLimit = mo.end;
      const parsed = parseDateSafe(currentDate);
      rangeLabel = parsed ? parsed.toLocaleDateString([], { timeZone: timezone, month: 'long', year: 'numeric' }) : 'This Month';
    } else {
      // Schedule / List: Next 30 days from currentDate
      const sod = getStartOfDay(currentDate, timezone);
      startLimit = sod;
      endLimit = new Date(sod.getTime() + 30 * 86400000);
      rangeLabel = `Schedule: ${formatDateForDisplay(sod, timezone, 'short')} – ${formatDateForDisplay(endLimit, timezone, 'short')}`;
    }

    const filtered = unifiedEvents.filter((item) => {
      // Type Filter
      if (typeFilter === 'study_plan' && item.eventType !== 'study_plan') {
        return false;
      }
      if (typeFilter === 'google_calendar' && item.eventType !== 'google_calendar' && !item.isSynced) {
        return false;
      }
      if (typeFilter === 'personal') {
        if (item.eventType !== 'google_calendar' || item.planId || !item.isPersonal) {
          return false;
        }
      }

      // Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesTitle = item.title?.toLowerCase().includes(q);
        const matchesLocation = item.location?.toLowerCase().includes(q);
        const matchesPlan = item.planTitle?.toLowerCase().includes(q);
        if (!matchesTitle && !matchesLocation && !matchesPlan) {
          return false;
        }
      }

      // Range Boundary Filter
      if (view === 'schedule') {
        if (!item.scheduledDate && !item.startTime) return true;
      }
      const itemDate = item.startTime ? parseDateSafe(item.startTime) : parseDateSafe(item.scheduledDate);
      if (!itemDate) return true; // Keep unscheduled items in list

      if (startLimit && endLimit) {
        const t = itemDate.getTime();
        return t >= startLimit.getTime() && t <= endLimit.getTime();
      }
      return true;
    });

    // Sort chronologically
    filtered.sort((a, b) => {
      const tA = a.startTime ? new Date(a.startTime).getTime() : (a.scheduledDate ? new Date(a.scheduledDate).getTime() : 0);
      const tB = b.startTime ? new Date(b.startTime).getTime() : (b.scheduledDate ? new Date(b.scheduledDate).getTime() : 0);
      return tA - tB;
    });

    return { currentRangeLabel: rangeLabel, filteredEvents: filtered };
  }, [unifiedEvents, view, currentDate, typeFilter, searchQuery, timezone]);

  // Unsynced study tasks available for Google Calendar sync
  const unsyncedStudyTasks = useMemo(() => {
    return unifiedEvents.filter((e) => e.eventType === 'study_plan' && !e.isSynced);
  }, [unifiedEvents]);

  // --- NAVIGATION HANDLERS ---
  const handlePrev = () => {
    const d = new Date(currentDate);
    if (view === 'day') d.setDate(d.getDate() - 1);
    else if (view === 'week') d.setDate(d.getDate() - 7);
    else if (view === 'month') d.setMonth(d.getMonth() - 1);
    else if (view === 'schedule') d.setDate(d.getDate() - 30);
    setCurrentDate(d);
  };

  const handleNext = () => {
    const d = new Date(currentDate);
    if (view === 'day') d.setDate(d.getDate() + 1);
    else if (view === 'week') d.setDate(d.getDate() + 7);
    else if (view === 'month') d.setMonth(d.getMonth() + 1);
    else if (view === 'schedule') d.setDate(d.getDate() + 30);
    setCurrentDate(d);
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  // --- NATURAL LANGUAGE PREVIEW & CONFIRM ---
  const handlePreview = async (e) => {
    e.preventDefault();
    if (!nlQuery.trim() || previewLoading) return;

    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const res = await api.previewCalendarEvent(nlQuery);
      setPreviewData(res);
    } catch (err) {
      setPreviewError(err.message || 'Failed to check calendar availability.');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleConfirmPreview = async () => {
    if (!previewData || confirming) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const created = await api.confirmCalendarEvent(
        previewData.confirmationToken,
        previewData.previewEvent
      );
      setEvents((prev) => [...prev, created]);
      setPreviewData(null);
      setNlQuery('');
    } catch (err) {
      setConfirmError(err.message || 'Could not write event to Google Calendar.');
    } finally {
      setConfirming(false);
    }
  };

  // --- TASK COMPLETION TOGGLE ---
  const handleToggleTaskCompletion = async (eventItem) => {
    if (eventItem.eventType !== 'study_plan' || !eventItem.planId || !eventItem.rawId) return;

    const newCompleted = !eventItem.completed;
    try {
      await api.updatePlanTask(eventItem.planId, eventItem.rawId, { completed: newCompleted });
      setStudyTasks((prev) =>
        prev.map((t) => (t.id === eventItem.rawId ? { ...t, completed: newCompleted } : t))
      );
      if (selectedEvent && selectedEvent.rawId === eventItem.rawId) {
        setSelectedEvent((prev) => ({ ...prev, completed: newCompleted }));
      }
    } catch (err) {
      alert('Failed to update task completion: ' + err.message);
    }
  };

  // --- DELETE EVENT ---
  const handleDeleteEvent = async (eventItem) => {
    if (!window.confirm(`Are you sure you want to remove "${eventItem.title}"?`)) return;

    try {
      if (eventItem.googleCalendarEventId) {
        await api.deleteCalendarEvent(eventItem.googleCalendarEventId);
        setEvents((prev) => prev.filter((e) => e.id !== eventItem.googleCalendarEventId));
      }
      if (eventItem.eventType === 'study_plan' && eventItem.planId && eventItem.rawId) {
        // If it's a study task, we can clear the calendar link or delete task if user requested
        await api.deletePlanTask(eventItem.planId, eventItem.rawId);
        setStudyTasks((prev) => prev.filter((t) => t.id !== eventItem.rawId));
      }
      setSelectedEvent(null);
    } catch (err) {
      alert('Failed to delete event: ' + (err.message || 'Unknown error'));
    }
  };

  // --- SYNC SELECTED TO GOOGLE CALENDAR ---
  const handleOpenSyncModal = () => {
    setSelectedSyncTaskIds(unsyncedStudyTasks.map((t) => t.rawId));
    setSyncResult(null);
    setShowSyncModal(true);
  };

  const handleToggleSyncSelection = (taskId) => {
    setSelectedSyncTaskIds((prev) =>
      prev.includes(taskId) ? prev.filter((id) => id !== taskId) : [...prev, taskId]
    );
  };

  const handleConfirmSync = async () => {
    if (selectedSyncTaskIds.length === 0 || syncing) return;
    setSyncing(true);
    setSyncResult(null);

    // Group selected tasks by planId
    const tasksToSync = unsyncedStudyTasks.filter((t) => selectedSyncTaskIds.includes(t.rawId));
    let totalSynced = 0;
    let errors = [];

    const planGroups = new Map();
    for (const t of tasksToSync) {
      if (!planGroups.has(t.planId)) planGroups.set(t.planId, []);
      planGroups.get(t.planId).push(t);
    }

    try {
      for (const [planId, groupTasks] of planGroups.entries()) {
        const studyBlocks = groupTasks.map((t) => ({
          id: `blk_${t.rawId}`,
          taskId: t.rawId,
          title: t.title,
          date: t.scheduledDate || getCurrentUserDate(timezone),
          startTime: t.startTime ? t.startTime.slice(11, 16) : '10:00',
          endTime: t.endTime ? t.endTime.slice(11, 16) : '11:00',
          durationMinutes: t.durationMinutes || 60
        }));

        try {
          const res = await api.syncPlanToCalendar(planId, studyBlocks);
          totalSynced += res.synced || 0;
        } catch (err) {
          errors.push(err.message);
        }
      }

      await fetchData(); // Refresh data from backend to show new Google Calendar IDs
      setSyncResult({
        success: true,
        message: `Successfully synchronized ${totalSynced} session(s) to Google Calendar.`
      });
    } catch (err) {
      setSyncResult({ success: false, message: err.message || 'Sync operation failed.' });
    } finally {
      setSyncing(false);
    }
  };

  // --- MANUAL CREATE EVENT ---
  const handleCreateEventSubmit = async (e) => {
    e.preventDefault();
    if (!createForm.title.trim() || creatingEvent) return;

    setCreatingEvent(true);
    try {
      const startDateTime = `${createForm.date}T${createForm.startTime}:00`;
      const endDateTime = `${createForm.date}T${createForm.endTime}:00`;

      if (createForm.isStudySession && createForm.planId) {
        // Add as Study Task to selected plan
        await api.addTaskToPlan(createForm.planId, {
          title: createForm.title,
          scheduledDate: createForm.date,
          startTime: startDateTime,
          endTime: endDateTime,
          durationMinutes: 60
        });
      } else {
        // Create directly via Google Calendar preview & confirm
        const preview = await api.previewCalendarEvent(
          `Schedule ${createForm.title} on ${createForm.date} at ${createForm.startTime}`
        );
        if (preview && preview.confirmationToken) {
          await api.confirmCalendarEvent(preview.confirmationToken, preview.previewEvent);
        }
      }

      await fetchData();
      setShowCreateModal(false);
      setCreateForm({
        title: '',
        date: getCurrentUserDate(),
        startTime: '10:00',
        endTime: '11:00',
        isStudySession: false,
        planId: ''
      });
    } catch (err) {
      alert('Failed to schedule event: ' + err.message);
    } finally {
      setCreatingEvent(false);
    }
  };

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-6">
      {/* Top Header & View Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white tracking-tight">Calendar Workspace</h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[#C59A55]">
              {timezone}
            </span>
          </div>
          <p className="text-xs text-[#A1A4AA] mt-1">
            One unified schedule for your study plan blocks, Google Calendar events, and academic commitments.
          </p>
        </div>

        {/* Global Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {unsyncedStudyTasks.length > 0 && (
            <button
              onClick={handleOpenSyncModal}
              className="btn-bronze text-xs py-1.5 px-3.5 flex items-center gap-1.5 shadow-sm"
              title="Sync study sessions to external Google Calendar"
            >
              <CalendarCheck size={14} />
              <span>Sync to Google Calendar ({unsyncedStudyTasks.length})</span>
            </button>
          )}

          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5"
          >
            <Plus size={14} />
            <span>New Event</span>
          </button>

          <button
            onClick={fetchData}
            className="p-1.5 rounded-lg bg-[#121418] border border-white/10 text-[#A1A4AA] hover:text-white transition-colors"
            title="Refresh Schedule"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Disconnection Warning if Google Calendar is offline */}
      {!checkingGoogleCal && !connected && (
        <div className="p-3.5 rounded-xl bg-[#C59A55]/10 border border-[#C59A55]/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-[#E6C17A]">
            <CalendarIcon size={16} />
            <span>Google Calendar is currently disconnected. Local study plans and schedule tasks remain fully functional.</span>
          </div>
          <button
            onClick={() => navigate('/app/integrations')}
            className="btn-bronze text-xs py-1 px-3 self-start sm:self-auto flex items-center gap-1"
          >
            <ExternalLink size={12} />
            <span>Connect Live Calendar</span>
          </button>
        </div>
      )}

      {/* Natural Language Event Dispatcher */}
      <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-3">
        <div className="flex items-center gap-2 text-xs font-mono uppercase text-[#E6C17A]">
          <Sparkles size={14} />
          <span>AI Schedule Dispatcher &amp; Conflict Checker</span>
        </div>

        <form onSubmit={handlePreview} className="flex flex-col sm:flex-row gap-2.5">
          <input
            type="text"
            placeholder="e.g. 'Schedule DSA Practice tomorrow at 4 PM for 90 minutes'..."
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            className="flex-1 bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-[#C59A55]"
          />
          <button
            type="submit"
            disabled={!nlQuery.trim() || previewLoading}
            className="btn-bronze text-xs py-2 px-4 whitespace-nowrap flex items-center justify-center gap-1.5"
          >
            {previewLoading ? <Loader2 size={13} className="animate-spin" /> : <span>Check Availability</span>}
          </button>
        </form>

        {previewError && (
          <div className="p-2.5 rounded-lg bg-[#F07878]/10 border border-[#F07878]/30 text-xs text-[#F07878] flex items-center gap-2">
            <AlertTriangle size={14} />
            <span>{previewError}</span>
          </div>
        )}

        {/* Dispatcher Confirmation Proposal Banner */}
        {previewData && (
          <div className="p-4 rounded-xl bg-[#181B20] border border-[#C59A55]/40 space-y-3 animate-in fade-in">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-white flex items-center gap-1.5">
                <CheckCircle2 size={15} className="text-[#42D6A4]" />
                Proposed Event Verification
              </span>
              <span className="text-[10px] font-mono text-[#E6C17A] bg-[#C59A55]/15 px-2 py-0.5 rounded border border-[#C59A55]/30">
                Awaiting Confirmation
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-[#08090B] p-3 rounded-lg border border-white/5 font-mono">
              <div>
                <span className="text-[#696E78]">Title: </span>
                <span className="text-white font-semibold">{previewData.previewEvent?.title}</span>
              </div>
              <div>
                <span className="text-[#696E78]">Time: </span>
                <span className="text-[#E6C17A]">
                  {formatTimeRange(previewData.previewEvent?.startTime, previewData.previewEvent?.endTime, timezone, previewData.previewEvent?.isAllDay)}
                </span>
              </div>
            </div>

            {previewData.conflicts && previewData.conflicts.length > 0 ? (
              <div className="p-2 rounded bg-[#F07878]/10 border border-[#F07878]/30 text-xs text-[#F07878] flex items-center gap-2">
                <AlertTriangle size={14} />
                <span>Conflict detected with an existing scheduled commitment!</span>
              </div>
            ) : (
              <div className="text-[11px] text-[#42D6A4] flex items-center gap-1.5 font-mono">
                <Check size={13} />
                <span>Zero schedule conflicts detected. Ready to commit to calendar.</span>
              </div>
            )}

            {confirmError && (
              <div className="p-2 rounded bg-[#F07878]/10 border border-[#F07878]/30 text-xs text-[#F07878] flex items-center gap-2">
                <AlertTriangle size={14} />
                <span>{confirmError}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-2.5 pt-1">
              <button
                type="button"
                onClick={() => setPreviewData(null)}
                className="btn-ghost text-xs py-1.5 px-3"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmPreview}
                disabled={confirming}
                className="btn-bronze text-xs py-1.5 px-4 font-semibold flex items-center gap-1.5"
              >
                {confirming ? <Loader2 size={13} className="animate-spin" /> : <span>Explicitly Confirm Event</span>}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Calendar Controls Bar: Navigation, Views & Filters */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-3 bg-[#121418] border border-white/10 rounded-xl">
        {/* Navigation Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center border border-white/10 rounded-lg overflow-hidden">
            <button
              onClick={handlePrev}
              className="p-1.5 hover:bg-white/5 text-[#A1A4AA] hover:text-white transition-colors"
              title="Previous period"
            >
              <ChevronLeft size={16} />
            </button>
            <div className="w-[1px] h-4 bg-white/10" />
            <button
              onClick={handleNext}
              className="p-1.5 hover:bg-white/5 text-[#A1A4AA] hover:text-white transition-colors"
              title="Next period"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <span className="text-sm font-semibold text-white ml-2">
            {currentRangeLabel}
          </span>
        </div>

        {/* Filters and Views */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search Input */}
          <div className="flex items-center gap-1.5 bg-[#08090B] border border-white/10 rounded-lg px-2.5 py-1 w-full sm:w-44">
            <Search size={13} className="text-[#696E78]" />
            <input
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-transparent text-xs text-white focus:outline-none"
            />
          </div>

          {/* Event Type Filter */}
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="bg-[#08090B] border border-white/10 text-xs text-[#A1A4AA] rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-[#C59A55]"
          >
            <option value="all">All Event Types</option>
            <option value="study_plan">Study Plan Blocks</option>
            <option value="google_calendar">Google Calendar</option>
            <option value="personal">Personal Events</option>
          </select>

          {/* View Mode Switcher */}
          <div className="flex items-center gap-1 bg-[#08090B] border border-white/10 p-1 rounded-lg">
            {[
              { id: 'day', label: 'Day' },
              { id: 'week', label: 'Week' },
              { id: 'month', label: 'Month' },
              { id: 'schedule', label: 'Schedule' }
            ].map((v) => (
              <button
                key={v.id}
                onClick={() => setView(v.id)}
                className={`px-2.5 py-1 rounded text-xs font-medium capitalize transition-all ${
                  view === v.id
                    ? 'bg-[#C59A55] text-black font-semibold'
                    : 'text-[#A1A4AA] hover:text-white'
                }`}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Unified Calendar Grid / Schedule */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((idx) => (
            <div key={idx} className="card-dark p-4 rounded-xl border border-white/5 bg-[#121418] space-y-3 animate-pulse">
              <div className="flex justify-between items-center">
                <div className="h-4 w-20 bg-white/10 rounded"></div>
                <div className="h-4 w-12 bg-white/5 rounded"></div>
              </div>
              <div className="h-5 w-3/4 bg-white/10 rounded"></div>
              <div className="h-3 w-1/2 bg-white/5 rounded"></div>
              <div className="pt-2.5 border-t border-white/5 flex justify-between">
                <div className="h-3 w-24 bg-white/5 rounded"></div>
                <div className="h-3 w-16 bg-white/5 rounded"></div>
              </div>
            </div>
          ))}
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="card-dark p-12 rounded-xl bg-[#121418] border border-white/10 text-center space-y-3">
          <CalendarIcon size={32} className="mx-auto text-[#696E78]" />
          <h3 className="text-sm font-semibold text-white">No Scheduled Events</h3>
          <p className="text-xs text-[#A1A4AA] max-w-md mx-auto">
            No study sessions or calendar commitments were found for the selected {view} filter.
          </p>
          <div className="flex justify-center gap-2 pt-2">
            <button
              onClick={() => setView('schedule')}
              className="btn-secondary text-xs py-1.5 px-3"
            >
              View Full Schedule
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
              className="btn-bronze text-xs py-1.5 px-3.5"
            >
              Schedule New Event
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredEvents.map((evt) => {
            const isStudy = evt.eventType === 'study_plan';
            const isUnscheduled = !evt.startTime && !evt.scheduledDate;
            const timeStr = isUnscheduled
              ? 'Unscheduled study task'
              : formatTimeRange(evt.startTime, evt.endTime, timezone, evt.isAllDay);
            const dateStr = evt.scheduledDate
              ? formatDateForDisplay(evt.scheduledDate, timezone, 'weekday_short')
              : (evt.startTime ? formatDateForDisplay(evt.startTime, timezone, 'weekday_short') : 'TBD');

            return (
              <div
                key={evt.id}
                onClick={() => setSelectedEvent(evt)}
                className={`card-dark p-4 rounded-xl border flex flex-col justify-between space-y-3 cursor-pointer hover:border-[#C59A55]/50 transition-all ${
                  evt.completed
                    ? 'bg-[#121418]/60 border-[#42D6A4]/30'
                    : isStudy
                    ? 'bg-[#121418] border-[#C59A55]/25'
                    : 'bg-[#121418] border-white/10'
                }`}
              >
                <div>
                  {/* Card Header Badges */}
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="text-[10px] font-mono uppercase tracking-wider">
                      {isStudy ? (
                        <span className="text-[#E6C17A] bg-[#C59A55]/15 px-1.5 py-0.5 rounded border border-[#C59A55]/30">
                          Study Plan
                        </span>
                      ) : (
                        <span className="text-[#82AFFF] bg-[#82AFFF]/15 px-1.5 py-0.5 rounded border border-[#82AFFF]/30">
                          Google Calendar
                        </span>
                      )}
                    </span>

                    <div className="flex items-center gap-1.5">
                      {evt.isSynced ? (
                        <span className="text-[10px] font-mono text-[#42D6A4] flex items-center gap-1 bg-[#42D6A4]/10 px-1.5 py-0.5 rounded">
                          <Check size={10} />
                          Synced
                        </span>
                      ) : (
                        <span className="text-[10px] font-mono text-[#A1A4AA] bg-white/5 px-1.5 py-0.5 rounded">
                          Local Plan
                        </span>
                      )}

                      {isStudy && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleTaskCompletion(evt);
                          }}
                          className={`p-1 rounded transition-colors ${
                            evt.completed
                              ? 'bg-[#42D6A4]/20 text-[#42D6A4]'
                              : 'bg-white/5 hover:bg-white/10 text-[#696E78]'
                          }`}
                          title={evt.completed ? 'Mark task as pending' : 'Mark task as completed'}
                        >
                          <Check size={11} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Title & Plan/Location */}
                  <h3 className={`text-sm font-semibold text-white ${evt.completed ? 'line-through text-[#A1A4AA]' : ''}`}>
                    {evt.title}
                  </h3>
                  {evt.location && (
                    <p className="text-xs text-[#696E78] mt-0.5 truncate">
                      {evt.location}
                    </p>
                  )}
                </div>

                {/* Card Footer: Timing & Date */}
                <div className="pt-2.5 border-t border-white/5 flex items-center justify-between text-xs font-mono text-[#A1A4AA]">
                  <div className="flex items-center gap-1 text-[#C59A55]">
                    <Clock size={11} />
                    <span>{timeStr}</span>
                  </div>
                  <span>{dateStr}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* --- MODAL 1: SYNC TO GOOGLE CALENDAR --- */}
      {showSyncModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#121418] border border-white/15 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2 text-white font-semibold">
                <CalendarCheck size={18} className="text-[#C59A55]" />
                <h3>Sync Study Sessions to Google Calendar</h3>
              </div>
              <button
                onClick={() => setShowSyncModal(false)}
                className="text-[#696E78] hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <p className="text-xs text-[#A1A4AA]">
              Select which study sessions to explicitly write into your authorized Google Calendar.
              Synchronized sessions will appear with live notifications and conflict checking.
            </p>

            {syncResult && (
              <div className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                syncResult.success ? 'bg-[#42D6A4]/10 text-[#42D6A4] border border-[#42D6A4]/30' : 'bg-[#F07878]/10 text-[#F07878] border border-[#F07878]/30'
              }`}>
                {syncResult.success ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                <span>{syncResult.message}</span>
              </div>
            )}

            <div className="max-h-60 overflow-y-auto divide-y divide-white/5 bg-[#08090B] rounded-xl border border-white/5 p-2">
              {unsyncedStudyTasks.map((t) => {
                const isChecked = selectedSyncTaskIds.includes(t.rawId);
                return (
                  <label
                    key={t.id}
                    className="flex items-center justify-between p-2.5 hover:bg-white/5 rounded-lg cursor-pointer text-xs"
                  >
                    <div className="flex items-center gap-2.5">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => handleToggleSyncSelection(t.rawId)}
                        className="rounded border-white/20 text-[#C59A55] focus:ring-0"
                      />
                      <div>
                        <div className="text-white font-medium">{t.title}</div>
                        <div className="text-[10px] font-mono text-[#696E78]">
                          {t.scheduledDate || 'Today'} • {t.durationMinutes || 45} mins
                        </div>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-[#E6C17A]">{t.planTitle}</span>
                  </label>
                );
              })}
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => {
                  if (selectedSyncTaskIds.length === unsyncedStudyTasks.length) {
                    setSelectedSyncTaskIds([]);
                  } else {
                    setSelectedSyncTaskIds(unsyncedStudyTasks.map((t) => t.rawId));
                  }
                }}
                className="text-xs text-[#A1A4AA] hover:text-white underline font-mono"
              >
                {selectedSyncTaskIds.length === unsyncedStudyTasks.length ? 'Deselect All' : 'Select All'}
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowSyncModal(false)}
                  className="btn-ghost text-xs"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={handleConfirmSync}
                  disabled={syncing || selectedSyncTaskIds.length === 0}
                  className="btn-bronze text-xs py-2 px-4 flex items-center gap-1.5"
                >
                  {syncing ? <Loader2 size={13} className="animate-spin" /> : <span>Confirm Sync ({selectedSyncTaskIds.length})</span>}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* --- MODAL 2: EVENT DETAILS & ACTIONS --- */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#121418] border border-white/15 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <span className="text-[10px] font-mono uppercase text-[#C59A55]">
                {selectedEvent.eventType === 'study_plan' ? 'Study Plan Session' : 'Calendar Event'}
              </span>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-[#696E78] hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div>
              <h2 className="text-lg font-bold text-white">{selectedEvent.title}</h2>
              {selectedEvent.planTitle && (
                <p className="text-xs text-[#E6C17A] mt-0.5">Plan: {selectedEvent.planTitle}</p>
              )}
            </div>

            <div className="space-y-2 text-xs bg-[#08090B] p-3.5 rounded-xl border border-white/5 font-mono">
              <div className="flex justify-between">
                <span className="text-[#696E78]">Date:</span>
                <span className="text-white">
                  {selectedEvent.scheduledDate || (selectedEvent.startTime ? selectedEvent.startTime.slice(0, 10) : 'TBD')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#696E78]">Time:</span>
                <span className="text-[#C59A55]">
                  {formatTimeRange(selectedEvent.startTime, selectedEvent.endTime, timezone, selectedEvent.isAllDay)}
                </span>
              </div>
              {selectedEvent.durationMinutes && (
                <div className="flex justify-between">
                  <span className="text-[#696E78]">Duration:</span>
                  <span className="text-white">{selectedEvent.durationMinutes} minutes</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-[#696E78]">Sync Status:</span>
                <span className={selectedEvent.isSynced ? 'text-[#42D6A4]' : 'text-[#A1A4AA]'}>
                  {selectedEvent.isSynced ? 'Synced to Google Calendar' : 'Local Only'}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => handleDeleteEvent(selectedEvent)}
                className="text-xs text-[#F07878] hover:underline flex items-center gap-1"
              >
                <Trash2 size={13} />
                <span>Delete</span>
              </button>

              <div className="flex items-center gap-2">
                {selectedEvent.eventType === 'study_plan' && (
                  <button
                    type="button"
                    onClick={() => handleToggleTaskCompletion(selectedEvent)}
                    className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1"
                  >
                    <Check size={13} />
                    <span>{selectedEvent.completed ? 'Mark Pending' : 'Mark Completed'}</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setSelectedEvent(null)}
                  className="btn-ghost text-xs py-1.5 px-3"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* --- MODAL 3: MANUAL CREATE EVENT --- */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <form
            onSubmit={handleCreateEventSubmit}
            className="bg-[#121418] border border-white/15 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Plus size={16} className="text-[#C59A55]" />
                <span>Schedule New Event</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="text-[#696E78] hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-[#A1A4AA] mb-1">Event Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Algorithms Review Session"
                  value={createForm.title}
                  onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
                  className="w-full bg-[#08090B] border border-white/10 rounded-lg p-2 text-white focus:outline-none focus:border-[#C59A55]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#A1A4AA] mb-1">Date</label>
                  <input
                    type="date"
                    required
                    value={createForm.date}
                    onChange={(e) => setCreateForm({ ...createForm, date: e.target.value })}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg p-2 text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
                <div>
                  <label className="block text-[#A1A4AA] mb-1">Start Time</label>
                  <input
                    type="time"
                    required
                    value={createForm.startTime}
                    onChange={(e) => setCreateForm({ ...createForm, startTime: e.target.value })}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg p-2 text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
              </div>

              {plans.length > 0 && (
                <div>
                  <label className="flex items-center gap-2 text-[#A1A4AA] cursor-pointer mb-2">
                    <input
                      type="checkbox"
                      checked={createForm.isStudySession}
                      onChange={(e) => setCreateForm({ ...createForm, isStudySession: e.target.checked })}
                      className="rounded border-white/20 text-[#C59A55] focus:ring-0"
                    />
                    <span>Associate with an active Study Plan</span>
                  </label>

                  {createForm.isStudySession && (
                    <select
                      value={createForm.planId}
                      onChange={(e) => setCreateForm({ ...createForm, planId: e.target.value })}
                      className="w-full bg-[#08090B] border border-white/10 rounded-lg p-2 text-white focus:outline-none focus:border-[#C59A55]"
                      required={createForm.isStudySession}
                    >
                      <option value="">Select Study Plan...</option>
                      {plans.map((p) => (
                        <option key={p.id} value={p.id}>{p.title}</option>
                      ))}
                    </select>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-white/5">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="btn-ghost text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creatingEvent || !createForm.title.trim()}
                className="btn-bronze text-xs py-2 px-4 flex items-center gap-1.5"
              >
                {creatingEvent ? <Loader2 size={13} className="animate-spin" /> : <span>Create Event</span>}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
