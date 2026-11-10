import React, { useState } from 'react';
import { 
  ChevronDown, 
  ChevronRight, 
  CheckSquare, 
  Square, 
  Trash2, 
  Calendar, 
  Clock, 
  CheckCircle2, 
  Plus, 
  Layers, 
  Filter, 
  Sparkles,
  Loader2,
  CalendarCheck,
  Palmtree
} from 'lucide-react';

export const PlanRoadmapTab = ({
  plan,
  roadmapData,
  onToggleTask,
  onAddTask,
  onDeleteTask,
  onRegenerateRoadmap
}) => {
  const [selectedMonth, setSelectedMonth] = useState('all'); // 'all' or monthNumber
  const [expandedMonths, setExpandedMonths] = useState(new Set([1, 2]));
  const [expandedWeeks, setExpandedWeeks] = useState(new Set([1, 2, 3, 4]));
  const [searchFilter, setSearchFilter] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskDuration, setNewTaskDuration] = useState(plan?.dailyHoursTarget ? Math.round(plan.dailyHoursTarget * 60) : 60);
  const [newTaskMonth, setNewTaskMonth] = useState(1);
  const [newTaskWeek, setNewTaskWeek] = useState(1);
  const [newTaskDay, setNewTaskDay] = useState(1);
  const [addingTask, setAddingTask] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const months = roadmapData?.months || [];
  const summary = roadmapData?.summary || {};

  const toggleMonthExpand = (mNum) => {
    setExpandedMonths(prev => {
      const next = new Set(prev);
      if (next.has(mNum)) next.delete(mNum);
      else next.add(mNum);
      return next;
    });
  };

  const toggleWeekExpand = (wNum) => {
    setExpandedWeeks(prev => {
      const next = new Set(prev);
      if (next.has(wNum)) next.delete(wNum);
      else next.add(wNum);
      return next;
    });
  };

  const handleExpandAll = () => {
    setExpandedMonths(new Set(months.map(m => m.monthNumber)));
    setExpandedWeeks(new Set(months.flatMap(m => m.weeks.map(w => w.weekNumber))));
  };

  const handleCollapseAll = () => {
    setExpandedMonths(new Set());
    setExpandedWeeks(new Set());
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    if (!newTaskTitle.trim() || addingTask) return;

    setAddingTask(true);
    try {
      await onAddTask({
        title: newTaskTitle.trim(),
        durationMinutes: Number(newTaskDuration) || 60,
        monthNumber: Number(newTaskMonth) || 1,
        weekNumber: Number(newTaskWeek) || 1,
        dayNumber: Number(newTaskDay) || 1,
        taskType: 'daily',
        dayLabel: `Day ${newTaskDay}`,
        weekLabel: `Week ${newTaskWeek}`,
        monthLabel: `Month ${newTaskMonth}`,
        priority: 'high',
        completed: false
      });
      setNewTaskTitle('');
      setShowAddModal(false);
    } catch (err) {
      alert('Failed to add task: ' + (err.message || 'Unknown error'));
    } finally {
      setAddingTask(false);
    }
  };

  const handleRegenerate = async () => {
    if (!window.confirm('Regenerate full-duration roadmap for this plan? Uncompleted tasks will be replaced with a fresh curriculum.')) {
      return;
    }
    setRegenerating(true);
    try {
      await onRegenerateRoadmap();
    } catch (err) {
      alert('Failed to regenerate roadmap: ' + (err.message || 'Unknown error'));
    } finally {
      setRegenerating(false);
    }
  };

  const filteredMonths = selectedMonth === 'all' 
    ? months 
    : months.filter(m => m.monthNumber === Number(selectedMonth));

  return (
    <div className="space-y-6">
      {/* Roadmap Controls Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-[#121418] border border-white/10">
        {/* Month Pills Filter */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <span className="text-[10px] font-mono uppercase text-[#696E78] mr-1">
            VIEW:
          </span>
          <button
            onClick={() => setSelectedMonth('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all whitespace-nowrap ${
              selectedMonth === 'all'
                ? 'bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/50 font-semibold'
                : 'bg-white/5 text-[#A1A4AA] hover:text-white border border-white/5'
            }`}
          >
            All Months ({months.length})
          </button>
          {months.map((m) => (
            <button
              key={m.monthNumber}
              onClick={() => setSelectedMonth(m.monthNumber)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all whitespace-nowrap ${
                selectedMonth === m.monthNumber
                  ? 'bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/50 font-semibold'
                  : 'bg-white/5 text-[#A1A4AA] hover:text-white border border-white/5'
              }`}
            >
              {m.monthLabel}
            </button>
          ))}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
          <button
            onClick={handleExpandAll}
            className="text-[11px] text-[#A1A4AA] hover:text-white px-2 py-1 rounded bg-white/5"
          >
            Expand All
          </button>
          <button
            onClick={handleCollapseAll}
            className="text-[11px] text-[#A1A4AA] hover:text-white px-2 py-1 rounded bg-white/5"
          >
            Collapse All
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1"
          >
            <Plus size={13} />
            <span>Add Task</span>
          </button>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            className="text-[11px] text-[#A1A4AA] hover:text-[#E6C17A] px-2 py-1 rounded border border-white/10 flex items-center gap-1"
            title="Regenerate curriculum"
          >
            {regenerating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            <span>Regenerate</span>
          </button>
        </div>
      </div>

      {/* Empty State */}
      {(!months || months.length === 0) && (
        <div className="card-dark p-12 rounded-2xl bg-[#121418] border border-white/10 text-center space-y-4">
          <Layers size={32} className="text-[#C59A55] mx-auto" />
          <h3 className="text-base font-bold text-white">No Roadmap Generated Yet</h3>
          <p className="text-xs text-[#A1A4AA] max-w-md mx-auto">
            This study plan currently has no structured tasks. Click &quot;Regenerate&quot; to have AURELIA build the full month, week, and daily roadmap.
          </p>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            className="btn-bronze text-xs py-2 px-4 mx-auto flex items-center gap-1.5 font-semibold"
          >
            <Sparkles size={14} />
            <span>Generate Full Roadmap</span>
          </button>
        </div>
      )}

      {/* Month -> Week -> Day Hierarchy */}
      <div className="space-y-6">
        {filteredMonths.map((m) => {
          const isMonthExpanded = expandedMonths.has(m.monthNumber);
          return (
            <div
              key={m.monthNumber}
              className="card-dark rounded-xl bg-[#121418] border border-white/10 overflow-hidden transition-all shadow-lg"
            >
              {/* Month Header Banner */}
              <div
                onClick={() => toggleMonthExpand(m.monthNumber)}
                className="p-5 bg-gradient-to-r from-[#181B20] to-[#121418] border-b border-white/5 cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-white/[0.02]"
              >
                <div className="flex items-center gap-3">
                  <div className="p-1.5 rounded-lg bg-[#C59A55]/15 text-[#E6C17A]">
                    {isMonthExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold uppercase text-[#C59A55]">
                        {m.monthLabel}
                      </span>
                      {m.startDate && (
                        <span className="text-[11px] font-mono text-[#A1A4AA]">
                          ({m.startDate} → {m.endDate || ''})
                        </span>
                      )}
                    </div>
                    <h3 className="text-sm font-bold text-white mt-0.5">
                      {m.milestone || `Month ${m.monthNumber} Learning Milestone`}
                    </h3>
                  </div>
                </div>

                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="text-right">
                    <div className="text-xs font-mono font-bold text-white">
                      {m.completedTasks} / {m.totalTasks} Tasks ({m.progress}%)
                    </div>
                    <div className="text-[10px] font-mono text-[#A1A4AA]">
                      {m.completedHours}h completed / {m.plannedHours}h planned
                    </div>
                  </div>
                  <div className="w-24 bg-white/5 h-2 rounded-full overflow-hidden flex-shrink-0">
                    <div
                      className="bg-gradient-to-r from-[#C59A55] to-[#42D6A4] h-full transition-all duration-300 rounded-full"
                      style={{ width: `${m.progress}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Month Objectives Summary */}
              {isMonthExpanded && m.objectives && m.objectives.length > 0 && (
                <div className="px-5 py-3 bg-[#08090B]/60 border-b border-white/5 text-[11px] text-[#A1A4AA] flex flex-wrap gap-x-6 gap-y-1">
                  <span className="text-white font-mono uppercase text-[10px]">Month Objectives:</span>
                  {m.objectives.map((obj, i) => (
                    <span key={i} className="flex items-center gap-1.5">
                      <span className="text-[#C59A55]">•</span>
                      <span>{obj}</span>
                    </span>
                  ))}
                </div>
              )}

              {/* Weeks List */}
              {isMonthExpanded && (
                <div className="p-4 sm:p-5 space-y-4">
                  {m.weeks.map((w) => {
                    const isWeekExpanded = expandedWeeks.has(w.weekNumber);
                    return (
                      <div
                        key={w.weekNumber}
                        className="rounded-xl bg-[#08090B] border border-white/10 overflow-hidden"
                      >
                        {/* Week Header */}
                        <div
                          onClick={() => toggleWeekExpand(w.weekNumber)}
                          className="p-4 bg-white/[0.02] border-b border-white/5 cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-white/[0.04]"
                        >
                          <div className="flex items-center gap-2.5">
                            <div className="text-[#A1A4AA]">
                              {isWeekExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-mono font-semibold text-[#E6C17A]">
                                  {w.weekLabel}
                                </span>
                                {w.startDate && (
                                  <span className="text-[10px] font-mono text-[#696E78]">
                                    ({w.startDate} → {w.endDate || ''})
                                  </span>
                                )}
                              </div>
                              <div className="text-xs font-medium text-white/90">
                                {w.goal}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3">
                            <span className="text-[11px] font-mono text-[#A1A4AA]">
                              {w.completedTasks}/{w.totalTasks} Done ({w.progress}%)
                            </span>
                            <div className="w-16 bg-white/5 h-1.5 rounded-full overflow-hidden flex-shrink-0">
                              <div
                                className="bg-[#42D6A4] h-full transition-all duration-300 rounded-full"
                                style={{ width: `${w.progress}%` }}
                              />
                            </div>
                          </div>
                        </div>

                        {/* Days inside Week */}
                        {isWeekExpanded && (
                          <div className="p-3 sm:p-4 space-y-2.5">
                            {w.days.map((d) => (
                              <div
                                key={d.dayNumber}
                                className={`p-3 rounded-lg border text-xs transition-all ${
                                  d.isRestDay
                                    ? 'bg-white/[0.01] border-white/5 text-[#696E78]'
                                    : 'bg-[#121418] border-white/5 hover:border-white/10'
                                }`}
                              >
                                {/* Day Header */}
                                <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-white/5 text-[11px] font-mono">
                                  <div className="flex items-center gap-2">
                                    <span className="font-semibold text-white/90">
                                      {d.dayOfWeek}, {d.date}
                                    </span>
                                    <span className="text-[#696E78]">· Day {d.dayNumber}</span>
                                  </div>
                                  {d.isRestDay ? (
                                    <span className="flex items-center gap-1 text-[#696E78] text-[10px]">
                                      <Palmtree size={12} />
                                      <span>Rest &amp; Recovery</span>
                                    </span>
                                  ) : (
                                    <span className="text-[10px] text-[#A1A4AA]">
                                      {d.totalPlannedMinutes} mins planned
                                    </span>
                                  )}
                                </div>

                                {/* Task Rows */}
                                {d.tasks.length === 0 && !d.isRestDay && (
                                  <div className="text-[11px] text-[#696E78] py-1 font-mono">
                                    No tasks allocated for this day.
                                  </div>
                                )}

                                {d.tasks.map((task) => (
                                  <div
                                    key={task.id}
                                    onClick={() => onToggleTask(task.id, task.completed)}
                                    className={`p-2 rounded-lg flex items-center justify-between cursor-pointer transition-all ${
                                      task.completed
                                        ? 'bg-[#08090B]/60 text-[#696E78] line-through'
                                        : 'hover:bg-white/5 text-white'
                                    }`}
                                  >
                                    <div className="flex items-center gap-2.5 min-w-0">
                                      {task.completed ? (
                                        <CheckSquare size={15} className="text-[#42D6A4] flex-shrink-0" />
                                      ) : (
                                        <Square size={15} className="text-[#696E78] flex-shrink-0" />
                                      )}
                                      <div className="min-w-0">
                                        <span className="font-medium truncate block">{task.title}</span>
                                        {task.taskType && task.taskType !== 'daily' && (
                                          <span className="text-[9px] uppercase font-mono px-1.5 py-0.2 rounded bg-white/5 text-[#E6C17A] mr-2">
                                            {task.taskType}
                                          </span>
                                        )}
                                      </div>
                                    </div>

                                    <div className="flex items-center gap-2 flex-shrink-0 text-[10px] font-mono">
                                      <span className="text-[#A1A4AA]">{task.durationMinutes}m</span>
                                      {task.googleCalendarEventId && (
                                        <span className="text-[#42D6A4] flex items-center gap-0.5" title="Synced to Google Calendar">
                                          <CalendarCheck size={12} />
                                        </span>
                                      )}
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          onDeleteTask(task.id);
                                        }}
                                        className="text-[#696E78] hover:text-[#F07878] p-1 transition-colors"
                                        title="Delete task"
                                      >
                                        <Trash2 size={12} />
                                      </button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add Task Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="card-dark p-6 rounded-2xl bg-[#121418] border border-white/10 max-w-md w-full space-y-4 animate-in fade-in">
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Plus size={15} className="text-[#C59A55]" />
                <span>Add Task to Roadmap</span>
              </h3>
              <button onClick={() => setShowAddModal(false)} className="text-[#696E78] hover:text-white">
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="space-y-4 text-xs">
              <div>
                <label className="text-[#A1A4AA] block mb-1 font-mono uppercase text-[10px]">
                  Task Title
                </label>
                <input
                  type="text"
                  value={newTaskTitle}
                  onChange={(e) => setNewTaskTitle(e.target.value)}
                  placeholder="e.g. Implement Dijkstra Algorithm & Solve LeetCode 743"
                  className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[#A1A4AA] block mb-1 font-mono uppercase text-[10px]">
                    Duration (Minutes)
                  </label>
                  <input
                    type="number"
                    min={15}
                    max={360}
                    step={15}
                    value={newTaskDuration}
                    onChange={(e) => setNewTaskDuration(e.target.value)}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>

                <div>
                  <label className="text-[#A1A4AA] block mb-1 font-mono uppercase text-[10px]">
                    Month Number
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={months.length || 6}
                    value={newTaskMonth}
                    onChange={(e) => setNewTaskMonth(e.target.value)}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[#A1A4AA] block mb-1 font-mono uppercase text-[10px]">
                    Week Number
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={26}
                    value={newTaskWeek}
                    onChange={(e) => setNewTaskWeek(e.target.value)}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>

                <div>
                  <label className="text-[#A1A4AA] block mb-1 font-mono uppercase text-[10px]">
                    Day Number
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={183}
                    value={newTaskDay}
                    onChange={(e) => setNewTaskDay(e.target.value)}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="btn-ghost text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingTask || !newTaskTitle.trim()}
                  className="btn-bronze text-xs py-2 px-4 flex items-center gap-1.5"
                >
                  {addingTask ? <Loader2 size={13} className="animate-spin" /> : <Plus size={14} />}
                  <span>Save Task</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

