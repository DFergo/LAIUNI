const API_BASE = '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('hrdd_admin_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function getAdminStatus(): Promise<{ setup_complete: boolean }> {
  return request('/admin/status');
}

export async function setupAdmin(password: string, confirmPassword: string): Promise<{ message: string }> {
  return request('/admin/setup', {
    method: 'POST',
    body: JSON.stringify({ password, confirm_password: confirmPassword }),
  });
}

export async function loginAdmin(password: string, rememberMe: boolean): Promise<{ token: string; expires_in: number }> {
  return request('/admin/login', {
    method: 'POST',
    body: JSON.stringify({ password, remember_me: rememberMe }),
  });
}

export async function verifyToken(): Promise<{ valid: boolean }> {
  return request('/admin/verify');
}

// --- Frontends API ---

export interface Frontend {
  id: string
  url: string
  frontend_type: string
  name: string
  enabled: boolean
  status: string
  last_seen: string | null
  created_at: string
}

export async function listFrontends(): Promise<{ frontends: Frontend[] }> {
  return request('/admin/frontends');
}

export async function registerFrontend(url: string, name: string = ''): Promise<{ frontend: Frontend }> {
  return request('/admin/frontends', {
    method: 'POST',
    body: JSON.stringify({ url, name }),
  });
}

