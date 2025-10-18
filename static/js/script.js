document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element References ---
    const body = document.body;
    const sidebar = document.querySelector('.sidebar');
    const chatContainer = document.querySelector('.chat-container');
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const chatMessages = document.getElementById('chat-messages');
    const newChatBtn = document.getElementById('new-chat-btn');
    const chatHistoryList = document.getElementById('chat-history-list');
    const typingIndicator = document.getElementById('typing-indicator');
    const menuToggleBtn = document.getElementById('menu-toggle-btn');
    const attachBtn = document.getElementById('attach-btn');
    const fileUploadInput = document.getElementById('file-upload-input');
    const imagePreviewContainer = document.getElementById('image-preview-container');
    const imagePreview = document.getElementById('image-preview');
    const removeImageBtn = document.getElementById('remove-image-btn');

    let currentChatId = null;
    let attachedFile = null;

    // --- All Helper Functions ---
    const promptSuggestions = ["What are you working on?", "Ready when you are.", "What’s on the agenda today?", "Explain a complex topic simply.", "Let's brainstorm some ideas.", "Help me write a Python script.", "What's a fun fact you know?", "How can I be more productive?"];
    
    const setRandomPrompt = () => {
        const promptElement = document.getElementById('random-prompt');
        if (promptElement) {
            const randomIndex = Math.floor(Math.random() * promptSuggestions.length);
            promptElement.textContent = promptSuggestions[randomIndex];
        }
    };
    
    const updateChatTitleInBackground = async (chatId) => {
        try {
            const response = await fetch('/generate_title', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chat_id: chatId }) });
            if (!response.ok) return;
            const data = await response.json();
            if (data.success && data.title) {
                const chatItem = chatHistoryList.querySelector(`[data-chat-id="${chatId}"]`);
                if (chatItem) {
                    const titleSpan = chatItem.querySelector('.history-item-title');
                    if (titleSpan) titleSpan.textContent = data.title;
                }
            }
        } catch (error) { console.error('Error updating title in background:', error); }
    };

    const addCopyButtons = (messageElement) => {
        const codeBlocks = messageElement.querySelectorAll('pre');
        codeBlocks.forEach(codeBlock => {
            if (codeBlock.parentElement.classList.contains('code-block-wrapper')) return;
            const wrapper = document.createElement('div');
            wrapper.classList.add('code-block-wrapper');
            codeBlock.parentNode.insertBefore(wrapper, codeBlock);
            wrapper.appendChild(codeBlock);
            const copyButton = document.createElement('button');
            copyButton.classList.add('copy-code-btn');
            copyButton.innerHTML = `<svg><use href="#icon-copy"></use></svg> Copy`;
            copyButton.addEventListener('click', () => {
                const code = codeBlock.querySelector('code').innerText;
                navigator.clipboard.writeText(code);
                copyButton.innerHTML = `✓ Copied!`;
                copyButton.classList.add('copied');
                setTimeout(() => {
                    copyButton.innerHTML = `<svg><use href="#icon-copy"></use></svg> Copy`;
                    copyButton.classList.remove('copied');
                }, 2000);
            });
            wrapper.appendChild(copyButton);
        });
    };

    const addMessage = (sender, text, messageId, fileInfo = null) => {
        const lastMessage = document.querySelector('.latest-luna-message');
        if (lastMessage) lastMessage.classList.remove('latest-luna-message');

        const welcomeScreen = chatMessages.querySelector('.welcome-screen');
        if (welcomeScreen) chatMessages.innerHTML = '';
        
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', `${sender}-message`);
        if (messageId) messageElement.dataset.messageId = messageId;
        
        const avatar = document.createElement('div');
        avatar.classList.add('avatar');
        avatar.textContent = sender === 'user' ? 'You' : 'L';
        
        const messageContent = document.createElement('div');
        messageContent.classList.add('message-content');
        
        if (fileInfo) {
            if (fileInfo.type.startsWith('image/')) {
                const img = document.createElement('img');
                img.src = fileInfo.imageSrc;
                messageContent.appendChild(img);
            } else {
                const fileAttachment = document.createElement('div');
                fileAttachment.className = 'file-attachment';
                fileAttachment.innerHTML = `📄 <span>${fileInfo.filename}</span>`;
                messageContent.appendChild(fileAttachment);
            }
        }

        if (sender === 'luna') {
            const bubbleWrapper = document.createElement('div');
            bubbleWrapper.classList.add('bubble-wrapper');
            messageContent.innerHTML += marked.parse(text);
            bubbleWrapper.appendChild(messageContent);
            messageElement.append(avatar, bubbleWrapper);
        } else { // User message
            const p = document.createElement('p');
            p.textContent = text;
            messageContent.appendChild(p);
            const editBtn = document.createElement('button');
            editBtn.classList.add('edit-btn');
            editBtn.innerHTML = `<svg><use href="#icon-edit"></use></svg>`;
            messageElement.append(messageContent, avatar, editBtn);
        }
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return messageElement;
    };

    const sendMessage = async(event) => {
        if (event) event.preventDefault();
        const messageText = messageInput.value.trim();
        const userFile = attachedFile;
        if (!messageText && !userFile) return;

        const formData = new FormData();
        formData.append('message', messageText);
        if (currentChatId) formData.append('chat_id', currentChatId);
        if (userFile) formData.append('file', userFile, userFile.name);

        let fileDataForUI = null;
        if (userFile) {
            fileDataForUI = { filename: userFile.name, type: userFile.type };
            if (userFile.type.startsWith('image/')) {
                fileDataForUI.imageSrc = URL.createObjectURL(userFile);
            }
        }
        addMessage('user', messageText, 'temp-user-id', fileDataForUI);
        
        messageInput.value = '';
        messageInput.style.height = 'auto';
        attachedFile = null;
        imagePreviewContainer.style.display = 'none';
        imagePreview.src = '';
        const existingFileName = imagePreviewContainer.querySelector('span');
        if(existingFileName) existingFileName.remove();


        typingIndicator.style.display = 'flex';
        try {
            const response = await fetch('/chat', { method: 'POST', body: formData });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let lunaMessageElement = null;
            let fullResponse = "";
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const textChunk = decoder.decode(value);
                const lines = textChunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data:')) {
                        const jsonData = JSON.parse(line.substring(5));
                        if (jsonData.error) { addMessage('luna', `Error: ${jsonData.error}`, 'error-id'); return; }
                        if (jsonData.chat_id) {
                            currentChatId = jsonData.chat_id;
                            localStorage.setItem('activeChatId', currentChatId);
                            const userMsg = chatMessages.querySelector('[data-message-id="temp-user-id"]');
                            if (userMsg) userMsg.dataset.messageId = jsonData.user_message_id;
                        }
                        if (jsonData.chunk) {
                            fullResponse += jsonData.chunk;
                            if (!lunaMessageElement) {
                                lunaMessageElement = addMessage('luna', fullResponse, 'temp-luna-id');
                            } else {
                                const contentDiv = lunaMessageElement.querySelector('.message-content');
                                contentDiv.innerHTML = marked.parse(fullResponse + '▍');
                            }
                            chatMessages.scrollTop = chatMessages.scrollHeight;
                        }
                        if (jsonData.is_new_chat) {
                            await loadChatHistory();
                            setActiveChatItem(currentChatId);
                            updateChatTitleInBackground(currentChatId);
                        }
                    }
                }
            }
            if (lunaMessageElement) {
                const contentDiv = lunaMessageElement.querySelector('.message-content');
                contentDiv.innerHTML = marked.parse(fullResponse);
                addCopyButtons(contentDiv);
                if (!contentDiv.querySelector('pre')) {
                    const bubbleWrapper = lunaMessageElement.querySelector('.bubble-wrapper');
                    const actionsWrapper = document.createElement('div');
                    actionsWrapper.classList.add('message-actions');
                    const copyBtn = document.createElement('button');
                    copyBtn.classList.add('action-btn', 'copy-text-btn');
                    copyBtn.title = 'Copy message';
                    copyBtn.innerHTML = `<svg><use href="#icon-copy"></use></svg>`;
                    copyBtn.addEventListener('click', () => {
                        navigator.clipboard.writeText(contentDiv.innerText);
                        copyBtn.classList.add('copied');
                        setTimeout(() => { copyBtn.classList.remove('copied'); }, 2000);
                    });
                    actionsWrapper.appendChild(copyBtn);
                    bubbleWrapper.appendChild(actionsWrapper);
                }
                lunaMessageElement.classList.add('latest-luna-message');
                await loadChatHistory();
            }
        } catch (error) {
            addMessage('luna', 'Sorry, an error occurred.', 'error-id');
            console.error(error);
        } finally {
            typingIndicator.style.display = 'none';
        }
    };
    const saveEdit = async(messageElement, newText) => {
        const messageId = Number(messageElement.dataset.messageId);
        if (!newText.trim() || !messageId) return;
        typingIndicator.style.display = 'flex';
        try {
            let nextElement = messageElement.nextElementSibling;
            while (nextElement) {
                const toRemove = nextElement;
                nextElement = nextElement.nextElementSibling;
                toRemove.remove();
            }
            messageElement.querySelector('.message-content').innerHTML = `<p>${newText}</p>`;
            const response = await fetch('/edit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: currentChatId, message_id: messageId, new_text: newText }),
            });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let lunaMessageElement = null;
            let fullResponse = "";
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const textChunk = decoder.decode(value);
                const lines = textChunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data:')) {
                        const jsonData = JSON.parse(line.substring(5));
                        if (jsonData.error) { addMessage('luna', `Error: ${jsonData.error}`, 'error-id'); return; }
                        if (jsonData.chunk) {
                            fullResponse += jsonData.chunk;
                            if (!lunaMessageElement) {
                                lunaMessageElement = addMessage('luna', fullResponse, 'temp-luna-id');
                            } else {
                                const contentDiv = lunaMessageElement.querySelector('.message-content');
                                contentDiv.innerHTML = marked.parse(fullResponse + '▍');
                            }
                            chatMessages.scrollTop = chatMessages.scrollHeight;
                        }
                    }
                }
            }
            if (lunaMessageElement) {
                const contentDiv = lunaMessageElement.querySelector('.message-content');
                contentDiv.innerHTML = marked.parse(fullResponse);
                addCopyButtons(contentDiv);
                if (!contentDiv.querySelector('pre')) {
                    const bubbleWrapper = lunaMessageElement.querySelector('.bubble-wrapper');
                    const actionsWrapper = document.createElement('div');
                    actionsWrapper.classList.add('message-actions');
                    const copyBtn = document.createElement('button');
                    copyBtn.classList.add('action-btn', 'copy-text-btn');
                    copyBtn.title = 'Copy message';
                    copyBtn.innerHTML = `<svg><use href="#icon-copy"></use></svg>`;
                    copyBtn.addEventListener('click', () => {
                        navigator.clipboard.writeText(contentDiv.innerText);
                        copyBtn.classList.add('copied');
                        setTimeout(() => { copyBtn.classList.remove('copied'); }, 2000);
                    });
                    actionsWrapper.appendChild(copyBtn);
                    bubbleWrapper.appendChild(actionsWrapper);
                }
                lunaMessageElement.classList.add('latest-luna-message');
                await loadChatHistory();
            }
        } catch (error) {
            addMessage('luna', 'Sorry, an error occurred during edit.', 'error-id');
            console.error(error);
        } finally {
            typingIndicator.style.display = 'none';
        }
    };
    const loadSpecificChat = async(chatId) => {
        if (!chatId) return;
        if (currentChatId === chatId && chatMessages.children.length > 1) return;
        currentChatId = chatId;
        localStorage.setItem('activeChatId', chatId);
        try {
            const response = await fetch(`/get_chat/${chatId}`);
            const messages = await response.json();
            chatMessages.innerHTML = '';
            if (messages && messages.length > 0) {
                messages.forEach(msg => {
                    let fileInfo = msg.file || null;
                    if(fileInfo && msg.image) {
                        fileInfo.imageSrc = msg.image;
                    }
                    addMessage(msg.role === 'model' ? 'luna' : 'user', msg.parts[0], msg.id, fileInfo);
                });
                const allLunaMessages = chatMessages.querySelectorAll('.luna-message');
                if (allLunaMessages.length > 0) {
                    allLunaMessages[allLunaMessages.length - 1].classList.add('latest-luna-message');
                }
            } else {
                startNewChat(false);
            }
            setActiveChatItem(chatId);
        } catch (error) { console.error('Error loading chat:', error); }
    };
    const startNewChat = (resetId = true) => {
        if (resetId) {
            currentChatId = null;
            localStorage.removeItem('activeChatId');
        }
        chatMessages.innerHTML = `<div class="welcome-screen"><img src="/static/images/luna_logo.png" alt="LUNA Logo" class="welcome-logo"><h3><span class="acronym">L</span>ogical <span class="acronym">U</span>nderstanding and <span class="acronym">N</span>eural <span class="acronym">A</span>ssistance</h3><p>"Putting your needs <i>una</i>, one answer at a time."</p><p id="random-prompt" class="random-prompt"></p></div>`;
        setRandomPrompt();
        if (resetId) setActiveChatItem(null);
        messageInput.focus();
    };
    const loadChatHistory = async() => {
        try {
            const response = await fetch('/history');
            const chats = await response.json();
            chatHistoryList.innerHTML = '';
            chats.forEach(chat => {
                const li = document.createElement('li');
                li.classList.add('history-item');
                li.dataset.chatId = chat.id;
                if (chat.pinned) li.classList.add('is-pinned');
                const mainDiv = document.createElement('div');
                mainDiv.classList.add('history-item-main');
                const pinIndicator = document.createElement('div');
                pinIndicator.classList.add('pin-indicator');
                pinIndicator.innerHTML = `<svg><use href="#icon-pin"></use></svg>`;
                const titleSpan = document.createElement('span');
                titleSpan.classList.add('history-item-title');
                titleSpan.textContent = chat.title;
                mainDiv.append(pinIndicator, titleSpan);
                const controlsDiv = document.createElement('div');
                controlsDiv.classList.add('history-item-controls');
                const pinBtn = document.createElement('button');
                pinBtn.classList.add('pin-btn');
                if (chat.pinned) pinBtn.classList.add('pinned');
                pinBtn.innerHTML = `<svg><use href="#icon-pin"></use></svg>`;
                pinBtn.dataset.action = 'pin';
                const renameBtn = document.createElement('button');
                renameBtn.innerHTML = `<svg><use href="#icon-edit"></use></svg>`;
                renameBtn.dataset.action = 'rename';
                const deleteBtn = document.createElement('button');
                deleteBtn.innerHTML = `<svg><use href="#icon-delete"></use></svg>`;
                deleteBtn.dataset.action = 'delete';
                controlsDiv.append(pinBtn, renameBtn, deleteBtn);
                li.append(mainDiv, controlsDiv);
                chatHistoryList.appendChild(li);
            });
            setActiveChatItem(currentChatId);
        } catch (error) { console.error('Error loading chat history:', error); }
    };
    const handleRename = (item, titleSpan) => {
        const currentTitle = titleSpan.textContent;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = currentTitle;
        titleSpan.replaceWith(input);
        input.focus();
        const saveRename = async() => {
            const newTitle = input.value.trim();
            if (newTitle && newTitle !== currentTitle) {
                await fetch('/rename_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: item.dataset.chatId, new_title: newTitle }),
                });
                titleSpan.textContent = newTitle;
            } else {
                titleSpan.textContent = currentTitle;
            }
            input.replaceWith(titleSpan);
        };
        input.addEventListener('blur', saveRename);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') input.blur();
            if (e.key === 'Escape') { input.value = currentTitle; input.blur(); }
        });
    };
    const handleDelete = async(item) => {
        if (confirm(`Are you sure you want to delete this chat?`)) {
            const chatIdToDelete = item.dataset.chatId;
            await fetch('/delete_chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatIdToDelete }),
            });
            item.remove();
            if (currentChatId === chatIdToDelete) startNewChat(true);
        }
    };
    const handlePin = async(item, pinBtn) => {
        const isPinned = pinBtn.classList.contains('pinned');
        await fetch('/pin_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: item.dataset.chatId, pin_status: !isPinned }),
        });
        await loadChatHistory();
    };
    const setActiveChatItem = (chatId) => {
        const items = chatHistoryList.querySelectorAll('.history-item');
        items.forEach(item => {
            if (item.dataset.chatId === chatId) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    };
    const enterEditMode = (messageElement) => {
        const contentDiv = messageElement.querySelector('.message-content');
        const originalText = contentDiv.querySelector('p').textContent;
        contentDiv.innerHTML = `<div class="edit-area"><textarea>${originalText}</textarea><div class="edit-controls"><button class="save-btn">Save & Submit</button><button class="cancel-btn">Cancel</button></div></div>`;
        const textarea = contentDiv.querySelector('textarea');
        textarea.style.height = `${textarea.scrollHeight}px`;
        textarea.focus();
        contentDiv.querySelector('.save-btn').onclick = () => saveEdit(messageElement, textarea.value);
        contentDiv.querySelector('.cancel-btn').onclick = () => cancelEdit(messageElement, originalText);
    };
    const cancelEdit = (messageElement, originalText) => {
        const contentDiv = messageElement.querySelector('.message-content');
        contentDiv.innerHTML = `<p>${originalText}</p>`;
    };

    // --- All Event Listeners ---
    chatForm.addEventListener('submit', sendMessage);
    newChatBtn.addEventListener('click', () => startNewChat(true));
    messageInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
    chatHistoryList.addEventListener('click', (e) => {
        const item = e.target.closest('.history-item');
        if (!item) return;
        const actionBtn = e.target.closest('button');
        if (actionBtn) {
            const action = actionBtn.dataset.action;
            if (action === 'rename') handleRename(item, item.querySelector('.history-item-title'));
            else if (action === 'delete') handleDelete(item);
            else if (action === 'pin') handlePin(item, actionBtn);
        } else {
            loadSpecificChat(item.dataset.chatId);
        }
        if (window.innerWidth <= 768) {
            body.classList.remove('sidebar-open');
        }
    });
    chatMessages.addEventListener('click', (event) => {
        const editBtn = event.target.closest('.edit-btn');
        if (editBtn) enterEditMode(editBtn.closest('.message.user-message'));
    });
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = `${messageInput.scrollHeight}px`;
    });

    // --- Image Upload Listeners ---
    attachBtn.addEventListener('click', () => {
        fileUploadInput.click();
    });
    fileUploadInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (!file) return;
        
        attachedFile = file; // Store the file object
        
        // Clear previous preview
        const existingFileName = imagePreviewContainer.querySelector('span');
        if (existingFileName) existingFileName.remove();
        imagePreview.style.display = 'none';

        if (file.type.startsWith('image/')) {
            imagePreview.src = URL.createObjectURL(file);
            imagePreview.alt = file.name;
            imagePreview.style.display = 'block';
        } else {
            const fileNameSpan = document.createElement('span');
            fileNameSpan.textContent = `📄 ${file.name}`;
            imagePreviewContainer.appendChild(fileNameSpan);
        }
        imagePreviewContainer.style.display = 'flex';
        event.target.value = '';
    });
    removeImageBtn.addEventListener('click', () => {
        attachedFile = null;
        imagePreviewContainer.style.display = 'none';
        imagePreview.src = '';
        const existingFileName = imagePreviewContainer.querySelector('span');
        if (existingFileName) existingFileName.remove();
        fileUploadInput.value = '';
    });
