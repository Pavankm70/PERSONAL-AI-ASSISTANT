import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { 
  Layers, 
  Calendar, 
  Clock, 
  Sparkles, 
  Plus, 
  TrendingUp, 
  Trash2, 
  Loader2, 
  CheckCircle2, 
  AlertTriangle,
  LayoutDashboard,
  CheckSquare
} from 'lucide-react';

import { PlanOverviewTab } from './PlanOverviewTab';
import { PlanRoadmapTab } from './PlanRoadmapTab';
import { PlanScheduleTab } from './PlanScheduleTab';
import { PlanProgressTab } from './PlanProgressTab';
import { MyPlansTab } from './MyPlansTab';
import { CreatePlanModal } from './CreatePlanModal';

export const PlansPage = () => {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activePlan, setActivePlan] = useState(null);
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'roadmap' | 'schedule' | 'progress' | 'my-plans'

  // Roadmap detailed data
  const [roadmapData, setRoadmapData] = useState(null);
  const [loadingRoadmap, setLoadingRoadmap] = useState(false);

  // Proposed study slots & schedule state
  const [proposalResult, setProposalResult] = useState(null);
  const [proposing, setProposing] = useState(false);
  const [syncingCalendar, setSyncingCalendar] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  // Modals & messages
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [planToDelete, setPlanToDelete] = useState(null);
  const [deleteGoogleEvents, setDeleteGoogleEvents] = useState(true);
  const [deletingPlan, setDeletingPlan] = useState(false);
  const [planMessage, setPlanMessage] = useState(null);

  const fetchPlans = async (preferredPlanId = null) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPlans();
      const list = Array.isArray(data) ? data : [];
      setPlans(list);

      if (list.length > 0) {
        let targetPlan = list[0];
        if (preferredPlanId) {
          const found = list.find(p => p.id === preferredPlanId);
          if (found) targetPlan = found;
        } else if (activePlan) {
          const found = list.find(p => p.id === activePlan.id);
          if (found) targetPlan = found;
        }
        setActivePlan(targetPlan);
        await loadRoadmap(targetPlan.id);
      } else {
        setActivePlan(null);
        setRoadmapData(null);
        setProposalResult(null);
      }
    } catch (err) {
      setError(err.message || 'Failed to retrieve saved study plans.');
      setPlans([]);
      setActivePlan(null);
    } finally {
      setLoading(false);
    }
  };

  const loadRoadmap = async (planId) => {
    if (!planId) return;
    setLoadingRoadmap(true);
    try {
      const rData = await api.getPlanRoadmap(planId);
      setRoadmapData(rData);
    } catch (err) {
      console.warn('Roadmap endpoint response:', err.message);
    } finally {
      setLoadingRoadmap(false);
    }
  };

  useEffect(() => {
    fetchPlans();
  }, []);

  const handleSelectPlan = async (plan) => {
    setActivePlan(plan);
    setProposalResult(null);
    setSyncResult(null);
    await loadRoadmap(plan.id);
    setActiveTab('overview');
  };

  // Toggle Task Status (Complete/Incomplete)
  const handleToggleTask = async (taskId, currentStatus) => {
    if (!activePlan) return;
    try {
      const updated = await api.updatePlanTask(activePlan.id, taskId, {
        completed: !currentStatus
      });
      const updatedTasks = activePlan.tasks.map(t => (t.id === taskId ? updated : t));
      const updatedPlan = { ...activePlan, tasks: updatedTasks };
      setActivePlan(updatedPlan);
      setPlans(prev => prev.map(p => (p.id === activePlan.id ? updatedPlan : p)));

      // Reload roadmap data to update progress bars
      await loadRoadmap(activePlan.id);
    } catch (err) {
      setPlanMessage({
        type: 'error',
        text: 'Failed to update task completion status.'
      });
      setTimeout(() => setPlanMessage(null), 4000);
    }
  };

  // Add Task to Plan
  const handleAddTask = async (taskPayload) => {
    if (!activePlan) return;
    try {
      const created = await api.addTaskToPlan(activePlan.id, taskPayload);
      const updatedTasks = [...(activePlan.tasks || []), created];
      const updatedPlan = { ...activePlan, tasks: updatedTasks };
      setActivePlan(updatedPlan);
      setPlans(prev => prev.map(p => (p.id === activePlan.id ? updatedPlan : p)));
      await loadRoadmap(activePlan.id);
      setPlanMessage({
        type: 'success',
        text: `Added task "${created.title}" to ${created.dayLabel || 'plan'}.`
      });
      setTimeout(() => setPlanMessage(null), 4000);
    } catch (err) {
      throw err;
    }
  };

  // Delete Task from Plan
  const handleDeleteTask = async (taskId) => {
    if (!activePlan) return;
    try {
      await api.deletePlanTask(activePlan.id, taskId);
      const updatedTasks = activePlan.tasks.filter(t => t.id !== taskId);
      const updatedPlan = { ...activePlan, tasks: updatedTasks };
      setActivePlan(updatedPlan);
      setPlans(prev => prev.map(p => (p.id === activePlan.id ? updatedPlan : p)));
      await loadRoadmap(activePlan.id);
    } catch (err) {
      setPlanMessage({
        type: 'error',
        text: 'Failed to delete task.'
      });
      setTimeout(() => setPlanMessage(null), 4000);
    }
  };

  // Create Plan from Modal (Full Duration 1 Day to 6 Months)
  const handleCreatePlan = async (planData) => {
    try {
      const created = await api.createPlan(planData);
      const updatedPlans = [created, ...plans];
      setPlans(updatedPlans);
      setActivePlan(created);
      await loadRoadmap(created.id);
      setActiveTab('roadmap');

      // If user selected to sync to Google Calendar upon creation
      if (planData.syncToCalendar && created.tasks && created.tasks.length > 0) {
        try {
          const blocksToSync = created.tasks.map(t => ({
            id: t.id,
            title: t.title,
            day: t.dayLabel || 'Day',
            scheduledDate: t.scheduledDate,
            startTime: t.startTime,
            endTime: t.endTime,
            durationMinutes: t.durationMinutes,
            focus: t.title
          }));
          const taskIds = created.tasks.map(t => t.id);
          await api.applyStudySlots(created.id, blocksToSync, true, taskIds);
          await fetchPlans(created.id);
        } catch (e) {
          // Non-blocking sync error
        }
      }

      setPlanMessage({
        type: 'success',
        text: `Created "${created.title}" with ${created.tasks?.length || 0} tasks spanning ${created.durationDays || created.period}!`
      });
      setTimeout(() => setPlanMessage(null), 6000);
    } catch (err) {
      throw err;
    }
  };

  // Regenerate Roadmap
  const handleRegenerateRoadmap = async () => {
    if (!activePlan) return;
    try {
      const regenerated = await api.generatePlanRoadmap(activePlan.id, { replace: true });
      setActivePlan(regenerated);
      setPlans(prev => prev.map(p => (p.id === activePlan.id ? regenerated : p)));
      await loadRoadmap(activePlan.id);
      setPlanMessage({
        type: 'success',
        text: `Regenerated curriculum with ${regenerated.tasks?.length || 0} structured tasks.`
      });
      setTimeout(() => setPlanMessage(null), 5000);
    } catch (err) {
      throw err;
    }
  };

  // Delete Plan
  const handleDeletePlanConfirm = async () => {
    const target = planToDelete || activePlan;
    if (!target || deletingPlan) return;

    setDeletingPlan(true);
    try {
      const res = await api.deletePlan(target.id, { deleteGoogleEvents });
      const remaining = plans.filter(p => p.id !== target.id);
      setPlans(remaining);
      const nextActive = remaining.length > 0 ? remaining[0] : null;
      setActivePlan(nextActive);
      setShowDeleteConfirm(false);
      setPlanToDelete(null);
      if (nextActive) {
        await loadRoadmap(nextActive.id);
      } else {
        setRoadmapData(null);
      }
      const calNote = res.deletedCalendarEvents ? ` and removed ${res.deletedCalendarEvents} synced calendar sessions` : '';
      setPlanMessage({
        type: 'success',
        text: `Permanently deleted study plan "${target.title}"${calNote}.`
      });
      setTimeout(() => setPlanMessage(null), 4000);
    } catch (err) {
      alert('Failed to delete study plan: ' + (err.message || 'Unknown error'));
    } finally {
      setDeletingPlan(false);
    }
  };

  // Propose Smart Study Schedule (Full Duration Preview)
  const handleProposeSchedule = async () => {
    if (!activePlan) return;
    setProposing(true);
    setSyncResult(null);
    setPlanMessage(null);
    try {
      const data = await api.proposeStudySlots(activePlan.id);
      setProposalResult(data);
      setActiveTab('schedule');
      if (data.proposedStudyBlocks && data.proposedStudyBlocks.length > 0) {
        setPlanMessage({
          type: 'success',
          text: `Generated ${data.proposedStudyBlocks.length} proposed study session(s) spanning ${activePlan.period || 'your plan'}. ${
            data.calendarConnected ? data.calendarNote : 'Calendar unlinked.'
          }${data.conflictCount ? ` ⚠️ ${data.conflictCount} conflict(s) detected.` : ''}`
        });
      }
    } catch (err) {
      setPlanMessage({
        type: 'error',
        text: err.response?.data?.detail || err.message || 'Failed to generate study slots.'
      });
    } finally {
      setProposing(false);
    }
  };

  // Apply Study Slots to Plan (Local Persistence Only)
  const handleApplySlots = async (blocks) => {
    if (!activePlan) return;
    try {
      await api.applyStudySlots(activePlan.id, blocks, false);
      await fetchPlans(activePlan.id);
      setPlanMessage({
        type: 'success',
        text: `Saved ${blocks.length} study session(s) to your plan.`
      });
      setTimeout(() => setPlanMessage(null), 5000);
    } catch (err) {
      setPlanMessage({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to save study slots.'
      });
    }
  };

  // Sync Selected Sessions to Google Calendar
  const handleSyncToCalendar = async (allBlocks, selectedIds) => {
    if (!activePlan || !selectedIds || selectedIds.length === 0) return;
    setSyncingCalendar(true);
    setSyncResult(null);
    setPlanMessage(null);
    try {
      const res = await api.syncPlanToCalendar(activePlan.id, allBlocks, selectedIds);
      setSyncResult(res);
      if (res.successCount > 0) {
        await fetchPlans(activePlan.id);
        setPlanMessage({
          type: 'success',
          text: res.message
        });
      } else if (res.failedCount > 0) {
        setPlanMessage({
          type: 'error',
          text: res.message
        });
      }
    } catch (err) {
      setPlanMessage({
        type: 'error',
        text: err.message || 'Failed to sync sessions to Google Calendar.'
      });
    } finally {
      setSyncingCalendar(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 max-w-7xl mx-auto flex items-center justify-center min-h-[400px]">
        <div className="flex items-center gap-3 text-xs text-[#A1A4AA] font-mono">
          <Loader2 size={16} className="animate-spin text-[#C59A55]" />
          <span>Loading persistent study planning workspace...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 sm:p-8 max-w-7xl mx-auto space-y-6">
      {/* Top Workspace Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono uppercase text-[#C59A55] tracking-wider font-semibold">
              ACADEMIC INTELLIGENCE WORKSPACE
            </span>
            <span className="text-[10px] font-mono text-[#696E78]">v2.0 (1 Day to 6 Months)</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight mt-0.5">
            AI Study Planning Workspace
          </h1>
          <p className="text-xs sm:text-sm text-[#A1A4AA] mt-1">
            Synthesize learning goals into structured monthly, weekly, and daily roadmaps with Google Calendar sync.
          </p>
        </div>

        <div className="flex items-center gap-3 self-start sm:self-auto flex-wrap">
          {activePlan && (
            <button
              onClick={handleProposeSchedule}
              disabled={proposing}
              className="btn-bronze text-xs py-2 px-3.5 whitespace-nowrap flex items-center gap-1.5 font-semibold"
            >
              {proposing ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={14} />}
              <span>{proposing ? 'Analyzing Schedule...' : 'Propose Smart Schedule'}</span>
            </button>
          )}

          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-secondary text-xs py-2 px-3.5 whitespace-nowrap flex items-center gap-1.5"
          >
            <Plus size={14} />
            <span>Create Plan</span>
          </button>
        </div>
      </div>

      {/* Global Status Banner */}
      {planMessage && (
        <div
          className={`p-3.5 rounded-xl text-xs border animate-in fade-in ${
            planMessage.type === 'success'
              ? 'bg-[#42D6A4]/10 border-[#42D6A4]/30 text-[#42D6A4]'
              : planMessage.type === 'error'
              ? 'bg-[#F07878]/10 border-[#F07878]/30 text-[#F07878]'
              : 'bg-white/5 border-white/10 text-[#A1A4AA]'
          }`}
        >
          {planMessage.text}
        </div>
      )}

      {/* Active Plan Selector Strip if multiple plans exist */}
      {plans.length > 1 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-white/5">
          <span className="text-[10px] font-mono uppercase text-[#696E78] mr-1">PLANS:</span>
          {plans.map((p) => {
            const isSelected = activePlan?.id === p.id;
            return (
              <button
                key={p.id}
                onClick={() => handleSelectPlan(p)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                  isSelected
                    ? 'bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/40 font-semibold'
                    : 'bg-white/5 text-[#A1A4AA] hover:text-white border border-white/5'
                }`}
              >
                {p.title}
              </button>
            );
          })}
        </div>
      )}

      {/* Workspace Tabs Navigation */}
      {activePlan && (
        <div className="flex items-center gap-2 border-b border-white/10 pb-2 overflow-x-auto">
          {[
            { id: 'overview', label: 'Plan Overview', icon: LayoutDashboard },
            { id: 'roadmap', label: 'Roadmap (Months · Weeks · Days)', icon: Layers, badge: `${activePlan.tasks?.length || 0} tasks` },
            { id: 'schedule', label: 'Schedule & Calendar Sync', icon: Calendar, badge: `${activePlan.suggestedStudyBlocks?.length || proposalResult?.proposedStudyBlocks?.length || 0} slots` },
            { id: 'progress', label: 'Progress & Velocity', icon: TrendingUp },
            { id: 'my-plans', label: `My Plans (${plans.length})`, icon: CheckSquare }
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                  isActive
                    ? 'bg-[#181B20] text-white border border-[#C59A55]/30 shadow-sm'
                    : 'text-[#A1A4AA] hover:text-white hover:bg-white/5'
                }`}
              >
                <Icon size={14} className={isActive ? 'text-[#C59A55]' : 'text-[#696E78]'} />
                <span>{tab.label}</span>
                {tab.badge && (
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-white/5 text-[#E6C17A]">
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Active Tab View */}
      {(!plans || plans.length === 0) ? (
        <MyPlansTab
          plans={[]}
          activePlan={null}
          onSelectPlan={handleSelectPlan}
          onOpenCreateModal={() => setShowCreateModal(true)}
          onDeletePlan={() => {}}
        />
      ) : activePlan && (
        <>
          {activeTab === 'overview' && (
            <PlanOverviewTab
              plan={activePlan}
              roadmapData={roadmapData}
              onNavigateTab={setActiveTab}
              onToggleTask={handleToggleTask}
              onProposeSchedule={handleProposeSchedule}
            />
          )}

          {activeTab === 'roadmap' && (
            <PlanRoadmapTab
              plan={activePlan}
              roadmapData={roadmapData}
              onToggleTask={handleToggleTask}
              onAddTask={handleAddTask}
              onDeleteTask={handleDeleteTask}
              onRegenerateRoadmap={handleRegenerateRoadmap}
            />
          )}

          {activeTab === 'schedule' && (
            <PlanScheduleTab
              plan={activePlan}
              proposalResult={proposalResult}
              proposing={proposing}
              onGenerateProposal={handleProposeSchedule}
              onApplySlots={handleApplySlots}
              onSyncCalendar={handleSyncToCalendar}
              syncingCalendar={syncingCalendar}
              syncResult={syncResult}
            />
          )}

          {activeTab === 'progress' && (
            <PlanProgressTab
              plan={activePlan}
              roadmapData={roadmapData}
            />
          )}

          {activeTab === 'my-plans' && (
            <MyPlansTab
              plans={plans}
              activePlan={activePlan}
              onSelectPlan={handleSelectPlan}
              onOpenCreateModal={() => setShowCreateModal(true)}
              onDeletePlan={(p) => {
                setPlanToDelete(p);
                setShowDeleteConfirm(true);
              }}
            />
          )}
        </>
      )}

      {/* Create Plan Modal */}
      <CreatePlanModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreate={handleCreatePlan}
      />

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="card-dark p-6 rounded-2xl bg-[#121418] border border-[#F07878]/30 max-w-md w-full space-y-4 animate-in fade-in">
            <div className="flex items-center gap-2 text-[#F07878] font-semibold text-sm">
              <AlertTriangle size={18} />
              <span>Confirm Permanent Deletion</span>
            </div>

            <p className="text-xs text-[#A1A4AA] leading-relaxed">
              Are you sure you want to delete the study plan{' '}
              <strong className="text-white">&quot;{(planToDelete || activePlan)?.title}&quot;</strong>?
              All associated daily tasks and roadmap records will be removed from your workspace.
            </p>

            <label className="flex items-center gap-2.5 p-3 rounded-lg bg-[#C59A55]/10 border border-[#C59A55]/30 cursor-pointer text-xs">
              <input
                type="checkbox"
                checked={deleteGoogleEvents}
                onChange={(e) => setDeleteGoogleEvents(e.target.checked)}
                className="rounded border-white/20 text-[#C59A55] focus:ring-0"
              />
              <span className="text-[#E6C17A] font-medium">
                Also remove linked study sessions from Google Calendar
              </span>
            </label>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setPlanToDelete(null);
                }}
                className="btn-ghost text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeletePlanConfirm}
                disabled={deletingPlan}
                className="btn-danger text-xs py-2 px-4 flex items-center gap-1.5 bg-[#F07878] hover:bg-[#d66565] text-white rounded-lg font-semibold"
              >
                {deletingPlan ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={14} />}
                <span>Permanently Delete</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
