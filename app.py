import os
import uuid
import time
import json
import base64
import io
from flask import Flask, render_template, request, jsonify, Response
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
from PIL import Image
import PyPDF2
import docx

# --- Initialization ---
load_dotenv()
app = Flask(__name__)

# Firebase & Gemini Initialization
cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred, {'databaseURL': os.getenv('FIREBASE_DATABASE_URL')})
ref = db.reference('chats')
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Use a single, powerful multimodal model for everything
model = genai.GenerativeModel('gemini-pro-latest') 

# --- Helper Functions for Text Extraction ---
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

# --- Other Helper Functions ---
def format_history_for_api(history):
    return [{'role': msg['role'], 'parts': msg['parts']} for msg in history if msg.get('parts')]

def get_chat_title(history):
    context = "\n".join([f"{msg['role']}: {msg['parts'][0]}" for msg in history[:2] if msg.get('parts')])
    prompt = f"Analyze this conversation start:\n---\n{context}\n---\nGenerate a concise, formal, Title Case title for this chat, 5 words or less. Respond only with the title."
    try:
        response = model.generate_content(prompt)
        title = response.text.strip().strip('"')
        return title if title else "New Chat"
    except Exception:
        return (history[0]['parts'][0][:30] + '...') if history and history[0].get('parts') else "Chat"

# --- Main Flask Routes ---
@app.route("/")
def index():
    return render_template('index.html')

@app.route("/chat", methods=['POST'])
def chat():
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
        
        if filename.endswith('.pdf'):
            extracted_text = extract_text_from_pdf(file_stream)
        elif filename.endswith('.docx'):
            extracted_text = extract_text_from_docx(file_stream)
        elif file.mimetype and (file.mimetype.startswith('text/') or filename.endswith('.txt')):
            extracted_text = file_stream.read().decode('utf-8', errors='ignore')
        elif file.mimetype and file.mimetype.startswith('image/'):
            is_image = True
        else:
            extracted_text = f"Unsupported file type: {filename}. Please upload a PDF, DOCX, image, or TXT file."

    current_timestamp = int(time.time() * 1000)
    is_new_chat = not chat_id
    if is_new_chat:
        chat_id = str(uuid.uuid4())
        history = []
    else:
        history = ref.child(chat_id).child('messages').get() or []

    user_message = {"id": current_timestamp, "role": "user", "parts": [user_message_text]}
    if file_info:
        user_message['file'] = file_info
        if is_image:
            file.seek(0)
            img_bytes = file.read()
            user_message['image'] = f"data:{file_info['type']};base64," + base64.b64encode(img_bytes).decode('utf-8')

    full_history = history + [user_message]
    chat_ref = ref.child(chat_id)

    def generate_stream():
        try:
            initial_data = {"chat_id": chat_id, "user_message_id": user_message['id']}
            yield f"data: {json.dumps(initial_data)}\n\n"
            
            api_content = []
            
            if is_image:
                file.seek(0)
                img = Image.open(file)
                api_content = [user_message_text, img]
            else:
                prompt_text = user_message_text
                if extracted_text:
                    prompt_text = f"Based on the following document content, answer the user's question.\n\n--- DOCUMENT: {file.filename} ---\n{extracted_text}\n--- DOCUMENT END ---\n\nUser Question: {user_message_text}"
                
                temp_history = format_history_for_api(history)
                temp_history.append({'role': 'user', 'parts': [prompt_text]})
                api_content = temp_history

            response_stream = model.generate_content(
                api_content, stream=True,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
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
def edit():
    data = request.json
    chat_id, message_id, new_text = data.get('chat_id'), data.get('message_id'), data.get('new_text')
    current_timestamp = int(time.time() * 1000)
    try:
        messages = ref.child(chat_id).child('messages').get()
        message_index = next((i for i, msg in enumerate(messages) if msg['id'] == message_id), -1)
        if message_index == -1: return jsonify({"error": "Message not found"}), 404
        
        if messages[message_index].get('image') or messages[message_index].get('file'):
             return Response(f"data: {json.dumps({'error': 'Editing messages with attachments is not supported.'})}\n\n", mimetype='text/event-stream')

        messages[message_index]['parts'] = [new_text]
        truncated_history = messages[:message_index + 1]

        def generate_edit_stream():
            try:
                api_history = format_history_for_api(truncated_history)
                response_stream = model.generate_content(api_history, stream=True)
                complete_luna_response = ""
                for chunk in response_stream:
                    if chunk.text:
                        complete_luna_response += chunk.text
                        yield f"data: {json.dumps({'chunk': chunk.text})}\n\n"
                luna_message = {"id": current_timestamp, "role": "model", "parts": [complete_luna_response]}
                final_history = truncated_history + [luna_message]
                chat_ref = ref.child(chat_id)
                chat_ref.child('messages').set(final_history)
                chat_ref.child('last_updated').set(current_timestamp)
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return Response(generate_edit_stream(), mimetype='text/event-stream')
    except Exception as e:
        return jsonify({"error": "Failed to edit"}), 500

@app.route('/generate_title', methods=['POST'])
def generate_title():
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
def history():
    all_chats_raw = ref.get(); chat_list = []
    if all_chats_raw:
        for chat_id, data in all_chats_raw.items():
            chat_list.append({"id": chat_id,"title": data.get('title', 'Untitled Chat'),"last_updated": data.get('last_updated', 0),"pinned": data.get('pinned', False)})
    chat_list.sort(key=lambda x: (x['pinned'], x['last_updated']), reverse=True)
    return jsonify(chat_list)

@app.route('/get_chat/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    chat_data = ref.child(chat_id).child('messages').get()
    return jsonify(chat_data or [])

@app.route('/rename_chat', methods=['POST'])
def rename_chat():
    data = request.json; chat_id, new_title = data.get('chat_id'), data.get('new_title')
    if not all([chat_id, new_title]): return jsonify({"error": "Missing data"}), 400
    ref.child(chat_id).child('title').set(new_title)
    ref.child(chat_id).child('last_updated').set(int(time.time() * 1000))
    return jsonify({"success": True})

@app.route('/delete_chat', methods=['POST'])
def delete_chat():
    data = request.json; chat_id = data.get('chat_id')
    if not chat_id: return jsonify({"error": "Missing chat_id"}), 400
    ref.child(chat_id).delete()
    return jsonify({"success": True})

@app.route('/pin_chat', methods=['POST'])
def pin_chat():
    data = request.json; chat_id, pin_status = data.get('chat_id'), data.get('pin_status')
    if not chat_id or pin_status is None: return jsonify({"error": "Missing data"}), 400
    ref.child(chat_id).child('pinned').set(pin_status)
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='192.168.1.18', port=5000, debug=True)