menuToggleBtn.addEventListener('click', () => {
        body.classList.toggle('sidebar-open');
    });

    // --- Mobile Gesture Logic ---
    chatContainer.addEventListener('click', (event) => {
    if (menuToggleBtn.contains(event.target)) {
        return;
    }

    // If the sidebar is open, any other click in the chat container will close it.
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
        return; // Don't swipe if interacting with code blocks
    }

    startX = e.targetTouches[0].clientX;
    startY = e.targetTouches[0].clientY;
    isDragging = true;
    gestureDetermined = false; // Reset gesture direction on new touch

    // Get the current transform value only if the sidebar is already open
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
        // Determine if the swipe is mostly horizontal or vertical
        if (Math.abs(diffX) > Math.abs(diffY)) {
            gestureDetermined = 'horizontal';
            sidebar.classList.add('is-dragging'); // Disable CSS transitions during drag
        } else {
            // It's a vertical scroll, cancel the drag
            isDragging = false;
            return;
        }
    }

    if (gestureDetermined === 'horizontal') {
        // Prevent background from scrolling on mobile
        e.preventDefault();

        let newTranslate = currentTranslate + diffX;
        newTranslate = Math.max(-sidebarWidth, Math.min(0, newTranslate)); // Clamp the value
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
    sidebar.classList.remove('is-dragging'); // Re-enable transitions for smooth snap
    sidebar.style.transform = ''; // Let CSS classes take over

    const finalX = e.changedTouches[0].clientX;
    const swipeDistance = finalX - startX;
    const openThreshold = sidebarWidth / 3; // Must swipe 1/3 of the way to trigger

    // Determine whether to snap open or closed
    if (body.classList.contains('sidebar-open')) {
        // If it was open, a left swipe closes it
        if (swipeDistance < -openThreshold) {
            body.classList.remove('sidebar-open');
        }
    } else {
        // If it was closed, a right swipe opens it
        if (swipeDistance > openThreshold) {
            body.classList.add('sidebar-open');
        }
    }
});

    // --- Initial App Load ---
    const initializeApp = async () => {
        await loadChatHistory();
        const savedChatId = localStorage.getItem('activeChatId');
        if (savedChatId) {
            await loadSpecificChat(savedChatId);
        } else {
            setRandomPrompt();
        }
    };
    initializeApp();
});