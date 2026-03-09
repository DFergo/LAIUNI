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
