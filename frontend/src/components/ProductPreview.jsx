import React, { useState } from 'react';
import { 
  Bot, 
  Calendar, 
  Mail, 
  FileText, 
  Layers, 
  Sparkles, 
  CheckCircle2, 
  Clock, 
  Search,
  ExternalLink,
  ChevronRight,
  TrendingUp,
  Activity
} from 'lucide-react';

export const ProductPreview = () => {
  const [activeTab, setActiveTab] = useState('chat');
  const [selectedPrompt, setSelectedPrompt] = useState(0);

  const demoPrompts = [
    {
      q: "What do I have scheduled tomorrow, and when is my MSc class?",
      tools: ["Google Calendar API", "Timetable Knowledge Engine"],
      answer: "You have 2 calendar commitments tomorrow. Your MSc Advanced Machine Learning lecture is at 10:00 AM in Hall B. You have an open study window between 2:00 PM and 4:30 PM.",
      citations: [
        { type: "doc", name: "MSc_Timetable_Sem1.pdf", page: "p. 3" },
        { type: "cal", name: "Google Calendar (Synced)", time: "Tomorrow 10:00 AM" }
      ],
      action: {
        type: "Propose Study Block",
        time: "2:30 PM – 4:00 PM (90 mins)",
        ready: true
      }
    },
    {
      q: "Summarize my important emails from today.",
      tools: ["Gmail Intelligence API"],
      answer: "Found 3 priority emails: Professor Vance sent project feedback requiring review by Friday; Registrar confirmed exam registration dates; Research lab sent grant submission guidelines.",
      citations: [
        { type: "email", name: "Prof. Vance - Thesis Feedback", time: "11:24 AM" },
        { type: "email", name: "Academic Office - Exams", time: "09:15 AM" }
      ]
    }
  ];

  const current = demoPrompts[selectedPrompt];

  return (
    <div className="relative mx-auto max-w-6xl w-full">
      {/* Ambient background glow */}
      <div className="absolute -inset-1 bg-gradient-to-r from-[#C59A55]/20 via-[#8B622F]/10 to-transparent rounded-2xl blur-2xl opacity-60 pointer-events-none -z-10" />

      {/* Main Container Mockup */}
      <div className="rounded-xl border border-white/10 bg-[#0D0F12] shadow-2xl shadow-black overflow-hidden">
        {/* Window Chrome / Status Bar */}
        <div className="flex items-center justify-between px-4 py-3 bg-[#08090B] border-b border-white/5 text-xs text-[#A1A4AA]">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#F07878]/80" />
            <div className="w-3 h-3 rounded-full bg-[#E6C17A]/80" />
            <div className="w-3 h-3 rounded-full bg-[#42D6A4]/80" />
            <span className="ml-2 font-mono text-[11px] text-[#696E78]">aurelia.workspace.local</span>
          </div>

          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#42D6A4]/10 text-[#42D6A4] font-mono text-[10px] border border-[#42D6A4]/20">
              <span className="w-1.5 h-1.5 rounded-full bg-[#42D6A4] animate-pulse" />
              SYSTEM 001 ACTIVE
            </span>
            <span className="hidden sm:inline font-mono text-[11px] text-[#C59A55] bg-[#C59A55]/10 px-2 py-0.5 rounded border border-[#C59A55]/20">
              SIMULATED PREVIEW — DEMO
            </span>
          </div>
        </div>

        {/* Dashboard Body Grid */}
        <div className="grid grid-cols-1 md:grid-cols-12 min-h-[480px]">
          {/* Mock Sidebar */}
          <div className="md:col-span-3 border-r border-white/5 bg-[#08090B]/60 p-4 flex flex-col justify-between">
            <div className="space-y-4">
              <div className="text-[11px] font-mono tracking-wider text-[#696E78] uppercase px-2">
                Workspace
              </div>
              <div className="space-y-1">
                {[
                  { id: 'chat', label: 'AI Assistant', icon: Bot },
                  { id: 'inbox', label: 'Connected Inbox', icon: Mail, badge: '3' },
                  { id: 'calendar', label: 'Calendar Engine', icon: Calendar, badge: '2' },
                  { id: 'knowledge', label: 'Knowledge Base', icon: FileText, badge: '5 docs' },
                  { id: 'plans', label: 'Personal Plans', icon: Layers }
                ].map((tab) => {
                  const Icon = tab.icon;
                  const isActive = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                        isActive
                          ? 'bg-[#181B20] text-white border border-[#C59A55]/30 shadow-sm shadow-[#C59A55]/10'
                          : 'text-[#A1A4AA] hover:text-white hover:bg-white/5'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon size={14} className={isActive ? 'text-[#C59A55]' : 'text-[#696E78]'} />
                        <span>{tab.label}</span>
                      </div>
                      {tab.badge && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                          isActive ? 'bg-[#C59A55]/20 text-[#E6C17A]' : 'bg-white/5 text-[#696E78]'
                        }`}>
                          {tab.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Connected Services mini badge */}
            <div className="pt-4 border-t border-white/5 space-y-2">
              <div className="text-[10px] font-mono text-[#696E78] uppercase tracking-wider">
                Authorized Streams
              </div>
              <div className="flex flex-wrap gap-1.5">
                {['Gmail', 'Calendar', 'Drive', 'PgVector'].map((srv) => (
                  <span key={srv} className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-[#121418] text-[#A1A4AA] border border-white/5">
                    <span className="w-1 h-1 rounded-full bg-[#42D6A4]" />
                    {srv}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Central AI Conversation Preview */}
          <div className="md:col-span-6 p-5 flex flex-col justify-between bg-[#0D0F12]">
            <div className="space-y-4">
              {/* Prompt switcher pills */}
              <div className="flex gap-2 pb-2 border-b border-white/5 overflow-x-auto">
                {demoPrompts.map((p, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSelectedPrompt(idx)}
                    className={`text-xs px-3 py-1 rounded-full border transition-all text-left whitespace-nowrap ${
                      selectedPrompt === idx
                        ? 'border-[#C59A55] bg-[#C59A55]/10 text-[#E6C17A]'
                        : 'border-white/10 bg-[#121418] text-[#A1A4AA] hover:border-white/20'
                    }`}
                  >
                    Demo Query #{idx + 1}
                  </button>
                ))}
              </div>

              {/* User message block */}
              <div className="flex items-start gap-3 justify-end">
                <div className="bg-[#181B20] border border-white/10 rounded-xl px-4 py-3 max-w-[85%] text-xs text-[#F5F3EE] shadow-sm">
                  {current.q}
                </div>
              </div>

              {/* Assistant response block */}
              <div className="space-y-2">
                {/* Tool execution indicator */}
                <div className="flex flex-wrap items-center gap-2">
                  {current.tools.map((tool) => (
                    <div key={tool} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#121418] border border-[#42D6A4]/30 text-[11px] font-mono text-[#42D6A4]">
                      <CheckCircle2 size={11} />
                      <span>{tool}</span>
                    </div>
                  ))}
                </div>

                <div className="bg-[#121418] border border-white/10 rounded-xl p-4 text-xs text-[#F5F3EE] leading-relaxed shadow-card">
                  <p className="mb-3">{current.answer}</p>

                  {/* Grounded Citations */}
                  <div className="pt-3 border-t border-white/5 space-y-1.5">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-[#C59A55]">
                      Grounding References
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {current.citations.map((c, i) => (
                        <div key={i} className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-[#08090B] border border-white/5 text-[11px] text-[#A1A4AA]">
                          <FileText size={10} className="text-[#C59A55]" />
                          <span>{c.name}</span>
                          <span className="text-[#696E78]">({c.page || c.time})</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Proposed Action Preview */}
                  {current.action && (
                    <div className="mt-3 p-3 rounded-lg bg-[#181B20] border border-[#C59A55]/30 flex items-center justify-between">
                      <div>
                        <div className="text-[10px] font-mono text-[#E6C17A] uppercase">Suggested Action</div>
                        <div className="text-xs font-semibold text-white">{current.action.type}</div>
                        <div className="text-[11px] text-[#A1A4AA]">{current.action.time}</div>
                      </div>
                      <button className="btn-bronze text-xs py-1 px-3">
                        Confirm Event
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Input Composer Mockup */}
            <div className="mt-4 pt-3 border-t border-white/5 flex items-center gap-2">
              <div className="flex-1 bg-[#121418] border border-white/10 rounded-lg px-3 py-2 text-xs text-[#696E78] flex items-center justify-between">
                <span>Ask Aurelia to plan, search, or summarize...</span>
                <span className="font-mono text-[10px] text-[#696E78] bg-black/40 px-1.5 py-0.5 rounded">↵ Return</span>
              </div>
            </div>
          </div>

          {/* Right Panel: Dynamic Telemetry & Highlights */}
          <div className="md:col-span-3 border-l border-white/5 bg-[#08090B]/60 p-4 space-y-4">
            {/* Live Schedule Pulse */}
            <div className="p-3 rounded-xl bg-[#121418] border border-white/5 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-white flex items-center gap-1.5">
                  <Calendar size={13} className="text-[#C59A55]" />
                  Tomorrow's Agenda
                </span>
                <span className="text-[10px] font-mono text-[#42D6A4]">2 Events</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="p-2 rounded bg-[#08090B] border border-white/5">
                  <div className="font-medium text-white text-[11px]">MSc Adv. Machine Learning</div>
                  <div className="text-[10px] text-[#696E78] font-mono">10:00 – 12:00 PM • Hall B</div>
                </div>
                <div className="p-2 rounded bg-[#08090B] border border-white/5">
                  <div className="font-medium text-white text-[11px]">Lab Meeting & Sync</div>
                  <div className="text-[10px] text-[#696E78] font-mono">01:00 – 02:00 PM • Online</div>
                </div>
              </div>
            </div>

            {/* Weekly Optimization Activity Chart */}
            <div className="p-3 rounded-xl bg-[#121418] border border-white/5 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-white flex items-center gap-1.5">
                  <Activity size={13} className="text-[#E6C17A]" />
                  Productive Windows
                </span>
                <span className="text-[10px] font-mono text-[#C59A55]">+4.5 hrs saved</span>
              </div>
              {/* Subtle animated bar lines */}
              <div className="flex items-end gap-1.5 h-16 pt-2">
                {[40, 75, 55, 90, 65, 80, 45].map((h, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <div 
                      className="w-full rounded-t bg-gradient-to-t from-[#8B622F]/40 to-[#C59A55] transition-all hover:brightness-125"
                      style={{ height: `${h}%` }}
                    />
                    <span className="text-[8px] font-mono text-[#696E78]">
                      {['M','T','W','T','F','S','S'][i]}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Knowledge Index Status */}
            <div className="p-3 rounded-xl bg-[#121418] border border-white/5 space-y-1 text-xs">
              <div className="text-[10px] font-mono text-[#696E78] uppercase">Knowledge Vector Index</div>
              <div className="text-white font-medium">5 Documents Synced</div>
              <div className="text-[11px] text-[#42D6A4] flex items-center gap-1">
                <CheckCircle2 size={12} />
                <span>RAG retrieval ready (pgvector)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
