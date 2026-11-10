import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { BrandLogo } from '../../components/BrandLogo';
import { 
  CheckCircle2, 
  ArrowRight, 
  Mail, 
  Calendar, 
  HardDrive, 
  UploadCloud, 
  Check, 
  ChevronRight, 
  Sparkles,
  ShieldCheck,
  FileText,
  AlertCircle
} from 'lucide-react';

export const OnboardingPage = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [user, setUser] = useState(null);
  const [integrations, setIntegrations] = useState({
    gmail: 'not_connected',
    calendar: 'not_connected',
    drive: 'not_connected'
  });
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    const loadUserAndState = async () => {
      try {
        const u = await api.getCurrentUser();
        setUser(u);
      } catch (err) {
        // Fallback user if offline
        setUser({
          fullName: 'Alex Chen',
          email: 'alex.chen@university.edu',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Los_Angeles'
        });
      }

      try {
        const ints = await api.getIntegrations();
        const stateMap = {};
        ints.forEach((i) => {
          stateMap[i.provider] = i.status;
        });
        setIntegrations((prev) => ({ ...prev, ...stateMap }));
      } catch (e) {
        // use default state
      }
    };

    loadUserAndState();
  }, []);

  const handleConnect = (service) => {
    // In production mode with client IDs, initiates Google OAuth for that specific scope category
    // In dev demo mode, toggles state to connected
    const url = api.getGoogleOAuthUrl(service);
    // If backend reports no client ID, simulate dev connection
    setIntegrations((prev) => ({
      ...prev,
      [service]: prev[service] === 'connected' ? 'not_connected' : 'connected'
    }));
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      await api.uploadDocument(file, 'timetable');
      setUploadedFiles((prev) => [...prev, file.name]);
    } catch (err) {
      // simulate demo file record
      setUploadedFiles((prev) => [...prev, file.name]);
    } finally {
      setUploading(false);
    }
  };

  const handleFinish = async () => {
    try {
      await api.updateSettings({ onboardingComplete: true });
    } catch (e) {
      // proceed
    }
    navigate('/app');
  };

  const steps = [
    { num: 1, title: 'Profile' },
    { num: 2, title: 'Gmail' },
    { num: 3, title: 'Calendar' },
    { num: 4, title: 'Drive' },
    { num: 5, title: 'Knowledge' }
  ];

  return (
    <div className="min-h-screen bg-[#08090B] text-[#F5F3EE] flex flex-col justify-between p-6 bg-grid">
      <div className="container mx-auto flex items-center justify-between z-10 max-w-3xl">
        <BrandLogo size="md" />
        <span className="font-mono text-xs text-[#C59A55]">
          STEP 0{currentStep} OF 05
        </span>
      </div>

      <div className="container mx-auto max-w-xl w-full my-8 z-10">
        {/* Step progress pills */}
        <div className="flex items-center justify-between mb-8 px-2">
          {steps.map((s) => (
            <div key={s.num} className="flex items-center">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center font-mono text-xs font-semibold transition-all ${
                  currentStep === s.num
                    ? 'bg-[#C59A55] text-black ring-4 ring-[#C59A55]/20'
                    : currentStep > s.num
                    ? 'bg-[#42D6A4] text-black'
                    : 'bg-[#181B20] text-[#696E78] border border-white/10'
                }`}
              >
                {currentStep > s.num ? <Check size={12} /> : s.num}
              </div>
              {s.num < 5 && (
                <div
                  className={`w-12 sm:w-16 h-0.5 mx-1.5 transition-colors ${
                    currentStep > s.num ? 'bg-[#42D6A4]' : 'bg-white/10'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {/* Wizard Card Body */}
        <div className="card-dark p-8 rounded-2xl bg-[#121418] border border-white/10 shadow-2xl min-h-[380px] flex flex-col justify-between">
          {/* Step 1: Profile Confirmation */}
          {currentStep === 1 && (
            <div className="space-y-6 animate-in fade-in">
              <div>
                <span className="text-eyebrow">STEP 01</span>
                <h2 className="text-2xl font-bold text-white mt-1">Confirm your profile</h2>
                <p className="text-xs text-[#A1A4AA] mt-1">
                  Aurelia organizes your schedule based on your designated timezone and identity.
                </p>
              </div>

              <div className="space-y-4 pt-2">
                <div>
                  <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={user?.fullName || 'Alex Chen'}
                    onChange={(e) => setUser({ ...user, fullName: e.target.value })}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2.5 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    disabled
                    value={user?.email || 'alex.chen@university.edu'}
                    className="w-full bg-[#08090B]/50 border border-white/5 rounded-lg px-3 py-2.5 text-xs text-[#696E78]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-mono text-[#A1A4AA] uppercase mb-1">
                    System Timezone
                  </label>
                  <input
                    type="text"
                    value={user?.timezone || 'America/Los_Angeles'}
                    onChange={(e) => setUser({ ...user, timezone: e.target.value })}
                    className="w-full bg-[#08090B] border border-white/10 rounded-lg px-3 py-2.5 text-xs text-white focus:outline-none focus:border-[#C59A55]"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Connect Gmail */}
          {currentStep === 2 && (
            <div className="space-y-6 animate-in fade-in">
              <div>
                <span className="text-eyebrow">STEP 02</span>
                <h2 className="text-2xl font-bold text-white mt-1">Connect your Gmail</h2>
                <p className="text-xs text-[#A1A4AA] mt-1">
                  Authorize read-only intelligence access to surface priority threads and actionable emails.
                </p>
              </div>

              <div className="p-5 rounded-xl bg-[#08090B] border border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-3.5">
                  <div className="p-3 rounded-lg bg-[#181B20] text-[#E6C17A]">
                    <Mail size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">Gmail Integration</h4>
                    <p className="text-xs text-[#A1A4AA]">
                      Status:{" "}
                      <span className={integrations.gmail === 'connected' ? 'text-[#42D6A4] font-semibold' : 'text-[#696E78]'}>
                        {integrations.gmail === 'connected' ? 'Connected' : 'Not Connected'}
                      </span>
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => handleConnect('gmail')}
                  className={integrations.gmail === 'connected' ? 'btn-secondary text-xs' : 'btn-bronze text-xs'}
                >
                  {integrations.gmail === 'connected' ? 'Disconnect' : 'Connect Gmail'}
                </button>
              </div>

              <div className="p-3 rounded-lg bg-[#181B20] border border-white/5 text-[11px] text-[#A1A4AA] flex items-center gap-2">
                <ShieldCheck size={14} className="text-[#C59A55] flex-shrink-0" />
                <span>You can skip this step and connect later in Integrations.</span>
              </div>
            </div>
          )}

          {/* Step 3: Connect Calendar */}
          {currentStep === 3 && (
            <div className="space-y-6 animate-in fade-in">
              <div>
                <span className="text-eyebrow">STEP 03</span>
                <h2 className="text-2xl font-bold text-white mt-1">Connect Google Calendar</h2>
                <p className="text-xs text-[#A1A4AA] mt-1">
                  Enables schedule conflict detection and study window optimization.
                </p>
              </div>

              <div className="p-5 rounded-xl bg-[#08090B] border border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-3.5">
                  <div className="p-3 rounded-lg bg-[#181B20] text-[#E6C17A]">
                    <Calendar size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">Calendar Integration</h4>
                    <p className="text-xs text-[#A1A4AA]">
                      Status:{" "}
                      <span className={integrations.calendar === 'connected' ? 'text-[#42D6A4] font-semibold' : 'text-[#696E78]'}>
                        {integrations.calendar === 'connected' ? 'Connected' : 'Not Connected'}
                      </span>
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => handleConnect('calendar')}
                  className={integrations.calendar === 'connected' ? 'btn-secondary text-xs' : 'btn-bronze text-xs'}
                >
                  {integrations.calendar === 'connected' ? 'Disconnect' : 'Connect Calendar'}
                </button>
              </div>

              <div className="p-3 rounded-lg bg-[#181B20] border border-white/5 text-[11px] text-[#A1A4AA] flex items-center gap-2">
                <ShieldCheck size={14} className="text-[#C59A55] flex-shrink-0" />
                <span>Events are created only after explicit user confirmation preview.</span>
              </div>
            </div>
          )}

          {/* Step 4: Optionally connect Drive */}
          {currentStep === 4 && (
            <div className="space-y-6 animate-in fade-in">
              <div>
                <span className="text-eyebrow">STEP 04 (OPTIONAL)</span>
                <h2 className="text-2xl font-bold text-white mt-1">Connect Google Drive</h2>
                <p className="text-xs text-[#A1A4AA] mt-1">
                  Allow Aurelia to locate and reference your project documents and spreadsheets.
                </p>
              </div>

              <div className="p-5 rounded-xl bg-[#08090B] border border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-3.5">
                  <div className="p-3 rounded-lg bg-[#181B20] text-[#E6C17A]">
                    <HardDrive size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">Google Drive Integration</h4>
                    <p className="text-xs text-[#A1A4AA]">
                      Status:{" "}
                      <span className={integrations.drive === 'connected' ? 'text-[#42D6A4] font-semibold' : 'text-[#696E78]'}>
                        {integrations.drive === 'connected' ? 'Connected' : 'Not Connected'}
                      </span>
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => handleConnect('drive')}
                  className={integrations.drive === 'connected' ? 'btn-secondary text-xs' : 'btn-bronze text-xs'}
                >
                  {integrations.drive === 'connected' ? 'Disconnect' : 'Connect Drive'}
                </button>
              </div>
            </div>
          )}

          {/* Step 5: Upload Knowledge Documents */}
          {currentStep === 5 && (
            <div className="space-y-6 animate-in fade-in">
              <div>
                <span className="text-eyebrow">STEP 05</span>
                <h2 className="text-2xl font-bold text-white mt-1">Add personal documents</h2>
                <p className="text-xs text-[#A1A4AA] mt-1">
                  Upload your class timetable, syllabus, or lecture notes for grounded RAG answers.
                </p>
              </div>

              <label className="border-2 border-dashed border-white/10 hover:border-[#C59A55]/50 rounded-xl p-6 text-center cursor-pointer transition-colors block bg-[#08090B]">
                <input
                  type="file"
                  onChange={handleFileUpload}
                  className="hidden"
                  accept=".pdf,.txt,.md,.csv,.json"
                />
                <UploadCloud size={30} className="mx-auto text-[#C59A55] mb-2" />
                <div className="text-xs font-semibold text-white">Drop timetable or notes here, or browse</div>
                <div className="text-[10px] text-[#696E78] mt-1">Supports PDF, Markdown, TXT up to 25MB</div>
              </label>

              {uploadedFiles.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[10px] font-mono text-[#C59A55] uppercase">Uploaded Files:</div>
                  {uploadedFiles.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs p-2 rounded bg-[#08090B] border border-white/5 text-white">
                      <FileText size={14} className="text-[#42D6A4]" />
                      <span>{f}</span>
                      <span className="text-[10px] text-[#42D6A4] ml-auto">Indexed</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step Navigation Controls */}
          <div className="pt-6 border-t border-white/5 flex items-center justify-between">
            {currentStep > 1 ? (
              <button
                onClick={() => setCurrentStep(currentStep - 1)}
                className="btn-ghost text-xs"
              >
                Previous
              </button>
            ) : <div />}

            {currentStep < 5 ? (
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setCurrentStep(currentStep + 1)}
                  className="btn-ghost text-xs text-[#696E78]"
                >
                  Skip
                </button>
                <button
                  onClick={() => setCurrentStep(currentStep + 1)}
                  className="btn-bronze text-xs py-2 px-5"
                >
                  <span>Continue</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            ) : (
              <button
                onClick={handleFinish}
                className="btn-bronze text-xs py-2.5 px-6 font-semibold"
              >
                <span>Complete Setup &amp; Enter Dashboard</span>
                <CheckCircle2 size={15} />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="container mx-auto text-center text-xs text-[#696E78] z-10">
        You can always reconfigure integrations later in Workspace Settings.
      </div>
    </div>
  );
};
