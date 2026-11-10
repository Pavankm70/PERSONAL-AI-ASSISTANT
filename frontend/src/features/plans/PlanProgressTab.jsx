import React from 'react';
import { 
  TrendingUp, 
  Clock, 
  CheckCircle2, 
  Calendar, 
  Layers, 
  Target, 
  Award,
  BarChart2
} from 'lucide-react';

export const PlanProgressTab = ({ plan, roadmapData }) => {
  if (!plan) return null;

  const tasks = plan.tasks || [];
  const totalTasks = tasks.length;
  const completedTasks = tasks.filter(t => t.completed).length;
  const pendingTasks = tasks.filter(t => !t.completed).length;
  const completionPercentage = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  const totalMinutes = tasks.reduce((sum, t) => sum + (t.durationMinutes || 0), 0);
  const completedMinutes = tasks.filter(t => t.completed).reduce((sum, t) => sum + (t.durationMinutes || 0), 0);
  const plannedHours = (totalMinutes / 60).toFixed(1);
  const completedHours = (completedMinutes / 60).toFixed(1);

  const months = roadmapData?.months || [];

  return (
    <div className="space-y-6">
      {/* Velocity Overview Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="text-[10px] font-mono uppercase text-[#A1A4AA]">Completion Rate</div>
          <div className="text-2xl font-bold text-white tracking-tight">{completionPercentage}%</div>
          <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-[#C59A55] to-[#42D6A4] h-full transition-all duration-300 rounded-full"
              style={{ width: `${completionPercentage}%` }}
            />
          </div>
          <div className="text-[10px] font-mono text-[#696E78]">
            {completedTasks} completed · {pendingTasks} remaining
          </div>
        </div>

        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="text-[10px] font-mono uppercase text-[#A1A4AA]">Study Velocity</div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {completedHours} <span className="text-sm font-normal text-[#A1A4AA]">/ {plannedHours} hrs</span>
          </div>
          <div className="text-[10px] font-mono text-[#E6C17A]">
            {totalMinutes > 0 ? Math.round((completedMinutes / totalMinutes) * 100) : 0}% hours logged
          </div>
        </div>

        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="text-[10px] font-mono uppercase text-[#A1A4AA]">Curriculum Span</div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {months.length} <span className="text-sm font-normal text-[#A1A4AA]">month(s)</span>
          </div>
          <div className="text-[10px] font-mono text-[#42D6A4]">
            {roadmapData?.summary?.totalWeeks || 1} weeks scheduled
          </div>
        </div>

        <div className="card-dark p-4 rounded-xl bg-[#121418] border border-white/10 space-y-2">
          <div className="text-[10px] font-mono uppercase text-[#A1A4AA]">Milestone Status</div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {months.filter(m => m.progress === 100).length} <span className="text-sm font-normal text-[#A1A4AA]">/ {months.length}</span>
          </div>
          <div className="text-[10px] font-mono text-[#696E78]">
            {months.length > 0 && months.every(m => m.progress === 100) ? 'Mastery Achieved' : 'In Progress'}
          </div>
        </div>
      </div>

      {/* Monthly Breakdown Section */}
      <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 space-y-5">
        <div className="flex items-center justify-between pb-3 border-b border-white/5">
          <div className="flex items-center gap-2">
            <BarChart2 size={16} className="text-[#C59A55]" />
            <h3 className="text-sm font-bold text-white">Monthly Progress &amp; Milestone Velocity</h3>
          </div>
          <span className="text-[10px] font-mono text-[#A1A4AA]">
            {plan.durationDays || 30} Days Total Span
          </span>
        </div>

        {months.length === 0 ? (
          <div className="text-xs text-[#696E78] py-4 text-center font-mono">
            No monthly milestones generated yet.
          </div>
        ) : (
          <div className="space-y-4">
            {months.map((m) => (
              <div key={m.monthNumber} className="p-4 rounded-lg bg-[#08090B] border border-white/5 space-y-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <span className="text-[10px] font-mono font-bold uppercase text-[#C59A55] mr-2">
                      {m.monthLabel}
                    </span>
                    <span className="text-xs font-semibold text-white">
                      {m.milestone}
                    </span>
                  </div>
                  <div className="text-right text-[11px] font-mono text-[#A1A4AA]">
                    <span className="text-white font-bold">{m.completedTasks} / {m.totalTasks}</span> tasks ({m.progress}%)
                  </div>
                </div>

                <div className="w-full bg-white/5 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-[#C59A55] to-[#42D6A4] h-full transition-all duration-300 rounded-full"
                    style={{ width: `${m.progress}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-[10px] font-mono text-[#696E78]">
                  <span>{m.startDate} → {m.endDate}</span>
                  <span>{m.completedHours}h completed of {m.plannedHours}h planned</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Major Milestones Checklist */}
      <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-white/5">
          <Award size={16} className="text-[#E6C17A]" />
          <h3 className="text-sm font-bold text-white">Curriculum Milestones Checklist</h3>
        </div>

        <div className="space-y-2.5">
          {months.map((m) => {
            const isDone = m.progress === 100;
            return (
              <div
                key={m.monthNumber}
                className={`p-3 rounded-lg border text-xs flex items-center justify-between ${
                  isDone
                    ? 'bg-[#42D6A4]/10 border-[#42D6A4]/30 text-white'
                    : 'bg-[#08090B] border-white/5 text-[#A1A4AA]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <CheckCircle2
                    size={16}
                    className={isDone ? 'text-[#42D6A4]' : 'text-[#696E78]'}
                  />
                  <div>
                    <span className="font-semibold text-white mr-2">{m.monthLabel}:</span>
                    <span>{m.milestone}</span>
                  </div>
                </div>

                <span className="text-[10px] font-mono font-bold">
                  {isDone ? '✓ COMPLETED' : `${m.progress}%`}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

