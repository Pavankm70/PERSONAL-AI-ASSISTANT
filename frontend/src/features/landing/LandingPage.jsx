import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from '../../components/Navbar';
import { Marquee } from '../../components/Marquee';
import { ProductPreview } from '../../components/ProductPreview';
import { BRAND_CONFIG } from '../../config/brand';
import { 
  Bot,
  ArrowRight, 
  ShieldCheck, 
  Mail, 
  Calendar, 
  HardDrive, 
  FileText, 
  Search, 
  Clock, 
  Sparkles, 
  Layers, 
  CheckCircle, 
  Lock, 
  ChevronDown, 
  Sliders, 
  Database,
  Globe,
  Zap,
  Check,
  ChevronRight
} from 'lucide-react';

export const LandingPage = () => {
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState(null);

  const toggleFaq = (index) => {
    setOpenFaq(openFaq === index ? null : index);
  };

  const tickerCapabilities = [
    "GMAIL",
    "GOOGLE CALENDAR",
    "GOOGLE DRIVE",
    "PERSONAL RAG",
    "WEB RESEARCH",
    "SMART PLANNING"
  ];

  const tickerPrinciples = [
    "PERSONAL INTELLIGENCE",
    "CONNECTED WORKSPACE",
    "YOUR DATA",
    "ONE ASSISTANT"
  ];

  const faqs = [
    {
      q: "How does Google sign-in work?",
      a: "Aurelia AI uses standard Google OAuth 2.0. The initial sign-in authenticates your identity without requesting inbox or calendar access. You then grant granular access to Gmail, Calendar, or Drive through incremental consent only when you choose to enable those features."
    },
    {
      q: "Does the assistant access my emails automatically?",
      a: "No. The assistant queries your Gmail account only when you ask an email-related question (such as 'Summarize my important emails today'). It never reads or trains public models on your personal correspondence."
    },
    {
      q: "Can I upload my own documents?",
      a: "Yes. You can upload PDFs, text documents, syllabi, notes, and timetables. Documents are parsed, chunked, and stored in a private PostgreSQL vector database with strict per-user tenant isolation."
    },
    {
      q: "How does personal memory work?",
      a: "Permanent information is stored persistently in the database and retrieved via hybrid vector similarity search and structured timetable schemas. When you ask about your class timetable, it queries structured records for 100% precision."
    },
    {
      q: "Can the assistant change my calendar?",
      a: "The assistant never silently modifies your calendar. When it proposes a study block or schedule adjustment, it generates a preview and requires your explicit confirmation before creating or updating any Google Calendar event."
    },
    {
      q: "Can I disconnect Google?",
      a: "At any time. You can disconnect your Google account or revoke specific scopes (Gmail, Calendar, Drive) from the Integrations page with a single click. Tokens are immediately erased."
    },
    {
      q: "Is my information shared with other users?",
      a: "Never. Every database query, vector retrieval, and OAuth token is strictly partitioned by your authenticated user ID. No data is shared across accounts."
    }
  ];

  return (
    <div className="min-h-screen bg-[#08090B] text-[#F5F3EE] overflow-x-hidden selection:bg-[#C59A55]/30 selection:text-white">
      {/* 4.1 Sticky Navigation */}
      <Navbar />

      {/* Ambient Radial Glow in Hero */}
      <div className="ambient-glow top-12 left-1/2 -translate-x-1/2" />

      {/* 4.2 Hero Section */}
      <section className="relative pt-36 pb-20 md:pt-44 md:pb-28 bg-grid">
        <div className="container mx-auto px-6 text-center relative z-10">
          {/* Eyebrow badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#181B20] border border-white/10 text-xs font-mono tracking-widest text-[#E6C17A] uppercase mb-8 shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-[#42D6A4] animate-pulse" />
            {BRAND_CONFIG.eyebrow}
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-white max-w-4xl mx-auto leading-[1.08] mb-6">
            Your life, in one{" "}
            <span className="text-gradient-bronze">intelligent workspace.</span>
          </h1>

          {/* Supporting Copy */}
          <p className="text-base sm:text-lg md:text-xl text-[#A1A4AA] max-w-2xl mx-auto mb-10 leading-relaxed font-normal">
            {BRAND_CONFIG.description}
          </p>

          {/* Dual CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-6">
            <button
              onClick={() => navigate('/auth')}
              className="btn-bronze w-full sm:w-auto text-base py-3.5 px-8"
            >
              <span>Get started</span>
              <ArrowRight size={16} />
            </button>

            <button
              onClick={() => {
                const el = document.getElementById('platform');
                if (el) el.scrollIntoView({ behavior: 'smooth' });
              }}
              className="btn-secondary w-full sm:w-auto text-base py-3.5 px-8"
            >
              Explore the platform
            </button>
          </div>

          {/* Trust Note */}
          <div className="flex items-center justify-center gap-2 text-xs font-mono text-[#696E78] tracking-wide">
            <ShieldCheck size={14} className="text-[#C59A55]" />
            <span>{BRAND_CONFIG.trustNote}</span>
          </div>

          {/* Subtle scroll down indicator */}
          <div className="mt-12 flex justify-center opacity-40 hover:opacity-100 transition-opacity">
            <div className="w-5 h-8 rounded-full border border-white/20 flex items-start justify-center p-1">
              <div className="w-1 h-2 rounded-full bg-[#C59A55] animate-bounce" />
            </div>
          </div>
        </div>

        {/* 4.3 Interactive Product Preview */}
        <div id="platform" className="container mx-auto px-6 mt-12">
          <ProductPreview />
        </div>
      </section>

      {/* 4.4 Moving Capability Tickers */}
      <section className="py-6 space-y-3">
        <Marquee items={tickerCapabilities} speedSeconds={28} />
        <Marquee items={tickerPrinciples} speedSeconds={34} reverse={true} />
      </section>

      {/* 4.5 Trusted-by / Integration Section */}
      <section className="py-14 border-b border-white/5 bg-[#08090B]">
        <div className="container mx-auto px-6 text-center">
          <p className="text-xs font-mono uppercase tracking-widest text-[#696E78] mb-8">
            Designed for seamless synchronization across your personal ecosystem
          </p>
          <div className="flex flex-wrap items-center justify-center gap-8 md:gap-14 opacity-75">
            {[
              { name: "GMAIL", icon: Mail },
              { name: "GOOGLE CALENDAR", icon: Calendar },
              { name: "GOOGLE DRIVE", icon: HardDrive },
              { name: "PERSONAL KNOWLEDGE", icon: FileText },
              { name: "WEB SEARCH", icon: Search },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.name}
                  className="flex items-center gap-2.5 px-4 py-2 rounded-lg bg-[#121418] border border-white/5 text-xs font-mono text-[#A1A4AA] tracking-wider hover:border-[#C59A55]/40 hover:text-white transition-all cursor-default"
                >
                  <Icon size={14} className="text-[#C59A55]" />
                  <span>{item.name}</span>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#42D6A4]" />
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* 4.6 Benefits and Metrics */}
      <section className="py-24 bg-[#08090B]">
        <div className="container mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <span className="text-eyebrow">INTEGRATED COGNITION</span>
            <h2 className="text-3xl sm:text-4xl font-bold text-white mt-2 mb-4 tracking-tight">
              More context. Less switching.
            </h2>
            <p className="text-sm sm:text-base text-[#A1A4AA]">
              Stop jumping between fragmented tabs, schedules, and note files. Aurelia bridges your digital life into one unified assistant.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              {
                icon: Bot,
                title: "One Conversational Interface",
                desc: "Ask questions, request summaries, and issue commands naturally through a single unified chat console."
              },
              {
                icon: FileText,
                title: "Context From Your Documents",
                desc: "Uploaded course timetables, research notes, and papers become instantly retrievable with grounded citations."
              },
              {
                icon: Calendar,
                title: "Calendar-Aware Planning",
                desc: "Proposes realistic study blocks and task slots that fit directly into open gaps in your authorized Google Calendar."
              },
              {
                icon: Globe,
                title: "Research With Citations",
                desc: "Combines personal records with live web intelligence, always referencing sources so you can verify facts."
              }
            ].map((card, i) => {
              const Icon = card.icon;
              return (
                <div key={i} className="card-dark card-hover p-6 rounded-xl border border-white/10 bg-[#121418] flex flex-col justify-between">
                  <div>
                    <div className="w-10 h-10 rounded-lg bg-[#181B20] border border-[#C59A55]/30 flex items-center justify-center text-[#E6C17A] mb-5">
                      <Icon size={18} />
                    </div>
                    <h3 className="text-base font-semibold text-white mb-2">{card.title}</h3>
                    <p className="text-xs text-[#A1A4AA] leading-relaxed">{card.desc}</p>
                  </div>
                  <div className="mt-6 pt-4 border-t border-white/5 flex items-center text-[10px] font-mono text-[#C59A55]">
                    <span>0{i + 1} / CAPABILITY</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Illustrative Telemetry Cards */}
          <div className="mt-12 p-6 rounded-xl border border-white/5 bg-[#0D0F12] grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div>
              <div className="text-2xl sm:text-3xl font-bold font-mono text-white mb-1">100%</div>
              <div className="text-[11px] text-[#696E78] uppercase font-mono tracking-wider">User Data Isolation</div>
            </div>
            <div>
              <div className="text-2xl sm:text-3xl font-bold font-mono text-[#C59A55] mb-1">&lt; 150ms</div>
              <div className="text-[11px] text-[#696E78] uppercase font-mono tracking-wider">Vector Query Latency*</div>
            </div>
            <div>
              <div className="text-2xl sm:text-3xl font-bold font-mono text-white mb-1">0</div>
              <div className="text-[11px] text-[#696E78] uppercase font-mono tracking-wider">Silent Event Creation</div>
            </div>
            <div>
              <div className="text-2xl sm:text-3xl font-bold font-mono text-[#42D6A4] mb-1">AES-256</div>
              <div className="text-[11px] text-[#696E78] uppercase font-mono tracking-wider">Token Encryption At Rest</div>
            </div>
          </div>
          <p className="text-center text-[10px] font-mono text-[#696E78] mt-3">
            *Illustrative architectural benchmark metrics. All actions and storage strictly verified against server state.
          </p>
        </div>
      </section>

      {/* 4.7 Feature Grid (Bento Style) */}
      <section id="capabilities" className="py-24 bg-[#08090B] border-t border-white/5">
        <div className="container mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <span className="text-eyebrow">CAPABILITIES</span>
            <h2 className="text-3xl sm:text-4xl font-bold text-white mt-2 mb-4 tracking-tight">
              A complete command center for your day.
            </h2>
            <p className="text-sm sm:text-base text-[#A1A4AA]">
              Every tool is engineered with modular safety boundaries, typed schemas, and human-in-the-loop approvals.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Feature 1: Connected Inbox */}
            <div className="card-dark card-hover p-7 rounded-xl bg-[#121418] border border-white/10 md:col-span-2">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2.5 rounded-lg bg-[#181B20] border border-[#C59A55]/30 text-[#E6C17A]">
                  <Mail size={18} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">Connected Inbox</h3>
                  <div className="text-[11px] font-mono text-[#C59A55]">FEATURE 01</div>
                </div>
              </div>
              <p className="text-sm text-[#A1A4AA] mb-6">
                Surface important messages, summarize threads, and identify what needs your immediate attention without scanning hundreds of newsletters.
              </p>
              <div className="p-4 rounded-lg bg-[#08090B] border border-white/5 text-xs space-y-2">
                <div className="flex items-center justify-between text-[#696E78] font-mono text-[10px]">
                  <span>SAMPLE EMAIL ANALYSIS</span>
                  <span className="text-[#42D6A4]">PARSED</span>
                </div>
                <div className="text-white font-medium">"Prof. Vance: Revised Thesis Methodology Feedback"</div>
                <div className="text-[#A1A4AA] text-[11px]">Action identified: Submit updated literature review by Friday 5 PM.</div>
              </div>
            </div>

            {/* Feature 2: Calendar Intelligence */}
            <div className="card-dark card-hover p-7 rounded-xl bg-[#121418] border border-white/10">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2.5 rounded-lg bg-[#181B20] border border-[#C59A55]/30 text-[#E6C17A]">
                  <Calendar size={18} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">Calendar Intelligence</h3>
                  <div className="text-[11px] font-mono text-[#C59A55]">FEATURE 02</div>
                </div>
              </div>
              <p className="text-sm text-[#A1A4AA] mb-4">
                Understand your schedule, detect conflicts, and propose the right time for your next study block or personal commitment.
              </p>
              <div className="p-3 rounded-lg bg-[#08090B] border border-white/5 text-xs text-[#E6C17A] font-mono">
                Conflict check: 0 clashes found for proposed 3:00 PM slot.
              </div>
            </div>

            {/* Feature 3: Personal Knowledge */}
            <div className="card-dark card-hover p-7 rounded-xl bg-[#121418] border border-white/10">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2.5 rounded-lg bg-[#181B20] border border-[#C59A55]/30 text-[#E6C17A]">
                  <FileText size={18} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">Personal Knowledge</h3>
                  <div className="text-[11px] font-mono text-[#C59A55]">FEATURE 03</div>
                </div>
              </div>
              <p className="text-sm text-[#A1A4AA] mb-4">
                Ask questions about your timetable, course notes, plans, and uploaded PDFs with exact section citations.
              </p>
              <div className="p-3 rounded-lg bg-[#08090B] border border-white/5 text-xs text-[#A1A4AA]">
                <span className="text-white font-medium">Structured Timetable Record:</span> Class Monday at 10:00 AM (Room 302).
              </div>
            </div>

            {/* Feature 4: Web Intelligence */}
            <div className="card-dark card-hover p-7 rounded-xl bg-[#121418] border border-white/10">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2.5 rounded-lg bg-[#181B20] border border-[#C59A55]/30 text-[#E6C17A]">
                  <Search size={18} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">Web Intelligence</h3>
                  <div className="text-[11px] font-mono text-[#C59A55]">FEATURE 04</div>
                </div>
              </div>
              <p className="text-sm text-[#A1A4AA] mb-4">
                Research current information and receive up-to-date answers supported by verified source URLs.
              </p>
              <div className="p-3 rounded-lg bg-[#08090B] border border-white/5 text-xs text-[#696E78] font-mono">
                Retrieved 4 live citations with zero hallucinations.
              </div>
            </div>

            {/* Feature 5: Personal Planning */}
            <div className="card-dark card-hover p-7 rounded-xl bg-[#121418] border border-white/10">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2.5 rounded-lg bg-[#181B20] border border-[#C59A55]/30 text-[#E6C17A]">
                  <Layers size={18} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">Personal Planning</h3>
                  <div className="text-[11px] font-mono text-[#C59A55]">FEATURE 05</div>
                </div>
              </div>
              <p className="text-sm text-[#A1A4AA] mb-4">
                Bring your academic goals, open availability, and personal priorities together into actionable weekly roadmaps.
              </p>
              <div className="p-3 rounded-lg bg-[#08090B] border border-white/5 text-xs text-[#42D6A4] font-mono">
                Generated study roadmap: 4 focused sessions planned.
              </div>
            </div>

            {/* Feature 6: Controlled Actions (Full width) */}
            <div className="card-dark card-hover p-7 rounded-xl bg-[#121418] border border-white/10 md:col-span-3">
              <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-[#181B20] border border-[#42D6A4]/30 text-[#42D6A4]">
                    <ShieldCheck size={20} />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-white">Controlled Actions</h3>
                    <div className="text-[11px] font-mono text-[#C59A55]">FEATURE 06 — SAFETY PROTOCOL</div>
                  </div>
                </div>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded bg-[#181B20] border border-white/10 text-xs font-mono text-[#42D6A4]">
                  <Check size={14} />
                  <span>PREVIEW &amp; CONFIRMATION REQUIRED</span>
                </div>
              </div>
              <p className="text-sm text-[#A1A4AA] mt-4 max-w-3xl">
                Review proposed schedule changes and approve consequential actions before they happen. The agent never silently writes to your calendar without your explicit approval.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 4.8 How It Works */}
      <section id="how-it-works" className="py-24 bg-[#08090B]">
        <div className="container mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <span className="text-eyebrow">WORKFLOW</span>
            <h2 className="text-3xl sm:text-4xl font-bold text-white mt-2 mb-4 tracking-tight">
              Three steps to complete clarity.
            </h2>
            <p className="text-sm sm:text-base text-[#A1A4AA]">
              Get started in minutes with standard OAuth and zero friction.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
            {[
              {
                step: "01",
                title: "Connect your Google account",
                desc: "Authorize only what you need. Connect Gmail, Google Calendar, and Drive through secure, revocable OAuth permissions."
              },
              {
                step: "02",
                title: "Add your personal knowledge",
                desc: "Upload your class timetable, syllabi, notes, or research documents into your isolated, private vector repository."
              },
              {
                step: "03",
                title: "Ask, discover, and organize",
                desc: "Instruct Aurelia naturally. Review generated agendas, approve calendar events, and execute tasks with confidence."
              }
            ].map((s, idx) => (
              <div key={s.step} className="p-8 rounded-xl bg-[#121418] border border-white/10 relative">
                <div className="text-3xl font-mono font-bold text-[#C59A55] mb-4">
                  {s.step}
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{s.title}</h3>
                <p className="text-xs sm:text-sm text-[#A1A4AA] leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 4.9 Security Section */}
      <section id="security" className="py-24 bg-[#08090B] border-t border-white/5">
        <div className="container mx-auto px-6">
          <div className="max-w-4xl mx-auto bg-[#121418] border border-white/10 rounded-2xl p-8 sm:p-12 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-80 h-80 bg-gradient-to-b from-[#C59A55]/10 to-transparent blur-3xl pointer-events-none" />

            <div className="flex items-center gap-3 mb-6">
              <div className="p-3 rounded-xl bg-[#181B20] border border-[#C59A55]/40 text-[#E6C17A]">
                <Lock size={22} />
              </div>
              <div>
                <span className="text-eyebrow">PRIVACY ARCHITECTURE</span>
                <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                  Your information stays yours.
                </h2>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mt-8 text-sm">
              <div className="flex items-start gap-3">
                <CheckCircle size={18} className="text-[#42D6A4] mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="font-semibold text-white mb-1">Explicit Google Authorization</h4>
                  <p className="text-xs text-[#A1A4AA]">
                    Google service access uses least-privilege incremental scopes. We never request blanket permissions.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle size={18} className="text-[#42D6A4] mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="font-semibold text-white mb-1">Instant Account Disconnection</h4>
                  <p className="text-xs text-[#A1A4AA]">
                    You can revoke any connected integration at any moment. Tokens are purged immediately from storage.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle size={18} className="text-[#42D6A4] mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="font-semibold text-white mb-1">Tenant Document Isolation</h4>
                  <p className="text-xs text-[#A1A4AA]">
                    Uploaded documents and embeddings are filtered by your strict authenticated user ID.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle size={18} className="text-[#42D6A4] mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="font-semibold text-white mb-1">AES-256 Protected Tokens</h4>
                  <p className="text-xs text-[#A1A4AA]">
                    OAuth refresh tokens are encrypted at rest with AES-GCM and never logged in plaintext.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4.10 FAQ */}
      <section id="faq" className="py-24 bg-[#08090B]">
        <div className="container mx-auto px-6 max-w-3xl">
          <div className="text-center mb-16">
            <span className="text-eyebrow">COMMON INQUIRIES</span>
            <h2 className="text-3xl sm:text-4xl font-bold text-white mt-2 mb-4 tracking-tight">
              Frequently asked questions.
            </h2>
            <p className="text-sm text-[#A1A4AA]">
              Clear answers describing our actual implemented architecture.
            </p>
          </div>

          <div className="space-y-4">
            {faqs.map((faq, idx) => {
              const isOpen = openFaq === idx;
              return (
                <div
                  key={idx}
                  className="rounded-xl border border-white/10 bg-[#121418] overflow-hidden transition-all"
                >
                  <button
                    onClick={() => toggleFaq(idx)}
                    className="w-full p-5 text-left flex items-center justify-between text-sm sm:text-base font-medium text-white hover:text-[#E6C17A] transition-colors"
                  >
                    <span>{faq.q}</span>
                    <ChevronDown
                      size={18}
                      className={`text-[#C59A55] transition-transform duration-200 ${
                        isOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-5 pt-1 text-xs sm:text-sm text-[#A1A4AA] leading-relaxed border-t border-white/5">
                      {faq.a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* 4.11 Final CTA & Footer */}
      <section className="relative py-24 bg-gradient-to-b from-[#08090B] via-[#0D0F12] to-[#08090B] border-t border-white/5">
        <div className="container mx-auto px-6 text-center relative z-10">
          <div className="max-w-2xl mx-auto">
            <h2 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight mb-4">
              Bring clarity to your <span className="text-gradient-bronze">entire life.</span>
            </h2>
            <p className="text-sm sm:text-base text-[#A1A4AA] mb-8">
              Experience the peace of mind that comes with an assistant that knows your schedule, respects your privacy, and acts on your terms.
            </p>
            <button
              onClick={() => navigate('/auth')}
              className="btn-bronze text-base py-3.5 px-8"
            >
              <span>Launch your workspace</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-24 pt-8 border-t border-white/5 text-xs text-[#696E78]">
          <div className="container mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-white">{BRAND_CONFIG.name}</span>
              <span>— {BRAND_CONFIG.version}</span>
            </div>

            <div className="flex items-center gap-6">
              <a href="#platform" className="hover:text-white transition-colors">Platform</a>
              <a href="#security" className="hover:text-white transition-colors">Privacy</a>
              <a href="#security" className="hover:text-white transition-colors">Terms</a>
              <a href="#security" className="hover:text-white transition-colors">Security</a>
              <a href="#faq" className="hover:text-white transition-colors">Contact</a>
            </div>
          </div>
        </footer>
      </section>
    </div>
  );
};
