document.addEventListener('DOMContentLoaded', () => {
    const recordBtn = document.getElementById('record-btn');
    const recordBtnText = document.getElementById('record-btn-text');
    const langSelect = document.getElementById('language-select');
    const translatorStatus = document.getElementById('translator-status');
    const statusText = document.getElementById('status-text');
    const translatorResult = document.getElementById('translator-result');
    const resultAudio = document.getElementById('result-audio');
    const errorMessage = document.getElementById('error-message');

    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;

    // Check for MediaRecorder API
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        recordBtn.disabled = true;
        recordBtnText.textContent = 'Voice not supported';
        console.error('MediaDevices API or MediaRecorder not supported in this browser.');
        return;
    }

    recordBtn.addEventListener('click', async () => {
        if (isRecording) {
            // Stop recording
            mediaRecorder.stop();
            recordBtn.classList.remove('is-recording');
            recordBtnText.textContent = 'Start Recording';
            isRecording = false;
        } else {
            // Start recording
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                
                mediaRecorder.ondataavailable = (event) => {
                    audioChunks.push(event.data);
                };

                mediaRecorder.onstart = () => {
                    recordBtn.classList.add('is-recording');
                    recordBtnText.textContent = 'Stop Recording';
                    translatorResult.style.display = 'none';
                    errorMessage.textContent = '';
                    audioChunks = []; // Clear previous chunks
                    isRecording = true;
                };

                mediaRecorder.onstop = () => {
                    // Stop all mic tracks to turn off browser "recording" icon
                    stream.getTracks().forEach(track => track.stop());
                    
                    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                    sendAudioToServer(audioBlob);
                };

                mediaRecorder.start();

            } catch (err) {
                console.error('Error accessing microphone:', err);
                errorMessage.textContent = 'Could not access microphone. Please grant permission.';
                translatorResult.style.display = 'block';
            }
        }
    });

    async function sendAudioToServer(audioBlob) {
        const formData = new FormData();
        formData.append('audio_data', audioBlob, 'recording.wav');
        formData.append('language', langSelect.value);

        // Show loading spinner
        translatorStatus.style.display = 'flex';
        statusText.textContent = 'Processing... This may take up to a minute.';
        recordBtn.disabled = true;

        try {
            const response = await fetch('/translate_voice', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Server error: ${response.status}`);
            }

            // The response is the audio file itself
            const blob = await response.blob();
            const audioUrl = URL.createObjectURL(blob);
            
            resultAudio.src = audioUrl;
            translatorResult.style.display = 'block';
            errorMessage.textContent = '';

        } catch (error) {
            console.error('Error during translation:', error);
            errorMessage.textContent = `Translation failed: ${error.message}`;
            translatorResult.style.display = 'block';
            resultAudio.src = '';
        } finally {
            // Hide loading spinner
            translatorStatus.style.display = 'none';
            recordBtn.disabled = false;
        }
    }
});