// API Service client for connecting to FastAPI backend (JavaScript)

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

// Safe storage access that never crashes in SSR, incognito, or restricted browser contexts
const safeStorage = {
  getItem: (key) => {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        return window.localStorage.getItem(key);
      }
    } catch (e) {
      return null;
    }
    return null;
  },
  setItem: (key, value) => {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(key, value);
      }
    } catch (e) {}
  },
  removeItem: (key) => {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.removeItem(key);
      }
    } catch (e) {}
  }
};

class ApiService {
  constructor() {
    this.token = safeStorage.getItem('aurelia_auth_token');
  }

  setToken(token) {
    this.token = token;
    if (token) {
      safeStorage.setItem('aurelia_auth_token', token);
    } else {
      safeStorage.removeItem('aurelia_auth_token');
    }
  }

  getToken() {
    let t = this.token || safeStorage.getItem('aurelia_auth_token');
    if (!t && (import.meta.env.DEV || import.meta.env.MODE === 'development')) {
      t = 'mock_jwt_token_aurelia_dev';
    }
    return t;
  }

  getHeaders(contentType = 'application/json') {
    const headers = {};
    if (contentType) {
      headers['Content-Type'] = contentType;
    }
    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  async handleResponse(response) {
    if (!response.ok) {
      let errorMsg = `Request failed with status ${response.status}`;
      try {
        const errorData = await response.json();
        errorMsg = errorData.detail || errorData.message || errorMsg;
      } catch (e) {
        errorMsg = response.statusText || errorMsg;
      }
      throw new Error(errorMsg);
    }
    return response.json();
  }

  /**
   * Resilient HTTP request helper.
   * Prioritizes the local Vite dev proxy (`/api/...`) to eliminate CORS preflight overhead
   * and Windows IPv6/IPv4 address resolution mismatches. Gracefully falls back to direct
   * backend URLs (127.0.0.1:8000 and localhost:8000) if needed.
   */
  async request(endpoint, options = {}) {
    let path = endpoint;
    if (path.startsWith('http://') || path.startsWith('https://')) {
      try {
        const u = new URL(path);
        path = u.pathname + u.search;
      } catch (e) {}
    }
    if (!path.startsWith('/')) {
      path = '/' + path;
    }
    if (!path.startsWith('/api')) {
      path = '/api' + path;
    }

    const candidateEndpoints = [
      path,
      `http://127.0.0.1:8000${path}`,
      `http://localhost:8000${path}`
    ];

    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
    const defaultHeaders = this.getHeaders(isFormData ? null : 'application/json');
    const finalHeaders = {
      ...defaultHeaders,
      ...(options.headers || {})
    };

    const finalOptions = {
      ...options,
      headers: finalHeaders
    };

    let lastError = null;
    for (const ep of candidateEndpoints) {
      try {
        const res = await fetch(ep, finalOptions);
        return await this.handleResponse(res);
      } catch (err) {
        if (err.name === 'AbortError') {
          throw err;
        }
        lastError = err;
      }
    }

    throw new Error('Unable to connect to Aurelia backend server. Please verify the backend is running on port 8000.');
  }

  async fetchWithFallback(urlOrPath, options = {}) {
    return this.request(urlOrPath, options);
  }

  // --- Auth & User ---
  async getCurrentUser() {
    try {
      return await this.request('/auth/me');
    } catch (err) {
      const local = safeStorage.getItem('aurelia_user');
      if (local) {
        try {
          return JSON.parse(local);
        } catch (e) {}
      }
      throw err;
    }
  }

  async devLogin(email = 'alex.chen@university.edu', name = 'Alex Chen') {
    try {
      const data = await this.request('/auth/dev-login', {
        method: 'POST',
        body: JSON.stringify({ email, fullName: name })
      });
      this.setToken(data.token);
      safeStorage.setItem('aurelia_user', JSON.stringify(data.user));
      return data;
    } catch (e) {
      // Local fallback for offline/preview
      const mockUser = {
        id: 'usr_dev_01',
        email,
        fullName: name,
        avatarUrl: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Los_Angeles',
        createdAt: new Date().toISOString(),
        onboardingComplete: true
      };
      const token = 'mock_jwt_token_aurelia_dev';
      this.setToken(token);
      safeStorage.setItem('aurelia_user', JSON.stringify(mockUser));
      return { user: mockUser, token };
    }
  }

  async logout() {
    try {
      await this.request('/auth/logout', { method: 'POST' });
    } catch (e) {
      // ignore
    } finally {
      this.setToken(null);
      safeStorage.removeItem('aurelia_user');
    }
  }

  getGoogleOAuthUrl(scopeCategory = 'identity') {
    return `${API_BASE_URL}/auth/google/start?scope_category=${scopeCategory}&purpose=login`;
  }

  getGoogleConnectUrl(scopeCategory = 'gmail') {
    const token = this.getToken();
    return `${API_BASE_URL}/auth/google/start?scope_category=${scopeCategory}&purpose=link&auth_token=${encodeURIComponent(token || '')}`;
  }

  // --- Dashboard ---
  async getDashboardOverview() {
    return this.request('/dashboard/overview');
  }

  // --- Chat ---
  async sendMessage(message, conversationId, options = {}) {
    return this.request('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversationId }),
      ...options
    });
  }

