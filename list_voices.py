import urllib.request
import json

req = urllib.request.Request(
    "https://api.elevenlabs.io/v1/voices",
    headers={"xi-api-key": "sk_2350235284a1bd7ca8377ffecfc72c124018b177f95d722d"}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
for v in data["voices"]:
    cat = v.get("category", "unknown")
    labels = v.get("labels", {})
    print(f'{v["voice_id"]} | {v["name"]} | category={cat} | labels={labels}')
