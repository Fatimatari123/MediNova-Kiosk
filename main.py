import os
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from dotenv import load_dotenv
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment
import pygame
from groq import Groq
import tempfile
import sounddevice as sd
import numpy as np
import io
import wave
import time
import random
from datetime import datetime
import re
from static_ffmpeg import add_paths

# Add ffmpeg paths
add_paths()

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Configure Groq
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)
else:
    client = None

# V6 MODERN THEME: Teal & Ocean Blue
COLOR_TEAL = "#00A699"
COLOR_OCEAN = "#006699"
COLOR_WHITE = "#FFFFFF"
COLOR_LIGHT_BG = "#F4F7F6"
COLOR_TEXT = "#2C3E50"
COLOR_URGENT = "#E74C3C"
COLOR_SHIELD = "#2ECC71"

QUOTES = [
    "تندرستی ہزار نعمت ہے۔",
    "صحت مند جسم میں ہی صحت مند دماغ ہوتا ہے۔",
    "احتیاط علاج سے بہتر ہے۔",
    "روزانہ ورزش آپ کی زندگی بدل سکتی ہے۔",
    "اچھی نیند بہترین دوا ہے۔"
]

class MedinovaKiosk:
    def __init__(self, root):
        self.root = root
        self.root.title("MEDINOVA HEALTH KIOSK")
        self.root.geometry("1000x850") # Reduced height for visibility
        self.root.configure(bg=COLOR_WHITE)

        # Logic States
        self.urgency_level = "GREEN"
        self.patient_data = {"name": "", "age": "", "symptom": "", "location": "", "duration": "", "severity": "", "associated": "", "specialist": "", "additional": "", "care": "", "time": ""}
        self.dialog_state = "idle"
        self.follow_up_index = 0
        self.follow_up_questions = [
            "یہ درد کب شروع ہوا؟",
            "کیا درد مستقل ہے یا وقفے وقفے سے ہوتا ہے؟",
            "کیا آپ کو بخار یا چکر محسوس ہو رہا ہے؟",
            "کیا کوئی چیز اس درد کو بہتر یا خراب کرتی ہے؟",
            "براہِ کرم بتائیں درد کی شدت کیا ہے؟ کم، درمیانہ، یا شدید؟"
        ]
        self.is_recording = False
        self.is_breathing = False
        self.conversation_started = False
        self.mic_pulse_id = None
        self.mic_pulse_step = 0
        self.dht_rules = self.load_dht_rules("data/dht_rules.txt")
        self.disease_rules = self.load_disease_rules("data/disease_rules.txt")
        self.disease_followups = self.create_disease_followups()
        self.detected_disease = None  # Track detected disease

        pygame.mixer.init()
        self.setup_ui()

    def setup_ui(self):
        # 1. Top Bar
        top_bar = tk.Frame(self.root, bg=COLOR_OCEAN, height=50)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        tk.Button(top_bar, text="EXIT ✖", font=("Arial", 10, "bold"), bg=COLOR_URGENT, fg=COLOR_WHITE, command=self.root.quit, relief=tk.FLAT).pack(side=tk.LEFT, padx=10, pady=5)
        
        disclaimer_lbl = tk.Label(top_bar, text="MEDICAL EMERGENCY? CALL 1122. Guidance Only.", font=("Arial", 10, "bold"), bg=COLOR_OCEAN, fg=COLOR_WHITE)
        disclaimer_lbl.pack(side=tk.LEFT, expand=True)

        tk.Label(top_bar, text="🛡️ Secure & Confidential", font=("Arial", 9), bg=COLOR_OCEAN, fg=COLOR_WHITE).pack(side=tk.RIGHT, padx=15)

        # 2. Circular Mic Section (NEW FOCAL POINT AT TOP)
        mic_section = tk.Frame(self.root, bg=COLOR_WHITE, pady=20)
        mic_section.pack(fill=tk.X)

        self.mic_canvas = tk.Canvas(mic_section, width=120, height=120, bg=COLOR_WHITE, highlightthickness=0)
        self.mic_circle = self.mic_canvas.create_oval(10, 10, 110, 110, fill=COLOR_OCEAN, outline="")
        self.mic_icon = self.mic_canvas.create_text(60, 60, text="🎤", fill="white", font=("Arial", 40))
        self.mic_canvas.pack()
        self.mic_canvas.bind("<Button-1>", lambda e: self.handle_mic_click())

        self.mic_btn = tk.Button(mic_section, text="🎤 START", font=("Arial", 12, "bold"), bg=COLOR_OCEAN, fg=COLOR_WHITE, relief=tk.FLAT, command=self.handle_mic_click, padx=20, pady=10)
        self.mic_btn.pack(pady=(10, 0))
        
        self.mic_instruction = tk.Label(mic_section, text="Click the mic to begin voice conversation", font=("Arial", 10, "bold"), bg=COLOR_WHITE, fg=COLOR_OCEAN)
        self.mic_instruction.pack(pady=(5, 0))

        # 3. Main Content (Chat + Avatar)
        content_frame = tk.Frame(self.root, bg=COLOR_WHITE)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        # Avatar on Left
        avatar_frame = tk.Frame(content_frame, bg=COLOR_WHITE)
        avatar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
        
        self.avatar_canvas = tk.Canvas(avatar_frame, width=100, height=100, bg=COLOR_WHITE, highlightthickness=0)
        self.avatar_circle_bg = self.avatar_canvas.create_oval(5, 5, 95, 95, fill=COLOR_TEAL, outline="")
        self.avatar_face = self.avatar_canvas.create_text(50, 50, text="😊", font=("Arial", 35), fill=COLOR_WHITE)
        self.avatar_canvas.pack(pady=5)
        
        tk.Label(avatar_frame, text="Medinova AI", font=("Arial", 10, "bold"), bg=COLOR_WHITE, fg=COLOR_OCEAN).pack()
        
        self.status_lbl = tk.Label(avatar_frame, text="Ready", font=("Arial", 9, "bold"), bg=COLOR_WHITE, fg=COLOR_TEAL)
        self.status_lbl.pack(pady=2)

        # Chat on Right
        chat_container = tk.Frame(content_frame, bg=COLOR_LIGHT_BG)
        chat_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_log = scrolledtext.ScrolledText(
            chat_container, wrap=tk.WORD, font=("Segoe UI", 18),
            bg=COLOR_LIGHT_BG, fg=COLOR_TEXT, bd=0, padx=20, pady=20
        )
        self.chat_log.pack(fill=tk.BOTH, expand=True)
        self.chat_log.tag_configure("ai", foreground=COLOR_OCEAN, font=("Segoe UI", 18, "bold"))
        self.chat_log.tag_configure("usr", foreground=COLOR_TEAL, font=("Segoe UI", 18))

        # 4. Control Panel (FOOTER)
        footer = tk.Frame(self.root, bg=COLOR_LIGHT_BG, height=100)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        btn_row = tk.Frame(footer, bg=COLOR_LIGHT_BG)
        btn_row.pack(expand=True, pady=10)

        tk.Button(btn_row, text="🧘 Breathe", font=("Arial", 11), bg=COLOR_TEAL, fg=COLOR_WHITE, command=self.pause_and_breathe, relief=tk.FLAT, padx=15, pady=8).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_row, text="📄 Scan", font=("Arial", 11), bg=COLOR_TEAL, fg=COLOR_WHITE, relief=tk.FLAT, padx=15, pady=8).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_row, text="🖨️ Print", font=("Arial", 11), bg="#95a5a6", fg=COLOR_WHITE, relief=tk.FLAT, command=self.print_summary).pack(side=tk.LEFT, padx=10)

    def load_dht_rules(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return f.read()
        return ""

    def load_disease_rules(self, file_path):
        rules = []
        if not os.path.exists(file_path):
            return rules
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split into blocks separated by one or more blank lines.
        blocks = [block.strip() for block in re.split(r"\n\s*\n+", content) if block.strip()]
        for block in blocks:
            if block.startswith("#"):
                continue
            # If block contains pipe-delimited lines, preserve old format behaviour.
            if "|" in block and not block.lower().startswith("condition:"):
                for line in block.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    parts = [part.strip() for part in line.split("|")]
                    if len(parts) >= 6:
                        rules.append({
                            "disease": parts[0],
                            "keywords": parts[1],
                            "symptoms": parts[2],
                            "urgency": parts[3],
                            "specialist": parts[4],
                            "care": parts[5]
                        })
                    elif len(parts) >= 4:
                        urgency = parts[2].strip().lower()
                        rules.append({
                            "disease": parts[0],
                            "keywords": "",
                            "symptoms": parts[1],
                            "urgency": urgency if urgency in ['red', 'yellow', 'green'] else ('CRITICAL' if urgency == 'critical' else 'LOW'),
                            "specialist": parts[3] if len(parts) > 3 else "",
                            "care": parts[4] if len(parts) > 4 else ""
                        })
                continue

            fields = {}
            for line in block.splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                if ":" not in line:
                    continue
                key, value = [part.strip() for part in line.split(":", 1)]
                fields[key.lower()] = value

            if "condition" not in fields:
                continue

            disease = fields.get("condition", "").strip()
            keywords = fields.get("spoken roman urdu keywords", "").strip()
            symptoms = fields.get("common symptoms", "").strip()
            urgency = fields.get("urgency", "").strip().upper()
            specialist = fields.get("specialist", "").strip()
            care = fields.get("home care", "").strip()

            if urgency not in ["RED", "YELLOW", "GREEN"]:
                urgency = urgency.lower()
                urgency = "RED" if urgency == "critical" else ("GREEN" if urgency == "low" else ("YELLOW" if urgency == "yellow" else urgency.upper()))

            rules.append({
                "disease": disease,
                "keywords": keywords,
                "symptoms": symptoms,
                "urgency": urgency,
                "specialist": specialist,
                "care": care
            })
        return rules

    def create_disease_followups(self):
        """Create disease-specific follow-up questions.
        Build dynamic follow-ups from `self.disease_rules` file and merge with
        a small set of curated category templates. This ensures each disease
        can have tailored follow-ups derived from the symptoms listed in the
        rules text file (so updating the file updates follow-ups).
        """
        # Start with curated templates for broad categories
        templates = {
            "dengue": {
                "questions": [
                    "یہ بخار کب شروع ہوا؟",
                    "کیا آپ کو جسم میں شدید درد ہے؟",
                    "کیا آپ کو آنکھوں کے پیچھے درد ہے؟",
                    "کیا آپ کو دانے نظر آ رہے ہیں؟",
                    "براہِ کرم بتائیں، بخار کتنا شدید ہے؟"
                ],
                "keys": ["duration", "body_pain", "eye_pain", "rash", "severity"]
            }
        }

        # Build dynamic followups from rules file
        dynamic = self.build_followups_from_rules()

        # merge: dynamic entries override templates when available
        for k, v in dynamic.items():
            templates[k] = v

        return templates

    def build_followups_from_rules(self):
        """Generate follow-up question sets from loaded disease rules.
        For each rule, create a 4-6 question set: onset, symptom checks,
        severity, and any rule-specific items. Returns a dict keyed by
        normalized disease name.
        """
        out = {}
        for rule in self.disease_rules:
            name = rule.get('disease', '').strip()
            if not name: continue
            key = name.lower()
            # extract symptom phrases (Urdu) split by punctuation
            symptoms_field = rule.get('symptoms', '')
            # split on Urdu comma and English comma
            phrases = [s.strip() for s in re.split('[,،]', symptoms_field) if s.strip()]
            questions = []
            keys = []

            # onset question
            questions.append("یہ علامات کب شروع ہوئیں؟")
            keys.append("duration")

            # for first 3 symptom keywords, ask targeted yes/no questions
            for i, ph in enumerate(phrases[:3]):
                q = f"کیا آپ کو {ph} محسوس ہو رہا/رہی ہے؟"
                # normalize key: replace non-word characters with underscore
                k = re.sub(r"[^\w]+", "_", ph)
                k = k.strip().lower()[:20] or f"sym_{i}"
                questions.append(q)
                keys.append(k)

            # severity question
            questions.append("براہِ کرم شدت بتائیں - کم، درمیانہ یا شدید؟")
            keys.append("severity")

            # offer a catch-all extra info question
            questions.append("کیا آپ کے پاس اس بارے میں کوئی اضافی معلومات ہے؟")
            keys.append("additional")

            out[key] = {"questions": questions, "keys": keys}

        return out


    def tokenize(self, text):
        import re
        if not text: return set()
        # capture Urdu/Arabic letters and latin words/numbers
        tokens = re.findall(r"[\u0600-\u06FF\w]+", text.lower())
        stop = set([
            "میں","ہے","کو","کا","کے","کی","اور","نہیں","کیہ","کیا","ہوں","ہوں","ہے","ہے","کا","بھی",
            "the","is","a","an","and","or","of","in","on","at","to","for","with","not"
        ])
        return set([t for t in tokens if t and t not in stop])

    def infer_green_home_care(self):
        text = ' '.join([
            self.patient_data.get('symptom', ''),
            self.patient_data.get('location', ''),
            self.patient_data.get('duration', ''),
            self.patient_data.get('severity', ''),
            self.patient_data.get('associated', ''),
            self.patient_data.get('additional', '')
        ]).lower()

        if any(word in text for word in ["بخار", "گرمی", "تپ"]):
            return "بخار کی صورت میں ٹھنڈی پتیاں لیں اور آرام کریں۔"
        if any(word in text for word in ["فلُو", "نزلہ", "کھانسی", "سردی", "گلے", "گلا", "ہلکا سر درد"]):
            return "فلُو کی علامات کے لئے چائے یا جوشاندہ پئیں۔"
        if any(word in text for word in ["ناک", "چھینک", "نزلہ", "ناک بند", "ناک کا درد"]):
            return "ناک کے درد یا بندش کے لئے بھاپ لیں یا سٹیم کریں۔"
        if any(word in text for word in ["سینے", "سینہ", "سانس", "جکڑن"]) and any(word in text for word in ["کھانسی", "پسینہ", "تھکاوٹ", "دشوار"]):
            return "سینے کی الجھن کے لئے بھاپ لیں، آرام کریں اور ہلکا گرم مشروب لیں۔"
        return "گھر پر آرام کریں، زیادہ پانی پیئیں اور اگر علامات برقرار رہیں تو ڈاکٹر سے رجوع کریں۔"

    def log(self, sender, message, tag=None):
        self.chat_log.config(state=tk.NORMAL)
        disp = "Medinova (AI)" if sender=="AI" else "Patient (User)"
        self.chat_log.insert(tk.END, f"{disp}:\n", "ai" if sender=="AI" else "usr")
        self.chat_log.insert(tk.END, f"{message}\n\n", tag if tag else None)
        self.chat_log.config(state=tk.DISABLED); self.chat_log.see(tk.END)

    def speak(self, text):
        try:
            self.status_lbl.config(text="Speaking...")
            tts = gTTS(text=text, lang='ur')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                tmp = fp.name
                tts.save(tmp)
            aud = AudioSegment.from_mp3(tmp)
            aud = aud._spawn(aud.raw_data, overrides={"frame_rate": int(aud.frame_rate * 1.1)}).set_frame_rate(aud.frame_rate)
            proc = tmp.replace(".mp3", "_p.wav")
            aud.export(proc, format="wav")
            pygame.mixer.music.load(proc); pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
            try: os.remove(tmp); os.remove(proc)
            except: pass
            self.status_lbl.config(text="Ready")
        except Exception as e: print(f"TTS Error: {e}")

    def initial_sequence(self):
        d = "یہ ایک AI میڈیکل اسسٹنٹ ہے، ڈاکٹر نہیں۔ یہ صرف عمومی رہنمائی فراہم کرتا ہے۔ کسی بھی سنجیدہ مسئلے کی صورت میں فوراً ڈاکٹر سے رجوع کریں۔"
        self.log("AI", d); self.speak(d)
        g = "السلام علیکم! میں میڈینووا ہوں۔ آپ آج کیسا محسوس کر رہے ہیں؟"
        self.log("AI", g); self.speak(g)

    def handle_mic_click(self):
        if self.is_recording:
            self.is_recording = False
            self.mic_btn.config(bg=COLOR_OCEAN, text="🎤 START")
            self.mic_instruction.config(text="Conversation paused. Click mic to resume.")
            self.stop_mic_animation()
            return

        self.is_recording = True
        self.mic_btn.config(bg=COLOR_URGENT, text="🛑 STOP")
        self.mic_instruction.config(text="Conversation started. Preparing the AI greeting...")
        self.start_mic_animation()

        if not self.conversation_started:
            self.conversation_started = True
            self.dialog_state = "awaiting_initial_response"
            threading.Thread(target=self.start_conversation, daemon=True).start()
        else:
            threading.Thread(target=self.voice_loop, daemon=True).start()

    def start_conversation(self):
        self.initial_sequence()
        if self.is_recording:
            self.mic_instruction.config(text="Listening now. Speak into the microphone.")
            self.voice_loop()
        else:
            self.mic_instruction.config(text="Conversation paused. Click mic to resume.")

    def start_mic_animation(self):
        self.mic_pulse_step = 0
        self.animate_mic()

    def animate_mic(self):
        if not self.is_recording:
            return
        colors = [COLOR_URGENT, "#FF6F61", COLOR_OCEAN]
        glow = colors[self.mic_pulse_step % len(colors)]
        self.mic_canvas.itemconfig(self.mic_circle, fill=glow)
        self.mic_pulse_step += 1
        self.mic_pulse_id = self.root.after(220, self.animate_mic)

    def stop_mic_animation(self):
        if self.mic_pulse_id:
            self.root.after_cancel(self.mic_pulse_id)
            self.mic_pulse_id = None
        self.mic_canvas.itemconfig(self.mic_circle, fill=COLOR_OCEAN)

    def voice_loop(self):
        while self.is_recording:
            self.avatar_canvas.itemconfig(self.avatar_face, text="👂")
            self.status_lbl.config(text="Listening...")
            
            rec = sr.Recognizer()
            rec.dynamic_energy_threshold = True
            rec.energy_threshold = 300
            rec.pause_threshold = 0.8
            rec.phrase_threshold = 0.3
            rec.non_speaking_duration = 0.4

            fs = 44100; secs = 6
            data = sd.rec(int(secs * fs), samplerate=fs, channels=1, dtype='int16')
            sd.wait()
            
            if not self.is_recording: break
            
            self.avatar_canvas.itemconfig(self.avatar_face, text="🤔")
            self.status_lbl.config(text="Thinking...")

            audio_data = sr.AudioData(data.tobytes(), fs, 2)
            txt = ""
            try:
                txt = rec.recognize_google(audio_data, language='ur-PK')
            except sr.UnknownValueError:
                try:
                    txt = rec.recognize_google(audio_data, language='ur')
                except sr.UnknownValueError:
                    txt = ""
            except Exception:
                txt = ""

            if txt:
                self.log("User", txt)
                if not self.process_logic(txt): break
            else:
                self.ai_reply("معذرت، میں سمجھ نہیں سکی۔ دوبارہ کہیے۔")
        
        self.is_recording = False
        self.stop_mic_animation()
        self.mic_btn.config(bg=COLOR_OCEAN, text="🎤 START")
        self.avatar_canvas.itemconfig(self.avatar_face, text="😊")
        self.status_lbl.config(text="Ready")

    def process_logic(self, user_text):
        user_text = user_text.lower()
        if self.dialog_state == "awaiting_initial_response":
            return self.handle_initial_response(user_text)

        if self.dialog_state == "awaiting_body_part":
            return self.handle_body_part_response(user_text)

        if self.dialog_state == "collect_follow_up":
            return self.handle_follow_up_response(user_text)

        if self.dialog_state == "appointment_offer":
            return self.handle_appointment_response(user_text)

        if self.dialog_state == "collect_name":
            return self.handle_booking_name(user_text)

        if self.dialog_state == "collect_age":
            return self.handle_booking_age(user_text)

        self.ai_reply("معاف کیجئے، براہ کرم دوبارہ کہئیے۔")
        return True

    def handle_initial_response(self, user_text):
        ok_keywords = ["ٹھیک", "بہتر", "شکریہ", "i am ok", "i am fine", "fine", "theek", "میں ٹھیک ہوں"]
        sick_keywords = ["بیمار", "درد", "ہوا", "بخار", "سردی", "کھانسی", "جلن", "sick", "pain", "ache", "hurt", "not feeling good", "not feeling well", "feeling bad", "feeling sick", "unwell", "theek nahi", "theek نہیں", "achha nahi", "not fine", "not okay", "ٹھیک نہیں", "بہتر نہیں", "اچھا نہیں"]

        if any(word in user_text for word in ok_keywords):
            self.ai_reply("ماشاءاللہ، یہ بہت اچھی بات ہے۔ گھر پر آرام کریں، اور خوش رہیں۔ اللہ آپ کی مدد کرے۔")
            self.dialog_state = "idle"
            self.conversation_started = False
            return False

        if any(word in user_text for word in sick_keywords):
            self.patient_data['symptom'] = user_text
            location = self.extract_body_part(user_text)
            if location:
                self.patient_data['location'] = location
                # Try to match a disease rule now using tokens
                match = self.match_disease_rule()
                # If we have a confident match (>=60% symptoms matched), ask disease-specific follow-ups
                if match and match.get('score', 0) >= 0.6:
                    # Generate disease-specific follow-up questions
                    self.generate_follow_ups_from_rules(location, match)
                    self.dialog_state = "collect_follow_up"
                    self.follow_up_index = 0
                    self.ai_reply("براہِ کرم مزید تفصیل بتائیں۔ " + self.follow_up_questions[self.follow_up_index])
                    self.follow_up_index += 1
                    return True
                else:
                    # Build targeted follow-ups for weaker matches
                    built = self.generate_follow_ups_from_rules(location, match)
                    if not built:
                        self.follow_up_keys = ["duration", "pattern", "associated", "additional", "severity"]
                    self.dialog_state = "collect_follow_up"
                    self.follow_up_index = 0
                    self.ai_reply("براہِ کرم مزید تفصیل بتائیں۔ " + self.follow_up_questions[self.follow_up_index])
                    self.follow_up_index += 1
                    return True

            self.dialog_state = "awaiting_body_part"
            self.ai_reply("آپ کے جسم کے کس حصے میں درد ہے؟")
            return True

        self.ai_reply("معاف کیجئے، میں سمجھ نہیں سکی۔ کیا آپ ٹھیک ہیں یا آپ کو جسم کے کسی حصے میں درد ہے؟")
        return True

    def handle_body_part_response(self, user_text):
        self.patient_data['location'] = user_text
        if not self.patient_data['symptom']:
            self.patient_data['symptom'] = "درد"
        # Try to match rule now
        match = self.match_disease_rule()
        if match and match.get('score',0) >= 0.6:
            # Generate disease-specific follow-ups
            self.generate_follow_ups_from_rules(user_text, match)
            self.dialog_state = "collect_follow_up"
            self.follow_up_index = 0
            self.ai_reply(self.follow_up_questions[self.follow_up_index])
            self.follow_up_index += 1
            return True

        # Build targeted follow-ups based on the provided location and match
        built = self.generate_follow_ups_from_rules(user_text, match)
        if not built:
            self.follow_up_keys = ["duration", "pattern", "associated", "additional", "severity"]
            # ensure default questions exist
            if not getattr(self, 'follow_up_questions', None):
                self.follow_up_questions = [
                    "یہ درد کب شروع ہوا؟",
                    "کیا درد مستقل ہے یا وقفے وقفے سے ہوتا ہے؟",
                    "کیا آپ کو بخار یا چکر محسوس ہو رہا ہے؟",
                    "کیا کوئی چیز اس درد کو بہتر یا خراب کرتی ہے؟",
                    "براہِ کرم بتائیں درد کی شدت کیا ہے؟ کم، درمیانہ، یا شدید؟"
                ]
        self.dialog_state = "collect_follow_up"
        self.follow_up_index = 0
        self.ai_reply(self.follow_up_questions[self.follow_up_index])
        self.follow_up_index += 1
        return True

    def handle_follow_up_response(self, user_text):
        # Use dynamic follow_up_keys if present
        if hasattr(self, 'follow_up_keys') and self.follow_up_keys:
            keys = self.follow_up_keys
        else:
            keys = ["duration", "pattern", "associated", "additional", "severity"]

        key = keys[self.follow_up_index - 1]

        # Store responses; allow dynamic symptom keys like 'sym_0'
        self.patient_data[key] = user_text

        # If this answer was the pain-level (severity) question, parse and apply it.
        if key == "severity":
            p = self.parse_pain_level(user_text)
            if p:
                if p == "critical":
                    self.urgency_level = "RED"
                elif p == "medium":
                    if self.urgency_level != "RED":
                        self.urgency_level = "YELLOW"
                elif p == "low":
                    if self.urgency_level != "RED":
                        self.urgency_level = "GREEN"

        # Proceed to next follow-up if any
        if self.follow_up_index < len(self.follow_up_questions):
            self.ai_reply(self.follow_up_questions[self.follow_up_index])
            self.follow_up_index += 1
            return True

        # All follow-ups collected - finalize triage and present analysis
        self.ai_reply("میں نے آپ کی تفصیل لے لی ہے۔ اب میں آپ کی صورتحال کا جائزہ لوں گا۔")
        self.finalize_triage()
        summary = self.build_analysis_summary()
        self.ai_reply(summary)
        
        # Based on urgency level, decide next action
        if self.urgency_level == "GREEN":
            self.dialog_state = "idle"
            self.conversation_started = False
            return False
        
        if self.urgency_level == "YELLOW":
            self.dialog_state = "appointment_offer"
            self.ai_reply("کیا آپ ڈاکٹر سے ملاقات بک کرنا چاہیں گے؟")
            return True
        
        # RED urgency
        self.dialog_state = "appointment_offer"
        self.ai_reply("کیا آپ ڈاکٹر سے ملاقات بک کرنا چاہیں گے؟")
        return True

    def handle_appointment_response(self, user_text):
        yes_keywords = ["جی ہاں", "ہاں", "yes", "yeah", "جی", "haan"]
        no_keywords = ["نہیں", "no", "nope", "nah"]

        if any(word in user_text for word in yes_keywords):
            self.dialog_state = "collect_name"
            self.ai_reply("آپ کا نام کیا ہے؟")
            return True
        if any(word in user_text for word in no_keywords):
            self.ai_reply("ٹھیک ہے، گھر جا کر آرام کریں۔ اگر علامات بدتر ہوں تو ڈاکٹر سے ضرور ملیں۔ اللہ حافظ۔")
            self.dialog_state = "idle"
            self.conversation_started = False
            return False
        self.ai_reply("براہ کرم ہاں یا نہیں میں جواب دیں۔ کیا آپ ڈاکٹر کے ساتھ ملاقات کا وقت طے کرنا چاہیں گے؟")
        return True

    def handle_booking_name(self, user_text):
        self.patient_data['name'] = user_text.title()
        self.dialog_state = "collect_age"
        self.ai_reply("آپ کی عمر کیا ہے؟")
        return True

    def handle_booking_age(self, user_text):
        age = self.parse_age(user_text)
        if age is not None and 0 <= age <= 130:
            self.patient_data['age'] = str(age)
            self.generate_downloadable_report()
            self.dialog_state = "idle"
            self.conversation_started = False
            return False
        self.ai_reply("براہ کرم اپنی عمر صرف نمبر میں بتائیں، مثلاً 18۔ عمر 0 سے 130 سال تک ہو سکتی ہے۔")
        return True

    def parse_age(self, text):
        import re
        text = text.lower()
        digits = re.findall(r"\d+", text)
        if digits:
            return int(digits[0])

        words = {
            "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
            "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
            "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
            "صفر": 0, "ایک": 1, "دوس": 2, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5,
            "چھ": 6, "سات": 7, "آٹھ": 8, "نو": 9, "دس": 10, "گیارہ": 11,
            "بارہ": 12, "تیرہ": 13, "چودہ": 14, "پندرہ": 15, "سولہ": 16,
            "سترہ": 17, "اٹھارہ": 18, "انیس": 19, "بیس": 20, "اکیس": 21,
            "بائیس": 22, "تائیس": 23, "تیس": 30, "چالیس": 40, "پچاس": 50,
            "ساٹھ": 60, "ستر": 70, "اسی": 80, "نوے": 90, "سو": 100,
            "ایک سو": 100, "ایک سو ایک": 101, "ایک سو پچاس": 150
        }
        parts = text.replace("سال", "").replace("سالانہ", "").split()
        value = 0
        current = 0
        for part in parts:
            if part in words:
                current += words[part]
            elif part == "اور":
                continue
            else:
                if current:
                    value += current
                    current = 0
        value += current
        return value if value > 0 else None

    def parse_pain_level(self, text):
        """Parse patient reported pain level into one of: 'low', 'medium', 'critical'."""
        t = text.lower()
        # Critical indicators
        critical = ["شدید", "انتہائی", "زیادہ", "ہنگامی", "قریب الموت", "critical", "severe", "emergency"]
        medium = ["درمیانہ", "معتدل", "medium", "moderate", "مڈ"]
        low = ["کم", "ہلکا", "ہلکی", "light", "low", "mild"]

        for w in critical:
            if w in t:
                return "critical"
        for w in medium:
            if w in t:
                return "medium"
        for w in low:
            if w in t:
                return "low"

        # If numeric scale provided (e.g., 1-10), interpret 1-3 low, 4-7 medium, 8-10 critical
        import re
        nums = re.findall(r"\d+", t)
        if nums:
            try:
                n = int(nums[0])
                # numeric scale interpreted below
                if n <= 3:
                    return "low"
                if n <= 7:
                    return "medium"
                return "critical"
            except:
                pass

        return None

    def ai_reply(self, message):
        self.log("AI", message)
        self.speak(message)

    def extract_body_part(self, text):
        body_parts = ["سر", "سینہ", "پیٹ", "پیر", "جاں", "کولہے", "بازو", "کمر", "گردن", "پیٹھ", "تینڈی", "پیٹ", "پیٹھ"]
        for part in body_parts:
            # match exact or common Urdu suffix variations (e.g., 'سینہ' -> 'سینے')
            if part in text or (part + 'ے') in text or (part[:-1] + 'ے') in text:
                return part
        keywords = {
            "chest": "سینہ",
            "stomach": "پیٹ",
            "head": "سر",
            "back": "پیٹھ",
            "arm": "بازو",
            "leg": "پیر",
            "neck": "گردن"
        }
        for eng, ur in keywords.items():
            if eng in text:
                return ur
        return ""

    def generate_follow_ups_from_rules(self, location, match=None):
        """Create targeted follow-up questions based on disease rules matching the given location.
        If a `match` dict (from `match_disease_rule`) is provided, use disease-specific questions.
        Returns True if any targeted questions were generated, False otherwise."""
        
        if match and match.get('rule'):
            disease_name = match['rule'].get('disease', '')
            self.detected_disease = disease_name
            
            # Get disease category for specific follow-ups
            # prefer exact rule name match (normalized), then category
            norm_name = disease_name.strip().lower()
            if norm_name in self.disease_followups:
                followup_set = self.disease_followups[norm_name]
                self.follow_up_questions = followup_set["questions"]
                self.follow_up_keys = followup_set["keys"]
                return True

            category = self.get_disease_category(disease_name)
            if category and category in self.disease_followups:
                followup_set = self.disease_followups[category]
                self.follow_up_questions = followup_set["questions"]
                self.follow_up_keys = followup_set["keys"]
                return True
        
        # Fallback to generic follow-ups
        self.follow_up_questions = [
            "یہ درد کب شروع ہوا؟",
            "کیا درد مستقل ہے یا وقفے وقفے سے ہوتا ہے؟",
            "کیا آپ کو بخار یا چکر محسوس ہو رہا ہے؟",
            "کیا کوئی چیز اس درد کو بہتر یا خراب کرتی ہے؟",
            "براہِ کرم بتائیں درد کی شدت کیا ہے؟ کم، درمیانہ، یا شدید؟"
        ]
        self.follow_up_keys = ["duration", "pattern", "associated", "improvement", "severity"]
        return True


    def finalize_triage(self):
        matched = self.match_disease_rule()
        if matched:
            rule = matched.get('rule', matched)
            # set disease name from rule
            self.patient_data['symptom'] = rule.get('disease', self.patient_data.get('symptom',''))
            self.detected_disease = rule.get('disease', '')
            
            # Map backend urgency to internal levels
            u = rule.get('urgency', '').strip().upper()
            if u == 'RED' or u == 'CRITICAL':
                new_level = 'RED'
            elif u == 'GREEN' or u == 'LOW':
                new_level = 'GREEN'
            else:
                new_level = 'YELLOW'
            # Respect patient-reported criticality: choose the more urgent level
            order = {'GREEN': 0, 'YELLOW': 1, 'RED': 2}
            if order.get(new_level, 0) > order.get(self.urgency_level, 0):
                self.urgency_level = new_level
            self.patient_data['specialist'] = rule.get('specialist', '')
            self.patient_data['care'] = rule.get('care', '')
            return True

        # If no disease rule matched, keep any patient-reported urgency (if set),
        # otherwise default to GREEN.
        if not self.urgency_level:
            self.urgency_level = 'GREEN'
        return True

    def build_analysis_summary(self):
        summary = []
        summary.append("میں نے آپ کی صورتحال کا مکمل جائزہ لے لیا ہے۔")
        
        # Mention the detected disease
        if self.detected_disease:
            summary.append(f"ممکنہ حالت: {self.detected_disease}")
        
        if self.patient_data.get('location'):
            summary.append(f"درد کا مقام: {self.patient_data['location']}")
        if self.patient_data.get('duration'):
            summary.append(f"درد کی مدت: {self.patient_data['duration']}")
        if self.patient_data.get('severity'):
            summary.append(f"شدت: {self.patient_data['severity']}")
        if self.patient_data.get('associated'):
            summary.append(f"متعلقہ علامات: {self.patient_data['associated']}")
        if self.patient_data.get('additional'):
            summary.append(f"اضافی معلومات: {self.patient_data['additional']}")

        # Only provide homecare for GREEN urgency
        if self.urgency_level == 'GREEN':
            summary.append("خطرے کی سطح: کم (سبز) - یہ شدید نہیں ہے۔")
            care_text = self.patient_data.get('care') or self.infer_green_home_care()
            summary.append(f"گھر پر دیکھ بھال: {care_text}")
            summary.append("اللہ حافظ۔")
        elif self.urgency_level == 'YELLOW':
            summary.append("خطرے کی سطح: درمیانی (زرد) - آپ کی علامات خطرناک سمت کی طرف جا سکتی ہیں۔")
            care_text = self.patient_data.get('care') or self.infer_green_home_care()
            summary.append(f"گھر پر دیکھ بھال: {care_text}")
            summary.append("میں آپ کو ڈاکٹر سے ملاقات بک کرنے کی سفارش کرتا ہوں۔")
        else:  # RED
            summary.append("خطرے کی سطح: شدید (سرخ) - یہ صورتحال بہت خطرناک ہے۔")
            summary.append("میں آپ کو فوری طور پر ڈاکٹر سے ملاقات بک کرنے کی سفارش کرتا ہوں۔")
            if self.patient_data.get('specialist'):
                summary.append(f"متخصص: {self.patient_data['specialist']}")

        return ' '.join(summary)

    def match_disease_rule(self):
        # Build token set from patient data
        text = ' '.join([
            self.patient_data.get('symptom', ''),
            self.patient_data.get('location', ''),
            self.patient_data.get('duration', ''),
            self.patient_data.get('severity', ''),
            self.patient_data.get('associated', ''),
            self.patient_data.get('additional', '')
        ])
        patient_tokens = self.tokenize(text)
        best = None
        best_score = 0.0
        for rule in self.disease_rules:
            # tokenize rule symptoms (Urdu)
            rule_symptoms = [s.strip() for s in rule.get('symptoms','').split('،') if s.strip()]
            if not rule_symptoms:
                continue
            rule_tokens = set()
            for s in rule_symptoms:
                rule_tokens.update(self.tokenize(s))

            # Also consider English/keyword column and disease name so English inputs match
            keywords_field = rule.get('keywords', '') or ''
            if keywords_field:
                # split on commas and whitespace
                kparts = [p.strip() for p in re.split('[,؛،]', keywords_field) if p.strip()]
                for kp in kparts:
                    rule_tokens.update(self.tokenize(kp))

            # include disease name tokens (helps when user says disease in English)
            rule_tokens.update(self.tokenize(rule.get('disease', '')))

            if not rule_tokens:
                continue

            matched = patient_tokens.intersection(rule_tokens)
            score = len(matched) / max(len(rule_tokens), 1)

            # Boost score if body-part/location tokens align (Urdu priority)
            body_parts = set(["سر", "سینہ", "پیٹ", "پیر", "بازو", "کمر", "گردن", "پیٹھ", "دائیں", "بائیں", "بازو"])
            # tokens for patient's stated location (if any)
            loc_tokens = self.tokenize(self.patient_data.get('location', ''))
            # check for overlap with rule text (full symptoms string)
            rule_text = ' '.join([rule.get('symptoms',''), rule.get('disease',''), rule.get('keywords','')])
            rule_text_tokens = self.tokenize(rule_text)

            if patient_tokens & body_parts:
                # if rule also mentions body part tokens, boost
                if (patient_tokens & rule_text_tokens) or (loc_tokens & rule_text_tokens):
                    score = score * 1.6
            if score > best_score:
                best_score = score
                best = {
                    'rule': rule,
                    'score': score,
                    'matched': list(matched),
                    'missing': [s for s in rule_symptoms if not (self.tokenize(s) & patient_tokens)]
                }

        return best

    def get_disease_category(self, disease_name):
        """Get the category key for disease-specific follow-ups"""
        name_lower = disease_name.lower()
        if "dengue" in name_lower:
            return "dengue"
        elif "flu" in name_lower or "influenza" in name_lower:
            return "flu"
        elif "cold" in name_lower:
            return "cold"
        elif "allergy" in name_lower:
            return "allergy"
        elif "throat" in name_lower or "pharyngitis" in name_lower:
            return "throat"
        elif "cardiac" in name_lower or "heart" in name_lower or "ischemic" in name_lower:
            return "cardiac"
        elif "diabetes" in name_lower:
            return "diabetes"
        elif "stroke" in name_lower:
            return "stroke"
        elif "breathing" in name_lower:
            return "breathing"
        elif "orthopedic" in name_lower or "sprain" in name_lower or "joint" in name_lower:
            return "orthopedic"
        elif "food poisoning" in name_lower or "gastroenteritis" in name_lower:
            return "food_poisoning"
        return None

    def generate_downloadable_report(self):
        spec_map = {"headache": "Neurologist", "fever": "General physician", "chest": "Cardiologist", "stomach": "Gastroenterologist"}
        if not self.patient_data.get('specialist'):
            self.patient_data['specialist'] = spec_map.get(self.patient_data['symptom'].lower(), "General physician")
        self.patient_data['time'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if self.patient_data['name']:
            filename_base = self.patient_data['name'].strip().replace(' ', '_')
        else:
            filename_base = 'medinova'
        report_note = ""
        if self.urgency_level == "GREEN":
            report_note = "آپ کی صورتحال کے مطابق یہ زیادہ خطرناک نہیں معلوم ہوتی۔"
        elif self.urgency_level == "YELLOW":
            report_note = "آپ کی صورتحال کچھ خطرناک سمت کی طرف اشارہ کرتی ہے، اگر یہ جاری رہا تو مسائل بڑھ سکتے ہیں۔"
        else:
            report_note = "آپ کی صورتحال شدید خطرے کی جانب اشارہ کرتی ہے اور فوری طبی توجہ ضروری ہے۔"

        lines = [
            ("نام", self.patient_data['name']),
            ("عمر", self.patient_data['age']),
            ("علامات", self.patient_data['symptom']),
            ("جسمانی مقام", self.patient_data['location']),
            ("مدت", self.patient_data['duration']),
            ("شدت", self.patient_data['severity']),
            ("متعلقہ علامات", self.patient_data['associated']),
            ("اضافی معلومات", self.patient_data['additional']),
            ("خطرے کی سطح", self.urgency_level),
            ("ماہر", self.patient_data['specialist']),
            ("تیاری کا وقت", self.patient_data['time']),
            ("رپورٹ نوٹ", report_note)
        ]

        path = f"{filename_base}_report_{int(time.time())}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("Medinova صحت کی رپورٹ\n")
            f.write("=" * 40 + "\n\n")
            for label, value in lines:
                f.write(f"{label}: {value}\n")

        self.log("AI", f"DOWNLOADABLE REPORT READY: {path}")
        self.speak("آپ کی رپورٹ تیار ہے۔ اللہ حافظ۔")
        messagebox.showinfo("Report Ready", f"Saved to {path}")

    def pause_and_breathe(self):
        if self.is_breathing: return
        self.is_breathing = True
        self.log("AI", "آرام سے سانس لیں۔ (Breathe...)")
        self.avatar_canvas.itemconfig(self.avatar_face, text="🧘")
        def anim():
            for _ in range(20):
                if not self.is_breathing: break
                time.sleep(0.5)
            self.avatar_canvas.itemconfig(self.avatar_face, text="😊")
            self.is_breathing = False
        threading.Thread(target=anim).start()

    def print_summary(self):
        messagebox.showinfo("Printing", "Printing Summary...")

if __name__ == "__main__":
    root = tk.Tk(); app = MedinovaKiosk(root); root.mainloop()
