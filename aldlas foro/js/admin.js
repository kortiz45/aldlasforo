const AdminApi = (() => {
    const state = {
        baseUrl: '',
        csrfToken: '',
    };

    function resolveBaseUrl() {
        const configuredBase = (localStorage.getItem('mb_api_base_url') || '').trim().replace(/\/$/, '');
        state.baseUrl = configuredBase || window.location.origin;
    }

    async function ensureSession() {
        const response = await fetch(`${state.baseUrl}/api/auth/session`, {
            method: 'GET',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Csrf-Token': state.csrfToken || '',
            },
        });
        const data = await response.json();
        if (!response.ok || !data?.authenticated) {
            throw new Error(data?.detail || 'Sesión admin no válida');
        }
        state.csrfToken = String(data.csrf_token || '');
    }

    async function adminFetch(path, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'X-Admin-Csrf-Token': state.csrfToken || '',
            ...(options.headers || {}),
        };
        const response = await fetch(`${state.baseUrl}${path}`, {
            ...options,
            credentials: 'include',
            headers,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data?.detail || 'Error en API de administración');
        }
        if (data?.csrf_token) {
            state.csrfToken = String(data.csrf_token);
        }
        return data;
    }

    async function loadUsers() {
        const tableBody = document.getElementById('user-table-body');
        const totalCount = document.getElementById('total-users') || document.getElementById('total-count');

        if (!tableBody) {
            return;
        }

        const data = await adminFetch('/api/admin/users', { method: 'GET' });
        const users = Array.isArray(data?.users) ? data.users : [];
        tableBody.innerHTML = '';
        if (totalCount) {
            totalCount.textContent = String(users.length);
        }

        users.forEach((user, index) => {
            const row = document.createElement('tr');
            const status = String(user?.status || 'Activo');
            const statusClass = status.toLowerCase() === 'vencido' ? 'status-expired' : 'status-active';
            row.innerHTML = `
                <td>#${index + 1}</td>
                <td>${String(user?.username || '')}</td>
                <td><span class="status-badge ${statusClass}">${status}</span></td>
                <td>${String(user?.createdAt || '').slice(0, 10)}</td>
                <td>
                    <button data-username="${String(user?.username || '')}" class="btn-delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            `;
            const btn = row.querySelector('button[data-username]');
            if (btn) {
                btn.addEventListener('click', async () => {
                    const username = btn.getAttribute('data-username') || '';
                    await deleteUser(username);
                });
            }
            tableBody.appendChild(row);
        });
    }

    async function addUser() {
        const usernameInput = document.getElementById('new-username');
        const passwordInput = document.getElementById('new-password');
        const statusInput = document.getElementById('new-status');

        const username = String(usernameInput?.value || '').trim();
        const password = String(passwordInput?.value || '').trim();
        const status = String(statusInput?.value || 'Activo').trim();

        if (!username || !password) {
            alert('Por favor, ingresa usuario y contraseña.');
            return;
        }

        await adminFetch('/api/admin/users', {
            method: 'POST',
            body: JSON.stringify({ username, password, status }),
        });

        if (usernameInput) usernameInput.value = '';
        if (passwordInput) passwordInput.value = '';
        await loadUsers();
    }

    async function deleteUser(username) {
        if (!username) return;
        if (!confirm('¿Seguro que deseas eliminar a este miembro?')) {
            return;
        }
        await adminFetch(`/api/admin/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
        await loadUsers();
    }

    async function init() {
        resolveBaseUrl();
        await ensureSession();
        await loadUsers();
    }

    return {
        init,
        loadUsers,
        addUser,
        deleteUser,
    };
})();

async function loadUsers() {
    try {
        await AdminApi.loadUsers();
    } catch (error) {
        console.error(error);
    }
}

async function addUser() {
    try {
        await AdminApi.addUser();
    } catch (error) {
        alert(error?.message || 'No se pudo crear el usuario');
    }
}

async function deleteUser(username) {
    try {
        await AdminApi.deleteUser(username);
    } catch (error) {
        alert(error?.message || 'No se pudo eliminar el usuario');
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    try {
        await AdminApi.init();
    } catch (error) {
        console.error(error);
    }
});