  async getConversations() {
    return this.request('/conversations');
  }

  async getConversation(conversationId) {
    return this.request(`/conversations/${conversationId}`);
  }

  // --- Gmail ---
  async getGmailMessages(filter = 'all') {
    return this.request(`/gmail/messages?filter=${filter}`);
  }

  async summarizeThread(messageId) {
    return this.request('/gmail/summarize', {
      method: 'POST',
      body: JSON.stringify({ messageId })
    });
  }

  async createEmailDraft(to, subject, body) {
    return this.request('/gmail/draft', {
      method: 'POST',
      body: JSON.stringify({ to, subject, body })
    });
  }

  async confirmSendEmail(confirmationToken) {
    return this.request('/gmail/confirm-send', {
      method: 'POST',
      body: JSON.stringify({ confirmationToken })
    });
  }

  // --- Calendar ---
  async getCalendarEvents(timeMin, timeMax) {
    const params = new URLSearchParams();
    if (timeMin) params.append('timeMin', timeMin);
    if (timeMax) params.append('timeMax', timeMax);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this.request(`/calendar/events${qs}`);
  }

  async previewCalendarEvent(naturalLanguageQuery) {
    return this.request('/calendar/events/preview', {
      method: 'POST',
      body: JSON.stringify({ query: naturalLanguageQuery })
    });
  }

