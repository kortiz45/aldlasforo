const AuthApi = (() => {
	const state = {
		baseUrl: '',
		adminCsrfToken: '',
		userCsrfToken: '',
	};

	function resolveBaseUrl() {
		const configuredBase = (localStorage.getItem('mb_api_base_url') || '').trim().replace(/\/$/, '');
		state.baseUrl = configuredBase || window.location.origin;
	}

	async function request(path, { method = 'GET', body = null, csrfType = null } = {}) {
		const headers = {
			'Content-Type': 'application/json',
		};

		if (csrfType === 'admin') {
			headers['X-Admin-Csrf-Token'] = state.adminCsrfToken || '';
		}
		if (csrfType === 'user') {
			headers['X-User-Csrf-Token'] = state.userCsrfToken || '';
		}

		const response = await fetch(`${state.baseUrl}${path}`, {
			method,
			credentials: 'include',
			headers,
			body: body ? JSON.stringify(body) : null,
		});

		const data = await response.json().catch(() => ({}));
		if (!response.ok) {
			throw new Error(data?.detail || 'Error de autenticación');
		}
		if (typeof data?.csrf_token === 'string' && data.csrf_token) {
			if (csrfType === 'admin' || path.includes('/auth/admin') || path === '/api/auth/session') {
				state.adminCsrfToken = data.csrf_token;
			} else {
				state.userCsrfToken = data.csrf_token;
			}
		}
		return data;
	}

	async function loginAdmin(username, password) {
		return request('/api/auth/admin/login', {
			method: 'POST',
			body: { username, password },
			csrfType: 'admin',
		});
	}

	async function logoutAdmin() {
		return request('/api/auth/logout', { method: 'POST', csrfType: 'admin' });
	}

	async function getAdminSession() {
		return request('/api/auth/session', { method: 'GET', csrfType: 'admin' });
	}

	async function registerUser(username, password, deviceId = '', bindDevice = true) {
		return request('/api/auth/user/register', {
			method: 'POST',
			body: {
				username,
				password,
				device_id: deviceId,
				bind_device: !!bindDevice,
			},
			csrfType: 'user',
		});
	}

	async function loginUser(username, password, deviceId = '', bindDevice = true) {
		return request('/api/auth/user/login', {
			method: 'POST',
			body: {
				username,
				password,
				device_id: deviceId,
				bind_device: !!bindDevice,
			},
			csrfType: 'user',
		});
	}

	async function logoutUser() {
		return request('/api/auth/user/logout', { method: 'POST', csrfType: 'user' });
	}

	async function getUserSession() {
		return request('/api/auth/user/session', { method: 'GET', csrfType: 'user' });
	}

	resolveBaseUrl();

	return {
		loginAdmin,
		logoutAdmin,
		getAdminSession,
		registerUser,
		loginUser,
		logoutUser,
		getUserSession,
		setBaseUrl(baseUrl) {
			state.baseUrl = String(baseUrl || '').trim().replace(/\/$/, '') || window.location.origin;
		},
		setAdminCsrfToken(token) {
			state.adminCsrfToken = String(token || '').trim();
		},
		setUserCsrfToken(token) {
			state.userCsrfToken = String(token || '').trim();
		},
	};
})();

window.AuthApi = AuthApi;