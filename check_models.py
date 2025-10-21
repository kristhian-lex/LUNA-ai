import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
    # Configure the API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found in .env file.")
    else:
        genai.configure(api_key=api_key)

        print("Finding available models for generateContent...")

        # List all models that support the 'generateContent' method
        found_models = False
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                print(f"  - {model.name}")
                found_models = True

        if not found_models:
            print("No models supporting 'generateContent' were found. Your API key may be invalid or restricted.")

except Exception as e:
    print(f"An error occurred: {e}")