export async function updateFrontend(id: string, data: { enabled?: boolean; name?: string }): Promise<{ frontend: Frontend }> {
  return request(`/admin/frontends/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function removeFrontend(id: string): Promise<void> {
  return request(`/admin/frontends/${id}`, { method: 'DELETE' });
}

// --- LLM API ---

export interface LLMHealth {
  lm_studio: { status: string; models: string[]; error?: string }
  ollama: { status: string; models: string[]; error?: string }
}

export interface LLMSettings {
  inference_provider: string
  inference_model: string
  inference_temperature: number
  inference_max_tokens: number
  inference_num_ctx: number
  summariser_enabled: boolean
  summariser_provider: string
  summariser_model: string
  summariser_temperature: number
  summariser_max_tokens: number
  summariser_num_ctx: number
  compression_threshold: number
  compression_first_threshold: number
  compression_step_size: number
}

export async function getLLMHealth(): Promise<LLMHealth> {
  return request('/admin/llm/health');
}

export async function getLLMModels(): Promise<LLMHealth> {
  return request('/admin/llm/models');
}

export async function getLLMSettings(): Promise<LLMSettings> {
  return request('/admin/llm/settings');
}

export async function updateLLMSettings(data: Partial<LLMSettings>): Promise<LLMSettings> {
  return request('/admin/llm/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function resetLLMSettings(): Promise<LLMSettings> {
  return request('/admin/llm/settings/reset', { method: 'POST' });
}

// --- Prompts API ---

export interface PromptFile {
  name: string
  size: number
  modified: number | null
}

export interface PromptsResponse {
  categories: Record<string, PromptFile[]>
}

export async function getPromptMode(): Promise<{ mode: string }> {
  return request('/admin/prompts/mode');
}

export async function setPromptMode(mode: string): Promise<{ mode: string }> {
  return request('/admin/prompts/mode', {
    method: 'PUT',
    body: JSON.stringify({ mode }),
  });
}

export async function copyPromptsToFrontend(frontendId: string): Promise<{ frontend_id: string; copied: number }> {
  return request(`/admin/prompts/copy-to-frontend/${frontendId}`, { method: 'POST' });
}

export async function deleteFrontendPrompts(frontendId: string): Promise<{ frontend_id: string; deleted: number }> {
  return request(`/admin/prompts/frontend/${frontendId}`, { method: 'DELETE' });
}

export async function listPrompts(frontendId?: string): Promise<PromptsResponse> {
  const qs = frontendId ? `?frontend_id=${frontendId}` : '';
  return request(`/admin/prompts${qs}`);
}

export async function readPrompt(name: string, frontendId?: string): Promise<{ name: string; content: string }> {
  const qs = frontendId ? `?frontend_id=${frontendId}` : '';
  return request(`/admin/prompts/${name}${qs}`);
}

export async function savePrompt(name: string, content: string, frontendId?: string): Promise<PromptFile> {
  const qs = frontendId ? `?frontend_id=${frontendId}` : '';
  return request(`/admin/prompts/${name}${qs}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

// --- Sessions API ---

export interface SessionSummary {
  token: string
  message_count: number
  role: string
  mode: string
  company: string
  frontend_name: string
  status: string
  flagged: boolean
  created_at: string | null
  last_activity: string | null
  docs?: Record<string, boolean>
}

export interface SessionDetail {
  token: string
  survey: Record<string, unknown>
  messages: { role: string; content: string; timestamp?: string }[]
  system_prompt: string
  flagged: boolean
  status: string
  language: string
  created_at: string | null
  last_activity: string | null
}

export async function listSessions(): Promise<{ sessions: SessionSummary[] }> {
  return request('/admin/sessions');
}

export async function getSession(token: string): Promise<SessionDetail> {
  return request(`/admin/sessions/${token}`);
}

export async function toggleSessionFlag(token: string): Promise<{ token: string; flagged: boolean }> {
  return request(`/admin/sessions/${token}/flag`, { method: 'PUT' });
}

export interface SessionDocuments {
  token: string
  documents: Record<string, string | null>
}

export async function getSessionDocuments(token: string): Promise<SessionDocuments> {
  return request(`/admin/sessions/${token}/documents`);
}

export async function generateDocument(token: string, docType: string): Promise<{ token: string; doc_type: string; content: string }> {
  return request(`/admin/sessions/${token}/generate/${docType}`, { method: 'POST' });
}

// --- Lifecycle API ---

export interface LifecycleConfig {
  auto_close_enabled: boolean
  auto_close_hours: number
  auto_cleanup_enabled: boolean
  auto_cleanup_days: number
}

export async function getLifecycleSettings(): Promise<{ settings: Record<string, LifecycleConfig>; defaults: LifecycleConfig }> {
  return request('/admin/sessions/lifecycle');
}

export async function updateLifecycleSettings(frontendId: string, config: LifecycleConfig): Promise<{ frontend_id: string; config: LifecycleConfig }> {
  return request(`/admin/sessions/lifecycle/${frontendId}`, {
    method: 'PUT',
    body: JSON.stringify(config),
  });
}

// --- RAG API ---

export interface RAGDocument {
  name: string
  size: number
  modified: number
}

export async function listRAGDocuments(frontendId?: string): Promise<{ documents: RAGDocument[] }> {
  const qs = frontendId ? `?frontend_id=${frontendId}` : '';
  return request(`/admin/rag/documents${qs}`);
}

export async function uploadRAGDocument(file: File, frontendId?: string): Promise<{ name: string; size: number }> {
  const token = localStorage.getItem('hrdd_admin_token');
  const formData = new FormData();
  formData.append('file', file);
  const qs = frontendId ? `?frontend_id=${frontendId}` : '';
  const res = await fetch(`/admin/rag/upload${qs}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function deleteRAGDocument(name: string, frontendId?: string): Promise<void> {
  const qs = frontendId ? `?frontend_id=${frontendId}` : '';
  return request(`/admin/rag/documents/${name}${qs}`, { method: 'DELETE' });
}

export async function reindexRAG(frontendId?: string): Promise<{ status: string; document_count: number; node_count?: number }> {
  const qs = frontendId ? `?frontend_id=${frontendId}` : '';
  return request(`/admin/rag/reindex${qs}`, { method: 'POST' });
}

export async function getCampaignRAGConfig(frontendId: string): Promise<{ include_global_rag: boolean }> {
  return request(`/admin/rag/campaign/${frontendId}/config`);
}

export async function updateCampaignRAGConfig(frontendId: string, includeGlobal: boolean): Promise<{ include_global_rag: boolean }> {
  return request(`/admin/rag/campaign/${frontendId}/config`, {
    method: 'PUT',
    body: JSON.stringify({ include_global_rag: includeGlobal }),
  });
}

// --- SMTP API ---

export interface SMTPConfig {
  host: string
  port: number
  username: string
  password: string
  use_tls: boolean
  from_address: string
  notification_emails: string[]
  notify_on_report: boolean
  send_summary_to_user: boolean
  send_report_to_user: boolean
}

export async function getSMTPConfig(): Promise<SMTPConfig> {
  return request('/admin/smtp');
}

export async function updateSMTPConfig(data: Partial<SMTPConfig>): Promise<SMTPConfig> {
  return request('/admin/smtp', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function testSMTP(): Promise<{ status: string; message: string }> {
  return request('/admin/smtp/test', { method: 'POST' });
}

export async function getAuthorizedEmails(): Promise<{ emails: string[] }> {
  return request('/admin/smtp/authorized-emails');
}

export async function updateAuthorizedEmails(emails: string[]): Promise<{ emails: string[] }> {
  return request('/admin/smtp/authorized-emails', {
    method: 'PUT',
    body: JSON.stringify({ emails }),
  });
}

export async function getFrontendNotificationEmails(frontendId: string): Promise<{ emails: string[] }> {
  return request(`/admin/smtp/frontend-notifications/${frontendId}`);
}

// --- Branding API ---

export interface BrandingConfig {
  app_title: string
  logo_url: string
  disclaimer_text: string
  instructions_text: string
}

export async function getFrontendBranding(frontendId: string): Promise<BrandingConfig> {
  return request(`/admin/frontends/${frontendId}/branding`);
}

export async function updateFrontendBranding(frontendId: string, data: BrandingConfig): Promise<BrandingConfig> {
  return request(`/admin/frontends/${frontendId}/branding`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateFrontendNotificationEmails(frontendId: string, emails: string[]): Promise<{ emails: string[] }> {
  return request(`/admin/smtp/frontend-notifications/${frontendId}`, {
    method: 'PUT',
    body: JSON.stringify({ emails }),
  });
}

// --- Knowledge Base API ---

export interface GlossaryTerm {
  term: string
  definition?: string
  translations?: Record<string, string>
}

export interface Organization {
  name: string
  type: string
  country: string
  description?: string
}

export async function getGlossary(): Promise<{ terms: GlossaryTerm[] }> {
  return request('/admin/knowledge/glossary');
}

export async function updateGlossary(terms: GlossaryTerm[]): Promise<{ terms: GlossaryTerm[] }> {
  return request('/admin/knowledge/glossary', {
    method: 'PUT',
    body: JSON.stringify({ terms }),
  });
}

export async function getOrganizations(): Promise<{ organizations: Organization[] }> {
  return request('/admin/knowledge/organizations');
}

export async function updateOrganizations(organizations: Organization[]): Promise<{ organizations: Organization[] }> {
  return request('/admin/knowledge/organizations', {
    method: 'PUT',
    body: JSON.stringify({ organizations }),
  });
}
