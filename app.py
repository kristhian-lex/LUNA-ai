import os
import uuid
import time
import json
import base64
import io
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import firebase_admin
from firebase_admin import credentials, db, auth
from dotenv import load_dotenv
from PIL import Image
import PyPDF2
import docx
from functools import wraps
import torch
import gc
import whisper
from transformers import pipeline
from TTS.api import TTS
from flask import send_file
import torch.serialization
import sys
import librosa
import soundfile
import warnings
from gtts import gTTS

# --- Suppress Specific Warnings ---
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="whisper")

# --- ADD PYTORCH 2.6+ SECURITY FIX HERE ---
try:
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
    from TTS.config.shared_configs import BaseDatasetConfig
    
    torch.serialization.add_safe_globals([
        XttsConfig, 
        XttsAudioConfig, 
        BaseDatasetConfig,
        XttsArgs
    ])
    print("Successfully added TTS classes to torch safe globals.", file=sys.stderr)

except ImportError:
    print("Could not import TTS classes. Make sure the TTS library is installed.", file=sys.stderr)
except Exception as e:
    print(f"Error adding TTS classes to torch safe globals: {e}", file=sys.stderr)
# --- END OF FIX ---


# --- Initialization ---
load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24) 

cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred, {'databaseURL': os.getenv('FIREBASE_DATABASE_URL')})

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- LUNA's Base System Instruction ---
LUNA_BASE_PERSONALITY = "You are LUNA, which stands for Logical Understanding and Neural Assistance. You are a helpful and friendly AI assistant. When asked your name, you must say you are LUNA."

# --- Authentication Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def extract_text_from_pdf(file_stream):
    pdf_reader = PyPDF2.PdfReader(file_stream)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def extract_text_from_docx(file_stream):
    doc = docx.Document(file_stream)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def format_history_for_api(history):
    clean_history = []
    for msg in history:
        if msg.get('parts') and msg.get('parts')[0]:
            role = 'user' if msg['role'] == 'user' else 'model'
            parts = [part for part in msg.get('parts', []) if part]
            if parts:
                clean_history.append({'role': role, 'parts': parts})
    return clean_history

def get_chat_title(history):
    context = "\n".join([f"{msg['role']}: {msg['parts'][0]}" for msg in history[:2] if msg.get('parts')])
    prompt = f"Analyze this conversation start:\n---\n{context}\n---\nGenerate a concise, formal, Title Case title for this chat, 5 words or less. Respond only with the title."
    try:
        text_model = genai.GenerativeModel('gemini-pro-latest', system_instruction=LUNA_BASE_PERSONALITY)
        response = text_model.generate_content(prompt)
        title = response.text.strip().strip('"')
        return title if title else "New Chat"
    except Exception:
        return (history[0]['parts'][0][:30] + '...') if history and history[0].get('parts') else "Chat"
    
    # --- VRAM & AI Helper Functions ---

