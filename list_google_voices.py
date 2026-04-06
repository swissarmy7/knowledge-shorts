import asyncio
import os
import httpx
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from backend.config import GOOGLE_APPLICATION_CREDENTIALS

async def list_voices():
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    if not credentials.valid:
        credentials.refresh(Request())
    
    token = credentials.token
    url = "https://texttospeech.googleapis.com/v1/voices?languageCode=ko-KR"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            for voice in data.get("voices", []):
                name = voice.get("name")
                gender = voice.get("ssmlGender")
                types = voice.get("voiceTypes", [])
                print(f"Voice: {name} | Gender: {gender} | Types: {types}")
        else:
            print(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    asyncio.run(list_voices())
