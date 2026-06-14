import sys
import os
import tkinter as tk
import time

# Ensure workspace root is on path so `main` can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Provide lightweight dummy modules for heavy dependencies so tests can import main
import types
dummy_names = [
    'speech_recognition', 'gtts', 'pydub', 'pygame', 'groq', 'sounddevice', 'numpy', 'wave', 'static_ffmpeg'
]
for name in dummy_names:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

# add expected attributes
sys.modules['gtts'].gTTS = lambda text, lang='ur': None
sys.modules['pygame'].mixer = types.SimpleNamespace(
    init=lambda: None,
    music=types.SimpleNamespace(load=lambda p: None, play=lambda: None, get_busy=lambda: (False), unload=lambda: None)
)
sys.modules['static_ffmpeg'].add_paths = lambda: None
# Minimal AudioSegment stub
class DummyAudio:
    def __init__(self, *a, **k): pass
    @staticmethod
    def from_mp3(path):
        return DummyAudio()
    def _spawn(self, raw, overrides=None):
        return self
    def set_frame_rate(self, r):
        return self
    def export(self, proc, format="wav"):
        open(proc, 'wb').close()

sys.modules['pydub'].AudioSegment = DummyAudio
sys.modules['groq'].Groq = lambda *a, **k: None

from main import MedinovaKiosk

# Helper to run a scenario
def run_scenario(name, initial_utterance, answers):
    print(f"--- Scenario: {name} ---")
    root = tk.Tk(); root.withdraw()
    app = MedinovaKiosk(root)
    # Silence TTS and redirect logs to console
    app.speak = lambda x: print("SPEAK:", x)
    app.log = lambda sender, message, tag=None: print(f"{sender}: {message}")
    # Start dialog at initial response
    app.dialog_state = "awaiting_initial_response"
    cont = app.process_logic(initial_utterance)
    # If follow ups generated, answer them
    while cont and app.dialog_state == "collect_follow_up":
        # get next question index
        idx = app.follow_up_index - 1
        q = app.follow_up_questions[idx] if idx < len(app.follow_up_questions) else None
        print("AI asked:", q)
        # pop next answer from provided answers list or use 'نہیں' default
        ans = answers.pop(0) if answers else "نہیں"
        print("User answers:", ans)
        cont = app.process_logic(ans)
        print("Current urgency:", app.urgency_level)
        time.sleep(0.1)
    # If appointment offer state, simulate a 'no' to stop
    if app.dialog_state == "appointment_offer":
        print("At appointment_offer; urgency:", app.urgency_level)
        app.process_logic("نہیں")
    print("Final urgency:", app.urgency_level)
    print("Patient data:", app.patient_data)
    print()

if __name__ == '__main__':
    # Scenario 1: Neck, mild
    run_scenario('Neck mild', 'میرا گردن درد ہے', ['دو دن ہوگئے', 'وقفے وقفے سے', 'نہیں', 'کچھ نہیں', 'کم'])

    # Scenario 2: Neck, severe with associated symptoms
    run_scenario('Neck severe', 'میرا گردن درد ہے', ['آج صبح', 'مستقل', 'ہاں، بخار اور چکر', 'نہیں', 'شدید'])

    # Scenario 3: Chest pain urgent
    run_scenario('Chest severe', 'میرے سینے میں درد ہے', ['آج رات', 'مستقل', 'ہاں، پسینہ آ رہا ہے', 'سانس لینے میں مشکل', '8'])
