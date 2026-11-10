import React from 'react';
import { 
  Layers, 
  Calendar, 
  Clock, 
  TrendingUp, 
  Trash2, 
  ExternalLink, 
  Plus, 
  BookOpen, 
  CheckCircle2, 
  ArrowRight 
} from 'lucide-react';

export const MyPlansTab = ({
  plans,
  activePlan,
  onSelectPlan,
  onOpenCreateModal,
  onDeletePlan
}) => {
  if (!plans || plans.length === 0) {
    return (
      <div className="card-dark p-12 rounded-2xl bg-[#121418] border border-white/10 text-center max-w-xl mx-auto space-y-6 animate-in fade-in">
        <div className="w-16 h-16 rounded-2xl bg-[#C59A55]/10 border border-[#C59A55]/30 flex items-center justify-center mx-auto text-[#E6C17A]">
          <Layers size={32} />
        </div>
        <div className="space-y-2">
          <h2 className="text-xl font-bold text-white tracking-tight">No study plan yet.</h2>
          <p className="text-xs sm:text-sm text-[#A1A4AA] max-w-md mx-auto">
            Create an AI study plan lasting from 1 day up to 6 months with structured monthly, weekly, and daily learning roadmaps.
          </p>
        </div>
        <button
          onClick={onOpenCreateModal}
          className="btn-bronze text-xs py-2.5 px-5 flex items-center gap-2 font-semibold mx-auto"
        >
          <Plus size={15} />
          <span>Create New Study Plan</span>
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-white">Your Saved Study Plans</h3>
          <p className="text-xs text-[#A1A4AA]">
            Select any plan to inspect its roadmap, calendar schedule, and progress.
          </p>
        </div>
        <button
          onClick={onOpenCreateModal}
          className="btn-bronze text-xs py-2 px-3.5 flex items-center gap-1.5 font-semibold"
        >
          <Plus size={14} />
          <span>New Plan</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {plans.map((p) => {
          const tasks = p.tasks || [];
          const totalTasks = tasks.length;
          const completedTasks = tasks.filter(t => t.completed).length;
          const pct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
          const nextPending = tasks.find(t => !t.completed);
          const isActive = activePlan?.id === p.id;

          return (
            <div
              key={p.id}
              onClick={() => onSelectPlan(p)}
              className={`p-5 rounded-xl border cursor-pointer transition-all space-y-4 flex flex-col justify-between ${
                isActive
                  ? 'bg-[#181B20] border-[#C59A55]/50 shadow-md shadow-[#C59A55]/10'
                  : 'bg-[#121418] border-white/5 hover:border-white/15 hover:bg-white/[0.02]'
              }`}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase text-[#C59A55] bg-[#C59A55]/10 px-2 py-0.5 rounded border border-[#C59A55]/20 font-semibold">
                    {p.period || `${p.durationDays || 30} Days`}
                  </span>
                  <div className="flex items-center gap-2">
                    {isActive && (
                      <span className="text-[10px] font-mono text-[#42D6A4] font-semibold">
                        ACTIVE
                      </span>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeletePlan(p);
                      }}
                      className="text-[#696E78] hover:text-[#F07878] p-1 transition-colors"
                      title="Delete study plan"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                <div>
                  <h4 className="text-sm font-bold text-white group-hover:text-[#E6C17A] tracking-tight">
                    {p.title}
                  </h4>
                  {p.learningGoal && (
                    <p className="text-xs text-[#A1A4AA] mt-1 line-clamp-2 leading-relaxed">
                      {p.learningGoal}
                    </p>
                  )}
                </div>

                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-between text-[11px] font-mono">
                    <span className="text-[#A1A4AA]">Completion</span>
                    <span className="text-white font-semibold">{pct}% ({completedTasks}/{totalTasks})</span>
                  </div>
                  <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-[#C59A55] to-[#42D6A4] h-full rounded-full transition-all duration-300"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-2 text-[10px] font-mono text-[#A1A4AA] border-t border-white/5">
                  <div className="flex items-center gap-1">
                    <Calendar size={11} className="text-[#C59A55]" />
                    <span>{p.startDate ? `${p.startDate}` : `${p.durationDays || 30}d span`}</span>
                  </div>
                  <div className="flex items-center gap-1 justify-end">
                    <Clock size={11} className="text-[#E6C17A]" />
                    <span>{p.dailyHoursTarget || 2}h/day</span>
                  </div>
                </div>

                {nextPending && (
                  <div className="p-2.5 rounded-lg bg-[#08090B] border border-white/5 text-[10px] space-y-0.5">
                    <span className="text-[#696E78] font-mono uppercase text-[9px]">Next Up:</span>
                    <div className="text-white/90 truncate font-medium">{nextPending.title}</div>
                  </div>
                )}
              </div>

              <div className="pt-2 flex items-center justify-between text-xs text-[#E6C17A] font-medium border-t border-white/5">
                <span>Open Planning Workspace</span>
                <ArrowRight size={13} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

