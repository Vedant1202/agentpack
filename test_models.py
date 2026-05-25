import os
from google import genai
client = genai.Client()
for m in client.models.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
