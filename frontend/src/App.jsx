import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LandingPage } from './features/landing/LandingPage';
import { AuthPage } from './features/auth/AuthPage';
import { AuthCallback } from './features/auth/AuthCallback';
import { OnboardingPage } from './features/onboarding/OnboardingPage';
import { DashboardShell } from './features/dashboard/DashboardShell';
import { DashboardOverview } from './features/dashboard/DashboardOverview';
import { ChatPage } from './features/chat/ChatPage';
import { InboxPage } from './features/inbox/InboxPage';
import { CalendarPage } from './features/calendar/CalendarPage';
import { KnowledgePage } from './features/knowledge/KnowledgePage';
import { PlansPage } from './features/plans/PlansPage';
import { IntegrationsPage } from './features/integrations/IntegrationsPage';
import { SettingsPage } from './features/settings/SettingsPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Landing Page */}
        <Route path="/" element={<LandingPage />} />

        {/* Authentication & Onboarding */}
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/onboarding" element={<OnboardingPage />} />

        {/* Authenticated Dashboard Shell */}
        <Route path="/app" element={<DashboardShell />}>
          <Route index element={<DashboardOverview />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="inbox" element={<InboxPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="plans" element={<PlansPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
