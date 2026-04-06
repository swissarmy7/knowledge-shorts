import io
from pathlib import Path
from pydub import AudioSegment
from pydub.effects import normalize

def test_normalization():
    # 1. Create a quiet sine wave
    print("Generating quiet audio...")
    quiet_tone = AudioSegment.sine(440).apply_gain(-30).set_duration(1000)
    
    # 2. Normalize
    print("Normalizing...")
    normalized = normalize(quiet_tone)
    
    # 3. Boost
    print("Boosting (+4dB)...")
    boosted = normalized + 4.0
    
    print(f"Original dBFS: {quiet_tone.dBFS:.2f}")
    print(f"Normalized dBFS: {normalized.dBFS:.2f}")
    print(f"Boosted dBFS: {boosted.dBFS:.2f}")
    
    if boosted.dBFS > quiet_tone.dBFS:
        print("✅ SUCCESS: Volume increased.")
    else:
        print("❌ FAILURE: Volume did not increase.")

if __name__ == "__main__":
    test_normalization()
