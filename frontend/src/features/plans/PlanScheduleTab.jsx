import React, { useState } from 'react';
import { 
  Calendar, 
  Clock, 
  Sparkles, 
  CheckCircle2, 
  AlertTriangle, 
  Loader2, 
  CheckSquare, 
  Square, 
  CalendarCheck, 
  Filter, 
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  List,
  CalendarDays,
  ShieldCheck,
  AlertCircle
} from 'lucide-react';

export const PlanScheduleTab = ({
  plan,
  proposalResult,
  proposing,
  onGenerateProposal,
  onApplySlots,
  onSyncCalendar,
  syncingCalendar,
  syncResult
}) => {
  const [selectedMonth, setSelectedMonth] = useState('all');
  const [selectedBlockIds, setSelectedBlockIds] = useState(new Set());
  const [applyingSlots, setApplyingSlots] = useState(false);
  const [viewMode, setViewMode] = useState('list'); // 'list' | 'grid'

  const proposedBlocks = proposalResult?.proposedStudyBlocks || plan?.suggestedStudyBlocks || [];

  // Derive unique months present in blocks
  const availableMonths = Array.from(new Set(proposedBlocks.map(b => b.monthNumber).filter(Boolean))).sort((a, b) => a - b);

  const filteredBlocks = selectedMonth === 'all'
    ? proposedBlocks
    : proposedBlocks.filter(b => b.monthNumber === Number(selectedMonth));

  const toggleSelectBlock = (blockId) => {
    setSelectedBlockIds(prev => {
      const next = new Set(prev);
      if (next.has(blockId)) next.delete(blockId);
      else next.add(blockId);
      return next;
    });
  };

  const selectAll = () => {
    setSelectedBlockIds(new Set(filteredBlocks.map(b => b.id)));
  };

  const selectConflictFree = () => {
    setSelectedBlockIds(new Set(filteredBlocks.filter(b => !b.hasConflict).map(b => b.id)));
  };

  const selectNext7Days = () => {
    const next7 = filteredBlocks.slice(0, 7).map(b => b.id);
    setSelectedBlockIds(new Set(next7));
  };

  const clearSelection = () => {
    setSelectedBlockIds(new Set());
  };

  const handleApply = async () => {
    if (selectedBlockIds.size === 0) return;
    const blocksToApply = proposedBlocks.filter(b => selectedBlockIds.has(b.id));
    setApplyingSlots(true);
    try {
      await onApplySlots(blocksToApply);
    } finally {
      setApplyingSlots(false);
    }
  };

  const handleSync = async () => {
    if (selectedBlockIds.size === 0) return;
    await onSyncCalendar(proposedBlocks, Array.from(selectedBlockIds));
  };

  // Selected metrics
  const selectedBlocksList = proposedBlocks.filter(b => selectedBlockIds.has(b.id));
  const selectedTotalMinutes = selectedBlocksList.reduce((sum, b) => sum + (b.durationMinutes || 0), 0);
  const selectedHours = (selectedTotalMinutes / 60).toFixed(1);
  const selectedConflictsCount = selectedBlocksList.filter(b => b.hasConflict).length;

  return (
    <div className="space-y-6">
      {/* Top Banner: Status & Action Bar */}
      <div className="p-5 rounded-xl bg-[#121418] border border-white/10 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono uppercase text-[#C59A55] font-semibold">
              FULL DURATION SCHEDULE WORKSPACE
            </span>
            {proposalResult?.calendarConnected ? (
              <span className="text-[10px] font-mono text-[#42D6A4] bg-[#42D6A4]/10 px-2 py-0.5 rounded border border-[#42D6A4]/20 flex items-center gap-1">
                <ShieldCheck size={11} />
                <span>Google Calendar Conflict-Checked</span>
              </span>
            ) : (
              <span className="text-[10px] font-mono text-[#A1A4AA] bg-white/5 px-2 py-0.5 rounded border border-white/5">
                Calendar Unlinked
              </span>
            )}
          </div>
          <h2 className="text-lg font-bold text-white mt-1">
            {plan?.title} — Study Sessions ({proposedBlocks.length})
          </h2>
          <p className="text-xs text-[#A1A4AA] mt-0.5">
            {proposalResult?.calendarNote || 'Preview proposed dates and times spanning your complete study plan.'}
          </p>
        </div>

        <button
          onClick={onGenerateProposal}
          disabled={proposing}
          className="btn-bronze text-xs py-2 px-4 whitespace-nowrap flex items-center gap-2 font-semibold flex-shrink-0"
        >
          {proposing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          <span>{proposing ? 'Analyzing Availability...' : 'Regenerate Proposed Slots'}</span>
        </button>
      </div>

      {/* Sync Result Feedback Banner */}
      {syncResult && (
        <div className={`p-4 rounded-xl text-xs border space-y-1.5 ${
          syncResult.failedCount > 0 && syncResult.successCount === 0
            ? 'bg-[#F07878]/10 border-[#F07878]/30 text-[#F07878]'
            : 'bg-[#42D6A4]/10 border-[#42D6A4]/30 text-[#42D6A4]'
        }`}>
          <div className="flex items-center justify-between font-semibold">
            <span className="flex items-center gap-2">
              <CheckCircle2 size={16} />
              <span>{syncResult.message}</span>
            </span>
            <span className="text-[11px] font-mono">
              {syncResult.successCount} added · {syncResult.alreadySyncedCount || 0} existing · {syncResult.failedCount || 0} failed
            </span>
          </div>
          {syncResult.results?.filter(r => r.status === 'error').map((r, i) => (
            <div key={i} className="text-[10px] font-mono text-[#F07878]">
              • Block {r.blockId}: {r.message}
            </div>
          ))}
        </div>
      )}

      {/* 2-Column Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (8 cols): Filters, Quick-select, and Session List */}
        <div className="lg:col-span-8 space-y-4">
          {/* Controls Bar */}
          <div className="p-3.5 rounded-xl bg-[#121418] border border-white/10 flex flex-wrap items-center justify-between gap-3 text-xs">
            {/* Month Filter */}
            <div className="flex items-center gap-1.5 overflow-x-auto">
              <span className="text-[10px] font-mono uppercase text-[#696E78] mr-1">MONTH:</span>
              <button
                onClick={() => setSelectedMonth('all')}
                className={`px-2.5 py-1 rounded text-[11px] font-mono transition-all ${
                  selectedMonth === 'all'
                    ? 'bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/40 font-semibold'
                    : 'bg-[#08090B] text-[#A1A4AA] border border-white/5 hover:text-white'
                }`}
              >
                All ({proposedBlocks.length})
              </button>
              {availableMonths.map((m) => (
                <button
                  key={m}
                  onClick={() => setSelectedMonth(m)}
                  className={`px-2.5 py-1 rounded text-[11px] font-mono transition-all ${
                    selectedMonth === m
                      ? 'bg-[#C59A55]/20 text-[#E6C17A] border border-[#C59A55]/40 font-semibold'
                      : 'bg-[#08090B] text-[#A1A4AA] border border-white/5 hover:text-white'
                  }`}
                >
                  Month {m}
                </button>
              ))}
            </div>

            {/* Selection Shortcuts */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                onClick={selectAll}
                className="text-[10px] font-mono px-2 py-1 rounded bg-white/5 text-[#A1A4AA] hover:text-white"
              >
                Select All
              </button>
              <button
                onClick={selectNext7Days}
                className="text-[10px] font-mono px-2 py-1 rounded bg-white/5 text-[#A1A4AA] hover:text-white"
              >
                Next 7 Days
              </button>
              <button
                onClick={selectConflictFree}
                className="text-[10px] font-mono px-2 py-1 rounded bg-white/5 text-[#42D6A4] hover:bg-[#42D6A4]/15"
              >
                Conflict-Free Only
              </button>
              <button
                onClick={clearSelection}
                className="text-[10px] font-mono px-2 py-1 rounded bg-white/5 text-[#696E78] hover:text-white"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Session Cards List */}
          {filteredBlocks.length === 0 ? (
            <div className="card-dark p-8 rounded-xl bg-[#121418] border border-white/10 text-center space-y-3">
              <Calendar size={28} className="text-[#C59A55] mx-auto" />
              <div className="text-sm font-semibold text-white">No sessions found for this filter.</div>
              <p className="text-xs text-[#A1A4AA]">
                Click &quot;Regenerate Proposed Slots&quot; above to build schedule intervals from your plan tasks.
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {filteredBlocks.map((b) => {
                const isSelected = selectedBlockIds.has(b.id);
                return (
                  <div
                    key={b.id}
                    onClick={() => toggleSelectBlock(b.id)}
                    className={`p-3.5 rounded-xl border text-xs cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-[#C59A55]/10 border-[#C59A55]/50 shadow-sm'
                        : 'bg-[#121418] border-white/5 hover:border-white/15 opacity-80'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 min-w-0">
                        <div className="mt-0.5">
                          {isSelected ? (
                            <CheckSquare size={16} className="text-[#C59A55] flex-shrink-0" />
                          ) : (
                            <Square size={16} className="text-[#696E78] flex-shrink-0" />
                          )}
                        </div>
                        <div className="min-w-0 space-y-0.5">
                          <h4 className="font-semibold text-white truncate">
                            {b.taskTitle || b.focus}
                          </h4>
                          <div className="flex items-center gap-2 text-[11px] font-mono text-[#E6C17A]">
                            <Calendar size={11} />
                            <span>{b.day || b.date}</span>
                            <span>•</span>
                            <Clock size={11} />
                            <span>{b.startTime} – {b.endTime}</span>
                          </div>
                          {b.milestoneGroup && (
                            <div className="text-[10px] text-[#A1A4AA] font-mono truncate">
                              {b.milestoneGroup}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right Badges */}
                      <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                        {b.hasConflict ? (
                          <span className="text-[9px] bg-[#F07878]/15 border border-[#F07878]/30 text-[#F07878] px-2 py-0.5 rounded font-mono uppercase font-bold flex items-center gap-1">
                            <AlertTriangle size={10} />
                            <span>Conflict</span>
                          </span>
                        ) : (
                          <span className="text-[9px] bg-[#42D6A4]/10 border border-[#42D6A4]/20 text-[#42D6A4] px-2 py-0.5 rounded font-mono uppercase font-semibold">
                            ✓ Free
                          </span>
                        )}

                        {b.calendarEventId ? (
                          <span className="text-[9px] text-[#42D6A4] bg-[#42D6A4]/10 px-1.5 py-0.5 rounded font-mono flex items-center gap-1">
                            <CalendarCheck size={10} />
                            <span>Synced</span>
                          </span>
                        ) : (
                          <span className="text-[9px] text-[#696E78] font-mono">
                            Unsynced
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column (4 cols): Confirmation & Calendar Sync Panel */}
        <div className="lg:col-span-4 space-y-6">
          <div className="card-dark p-6 rounded-xl bg-[#121418] border border-white/10 space-y-5 sticky top-6">
            <div className="pb-3 border-b border-white/5">
              <span className="text-[10px] font-mono uppercase text-[#C59A55] font-semibold">
                REVIEW &amp; CONFIRMATION
              </span>
              <h3 className="text-sm font-bold text-white mt-1">
                Calendar Synchronization Summary
              </h3>
            </div>

            {/* Summary Details */}
            <div className="space-y-2.5 text-xs">
              <div className="flex items-center justify-between text-[#A1A4AA]">
                <span>Selected Sessions:</span>
                <span className="font-mono font-bold text-white">
                  {selectedBlockIds.size} of {proposedBlocks.length}
                </span>
              </div>

              <div className="flex items-center justify-between text-[#A1A4AA]">
                <span>Total Study Time:</span>
                <span className="font-mono font-bold text-[#E6C17A]">
                  {selectedHours} hours
                </span>
              </div>

              <div className="flex items-center justify-between text-[#A1A4AA]">
                <span>Known Conflicts:</span>
                <span className={`font-mono font-bold ${selectedConflictsCount > 0 ? 'text-[#F07878]' : 'text-[#42D6A4]'}`}>
                  {selectedConflictsCount} {selectedConflictsCount > 0 ? '⚠️' : '✓ None'}
                </span>
              </div>

              <div className="flex items-center justify-between text-[#A1A4AA]">
                <span>Target Calendar:</span>
                <span className="font-mono text-white">Primary Google Calendar</span>
              </div>

              <div className="flex items-center justify-between text-[#A1A4AA]">
                <span>User Timezone:</span>
                <span className="font-mono text-white">{proposalResult?.timezone || 'UTC'}</span>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="space-y-2.5 pt-2 border-t border-white/5">
              <button
                onClick={handleSync}
                disabled={syncingCalendar || selectedBlockIds.size === 0}
                className="w-full btn-bronze text-xs py-2.5 flex items-center justify-center gap-2 font-semibold shadow-lg shadow-[#C59A55]/10 disabled:opacity-50"
              >
                {syncingCalendar ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Adding to Google Calendar...</span>
                  </>
                ) : (
                  <>
                    <Calendar size={14} />
                    <span>Confirm &amp; Add {selectedBlockIds.size} Sessions to Calendar</span>
                  </>
                )}
              </button>

              <button
                onClick={handleApply}
                disabled={applyingSlots || selectedBlockIds.size === 0}
                className="w-full btn-secondary text-xs py-2 flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {applyingSlots ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <CheckSquare size={13} />
                )}
                <span>Save to Plan Only</span>
              </button>
            </div>

            {/* Explicit Disclosure */}
            <div className="p-3 rounded-lg bg-white/5 text-[10px] text-[#A1A4AA] font-mono leading-relaxed space-y-1">
              <div>• <strong>Explicit confirmation required:</strong> No events are created until you click &quot;Confirm &amp; Add to Calendar&quot;.</div>
              <div>• <strong>Duplicate guard:</strong> Sessions already linked to Google Calendar are automatically skipped.</div>
              <div>• <strong>Partial success:</strong> If any session fails, already created event IDs are preserved safely.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

