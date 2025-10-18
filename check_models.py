# check_models.py
import google.generativeai as genai
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Configure the API key
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    print("API Key configured successfully.")
except Exception as e:
    print(f"Error configuring API Key: {e}")
    exit()

print("\n--- Available Models for 'generateContent' ---")
# List all models and find the ones that support the 'generateContent' method
found_model = False
for m in genai.list_models():
  if 'generateContent' in m.supported_generation_methods:
    print(f"Model name: {m.name}")
    found_model = True

if not found_model:
    print("\nNo models supporting 'generateContent' were found for your API key.")
    print("Please check the following:")
    print("1. Is the 'Generative Language API' enabled in your Google Cloud project?")
    print("2. Is your API key valid and without restrictions?")
    print("3. Are you in a supported region for Gemini models?")