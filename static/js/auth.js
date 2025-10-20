document.addEventListener('DOMContentLoaded', () => {
    const auth = firebase.auth();
    const notificationElement = document.getElementById('notification');

    // --- START: New Password Toggle Logic ---
    const passwordInput = document.getElementById('password');
    const togglePasswordButton = document.querySelector('.toggle-password');

    if (passwordInput && togglePasswordButton) {
        const eyeIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>`;
        const eyeSlashIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>`;
        
        togglePasswordButton.innerHTML = eyeIcon;

        togglePasswordButton.addEventListener('click', () => {
            const isPassword = passwordInput.type === 'password';
            passwordInput.type = isPassword ? 'text' : 'password';
            togglePasswordButton.innerHTML = isPassword ? eyeSlashIcon : eyeIcon;
        });
    }
    // --- END: New Password Toggle Logic ---

    const showNotification = (message, type) => {
        const icon = type === 'success' ? '✓' : '✗';
        notificationElement.className = `notification ${type}`;
        notificationElement.innerHTML = `<span class="icon">${icon}</span> ${message}`;
        notificationElement.style.display = 'flex';
    };

    const handleAuthError = (error) => {
        console.error("Firebase Auth Error:", error);
        switch (error.code) {
            case 'auth/invalid-credential':
            case 'auth/user-not-found':
            case 'auth/wrong-password':
                return 'Invalid email or password. Please try again.';
            case 'auth/email-already-in-use':
                return 'This email address is already in use by another account.';
            case 'auth/weak-password':
                return 'The password is too weak. It must be at least 6 characters long.';
            case 'auth/invalid-email':
                return 'Please enter a valid email address.';
            default:
                return 'An unexpected error occurred. Please try again later.';
        }
    };

    // Handle Login
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const submitButton = loginForm.querySelector('button');
            submitButton.disabled = true;
            submitButton.textContent = 'Logging In...';

            const email = loginForm.email.value;
            const password = loginForm.password.value;

            auth.signInWithEmailAndPassword(email, password)
                .then(userCredential => userCredential.user.getIdToken())
                .then(idToken => fetch('/session_login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idToken })
                }))
                .then(response => {
                    if (response.ok) {
                        showNotification('Login successful! Redirecting...', 'success');
                        setTimeout(() => window.location.assign('/'), 1500);
                    } else {
                        throw new Error('Server login failed.');
                    }
                })
                .catch(error => {
                    if (error.code) {
                        const friendlyMessage = handleAuthError(error);
                        showNotification(friendlyMessage, 'error');
                    } else {
                        console.error("Network/Server Error:", error);
                        showNotification('Could not connect to the server.', 'error');
                    }
                    submitButton.disabled = false;
                    submitButton.textContent = 'Login';
                });
        });
    }

    // Handle Signup
    const signupForm = document.getElementById('signup-form');
    if (signupForm) {
        signupForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const submitButton = signupForm.querySelector('button');
            submitButton.disabled = true;
            submitButton.textContent = 'Signing Up...';

            const email = signupForm.email.value;
            const password = signupForm.password.value;

            auth.createUserWithEmailAndPassword(email, password)
                .then(userCredential => userCredential.user.getIdToken())
                .then(idToken => fetch('/session_login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idToken })
                }))
                .then(response => {
                    if (response.ok) {
                        showNotification('Account created! Redirecting...', 'success');
                        setTimeout(() => window.location.assign('/'), 1500);
                    } else {
                        throw new Error('Server session creation failed.');
                    }
                })
                .catch(error => {
                    if (error.code) {
                        const friendlyMessage = handleAuthError(error);
                        showNotification(friendlyMessage, 'error');
                    } else {
                        console.error("Network/Server Error:", error);
                        showNotification('Could not connect to the server.', 'error');
                    }
                    submitButton.disabled = false;
                    submitButton.textContent = 'Sign Up';
                });
        });
    }
});