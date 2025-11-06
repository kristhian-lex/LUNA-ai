// This file contains shared JavaScript for index.html and translator.html

document.addEventListener('DOMContentLoaded', () => {
    // --- Shared DOM Elements ---
    const body = document.body;
    const sidebar = document.querySelector('.sidebar');
    const chatContainer = document.querySelector('.chat-container');
    const chatHistoryList = document.getElementById('chat-history-list');
    const menuToggleBtn = document.getElementById('menu-toggle-btn');
    const profileBtn = document.getElementById('profile-btn');
    const profileDropdown = document.getElementById('profile-dropdown');

    // --- Profile Dropdown Logic ---
    if (profileBtn) {
        profileBtn.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent click from bubbling up to the window
            profileDropdown.classList.toggle('show');
        });
    }

    // Close the dropdown if the user clicks outside of it
    window.addEventListener('click', (event) => {
        if (profileDropdown && profileDropdown.classList.contains('show')) {
            if (!profileBtn.contains(event.target)) {
                profileDropdown.classList.remove('show');
            }
        }
    });

    // --- Mobile Menu Toggle ---
    if (menuToggleBtn) {
        menuToggleBtn.addEventListener('click', () => {
            body.classList.toggle('sidebar-open');
        });
    }

    // --- Mobile Gesture Logic ---
    if (chatContainer) {
        chatContainer.addEventListener('click', (event) => {
            if (menuToggleBtn && menuToggleBtn.contains(event.target)) {
                return;
            }
            if (body.classList.contains('sidebar-open')) {
                body.classList.remove('sidebar-open');
            }
        });

        let isDragging = false;
        let startX = 0;
        let startY = 0;
        let currentTranslate = 0;
        let gestureDetermined = false;
        const sidebarWidth = 260;

        body.addEventListener('touchstart', (e) => {
            const target = e.target;
            if (target.closest('pre') || target.closest('code')) {
                isDragging = false;
                return;
            }
            startX = e.targetTouches[0].clientX;
            startY = e.targetTouches[0].clientY;
            isDragging = true;
            gestureDetermined = false;
            if (body.classList.contains('sidebar-open')) {
                const style = window.getComputedStyle(sidebar);
                const matrix = new DOMMatrixReadOnly(style.transform);
                currentTranslate = matrix.m41;
            } else {
                currentTranslate = -sidebarWidth;
            }
        }, { passive: true });

        body.addEventListener('touchmove', (e) => {
            if (!isDragging) return;
            const currentX = e.targetTouches[0].clientX;
            const currentY = e.targetTouches[0].clientY;
            const diffX = currentX - startX;
            const diffY = currentY - startY;

            if (!gestureDetermined) {
                if (Math.abs(diffX) > Math.abs(diffY)) {
                    gestureDetermined = 'horizontal';
                    sidebar.classList.add('is-dragging');
                } else {
                    isDragging = false;
                    return;
                }
            }
            if (gestureDetermined === 'horizontal') {
                e.preventDefault();
                let newTranslate = currentTranslate + diffX;
                newTranslate = Math.max(-sidebarWidth, Math.min(0, newTranslate));
                sidebar.style.transform = `translateX(${newTranslate}px)`;
            }
        });

        body.addEventListener('touchend', (e) => {
            if (!isDragging || gestureDetermined !== 'horizontal') {
                isDragging = false;
                return;
            }
            isDragging = false;
            gestureDetermined = false;
            sidebar.classList.remove('is-dragging');
            sidebar.style.transform = '';
            const finalX = e.changedTouches[0].clientX;
            const swipeDistance = finalX - startX;
            const openThreshold = sidebarWidth / 3;
            if (body.classList.contains('sidebar-open')) {
                if (swipeDistance < -openThreshold) {
                    body.classList.remove('sidebar-open');
                }
            } else {
                if (swipeDistance > openThreshold) {
                    body.classList.add('sidebar-open');
                }
            }
        });
    }

    // --- Shared Chat History Loading (for sidebar) ---
    // (This block is a bit complex, you can copy from script.js if needed)
    const loadChatHistory = async () => {
        try {
            const response = await fetch('/history');
            const chats = await response.json();
            chatHistoryList.innerHTML = '';
            chats.forEach(chat => {
                const li = document.createElement('li');
                li.classList.add('history-item');
                li.dataset.chatId = chat.id;
                if (chat.pinned) li.classList.add('is-pinned');
                
                li.innerHTML = `
                    <div class="history-item-main">
                        <div class="pin-indicator"><svg><use href="#icon-pin"></use></svg></div>
                        <span class="history-item-title">${chat.title}</span>
                    </div>
                    <div class="history-item-controls">
                        <button class="pin-btn ${chat.pinned ? 'pinned' : ''}" data-action="pin"><svg><use href="#icon-pin"></use></svg></button>
                        <button data-action="rename"><svg><use href="#icon-edit"></use></svg></button>
                        <button data-action="delete"><svg><use href="#icon-delete"></use></svg></button>
                    </div>
                `;
                chatHistoryList.appendChild(li);
            });
        } catch (error) {
            console.error('Error loading chat history:', error);
        }
    };
    
    // Load history on any page that has the list
    if (chatHistoryList) {
        loadChatHistory();
        
        // Add click listener ONLY for navigation, not the full chat logic
        chatHistoryList.addEventListener('click', (e) => {
            const item = e.target.closest('.history-item');
            if (!item) return;
            const actionBtn = e.target.closest('button');
            
            if (actionBtn) {
                 // The main script.js handles the actions, but we can load history again
                 // In a real app, you'd use a shared event system
                 console.log("Action button clicked, logic handled by script.js");
            } else {
                // Navigate to the main chat page and load that chat
                window.location.href = `/?chat=${item.dataset.chatId}`;
            }
            if (window.innerWidth <= 768) {
                body.classList.remove('sidebar-open');
            }
        });
    }
});