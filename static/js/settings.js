document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element References for Modal ---
    const settingsBtn = document.getElementById('settings-btn');
    const modalOverlay = document.getElementById('settings-modal-overlay');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const settingsForm = document.getElementById('settings-form');
    const saveStatus = document.getElementById('settings-save-status');
    const saveButton = document.querySelector('.save-btn'); // Get the save button

    // --- Form Field References ---
    const formInputs = settingsForm.querySelectorAll('input, textarea, select');
    const personalitySelect = document.getElementById('luna-personality');
    const customInstructionsTextarea = document.getElementById('custom-instructions');
    const nicknameInput = document.getElementById('user-nickname');
    const occupationInput = document.getElementById('user-occupation');
    const interestsTextarea = document.getElementById('user-interests');

    const showSaveButton = () => {
        saveButton.classList.remove('hidden');
    };

    const hideSaveButton = () => {
        saveButton.classList.add('hidden');
    };

    const openModal = async () => {
        if (!modalOverlay) return;
        
        hideSaveButton(); // Hide save button when modal opens

        try {
            const response = await fetch('/get_settings');
            if (!response.ok) throw new Error('Could not fetch settings.');
            
            const settings = await response.json();
            
            personalitySelect.value = settings.personality || 'Default';
            customInstructionsTextarea.value = settings.custom_instructions || '';
            nicknameInput.value = settings.nickname || '';
            occupationInput.value = settings.occupation || '';
            interestsTextarea.value = settings.interests || '';

        } catch (error) {
            console.error('Error fetching settings:', error);
            saveStatus.textContent = 'Could not load settings.';
        }

        modalOverlay.classList.add('show');
    };

    const closeModal = () => {
        if (!modalOverlay) return;
        modalOverlay.classList.remove('show');
        saveStatus.textContent = '';
    };

    const handleSaveSettings = async (event) => {
        event.preventDefault();
        saveButton.disabled = true;
        saveStatus.textContent = 'Saving...';

        const settingsData = {
            personality: personalitySelect.value,
            custom_instructions: customInstructionsTextarea.value.trim(),
            nickname: nicknameInput.value.trim(),
            occupation: occupationInput.value.trim(),
            interests: interestsTextarea.value.trim()
        };

        try {
            const response = await fetch('/save_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settingsData)
            });

            if (!response.ok) throw new Error('Failed to save settings.');

            const result = await response.json();
            if (result.status === 'success') {
                saveStatus.textContent = 'Saved!';
                hideSaveButton();
                setTimeout(() => closeModal(), 1000);
            }
        } catch (error) {
            console.error('Error saving settings:', error);
            saveStatus.textContent = 'Error saving.';
        } finally {
             setTimeout(() => {
                saveButton.disabled = false;
                saveStatus.textContent = '';
            }, 2000);
        }
    };

    // --- Event Listeners ---
    if (settingsBtn) {
        settingsBtn.addEventListener('click', openModal);
    }
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', closeModal);
    }
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (event) => {
            if (event.target === modalOverlay) {
                closeModal();
            }
        });
    }
    if (settingsForm) {
        settingsForm.addEventListener('submit', handleSaveSettings);
    }

    // Listen for any input changes on the form fields to show the save button
    formInputs.forEach(input => {
        input.addEventListener('input', showSaveButton);
    });
});