def clear_vram():
    """Manually clears VRAM by deleting models and running garbage collection."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

# --- LOW VRAM OPTIMIZATION ---
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# Use the 'small' model for better accuracy now that we're on GPU
WHISPER_MODEL_SIZE = "small"
# -----------------------------

def translate_and_clone_voice(audio_input_path, audio_output_path, target_lang):
    """
    Hybrid System:
    - Uses XTTS (Voice Cloning) for supported languages.
    - Uses gTTS (Google Translate Voice) for Tagalog/Hindi/Unsupported languages.
    """
    
    print(f"--- Using device: {DEVICE} ---", flush=True)

    # --- Step 1: Transcribe Audio with Whisper ---
    original_text = ""
    source_lang = ""
    try:
        print(f"[1/4] Loading Whisper model ('{WHISPER_MODEL_SIZE}')...", flush=True)
        whisper_model = whisper.load_model(WHISPER_MODEL_SIZE, device=DEVICE)
        
        print(f"[1/4] Transcribing audio: {audio_input_path}...", flush=True)
        transcribe_start = time.time()
        transcription_result = whisper_model.transcribe(audio_input_path)
        original_text = transcription_result["text"]
        source_lang = transcription_result["language"]
        transcribe_end = time.time()
        print(f"[1/4] Original Text ({source_lang}): {original_text} (Time: {transcribe_end - transcribe_start:.2f}s)", flush=True)

    except Exception as e:
        print(f"Error during Whisper transcription: {e}", flush=True)
        return None
    finally:
        if 'whisper_model' in locals():
            del whisper_model
            clear_vram()
            print("[VRAM Cleared] Unloaded Whisper model.", flush=True)
            
    if not original_text.strip():
        print("Error: No speech detected in the audio.", flush=True)
        return None

    # --- Step 2: Translate Text with Meta NLLB ---
    translated_text = ""
    try:
        print(f"[2/4] Loading Translation model (NLLB)...", flush=True)
        
        # --- MAP YOUR HTML VALUES TO NLLB CODES HERE ---
        FLORES_CODES = {
            # Standard & Your HTML Values
            "en": "eng_Latn", 
            "es": "spa_Latn", 
            "fr": "fra_Latn", 
            "de": "deu_Latn",
            "ko": "kor_Hang",
            "ru": "rus_Cyrl",
            "zh": "zho_Hans",    # Your HTML 'zh'
            "zh-CN": "zho_Hans", # Standard
            "jap": "jpn_Jpan",   # Your HTML 'jap' -> Japanese
            "ja": "jpn_Jpan",    # Standard
            "it": "ita_Latn",    # Italian
            "pt": "por_Latn",    # Portuguese
            "ar": "arb_Arab",    # Arabic
            "hi": "hin_Deva",    # Hindi
            "tl": "tgl_Latn",    # Tagalog
            "Tagalog": "tgl_Latn"
        }

        # Check source lang (Whisper usually returns standard codes like 'ja', 'en')
        # We might need to map whisper 'ja' to Flores 'ja' (which exists above)
        if source_lang == "ja": source_lang = "ja" # direct map
        
        if source_lang not in FLORES_CODES:
            # Fallback for common mismatches
            if source_lang == "jw": source_lang = "en" # Whisper sometimes mistakes silence for Javanese, default to En
            elif source_lang not in FLORES_CODES:
                 raise Exception(f"Unsupported source language for translation: {source_lang}")
        
        if target_lang not in FLORES_CODES:
            raise Exception(f"Unsupported target language for translation: {target_lang}")

        src_code = FLORES_CODES[source_lang]
        tgt_code = FLORES_CODES[target_lang]

        translator = pipeline("translation", model="facebook/nllb-200-distilled-600M", device=0 if DEVICE == "cuda" else -1)

        print(f"[2/4] Translating text from '{src_code}' to '{tgt_code}'...", flush=True)
        translate_start = time.time()
        
        translated_text_list = translator(original_text, src_lang=src_code, tgt_lang=tgt_code, max_length=1024)
        translated_text = translated_text_list[0]['translation_text']
        translate_end = time.time()
        print(f"[2/4] Translated Text ({target_lang}): {translated_text} (Time: {translate_end - translate_start:.2f}s)", flush=True)
        
    except Exception as e:
        print(f"Error: Could not translate text. {e}", flush=True)
        return None
    finally:
        if 'translator' in locals():
            del translator
            clear_vram()
            print("[VRAM Cleared] Unloaded Translation model.", flush=True)

    # --- Step 3: Synthesis (Hybrid: XTTS vs gTTS) ---
    try:
        # Languages supported by Coqui XTTS v2 for Voice Cloning
        # We need to map your HTML codes (jap, zh) to XTTS codes (ja, zh-cn)
        XTTS_MAP = {
            "en": "en", "es": "es", "fr": "fr", "de": "de", 
            "it": "it", "pt": "pt", "pl": "pl", "tr": "tr", 
            "ru": "ru", "nl": "nl", "cs": "cs", "ar": "ar", 
            "hu": "hu", "ko": "ko",
            "zh": "zh-cn", "zh-cn": "zh-cn", # Map 'zh' to 'zh-cn'
            "jap": "ja", "ja": "ja"          # Map 'jap' to 'ja'
        }
        
        # Determine the code to use for XTTS
        xtts_lang_code = XTTS_MAP.get(target_lang)

        if xtts_lang_code:
            # --- USE XTTS (VOICE CLONING) ---
            print(f"[3/4] Language '{target_lang}' (mapped to '{xtts_lang_code}') supported by XTTS. Cloning user voice...", flush=True)
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=(DEVICE == "cuda"))
            
            tts_start = time.time()
            tts.tts_to_file(
                text=translated_text,
                speaker_wav=audio_input_path,
                language=xtts_lang_code, 
                file_path=audio_output_path,
                temperature=0.65, top_k=50, top_p=0.85
            )
            tts_end = time.time()
            
            del tts
            clear_vram()
            print(f"[3/4] XTTS Synthesis complete. (Time: {tts_end - tts_start:.2f}s)", flush=True)

        else:
            # --- USE GOOGLE TTS (FALLBACK) ---
            # Used for: Hindi (hi), Tagalog (tl), etc.
            print(f"[3/4] Language '{target_lang}' NOT supported by XTTS. Using Google TTS...", flush=True)
            
            tts_start = time.time()
            # Map HTML codes to gTTS codes if needed
            gtts_lang = target_lang
            if target_lang == "Tagalog": gtts_lang = "tl"
            
            tts_google = gTTS(text=translated_text, lang=gtts_lang)
            tts_google.save(audio_output_path)
            
            tts_end = time.time()
            print(f"[3/4] Google TTS Synthesis complete. (Time: {tts_end - tts_start:.2f}s)", flush=True)

    except Exception as e:
        print(f"Error during Speech Synthesis: {e}", flush=True)
        return None

    # --- Step 4: Return Output Path ---
    print(f"[4/4] Process finished. Output file saved to: {audio_output_path}", flush=True)
    return audio_output_path

# --- Auth Routes ---
@app.route("/login")
def login():
    return render_template('login.html')

@app.route("/signup")
def signup():
    return render_template('signup.html')

@app.route("/session_login", methods=['POST'])
def session_login():
    try:
        id_token = request.json['idToken']
        decoded_token = auth.verify_id_token(id_token)
        session['user_id'] = decoded_token['uid']
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"!!! FIREBASE AUTH VERIFICATION ERROR: {repr(e)}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 401

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))


# --- NEW SETTINGS ROUTES ---
@app.route("/get_settings", methods=['GET'])
@login_required
def get_settings():
    user_id = session['user_id']
    settings_ref = db.reference(f'users/{user_id}/settings')
    settings = settings_ref.get()
    if settings:
        return jsonify(settings)
    else:
        # Return default settings if none are found
        return jsonify({
            "nickname": "",
            "occupation": "",
            "interests": "",
            "personality": "Default"
        })

@app.route("/save_settings", methods=['POST'])
@login_required
def save_settings():
    user_id = session['user_id']
    settings_ref = db.reference(f'users/{user_id}/settings')
    try:
        settings_data = request.json
        settings_ref.set(settings_data)
        return jsonify({"status": "success", "message": "Settings saved!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- Main App Routes ---
@app.route("/")
@login_required
def index():
    return render_template('index.html')

# --- ADD NEW TRANSLATOR ROUTES HERE ---

@app.route("/translator")
@login_required
def translator_page():
    """Serves the new voice translator page."""
    return render_template('translator.html')

@app.route('/translate_voice', methods=['POST'])
@login_required
def translate_voice_endpoint():
    """Handles the voice translation AI processing."""
    if 'audio_data' not in request.files:
        return jsonify({"error": "No audio file part in the request"}), 400

    file = request.files['audio_data']
    target_lang = request.form.get('language', 'es') # Default to Spanish if not provided

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # --- Create a temporary directory if it doesn't exist ---
    temp_dir = os.path.join(app.static_folder, 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Create unique filenames to prevent users from overwriting each other
    user_id = session.get('user_id', 'default_user')
    unique_id = str(uuid.uuid4())
    input_filename = f"in_{user_id}_{unique_id}.wav"
    output_filename = f"out_{user_id}_{unique_id}.wav"
    
    input_path = os.path.join(temp_dir, input_filename)
    output_path = os.path.join(temp_dir, output_filename)

    try:
        file.save(input_path)

        # --- AUDIO CLEANING FIX V2 (FOR 'DEMONIC' VOICE) ---
        TARGET_SR = 24000 
        
        try:
            # Load with librosa, letting it decide between soundfile or audioread automatically
            # The previous 'sr=None' was causing some issues, so we load at TARGET_SR directly if possible
            # or load native and resample.
            audio, _ = librosa.load(input_path, sr=TARGET_SR)
            soundfile.write(input_path, audio, TARGET_SR, format='WAV', subtype='PCM_16')
            print(f"Cleaned and resampled audio to {TARGET_SR}Hz.", flush=True)
            
        except Exception as e:
            print(f"Error cleaning audio file: {e}", flush=True)
            raise Exception(f"Failed to process audio file: {e}")
        # --- END OF FIX ---
        
        # Call your AI function
        result_path = translate_and_clone_voice(input_path, output_path, target_lang)
        
        if result_path and os.path.exists(result_path):
            response = send_file(result_path, mimetype='audio/wav')
            
            @response.call_on_close
            def cleanup_files():
                try:
                    os.remove(input_path)
                    os.remove(output_path)
                    print(f"Cleaned up temp files: {input_filename}, {output_filename}", flush=True)
                except Exception as e:
                    print(f"Error cleaning up temp files: {e}", flush=True)
            
            return response
        else:
            raise Exception("AI processing failed to produce an output file.")

    except Exception as e:
        print(f"Error in /translate_voice: {repr(e)}", flush=True)
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
            except:
                pass
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# --- END OF NEW ROUTES ---

@app.route("/chat", methods=['POST'])
@login_required
def chat():
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}') # Get user's root reference
    chats_ref = ref.child('chats')

    # --- DYNAMICALLY BUILD SYSTEM INSTRUCTION ---
    settings = ref.child('settings').get()
    dynamic_personality = LUNA_BASE_PERSONALITY
    if settings:
        nickname = settings.get("nickname")
        interests = settings.get("interests")
        personality = settings.get("personality")
        custom_instructions = settings.get("custom_instructions") # Get the new value

        if custom_instructions:
            dynamic_personality += f" Follow these custom instructions from the user: {custom_instructions}."

        if nickname:
            dynamic_personality += f" The user you are talking to wants to be called {nickname}."
        if interests:
            dynamic_personality += f" Keep in mind the user's interests, values, or preferences: {interests}."
        
        if personality and personality != "Default":
            personality_map = {
                "Cynic": "Adopt a critical and sarcastic tone in your responses.",
                "Robot": "Respond in an efficient, blunt, and robotic manner.",
                "Listener": "Be thoughtful, supportive, and a good listener.",
                "Nerd": "Be exploratory, enthusiastic, and nerdy about topics."
            }
            if personality in personality_map:
                dynamic_personality += " " + personality_map[personality]

    # --- CONTINUE WITH CHAT LOGIC ---
    user_message_text = request.form.get('message', '')
    chat_id = request.form.get('chat_id', None)
    if chat_id == 'null': chat_id = None
    
    file = request.files.get('file')
    
    extracted_text = ""
    file_info = {}
    is_image = False
    file_content = None

    if file and file.filename:
        filename = file.filename
        file_content = file.read()
        file_info = {'filename': filename, 'type': file.mimetype}
        
        if file.mimetype and file.mimetype.startswith('image/'):
            is_image = True
        elif filename.endswith('.pdf'):
            extracted_text = extract_text_from_pdf(io.BytesIO(file_content))
        elif filename.endswith('.docx'):
            extracted_text = extract_text_from_docx(io.BytesIO(file_content))
        elif file.mimetype and (file.mimetype.startswith('text/') or filename.endswith('.txt')):
            extracted_text = file_content.decode('utf-8', errors='ignore')
        else:
            extracted_text = f"Unsupported file type: {filename}. Please upload a PDF, DOCX, image, or TXT file."

    current_timestamp = int(time.time() * 1000)
    is_new_chat = not chat_id
    if is_new_chat:
        chat_id = str(uuid.uuid4())
        history = []
    else:
        history = chats_ref.child(chat_id).child('messages').get() or []

    user_message = {"id": current_timestamp, "role": "user", "parts": [user_message_text]}
    if file_info:
        user_message['file'] = file_info
        if is_image and file_content:
            user_message['image'] = f"data:{file_info['type']};base64," + base64.b64encode(file_content).decode('utf-8')

    full_history = history + [user_message]
    chat_ref = chats_ref.child(chat_id)

    def generate_stream():
        try:
            model = None
            api_content = None
            
            api_history = format_history_for_api(history)
            
            if is_image:
                model = genai.GenerativeModel('models/gemini-pro-vision', system_instruction=dynamic_personality)
                img = Image.open(io.BytesIO(file_content))
                api_content = api_history + [{'role': 'user', 'parts': [user_message_text, img]}]
            else:
                model = genai.GenerativeModel('gemini-pro-latest', system_instruction=dynamic_personality)
                prompt_text = user_message_text
                if extracted_text:
                    prompt_text = f"Based on the content of '{file_info.get('filename')}', the user asks: {user_message_text}\n\nDocument Content:\n{extracted_text}"
                
                api_content = api_history + [{'role': 'user', 'parts': [prompt_text]}]

            initial_data = {"chat_id": chat_id, "user_message_id": user_message['id']}
            yield f"data: {json.dumps(initial_data)}\n\n"

            response_stream = model.generate_content(
                api_content, stream=True,
                safety_settings={ HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE }
            )
            
            complete_luna_response = ""
            for chunk in response_stream:
                if chunk.text:
                    complete_luna_response += chunk.text
                    yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"
            
            luna_message = {"id": current_timestamp + 1, "role": "model", "parts": [complete_luna_response]}
            final_history_to_save = full_history + [luna_message]
            chat_ref.child('messages').set(final_history_to_save)
            chat_ref.child('last_updated').set(current_timestamp)

            if is_new_chat:
                title = (user_message_text[:40] + '...') if user_message_text else f"File: {file_info.get('filename')}"
                chat_ref.child('title').set(title)
                chat_ref.child('pinned').set(False)
                yield f"data: {json.dumps({'is_new_chat': True})}\n\n"

        except Exception as e:
            print(f"Error in stream: {repr(e)}", flush=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate_stream(), mimetype='text/event-stream')

@app.route("/edit", methods=['POST'])
@login_required
def edit():
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}/chats') 
    data = request.json
    chat_id, message_id, new_text = data.get('chat_id'), data.get('message_id'), data.get('new_text')
    current_timestamp = int(time.time() * 1000)
    try:
        messages = ref.child(chat_id).child('messages').get()
        message_index = next((i for i, msg in enumerate(messages) if msg['id'] == message_id), -1)
        if message_index == -1: return jsonify({"error": "Message not found"}), 404
        
        messages[message_index]['parts'] = [new_text]
        truncated_history = messages[:message_index + 1]
        
        text_model = genai.GenerativeModel('gemini-pro-latest', system_instruction=LUNA_BASE_PERSONALITY)

        def generate_edit_stream():
            try:
                api_history = format_history_for_api(truncated_history)
                response_stream = text_model.generate_content(api_history, stream=True)
                complete_luna_response = ""
                for chunk in response_stream:
                    if chunk.text:
                        complete_luna_response += chunk.text
                        yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"
                luna_message = {"id": current_timestamp, "role": "model", "parts": [complete_luna_response]}
                final_history = truncated_history + [luna_message]
                ref.child(chat_id).child('messages').set(final_history)
                ref.child(chat_id).child('last_updated').set(current_timestamp)
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return Response(generate_edit_stream(), mimetype='text/event-stream')
    except Exception as e:
        return jsonify({"error": "Failed to edit"}), 500

# --- All other routes below this line are unchanged and correct ---
@app.route('/generate_title', methods=['POST'])
@login_required
def generate_title():
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}/chats') 
    data = request.json; chat_id = data.get('chat_id')
    if not chat_id: return jsonify({"error": "Missing chat_id"}), 400
    try:
        messages = ref.child(chat_id).child('messages').get()
        if not messages or len(messages) < 1: return jsonify({"error": "Not enough messages"}), 400
        smart_title = get_chat_title(messages)
        ref.child(chat_id).child('title').set(smart_title)
        return jsonify({"success": True, "title": smart_title})
    except Exception as e: return jsonify({"error": "Failed to generate title"}), 500

@app.route("/history", methods=['GET'])
@login_required
def history():
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}/chats') 
    all_chats_raw = ref.get(); chat_list = []
    if all_chats_raw:
        for chat_id, data in all_chats_raw.items():
            chat_list.append({"id": chat_id,"title": data.get('title', 'Untitled Chat'),"last_updated": data.get('last_updated', 0),"pinned": data.get('pinned', False)})
    chat_list.sort(key=lambda x: (x['pinned'], x['last_updated']), reverse=True)
    return jsonify(chat_list)

@app.route('/get_chat/<chat_id>', methods=['GET'])
@login_required
def get_chat(chat_id):
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}/chats')
    chat_data = ref.child(chat_id).child('messages').get()
    return jsonify(chat_data or [])

@app.route('/rename_chat', methods=['POST'])
@login_required
def rename_chat():
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}/chats') 
    data = request.json; chat_id, new_title = data.get('chat_id'), data.get('new_title')
    if not all([chat_id, new_title]): return jsonify({"error": "Missing data"}), 400
    ref.child(chat_id).child('title').set(new_title)
    ref.child(chat_id).child('last_updated').set(int(time.time() * 1000))
    return jsonify({"success": True})

@app.route('/delete_chat', methods=['POST'])
@login_required
def delete_chat():
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}/chats') 
    data = request.json; chat_id = data.get('chat_id')
    if not chat_id: return jsonify({"error": "Missing chat_id"}), 400
    ref.child(chat_id).delete()
    return jsonify({"success": True})

@app.route('/pin_chat', methods=['POST'])
@login_required
def pin_chat():
    user_id = session['user_id']
    ref = db.reference(f'users/{user_id}/chats') 
    data = request.json; chat_id, pin_status = data.get('chat_id'), data.get('pin_status')
    if not chat_id or pin_status is None: return jsonify({"error": "Missing data"}), 400
    ref.child(chat_id).child('pinned').set(pin_status)
    return jsonify({"success": True})
    
@app.route('/update_model', methods=['POST'])
@login_required
def update_model():
    user_id = session['user_id']
    settings_ref = db.reference(f'users/{user_id}/settings')
    try:
        data = request.json
        model = data.get('model')
        if not model:
            return jsonify({"status": "error", "message": "No model specified"}), 400
            
        settings_ref.child('model').set(model)
        return jsonify({"status": "success", "message": f"Model updated to {model}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)