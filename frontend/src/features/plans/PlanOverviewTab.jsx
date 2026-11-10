import React from 'react';
import { 
  CheckCircle2, 
  Clock, 
  Calendar, 
  TrendingUp, 
  Target, 
  Sparkles, 
  Layers, 
  ArrowRight,
  BookOpen,
  CheckSquare,
  Square,
  AlertCircle
} from 'lucide-react';

export const PlanOverviewTab = ({
  plan,
  roadmapData,
  onNavigateTab,
  onToggleTask,
  onProposeSchedule
}) => {
  if (!plan) return null;

  const tasks = plan.tasks || [];
  const totalTasks = tasks.length;
  const completedTasks = tasks.filter(t => t.completed).length;
  const pendingTasks = tasks.filter(t => !t.completed);
  const completionPercentage = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  const totalMinutes = tasks.reduce((sum, t) => sum + (t.durationMinutes || 0), 0);
  const completedMinutes = tasks.filter(t => t.completed).reduce((sum, t) => sum + (t.durationMinutes || 0), 0);
  const plannedHours = (totalMinutes / 60).toFixed(1);
  const completedHours = (completedMinutes / 60).toFixed(1);

  const nextTask = pendingTasks[0] || null;

  return (
    <div className="space-y-6">
      {/* Top Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Progress Card */}
        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="flex items-center justify-between text-[#A1A4AA] text-xs font-mono uppercase">
            <span>Overall Progress</span>
            <TrendingUp size={14} className="text-[#C59A55]" />
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {completionPercentage}%
          </div>
          <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-[#C59A55] to-[#42D6A4] h-full transition-all duration-300 rounded-full"
              style={{ width: `${completionPercentage}%` }}
            />
          </div>
          <div className="text-[10px] text-[#696E78] font-mono">
            {completedTasks} completed · {pendingTasks.length} pending
          </div>
        </div>

        {/* Study Hours Card */}
        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="flex items-center justify-between text-[#A1A4AA] text-xs font-mono uppercase">
            <span>Study Hours</span>
            <Clock size={14} className="text-[#E6C17A]" />
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {completedHours} <span className="text-sm font-normal text-[#A1A4AA]">/ {plannedHours}h</span>
          </div>
          <div className="text-[10px] text-[#A1A4AA] font-mono">
            Target: {plan.dailyHoursTarget || 2}h daily study
          </div>
        </div>

        {/* Duration Card */}
        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="flex items-center justify-between text-[#A1A4AA] text-xs font-mono uppercase">
            <span>Duration & Timeline</span>
            <Calendar size={14} className="text-[#42D6A4]" />
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {plan.durationDays || totalTasks || 30} <span className="text-sm font-normal text-[#A1A4AA]">days</span>
          </div>
          <div className="text-[10px] text-[#A1A4AA] font-mono truncate">
            {plan.startDate ? `${plan.startDate} → ${plan.endDate || ''}` : plan.period || 'Active Sprint'}
          </div>
        </div>

        {/* Total Tasks Card */}
        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="flex items-center justify-between text-[#A1A4AA] text-xs font-mono uppercase">
            <span>Roadmap Tasks</span>
            <CheckCircle2 size={14} className="text-[#C59A55]" />
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {totalTasks} <span className="text-sm font-normal text-[#A1A4AA]">tasks</span>
          </div>
          <div className="text-[10px] text-[#696E78] font-mono">
            {roadmapData?.months?.length || 1} month(s) · {roadmapData?.summary?.totalWeeks || 4} week(s)
          </div>
        </div>
      </div>

      {/* Main 2-Column Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (8 cols): Next Up & Objectives */}
        <div className="lg:col-span-8 space-y-6">
          {/* Next Up Task Card */}
          {nextTask ? (
            <div className="card-dark p-5 rounded-xl bg-gradient-to-br from-[#121418] to-[#181B20] border border-[#C59A55]/30 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase text-[#E6C17A] bg-[#C59A55]/15 px-2 py-0.5 rounded border border-[#C59A55]/30 font-semibold">
                  NEXT UP IN ROADMAP
                </span>
                <span className="text-xs font-mono text-[#A1A4AA]">
                  {nextTask.scheduledDate ? `${nextTask.scheduledDate}` : (nextTask.dayLabel || 'Next Session')}
                </span>
              </div>
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-base font-bold text-white tracking-tight">
                    {nextTask.title}
                  </h3>
                  <div className="flex items-center gap-3 text-xs text-[#A1A4AA] font-mono">
                    <span>⏱ {nextTask.durationMinutes} mins</span>
                    <span>•</span>
                    <span className="capitalize">{nextTask.priority} Priority</span>
                    {nextTask.milestoneGroup && (
                      <>
                        <span>•</span>
                        <span className="text-[#E6C17A] truncate max-w-xs">{nextTask.milestoneGroup}</span>
                      </>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => onToggleTask(nextTask.id, false)}
                  className="btn-bronze text-xs py-2 px-3 flex items-center gap-1.5 whitespace-nowrap font-semibold flex-shrink-0"
                >
                  <CheckCircle2 size={14} />
                  <span>Mark Done</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="card-dark p-5 rounded-xl bg-[#121418] border border-[#42D6A4]/30 space-y-2 text-center py-8">
              <CheckCircle2 size={32} className="text-[#42D6A4] mx-auto" />
              <h3 className="text-base font-bold text-white">All Planned Tasks Completed!</h3>
              <p className="text-xs text-[#A1A4AA] max-w-md mx-auto">
                You have finished all {totalTasks} tasks in this study plan. You can regenerate the roadmap for your next milestone or create a new plan.
              </p>
            </div>
          )}

          {/* Primary Objectives & Goal */}
          <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Target size={16} className="text-[#C59A55]" />
                <h3 className="text-sm font-semibold text-white">Primary Objectives &amp; Milestones</h3>
              </div>
              <span className="text-[10px] font-mono uppercase text-[#A1A4AA]">
                {plan.subject || 'Domain Curriculum'}
              </span>
            </div>

            {plan.learningGoal && (
              <div className="p-3 rounded-lg bg-[#08090B] border border-white/5 text-xs text-[#E6C17A] leading-relaxed">
                <strong>Core Target:</strong> {plan.learningGoal}
              </div>
            )}

            {plan.goals && plan.goals.length > 0 && (
              <ul className="space-y-2 text-xs text-[#A1A4AA]">
                {plan.goals.map((g, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="text-[#C59A55] font-mono font-bold">•</span>
                    <span className="text-white/90">{g}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Right Column (4 cols): Quick Nav Shortcuts & Calendar Sync Status */}
        <div className="lg:col-span-4 space-y-6">
          {/* Quick Actions Card */}
          <div className="card-dark p-5 rounded-xl bg-[#121418] border border-white/10 space-y-3">
            <h4 className="text-xs font-semibold text-white uppercase font-mono tracking-wide">
              Planning Workspace Views
            </h4>
            <div className="space-y-2">
              <button
                onClick={() => onNavigateTab('roadmap')}
                className="w-full flex items-center justify-between p-3 rounded-lg bg-[#08090B] border border-white/5 hover:border-[#C59A55]/40 text-left transition-all group"
              >
                <div className="flex items-center gap-2.5">
                  <Layers size={16} className="text-[#C59A55]" />
                  <div>
                    <div className="text-xs font-medium text-white group-hover:text-[#E6C17A]">
                      Learning Roadmap
                    </div>
                    <div className="text-[10px] text-[#696E78]">
                      Month, week &amp; daily task breakdown
                    </div>
                  </div>
                </div>
                <ArrowRight size={14} className="text-[#696E78] group-hover:text-white" />
              </button>

              <button
                onClick={() => onNavigateTab('schedule')}
                className="w-full flex items-center justify-between p-3 rounded-lg bg-[#08090B] border border-white/5 hover:border-[#C59A55]/40 text-left transition-all group"
              >
                <div className="flex items-center gap-2.5">
                  <Calendar size={16} className="text-[#E6C17A]" />
                  <div>
                    <div className="text-xs font-medium text-white group-hover:text-[#E6C17A]">
                      Schedule &amp; Calendar
                    </div>
                    <div className="text-[10px] text-[#696E78]">
                      Full-duration preview &amp; Google sync
                    </div>
                  </div>
                </div>
                <ArrowRight size={14} className="text-[#696E78] group-hover:text-white" />
              </button>

              <button
                onClick={() => onNavigateTab('progress')}
                className="w-full flex items-center justify-between p-3 rounded-lg bg-[#08090B] border border-white/5 hover:border-[#C59A55]/40 text-left transition-all group"
              >
                <div className="flex items-center gap-2.5">
                  <TrendingUp size={16} className="text-[#42D6A4]" />
                  <div>
                    <div className="text-xs font-medium text-white group-hover:text-[#E6C17A]">
                      Progress &amp; Velocity
                    </div>
                    <div className="text-[10px] text-[#696E78]">
                      Workload completion &amp; hours tracked
                    </div>
                  </div>
                </div>
                <ArrowRight size={14} className="text-[#696E78] group-hover:text-white" />
              </button>
            </div>
          </div>

          {/* Calendar Sync Status Snapshot */}
          <div className="card-dark p-5 rounded-xl bg-[#121418] border border-white/10 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase text-[#A1A4AA]">
                GOOGLE CALENDAR
              </span>
              <span className="text-[10px] font-mono text-[#42D6A4] bg-[#42D6A4]/10 px-2 py-0.5 rounded">
                CONNECTED
              </span>
            </div>
            <p className="text-xs text-[#A1A4AA] leading-relaxed">
              Sessions can be previewed across all {plan.durationDays || 30} days and synchronized to your Google Calendar with explicit confirmation.
            </p>
            <button
              onClick={onProposeSchedule}
              className="w-full btn-secondary text-xs py-2 flex items-center justify-center gap-1.5"
            >
              <Sparkles size={13} className="text-[#E6C17A]" />
              <span>Review Calendar Schedule</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

