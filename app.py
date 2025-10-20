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

        # Add this block to include the custom instructions
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

    if file:
        filename = file.filename
        file_stream = io.BytesIO(file.read())
        file.seek(0)
        file_info = {'filename': filename, 'type': file.mimetype}
        
        if file.mimetype and file.mimetype.startswith('image/'):
            is_image = True
        elif filename.endswith('.pdf'):
            extracted_text = extract_text_from_pdf(file_stream)
        elif filename.endswith('.docx'):
            extracted_text = extract_text_from_docx(file_stream)
        elif file.mimetype and (file.mimetype.startswith('text/') or filename.endswith('.txt')):
            extracted_text = file_stream.read().decode('utf-8', errors='ignore')
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
        if is_image:
            file.seek(0)
            img_bytes = file.read()
            user_message['image'] = f"data:{file_info['type']};base64," + base64.b64encode(img_bytes).decode('utf-8')

    full_history = history + [user_message]
    chat_ref = chats_ref.child(chat_id)

    def generate_stream():
        try:
            model = None
            api_content = None
            
            if is_image:
                model = genai.GenerativeModel('gemini-pro-vision', system_instruction=dynamic_personality)
                file.seek(0)
                img = Image.open(file)
                api_content = [user_message_text, img]
            else:
                model = genai.GenerativeModel('gemini-pro-latest', system_instruction=dynamic_personality)
                prompt_text = user_message_text
                if extracted_text:
                    prompt_text = f"Based on the following document content... User Question: {user_message_text}"
                
                api_history = format_history_for_api(history)
                api_history.append({'role': 'user', 'parts': [prompt_text]})
                api_content = api_history

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
                title = (user_message_text[:40] + '...') if user_message_text else f"File: {file.filename}"
                chat_ref.child('title').set(title)
                chat_ref.child('pinned').set(False)
                yield f"data: {json.dumps({'is_new_chat': True})}\n\n"

        except Exception as e:
            print(f"Error in stream: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate_stream(), mimetype='text/event-stream')

@app.route("/edit", methods=['POST'])
@login_required
def edit():
    user_id = session['user_id']
    # You could also load settings here to influence the edit, but we'll keep it simple for now.
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)