  async confirmCalendarEvent(confirmationToken, eventDetails, actionId = null) {
    const payload = { confirmationToken, event: eventDetails };
    if (actionId) {
      payload.actionId = actionId;
    }
    return this.request('/calendar/events/confirm', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async deleteCalendarEvent(eventId) {
    return this.request(`/calendar/events/${eventId}`, {
      method: 'DELETE'
    });
  }

  // --- Google Drive ---
  async getDriveFiles(query = '', pageSize = 20) {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    params.append('pageSize', pageSize);
    return this.request(`/drive/files?${params.toString()}`);
  }

  async getDriveFileContent(fileId) {
    return this.request(`/drive/files/${fileId}/content`);
  }

  // --- Knowledge Base ---
  async getDocuments() {
    return this.request('/knowledge/documents');
  }

  async uploadDocument(file, category = 'general', documentType = null) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    if (documentType) {
      formData.append('document_type', documentType);
    }

    return this.request('/knowledge/upload', {
      method: 'POST',
      body: formData
    });
  }

  async getDocumentPreview(documentId) {
    return this.request(`/knowledge/documents/${documentId}/preview`);
  }

  async confirmDocument(documentId, data = {}) {
    return this.request(`/knowledge/documents/${documentId}/confirm`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async retryDocumentExtraction(documentId) {
    return this.request(`/knowledge/documents/${documentId}/retry`, {
      method: 'POST'
    });
  }

  async getAcademicEvents(params = {}) {
    const searchParams = new URLSearchParams();
    if (params.category) searchParams.append('category', params.category);
    if (params.query) searchParams.append('query', params.query);
    if (params.month) searchParams.append('month', params.month);
    const qs = searchParams.toString();
    return this.request(`/knowledge/academic-events${qs ? '?' + qs : ''}`);
  }

  async queryKnowledge(query) {
    return this.request('/knowledge/query', {
      method: 'POST',
      body: JSON.stringify({ query })
    });
  }

  async deleteDocument(documentId) {
    return this.request(`/knowledge/documents/${documentId}`, {
      method: 'DELETE'
    });
  }

  // --- Plans ---
  async getPlans() {
    return this.request('/plans');
  }

  async getPlan(planId) {
    return this.request(`/plans/${planId}`);
  }

  async getPlanRoadmap(planId) {
    return this.request(`/plans/${planId}/roadmap`);
  }

  async generatePlanRoadmap(planId, options = {}) {
    return this.request(`/plans/${planId}/generate-roadmap`, {
      method: 'POST',
      body: JSON.stringify(options)
    });
  }

  async createPlan(plan) {
    return this.request('/plans', {
      method: 'POST',
      body: JSON.stringify(plan)
    });
  }

  async generateProposal(proposalData) {
    return this.request('/plans/generate-proposal', {
      method: 'POST',
      body: JSON.stringify(proposalData)
    });
  }

  async updatePlan(planId, updates) {
    return this.request(`/plans/${planId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates)
    });
  }

  async deletePlan(planId, options = {}) {
    const params = new URLSearchParams();
    if (options.deleteGoogleEvents) {
      params.append('delete_google_events', 'true');
    }
    const q = params.toString() ? `?${params.toString()}` : '';
    return this.request(`/plans/${planId}${q}`, {
      method: 'DELETE'
    });
  }

  async reconcileOrphans() {
    return this.request('/plans/reconcile-orphans', {
      method: 'POST'
    });
  }

  async getTimetables() {
    return this.request('/knowledge/timetables');
  }

  // --- Manual Timetable Management ---
  async getTimetable() {
    return this.request('/timetable');
  }

  async getTimetableById(id) {
    return this.request(`/timetable/${id}`);
  }

  async createTimetable(data) {
    return this.request('/timetable', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async updateTimetable(id, data) {
    return this.request(`/timetable/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async deleteTimetable(id) {
    return this.request(`/timetable/${id}`, {
      method: 'DELETE'
    });
  }

  async addPeriod(timetableId, periodData) {
    return this.request(`/timetable/${timetableId}/periods`, {
      method: 'POST',
      body: JSON.stringify(periodData)
    });
  }

  async updatePeriod(timetableId, periodId, periodData) {
    return this.request(`/timetable/${timetableId}/periods/${periodId}`, {
      method: 'PUT',
      body: JSON.stringify(periodData)
    });
  }

  async deletePeriod(timetableId, periodId) {
    return this.request(`/timetable/${timetableId}/periods/${periodId}`, {
      method: 'DELETE'
    });
  }

  async addTaskToPlan(planId, taskData) {
    return this.request(`/plans/${planId}/tasks`, {
      method: 'POST',
      body: JSON.stringify(taskData)
    });
  }

  async updatePlanTask(planId, taskId, updates) {
    return this.request(`/plans/${planId}/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates)
    });
  }

  async deletePlanTask(planId, taskId) {
    return this.request(`/plans/${planId}/tasks/${taskId}`, {
      method: 'DELETE'
    });
  }

  async proposeStudySlots(planId, options = {}) {
    let url = `/plans/${planId}/propose-slots`;
    const params = new URLSearchParams();
    if (options.month) params.append('month', options.month);
    if (options.week) params.append('week', options.week);
    const qs = params.toString();
    if (qs) url += `?${qs}`;

    return this.request(url, {
      method: 'POST',
      body: JSON.stringify(options)
    });
  }

  async applyStudySlots(planId, studyBlocks, replace = false) {
    return this.request(`/plans/${planId}/apply-slots`, {
      method: 'POST',
      body: JSON.stringify({ studyBlocks, replace })
    });
  }

  async syncPlanToCalendar(planId, studyBlocks, selectedBlockIds = null) {
    return this.request(`/plans/${planId}/sync-calendar`, {
      method: 'POST',
      body: JSON.stringify({
        studyBlocks,
        selectedBlockIds: selectedBlockIds || studyBlocks.map(b => b.id)
      })
    });
  }

  // --- Integrations ---
  async getIntegrations() {
    return this.request('/integrations');
  }

  async disconnectIntegration(provider) {
    return this.request(`/integrations/${provider}/disconnect`, {
      method: 'POST'
    });
  }

  // --- Capabilities ---
  async getCapabilities(provider) {
    const data = await this.request('/integrations');
    const item = data.find(d => d.provider === provider);
    return item ? { capabilities: item.capabilities, supportedCapabilities: item.supportedCapabilities } : null;
  }

  async updateCapabilities(provider, capabilities) {
    return this.request(`/integrations/${provider}/capabilities`, {
      method: 'PATCH',
      body: JSON.stringify({ capabilities })
    });
  }

  // --- Settings & Account ---
  async getSettings() {
    return this.request('/settings');
  }

  async updateSettings(settings) {
    return this.request('/settings', {
      method: 'PATCH',
      body: JSON.stringify(settings)
    });
  }

  async purgeChatHistory() {
    return this.request('/chat/history', {
      method: 'DELETE'
    });
  }

  async deleteAccount() {
    return this.request('/settings/account', {
      method: 'DELETE'
    });
  }
}

export const api = new ApiService();
