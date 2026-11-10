import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { BrandLogo } from '../../components/BrandLogo';
import { api } from '../../services/api';
import { 
  Bot, 
  LayoutDashboard, 
  Mail, 
  Calendar, 
  FileText, 
  Layers, 
  Cpu, 
  Settings, 
  LogOut, 
  Search, 
  Bell, 
  ChevronRight, 
  Plus, 
  Menu, 
  X, 
  Command, 
  CheckCircle2, 
  Sparkles,
  ExternalLink
} from 'lucide-react';

export const DashboardShell = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const u = await api.getCurrentUser();
        setUser(u);
      } catch (e) {
        setUser({
          fullName: 'Alex Chen',
          email: 'alex.chen@university.edu',
          avatarUrl: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
          timezone: 'America/Los_Angeles'
        });
      }
    };
    fetchUser();

    // Listen for Cmd+K / Ctrl+K
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCmdOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setCmdOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleLogout = async () => {
    await api.logout();
    navigate('/');
  };

  const navItems = [
    { path: '/app', label: 'Overview', icon: LayoutDashboard },
    { path: '/app/chat', label: 'AI Assistant', icon: Bot, badge: 'Agent' },
    { path: '/app/inbox', label: 'Inbox', icon: Mail },
    { path: '/app/calendar', label: 'Calendar', icon: Calendar },
    { path: '/app/knowledge', label: 'Knowledge Base', icon: FileText },
    { path: '/app/plans', label: 'Plans', icon: Layers },
    { path: '/app/integrations', label: 'Integrations', icon: Cpu },
    { path: '/app/settings', label: 'Settings', icon: Settings },
  ];

  const getPageTitle = () => {
    const item = navItems.find((n) => n.path === location.pathname);
    return item ? item.label : 'Aurelia Workspace';
  };

  const handleCommandSelect = (path) => {
    setCmdOpen(false);
    navigate(path);
  };

  return (
    <div className="min-h-screen bg-[#08090B] text-[#F5F3EE] flex overflow-hidden">
      {/* Desktop Collapsible Sidebar */}
      <aside
        className={`hidden md:flex flex-col justify-between border-r border-white/5 bg-[#0D0F12] transition-all duration-300 z-30 ${
          collapsed ? 'w-20' : 'w-64'
        }`}
      >
        {/* Brand & Toggle */}
        <div className="p-4 border-b border-white/5 flex items-center justify-between">
          <div
            onClick={() => navigate('/app')}
            className="cursor-pointer overflow-hidden"
          >
            <BrandLogo size="sm" showText={!collapsed} />
          </div>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1 rounded text-[#696E78] hover:text-white hover:bg-white/5 transition-colors"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <Command size={14} />
          </button>
        </div>

        {/* Navigation list */}
        <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                title={collapsed ? item.label : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-[#181B20] text-white border border-[#C59A55]/30 shadow-sm shadow-[#C59A55]/10'
                    : 'text-[#A1A4AA] hover:text-white hover:bg-white/5'
                }`}
              >
                <Icon size={16} className={isActive ? 'text-[#C59A55]' : 'text-[#696E78]'} />
                {!collapsed && (
                  <span className="flex-1 text-left">{item.label}</span>
                )}
                {!collapsed && item.badge && (
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#C59A55]/15 text-[#E6C17A] border border-[#C59A55]/25">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* User profile bottom */}
        <div className="p-3 border-t border-white/5">
          <div className="flex items-center justify-between p-2 rounded-lg bg-[#121418] border border-white/5">
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="w-8 h-8 rounded-full bg-[#181B20] border border-[#C59A55]/40 flex items-center justify-center flex-shrink-0 text-[#E6C17A] font-semibold text-xs">
                {user?.fullName?.charAt(0) || 'A'}
              </div>
              {!collapsed && (
                <div className="overflow-hidden">
                  <div className="text-xs font-semibold text-white truncate">
                    {user?.fullName || 'Alex Chen'}
                  </div>
                  <div className="text-[10px] text-[#696E78] font-mono truncate">
                    {user?.email || 'alex.chen@university.edu'}
                  </div>
                </div>
              )}
            </div>

            {!collapsed && (
              <button
                onClick={handleLogout}
                className="text-[#696E78] hover:text-[#F07878] p-1 rounded transition-colors"
                title="Sign out"
              >
                <LogOut size={15} />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Header Bar */}
        <header className="h-16 border-b border-white/5 bg-[#0D0F12]/80 backdrop-blur-md px-6 flex items-center justify-between z-20">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileOpen(true)}
              className="md:hidden p-1.5 rounded bg-[#181B20] text-white"
            >
              <Menu size={18} />
            </button>
            <h1 className="text-sm font-semibold tracking-wide text-white">
              {getPageTitle()}
            </h1>
          </div>

          {/* Quick command & Status */}
          <div className="flex items-center gap-4">
            {/* Command palette search trigger */}
            <button
              onClick={() => setCmdOpen(true)}
              className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#121418] border border-white/10 text-xs text-[#696E78] hover:text-white hover:border-white/20 transition-all"
            >
              <Search size={13} />
              <span>Search or run command...</span>
              <kbd className="font-mono text-[10px] bg-black/40 px-1.5 py-0.5 rounded border border-white/10">
                ⌘K
              </kbd>
            </button>

            {/* Connection Health Indicator */}
            <div className="hidden lg:flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#121418] border border-white/5 text-[11px] font-mono text-[#A1A4AA]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#42D6A4] animate-pulse" />
              <span>SYSTEM ONLINE</span>
            </div>

            {/* Notifications placeholder */}
            <button
              onClick={() => navigate('/app/inbox')}
              className="p-2 rounded-lg bg-[#121418] border border-white/5 text-[#A1A4AA] hover:text-white transition-colors relative"
              title="Notifications & Priorities"
            >
              <Bell size={15} />
              <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-[#C59A55]" />
            </button>
          </div>
        </header>

        {/* Page Content Outlet */}
        <main className="flex-1 overflow-y-auto bg-[#08090B]">
          <Outlet />
        </main>
      </div>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <div className="relative w-64 bg-[#0D0F12] border-r border-white/10 p-4 flex flex-col justify-between z-10 animate-in slide-in-from-left duration-200">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-white/5">
                <BrandLogo size="sm" />
                <button
                  onClick={() => setMobileOpen(false)}
                  className="p-1 text-[#696E78] hover:text-white"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="mt-4 space-y-1">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path;
                  return (
                    <button
                      key={item.path}
                      onClick={() => {
                        setMobileOpen(false);
                        navigate(item.path);
                      }}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium ${
                        isActive
                          ? 'bg-[#181B20] text-white border border-[#C59A55]/30'
                          : 'text-[#A1A4AA] hover:bg-white/5'
                      }`}
                    >
                      <Icon size={16} className={isActive ? 'text-[#C59A55]' : 'text-[#696E78]'} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="pt-4 border-t border-white/5 flex items-center justify-between">
              <span className="text-xs text-[#A1A4AA]">{user?.fullName || 'User'}</span>
              <button onClick={handleLogout} className="text-[#F07878] text-xs">
                Log out
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Command Palette Modal (Cmd+K) */}
      {cmdOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setCmdOpen(false)}
          />
          <div className="relative max-w-lg w-full bg-[#121418] border border-white/15 rounded-xl shadow-2xl p-4 z-10 animate-in fade-in zoom-in-95 duration-150 space-y-3">
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#08090B] border border-white/10">
              <Search size={15} className="text-[#C59A55]" />
              <input
                type="text"
                autoFocus
                placeholder="Type a command or jump to page..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-transparent text-xs text-white focus:outline-none"
              />
              <kbd className="text-[10px] font-mono text-[#696E78] bg-[#181B20] px-1.5 py-0.5 rounded">
                ESC
              </kbd>
            </div>

            <div className="space-y-1 max-h-60 overflow-y-auto">
              <div className="text-[10px] font-mono text-[#696E78] uppercase px-2 py-1">
                Navigation
              </div>
              {navItems
                .filter((item) => item.label.toLowerCase().includes(searchQuery.toLowerCase()))
                .map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.path}
                      onClick={() => handleCommandSelect(item.path)}
                      className="w-full flex items-center justify-between p-2 rounded-lg text-xs text-[#A1A4AA] hover:text-white hover:bg-[#181B20] transition-colors text-left"
                    >
                      <div className="flex items-center gap-2">
                        <Icon size={14} className="text-[#C59A55]" />
                        <span>Go to {item.label}</span>
                      </div>
                      <ChevronRight size={13} className="text-[#696E78]" />
                    </button>
                  );
                })}

              <div className="text-[10px] font-mono text-[#696E78] uppercase px-2 py-1 pt-2">
                Quick Actions
              </div>
              <button
                onClick={() => handleCommandSelect('/app/chat')}
                className="w-full flex items-center justify-between p-2 rounded-lg text-xs text-[#A1A4AA] hover:text-white hover:bg-[#181B20] transition-colors text-left"
              >
                <div className="flex items-center gap-2">
                  <Sparkles size={14} className="text-[#E6C17A]" />
                  <span>Ask: "Summarize my day"</span>
                </div>
                <span className="text-[10px] font-mono text-[#696E78]">Agent</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
