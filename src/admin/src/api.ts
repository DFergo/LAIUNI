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

export async function listPrompts(): Promise<PromptsResponse> {
  return request('/admin/prompts');
}

export async function readPrompt(name: string): Promise<{ name: string; content: string }> {
  return request(`/admin/prompts/${name}`);
}

export async function savePrompt(name: string, content: string): Promise<PromptFile> {
  return request(`/admin/prompts/${name}`, {
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
  status: string
  flagged: boolean
  created_at: string | null
  last_activity: string | null
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

// --- RAG API ---

export interface RAGDocument {
  name: string
  size: number
  modified: number
}

export async function listRAGDocuments(): Promise<{ documents: RAGDocument[] }> {
  return request('/admin/rag/documents');
}

export async function uploadRAGDocument(file: File): Promise<{ name: string; size: number }> {
  const token = localStorage.getItem('hrdd_admin_token');
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/admin/rag/upload', {
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

export async function deleteRAGDocument(name: string): Promise<void> {
  return request(`/admin/rag/documents/${name}`, { method: 'DELETE' });
}

export async function reindexRAG(): Promise<{ status: string; document_count: number; node_count?: number }> {
  return request('/admin/rag/reindex', { method: 'POST' });
}

// --- SMTP API ---

export interface SMTPConfig {
  host: string
  port: number
  username: string
  password: string
  use_tls: boolean
  from_address: string
  admin_notify_address: string
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
