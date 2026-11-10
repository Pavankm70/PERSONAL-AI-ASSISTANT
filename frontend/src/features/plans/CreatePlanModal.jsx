import React, { useState } from 'react';
import { 
  BookOpen, 
  X, 
  Plus, 
  Loader2, 
  Sparkles, 
  Calendar, 
  Clock, 
  Check, 
  Edit3, 
  Trash2, 
  Coffee, 
  ChevronRight, 
  ArrowLeft,
  CalendarCheck
} from 'lucide-react';
import { api } from '../../services/api';

const DURATION_PRESETS = [
  { label: '1 Day Intensive', value: '1 day', days: 1 },
  { label: '7 Days (1 Week)', value: '7 days', days: 7 },
  { label: '14 Days (2 Weeks)', value: '14 days', days: 14 },
  { label: '30 Days (1 Month)', value: '30 days', days: 30 },
  { label: '60 Days (2 Months)', value: '2 months', days: 60 },
  { label: '90 Days (3 Months)', value: '3 months', days: 90 },
  { label: '180 Days (6 Months)', value: '6 months', days: 180 },
  { label: 'Custom Duration', value: 'custom', days: null }
];

const SUBJECT_PRESETS = [
  'Data Structures & Algorithms',
  'Java & Spring Boot',
  'Machine Learning & Deep Learning',
  'Full-Stack Web Development',
  'Python Programming'
];

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export const CreatePlanModal = ({ isOpen, onClose, onCreate }) => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowStr = tomorrow.toISOString().split('T')[0];

  // Wizard Step: 'config' | 'preview'
  const [step, setStep] = useState('config');

  // Step 1: Configuration State
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState(SUBJECT_PRESETS[0]);
  const [learningGoal, setLearningGoal] = useState('');
  const [durationPreset, setDurationPreset] = useState('30 days');
  const [customDays, setCustomDays] = useState(45);
  const [startDate, setStartDate] = useState(tomorrowStr);
  const [dailyHours, setDailyHours] = useState(2.0);
  const [preferredDays, setPreferredDays] = useState(WEEKDAYS);
  const [generatingProposal, setGeneratingProposal] = useState(false);
  const [proposalError, setProposalError] = useState(null);

  // Step 2: Editable Preview State
  const [proposalData, setProposalData] = useState(null);
  const [editableTasks, setEditableTasks] = useState([]);
  const [batchTime, setBatchTime] = useState('19:00');
  const [syncToCalendar, setSyncToCalendar] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSelectPresetDuration = (val) => {
    setDurationPreset(val);
    if (val !== 'custom') {
      const match = DURATION_PRESETS.find(p => p.value === val);
      if (match && subject) {
        setTitle(`${match.label.split(' ')[0]} ${subject} Roadmap`);
      }
    }
  };

  const handleSubjectChange = (newSubj) => {
    setSubject(newSubj);
    if (!title || SUBJECT_PRESETS.some(p => title.includes(p))) {
      const match = DURATION_PRESETS.find(p => p.value === durationPreset);
      const durLabel = match && match.value !== 'custom' ? match.label.split(' ')[0] : 'Study';
      setTitle(`${durLabel} ${newSubj} Roadmap`);
    }
  };

  const toggleDay = (day) => {
    setPreferredDays(prev => 
      prev.includes(day) 
        ? (prev.length > 1 ? prev.filter(d => d !== day) : prev) 
        : [...prev, day]
    );
  };

  const setDaysPreset = (preset) => {
    if (preset === 'all') setPreferredDays(WEEKDAYS);
    else if (preset === 'weekdays') setPreferredDays(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']);
    else if (preset === 'weekends') setPreferredDays(['Saturday', 'Sunday']);
  };

  // Generate Proposal Preview (Does not save to DB)
  const handleGenerateProposal = async (e) => {
    e.preventDefault();
    if (generatingProposal || !subject.trim()) return;

    const finalTitle = title.trim() || `${durationPreset} ${subject} Roadmap`;
    const finalDuration = durationPreset === 'custom' ? `${customDays} days` : durationPreset;

    setGeneratingProposal(true);
    setProposalError(null);
    try {
      const res = await api.generateProposal({
        title: finalTitle,
        subject: subject.trim(),
        learning_goal: learningGoal.trim() || `Master ${subject} in ${finalDuration}`,
        period: finalDuration,
        start_date: startDate,
        daily_hours_target: Number(dailyHours),
        preferred_study_days: preferredDays
      });

      setProposalData(res);
      setEditableTasks((res.tasks || []).map((t, idx) => ({
        ...t,
        id: t.id || `preview_${idx + 1}`,
        isRestDay: false
      })));
      setStep('preview');
    } catch (err) {
      setProposalError(err.message || 'Failed to generate plan proposal preview.');
    } finally {
      setGeneratingProposal(false);
    }
  };

  // Batch Time Shift (e.g. Set all sessions to 7:00 PM)
  const handleApplyBatchTime = () => {
    if (!batchTime) return;
    setEditableTasks(prev => prev.map(t => {
      if (t.isRestDay) return t;
      const [hStr, mStr] = batchTime.split(':');
      const h = parseInt(hStr, 10);
      const m = parseInt(mStr || '0', 10);
      const ampm = h >= 12 ? 'PM' : 'AM';
      const dispH = h % 12 === 0 ? 12 : h % 12;
      const formattedStart = `${String(dispH).padStart(2, '0')}:${String(m).padStart(2, '0')} ${ampm}`;

      // Calculate end time
      const dur = t.durationMinutes || Math.round(dailyHours * 60) || 60;
      const totalMins = h * 60 + m + dur;
      const endH = Math.floor(totalMins / 60) % 24;
      const endM = totalMins % 60;
      const endAmpm = endH >= 12 ? 'PM' : 'AM';
      const dispEndH = endH % 12 === 0 ? 12 : endH % 12;
      const formattedEnd = `${String(dispEndH).padStart(2, '0')}:${String(endM).padStart(2, '0')} ${endAmpm}`;

      return {
        ...t,
        startTime: formattedStart,
        endTime: formattedEnd
      };
    }));
  };

  // Toggle Rest Day for a specific session
  const handleToggleRestDay = (taskIndex) => {
    setEditableTasks(prev => prev.map((t, idx) => 
      idx === taskIndex ? { ...t, isRestDay: !t.isRestDay } : t
    ));
  };

  // Update a single task field
  const handleUpdateTaskField = (taskIndex, field, value) => {
    setEditableTasks(prev => prev.map((t, idx) => 
      idx === taskIndex ? { ...t, [field]: value } : t
    ));
  };

  // Delete a task from proposal
  const handleDeleteTask = (taskIndex) => {
    setEditableTasks(prev => prev.filter((_, idx) => idx !== taskIndex));
  };

  // Confirm & Persist Approved Plan
  const handleConfirmAndSave = async () => {
    if (submitting) return;

    const finalTitle = title.trim() || `${durationPreset} ${subject} Roadmap`;
    const finalDays = durationPreset === 'custom' ? Number(customDays) : null;
    const finalDuration = durationPreset === 'custom' ? `${customDays} days` : durationPreset;

    // Filter out rest days before saving
    const activeTasksToPersist = editableTasks.filter(t => !t.isRestDay);

    setSubmitting(true);
    try {
      await onCreate({
        title: finalTitle,
        subject: subject.trim(),
        learningGoal: learningGoal.trim() || `Master ${subject} in ${finalDuration}`,
        duration: finalDuration,
        durationDays: finalDays,
        startDate,
        dailyHours: Number(dailyHours),
        preferredStudyDays: preferredDays,
        tasks: activeTasksToPersist,
        syncToCalendar
      });
      onClose();
    } catch (err) {
      alert('Failed to save study plan: ' + (err.message || 'Unknown error'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
      <div className={`card-dark p-6 sm:p-8 rounded-2xl bg-[#121418] border border-white/10 max-w-2xl w-full space-y-6 my-8 animate-in fade-in zoom-in-95 ${
        step === 'preview' ? 'max-w-4xl' : 'max-w-xl'
      }`}>
        <div className="flex items-center justify-between pb-4 border-b border-white/5">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#C59A55]/15 border border-[#C59A55]/30 flex items-center justify-center text-[#E6C17A]">
              <Sparkles size={16} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                {step === 'config' ? 'Configure AI Study Plan' : 'Review & Edit Proposed Roadmap'}
              </h3>
              <p className="text-xs text-[#A1A4AA]">
                {step === 'config' 
                  ? 'Define roadmap duration (1 day to 6 months) and study parameters' 
                  : 'Customize task titles, study times, durations, and rest days before saving'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[#696E78] hover:text-white p-1 rounded transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {proposalError && (
          <div className="p-3 rounded-lg bg-[#F07878]/10 border border-[#F07878]/30 text-xs text-[#F07878]">
            {proposalError}
          </div>
        )}

        {/* STEP 1: CONFIGURATION FORM */}
        {step === 'config' && (
          <form onSubmit={handleGenerateProposal} className="space-y-5 text-xs">
            {/* Subject Quick Selector */}
            <div>
              <label className="text-[#A1A4AA] block mb-1.5 font-mono uppercase text-[10px]">
                Domain / Subject / Examination
              </label>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {SUBJECT_PRESETS.map((p) => (
                  <button
                    type="button"
                    key={p}
                    onClick={() => handleSubjectChange(p)}
                    className={`px-2.5 py-1 rounded text-[11px] transition-all ${
                      subject === p
                        ? 'bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/50 font-medium'
                        : 'bg-white/5 text-[#A1A4AA] border border-white/5 hover:text-white'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g. Distributed Systems, Kubernetes, Deep Learning"
                className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                required
              />
            </div>

            {/* Plan Title */}
            <div>
              <label className="text-[#A1A4AA] block mb-1.5 font-mono uppercase text-[10px]">
                Plan Title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. 6-Month Machine Learning & AI Engineering Roadmap"
                className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                required
              />
            </div>

            {/* Duration Selector */}
            <div>
              <label className="text-[#A1A4AA] block mb-1.5 font-mono uppercase text-[10px]">
                Plan Duration (1 Day up to 6 Months)
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
                {DURATION_PRESETS.map((preset) => (
                  <button
                    type="button"
                    key={preset.value}
                    onClick={() => handleSelectPresetDuration(preset.value)}
                    className={`p-2 rounded-lg text-left text-[11px] border transition-all ${
                      durationPreset === preset.value
                        ? 'bg-[#C59A55]/20 border-[#C59A55]/50 text-[#E6C17A] font-semibold'
                        : 'bg-[#08090B] border-white/5 text-[#A1A4AA] hover:text-white hover:border-white/10'
                    }`}
                  >
                    <div>{preset.label}</div>
                  </button>
                ))}
              </div>

              {durationPreset === 'custom' && (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-[#08090B] border border-white/10 mt-2">
                  <span className="text-white">Custom Duration:</span>
                  <input
                    type="number"
                    min={1}
                    max={183}
                    value={customDays}
                    onChange={(e) => setCustomDays(Math.max(1, Math.min(183, Number(e.target.value))))}
                    className="w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-center text-white focus:outline-none focus:border-[#C59A55]"
                  />
                  <span className="text-[#A1A4AA]">days (up to 183 days / 6 months)</span>
                </div>
              )}
            </div>

            {/* Start Date & Daily Hours */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-[#A1A4AA] block mb-1.5 font-mono uppercase text-[10px] flex items-center gap-1.5">
                  <Calendar size={12} className="text-[#C59A55]" />
                  <span>Start Date</span>
                </label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                  required
                />
              </div>

              <div>
                <label className="text-[#A1A4AA] block mb-1.5 font-mono uppercase text-[10px] flex items-center gap-1.5">
                  <Clock size={12} className="text-[#C59A55]" />
                  <span>Daily Study Target (hours)</span>
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={0.5}
                    max={12}
                    step={0.5}
                    value={dailyHours}
                    onChange={(e) => setDailyHours(e.target.value)}
                    className="w-24 bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55] text-center"
                  />
                  <span className="text-[#696E78] text-[11px] font-mono">
                    {Math.round(dailyHours * 60)} mins per study day
                  </span>
                </div>
              </div>
            </div>

            {/* Preferred Study Days */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[#A1A4AA] font-mono uppercase text-[10px]">
                  Active Study Days ({preferredDays.length}/7)
                </label>
                <div className="flex gap-2 text-[10px] text-[#C59A55]">
                  <button type="button" onClick={() => setDaysPreset('all')} className="hover:underline">All</button>
                  <span className="text-[#696E78]">•</span>
                  <button type="button" onClick={() => setDaysPreset('weekdays')} className="hover:underline">Weekdays</button>
                  <span className="text-[#696E78]">•</span>
                  <button type="button" onClick={() => setDaysPreset('weekends')} className="hover:underline">Weekends</button>
                </div>
              </div>
              <div className="grid grid-cols-7 gap-1">
                {WEEKDAYS.map((day) => {
                  const active = preferredDays.includes(day);
                  return (
                    <button
                      type="button"
                      key={day}
                      onClick={() => toggleDay(day)}
                      className={`py-1.5 px-1 rounded text-center text-[10px] font-mono transition-all ${
                        active
                          ? 'bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/40 font-semibold'
                          : 'bg-[#08090B] text-[#696E78] border border-white/5 hover:text-white'
                      }`}
                    >
                      {day.substring(0, 3)}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Primary Goals */}
            <div>
              <label className="text-[#A1A4AA] block mb-1.5 font-mono uppercase text-[10px]">
                Primary Learning Goal & Milestones
              </label>
              <textarea
                rows={2}
                value={learningGoal}
                onChange={(e) => setLearningGoal(e.target.value)}
                placeholder="e.g. Master core algorithms, solve 150 LeetCode problems, pass technical interviews"
                className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
              />
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/5">
              <button
                type="button"
                onClick={onClose}
                disabled={generatingProposal}
                className="btn-ghost text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={generatingProposal || !subject.trim()}
                className="btn-bronze text-xs py-2 px-5 flex items-center gap-2 font-semibold"
              >
                {generatingProposal ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Generating Proposal Preview...</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={14} />
                    <span>Generate Proposal Preview</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* STEP 2: EDITABLE PROPOSAL PREVIEW & SCHEDULE BUILDER */}
        {step === 'preview' && (
          <div className="space-y-5 text-xs animate-in fade-in">
            {/* Proposal Overview Banner */}
            <div className="p-4 rounded-xl bg-[#08090B] border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <span className="text-[10px] font-mono uppercase text-[#E6C17A] bg-[#C59A55]/15 px-2 py-0.5 rounded border border-[#C59A55]/30">
                  Proposal Preview
                </span>
                <h4 className="text-sm font-semibold text-white mt-1">{title}</h4>
                <p className="text-xs text-[#A1A4AA] font-mono">
                  {editableTasks.filter(t => !t.isRestDay).length} Active Sessions • {durationPreset} • {dailyHours}h daily
                </p>
              </div>

              {/* Batch Time Shift Control */}
              <div className="flex items-center gap-2 bg-[#121418] p-2 rounded-lg border border-white/5">
                <Clock size={13} className="text-[#C59A55]" />
                <span className="text-[#A1A4AA] text-[11px]">Batch Time:</span>
                <input
                  type="time"
                  value={batchTime}
                  onChange={(e) => setBatchTime(e.target.value)}
                  className="bg-[#08090B] border border-white/10 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                />
                <button
                  type="button"
                  onClick={handleApplyBatchTime}
                  className="btn-secondary text-[11px] py-1 px-2.5 whitespace-nowrap"
                  title="Apply this start time to all scheduled study sessions"
                >
                  Apply All
                </button>
              </div>
            </div>

            {/* Editable Sessions Table */}
            <div className="border border-white/10 rounded-xl overflow-hidden bg-[#08090B]">
              <div className="p-3 bg-[#121418] border-b border-white/10 flex items-center justify-between text-xs text-[#A1A4AA] font-mono">
                <span>Proposed Roadmap Sessions ({editableTasks.length})</span>
                <span>Click title, date, or time to customize</span>
              </div>

              <div className="max-h-80 overflow-y-auto divide-y divide-white/5 p-2 space-y-1">
                {editableTasks.map((task, idx) => (
                  <div
                    key={task.id || idx}
                    className={`p-2.5 rounded-lg flex flex-col md:flex-row md:items-center justify-between gap-2 transition-all ${
                      task.isRestDay
                        ? 'bg-white/[0.02] opacity-60 border border-dashed border-white/10'
                        : 'bg-[#121418] border border-white/5 hover:border-white/15'
                    }`}
                  >
                    {/* Left: Task Title & Day Label */}
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-[#C59A55] bg-[#C59A55]/10 px-1.5 py-0.5 rounded">
                          {task.dayLabel || `Day ${idx + 1}`}
                        </span>
                        {task.isRestDay && (
                          <span className="text-[10px] font-mono text-[#A1A4AA] flex items-center gap-1">
                            <Coffee size={10} />
                            Rest Day (Skipped)
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        disabled={task.isRestDay}
                        value={task.title}
                        onChange={(e) => handleUpdateTaskField(idx, 'title', e.target.value)}
                        className={`w-full bg-transparent border-b border-transparent focus:border-[#C59A55] text-xs font-medium focus:outline-none ${
                          task.isRestDay ? 'line-through text-[#696E78]' : 'text-white'
                        }`}
                      />
                    </div>

                    {/* Right: Date, Time & Controls */}
                    <div className="flex items-center gap-2 text-xs">
                      <input
                        type="date"
                        disabled={task.isRestDay}
                        value={task.scheduledDate || ''}
                        onChange={(e) => handleUpdateTaskField(idx, 'scheduledDate', e.target.value)}
                        className="bg-[#08090B] border border-white/10 rounded px-2 py-1 text-white text-[11px] focus:outline-none focus:border-[#C59A55]"
                      />
                      <input
                        type="text"
                        disabled={task.isRestDay}
                        value={task.startTime || '10:00 AM'}
                        onChange={(e) => handleUpdateTaskField(idx, 'startTime', e.target.value)}
                        placeholder="Time"
                        className="w-20 bg-[#08090B] border border-white/10 rounded px-2 py-1 text-center text-white text-[11px] focus:outline-none focus:border-[#C59A55]"
                      />
                      <div className="flex items-center gap-1 bg-[#08090B] border border-white/10 rounded px-1.5 py-1">
                        <input
                          type="number"
                          disabled={task.isRestDay}
                          value={task.durationMinutes || 60}
                          onChange={(e) => handleUpdateTaskField(idx, 'durationMinutes', Number(e.target.value))}
                          className="w-10 bg-transparent text-center text-white text-[11px] focus:outline-none"
                        />
                        <span className="text-[10px] text-[#696E78]">m</span>
                      </div>

                      {/* Rest Day Toggle */}
                      <button
                        type="button"
                        onClick={() => handleToggleRestDay(idx)}
                        className={`p-1.5 rounded transition-colors ${
                          task.isRestDay
                            ? 'bg-[#C59A55]/20 text-[#E6C17A]'
                            : 'bg-white/5 text-[#A1A4AA] hover:text-white'
                        }`}
                        title={task.isRestDay ? 'Re-enable study session' : 'Mark as rest day'}
                      >
                        <Coffee size={13} />
                      </button>

                      {/* Delete Task Button */}
                      <button
                        type="button"
                        onClick={() => handleDeleteTask(idx)}
                        className="p-1.5 rounded bg-white/5 text-[#696E78] hover:text-[#F07878] transition-colors"
                        title="Delete task from roadmap"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Google Calendar Sync Checkbox */}
            <label className="flex items-center gap-2.5 p-3 rounded-lg bg-[#C59A55]/10 border border-[#C59A55]/30 cursor-pointer text-xs">
              <input
                type="checkbox"
                checked={syncToCalendar}
                onChange={(e) => setSyncToCalendar(e.target.checked)}
                className="rounded border-white/20 text-[#C59A55] focus:ring-0"
              />
              <span className="text-[#E6C17A] font-medium flex items-center gap-1.5">
                <CalendarCheck size={14} />
                <span>Sync approved study sessions to Google Calendar upon creation</span>
              </span>
            </label>

            {/* Actions */}
            <div className="flex items-center justify-between pt-2 border-t border-white/5">
              <button
                type="button"
                onClick={() => setStep('config')}
                disabled={submitting}
                className="btn-ghost text-xs flex items-center gap-1.5"
              >
                <ArrowLeft size={13} />
                <span>Back to Settings</span>
              </button>

              <button
                type="button"
                onClick={handleConfirmAndSave}
                disabled={submitting || editableTasks.filter(t => !t.isRestDay).length === 0}
                className="btn-bronze text-xs py-2 px-6 flex items-center gap-2 font-semibold"
              >
                {submitting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Saving Study Plan...</span>
                  </>
                ) : (
                  <>
                    <Check size={14} />
                    <span>Confirm &amp; Save Plan ({editableTasks.filter(t => !t.isRestDay).length} Sessions)</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

