// js/admin.js

document.addEventListener('DOMContentLoaded', () => {
    loadUsers();
});

// Función para cargar usuarios guardados
function loadUsers() {
    const users = JSON.parse(localStorage.getItem('mb_users')) || [];
    const tableBody = document.getElementById('user-table-body');
    const totalCount = document.getElementById('total-users');
    
    tableBody.innerHTML = ''; // Limpiar tabla
    totalCount.textContent = users.length;

    users.forEach((user, index) => {
        const row = document.createElement('tr');
        
        // Estilo del estado
        const statusClass = user.status === 'Activo' ? 'status-active' : 'status-expired';

        row.innerHTML = `
            <td>#${index + 1}</td>
            <td>${user.username}</td>
            <td><span class="status-badge ${statusClass}">${user.status}</span></td>
            <td>${user.date}</td>
            <td>
                <button onclick="deleteUser(${index})" class="btn-delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

// Función para agregar un nuevo usuario
function addUser() {
    const usernameInput = document.getElementById('new-username');
    const passwordInput = document.getElementById('new-password');
    const statusInput = document.getElementById('new-status');

    if (usernameInput.value === '' || passwordInput.value === '') {
        alert('Por favor, ingresa usuario y contraseña.');
        return;
    }

    const newUser = {
        username: usernameInput.value,
        password: passwordInput.value, // En una app real, esto iría encriptado
        status: statusInput.value,
        date: new Date().toLocaleDateString()
    };

    // Obtener usuarios actuales, agregar el nuevo y guardar
    const users = JSON.parse(localStorage.getItem('mb_users')) || [];
    users.push(newUser);
    localStorage.setItem('mb_users', JSON.stringify(users));

    // Limpiar inputs y recargar tabla
    usernameInput.value = '';
    passwordInput.value = '';
    loadUsers();
}

// Función para eliminar usuario
function deleteUser(index) {
    if(confirm('¿Seguro que deseas eliminar a este miembro?')) {
        const users = JSON.parse(localStorage.getItem('mb_users')) || [];
        users.splice(index, 1);
        localStorage.setItem('mb_users', JSON.stringify(users));
        loadUsers();
    }
} 