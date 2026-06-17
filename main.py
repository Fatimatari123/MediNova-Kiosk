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
import re
import json
import subprocess
from datetime import datetime
from fpdf import FPDF
from static_ffmpeg import add_paths
from db_query import MediNovaDB
from vector_engine import MediNovaVectorEngine

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
        self.is_recording = False
        self.is_breathing = False
        self.conversation_started = False
        self.mic_pulse_id = None
        self.mic_pulse_step = 0
        self.conversation_history = []
        self.last_pdf = None  # Add this line to store the last generated report path
        self.vector_engine = MediNovaVectorEngine(os.path.join(os.path.dirname(__file__), "data", "Diseases_Symptoms.csv"))

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
        
        self.mic_instruction = tk.Label(mic_section, text="Click the mic icon to start your consultation", font=("Arial", 10, "bold"), bg=COLOR_WHITE, fg=COLOR_OCEAN)
        self.mic_instruction.pack(pady=(10, 0))

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
        # 4. Control Panel (FOOTER)
        footer = tk.Frame(self.root, bg=COLOR_LIGHT_BG, height=100)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        btn_row = tk.Frame(footer, bg=COLOR_LIGHT_BG)
        btn_row.pack(expand=True, pady=10)

        tk.Button(btn_row, text="🧘 Breathe", font=("Arial", 11), bg=COLOR_TEAL, fg=COLOR_WHITE, command=self.pause_and_breathe, relief=tk.FLAT, padx=15, pady=8).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_row, text="📄 Scan", font=("Arial", 11), bg=COLOR_TEAL, fg=COLOR_WHITE, relief=tk.FLAT, padx=15, pady=8).pack(side=tk.LEFT, padx=10)
        # Updated Print Button
        tk.Button(btn_row, text="🖨️ Print Report", font=("Arial", 11), bg="#95a5a6", fg=COLOR_WHITE, relief=tk.FLAT, command=self.print_summary, padx=15, pady=8).pack(side=tk.LEFT, padx=10)
    def log(self, sender, message, tag=None):
        self.chat_log.config(state=tk.NORMAL)
        disp = "Medinova (AI)" if sender=="AI" else "Patient (User)"
        self.chat_log.insert(tk.END, f"{disp}:\n", "ai" if sender=="AI" else "usr")
        self.chat_log.insert(tk.END, f"{message}\n\n", tag if tag else None)
        self.chat_log.config(state=tk.DISABLED); self.chat_log.see(tk.END)
    def speak(self, text):
        try:
            # Strip markdown symbols for natural TTS
            import re
            clean_text = re.sub(r'[\*#_~`]', '', text)
            self.status_lbl.config(text="Speaking...")
            tts = gTTS(text=clean_text, lang='ur')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                tmp = fp.name
                tts.save(tmp)
            aud = AudioSegment.from_mp3(tmp)
            
            # Increase speech speed for natural/fluent voice
            aud = aud._spawn(aud.raw_data, overrides={"frame_rate": int(aud.frame_rate * 1.2)}).set_frame_rate(aud.frame_rate)
            proc = tmp.replace(".mp3", "_p.wav")
            aud.export(proc, format="wav")
            
            pygame.mixer.music.load(proc)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): 
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
            try: 
                os.remove(tmp)
                os.remove(proc)
            except: 
                pass
            self.status_lbl.config(text="Ready")
        except Exception as e: 
            print(f"TTS Error: {e}")
    def initial_sequence(self):
        d = "یہ ایک AI میڈیکل اسسٹنٹ ہے، ڈاکٹر نہیں۔ یہ صرف عمومی رہنمائی فراہم کرتا ہے۔ کسی بھی سنجیدہ مسئلے کی صورت میں فوراً ڈاکٹر سے رجوع کریں۔"
        self.log("AI", d); self.speak(d)
        g = "السلام علیکم! براہ کرم مجھے اپنا نام، عمر اور اپنی طبی علامات کے بارے میں تفصیل سے بتائیں۔"
        self.log("AI", g); self.speak(g)

    def handle_mic_click(self):
        if self.is_recording:
            self.is_recording = False
            self.mic_instruction.config(text="Conversation paused. Click mic to resume.")
            self.stop_mic_animation()
            return

        self.is_recording = True
        self.mic_instruction.config(text="Conversation started. Preparing the AI greeting...")
        self.start_mic_animation()

        if not self.conversation_started:
            self.conversation_started = True
            self.conversation_history = []
            self.patient_data = {"name": "", "age": "", "symptom": "", "location": "", "duration": "", "severity": "", "associated": "", "specialist": "", "additional": "", "care": "", "time": ""}
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
            self.conversation_history.append({"role": "user", "content": user_text})
            self.dialog_state = "collect_follow_up"
            return self.get_ai_follow_up()

        self.ai_reply("معاف کیجئے، میں سمجھ نہیں سکی۔ کیا آپ ٹھیک ہیں یا آپ کو جسم کے کسی حصے میں درد ہے؟")
        return True

    def handle_follow_up_response(self, user_text):
        self.conversation_history.append({"role": "user", "content": user_text})
        return self.get_ai_follow_up()

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

    def call_groq(self, messages):
        if not client:
            return "معذرت، میں ابھی کام نہیں کر رہی۔"
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=512
            )
            raw_reply = response.choices[0].message.content
            # Surgical Script Filter: Removes Chinese (CJK) and Hindi (Devanagari) characters
            import re
            clean_reply = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\u0900-\u097f]', '', raw_reply)
            return clean_reply.strip()
        except Exception as e:
            print(f"!!! GROQ CONNECTION ERROR !!!")
            print(f"Details: {e}")
            return "معذرت، سرور کے ساتھ رابطہ کرنے میں مسئلہ پیش آیا۔"

    def get_ai_follow_up(self):
        # Extract full conversation history for semantic context
        all_text = " ".join([m["content"] for m in self.conversation_history if m["role"] == "user"])
        
        # Use Multilingual Semantic search (RAG) with enhanced formatting and confidence filtering
        valid_matches = self.vector_engine.get_valid_matches(all_text, top_n=5)
        
        if not valid_matches:
            rag_context = "No relevant medical conditions found in the database."
            top_diagnosis = "Unidentified Condition"
            top_treatments = "Consultation with a medical professional"
            rag_guidance = "CRITICAL RULE: The symptoms were NOT found in the dataset. DO NOT HALLUCINATE. You MUST respond exactly with the Urdu translation of: 'Sorry, I could not find sufficient information related to your symptoms in the available medical knowledge base. Please consult a qualified healthcare professional for proper medical advice.' and then continue the conversation professionally."
        else:
            rag_context = self.vector_engine.format_for_llm(valid_matches)
            top_diagnosis = valid_matches[0]["name"]
            top_treatments = valid_matches[0]["treatments"]
            rag_guidance = """CRITICAL RULE: A match WAS found in the dataset. You MUST use it as supporting evidence and include:
- The matched condition
- Supporting symptoms from the dataset
- Possible treatments from the dataset
- Recommendations from the dataset"""

        system_prompt = f"""You are an expert AI Medical Assistant for MediNova Health Kiosk. Your role is to:
1. Conduct a professional clinical interview
2. Gather patient demographics (Name, Age)
3. Collect comprehensive symptom details
4. Provide evidence-based medical guidance using the knowledge base
5. Guide toward appropriate specialist referral

CLINICAL KNOWLEDGE BASE (RAG - Retrieved from Medical Database):
{rag_context}

CONVERSATION PROTOCOL & RULES:
- Ask ONLY ONE clear follow-up question at a time. Wait for response. DO NOT ask multiple questions in a single message.
- {rag_guidance}
- COMPARE previous symptoms, previous urgency, previous assessments, and previous recommendations with current ones (if past history is provided in earlier contexts).
- Improve your assessment accuracy by using current symptoms, follow-up answers, dataset evidence, and patient history combined.
- Confirm patient identity/details early
- Ask specific follow-up questions about symptom onset, duration, severity
- Map symptoms to the medical conditions in the knowledge base
- Once confident with diagnosis, provide specialist recommendation
- When consultation ends and a report is generated with a specialist referral, YOU MUST remind the patient: "Please bring this report with you when visiting the specialist."
- Be empathetic, professional, and speak in Urdu (script format)
- Do NOT repeat information already provided

CRITICAL FORMATTING RULES:
- Speak ONLY in Urdu script (no English except medical terms like disease/specialist names)
- When ready to provide diagnosis, include this exact JSON structure:
--- BILINGUAL REPORT DATA ---
{{
  "diagnosed_disease": "{top_diagnosis}",
  "specialist_name": "[APPROPRIATE SPECIALIST]",
  "appointment_time": "[SUGGESTED TIME]",
  "patient_name": "[EXTRACTED NAME]",
  "patient_age": "[EXTRACTED AGE]",
  "detailed_analysis": "[CLINICAL SUMMARY]",
  "recommended_treatments": "{top_treatments}"
}}
--- END BILINGUAL REPORT DATA ---

- When diagnosis is complete and user confirms, append: [TRIGGER_BOOKING: TRUE]
- Extract and preserve patient data using: [EXTRACTED_DATA: {{"name": "[Name]", "age": "[Age]"}}]
"""
        messages = [{"role": "system", "content": system_prompt}] + self.conversation_history
        reply = self.call_groq(messages)
        
        # Data Extraction logic
        ext_match = re.search(r'\[EXTRACTED_DATA: (\{.*?\})\]', reply)
        if ext_match:
            try:
                ext_data = json.loads(ext_match.group(1))
                if ext_data.get("name") and "[" not in ext_data["name"]:
                    self.patient_data["name"] = ext_data["name"]
                if ext_data.get("age") and "[" not in ext_data["age"]:
                    self.patient_data["age"] = ext_data["age"]
            except: pass
            reply = re.sub(r'\[EXTRACTED_DATA: \{.*?\}\]', '', reply).strip()

        if "[TRIGGER_BOOKING: TRUE]" in reply or "--- BILINGUAL REPORT DATA ---" in reply:
            self.finalize_bilingual_conversation(reply)
            return False
            
        self.conversation_history.append({"role": "assistant", "content": reply})
        self.ai_reply(reply)
        return True

    def finalize_bilingual_conversation(self, full_reply):
        # Extract the Urdu part for voice/UI and store full reply for reporting
        urdu_summary = full_reply.split("--- BILINGUAL")[0].strip()
        self.ai_reply(urdu_summary)
        self.patient_data['additional'] = full_reply

        # Stop session logic
        self.dialog_state = "idle"
        self.conversation_started = False
        self.is_recording = False

        # If the assistant produced a bilingual report payload, try to generate a PDF
        if "BILINGUAL REPORT DATA" in full_reply or "--- BILINGUAL REPORT DATA ---" in full_reply or "[TRIGGER_FINISH" in full_reply or "[TRIGGER_BOOKING" in full_reply:
            try:
                self.generate_bilingual_pdf_report(full_reply)
            except Exception as e:
                print(f"Error generating bilingual PDF: {e}")

    def generate_bilingual_pdf_report(self, raw_data):
        """Generate a bilingual PDF report from the assistant's raw reply payload."""
        try:
            # Try new bilingual payload first
            match = re.search(r'--- BILINGUAL REPORT DATA ---\s*(\{.*?\})\s*--- END BILINGUAL REPORT DATA ---', raw_data, re.DOTALL)
            if not match:
                # Fallback to older REPORT DATA marker
                match = re.search(r'--- REPORT DATA ---\s*(\{.*?\})\s*--- END REPORT DATA ---', raw_data, re.DOTALL)

            if not match:
                raise ValueError("No valid report data found")

            data = json.loads(match.group(1))

            pdf = FPDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=15)

            # Header
            pdf.set_font("Arial", "B", 18)
            pdf.cell(0, 15, "MediNova Health Consultation Report", ln=True, align="C")
            pdf.set_font("Arial", "I", 10)
            pdf.cell(0, 8, "AI-Assisted Medical Consultation Summary", ln=True, align="C")
            pdf.ln(10)

            # Patient Information
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(0, 102, 153)
            pdf.cell(0, 10, "PATIENT INFORMATION", ln=True)
            pdf.set_text_color(0, 0, 0)

            patient_fields = [
                ("Name", data.get('patient_name', self.patient_data.get('name', 'N/A'))),
                ("Age", data.get('patient_age', self.patient_data.get('age', 'N/A'))),
                ("Date", self.patient_data.get('time', 'N/A'))
            ]

            for label, val in patient_fields:
                pdf.set_font("Arial", "B", 10)
                pdf.cell(40, 8, f"{label}:", 0)
                pdf.set_font("Arial", "", 10)
                pdf.cell(0, 8, str(val), ln=True)

            pdf.ln(5)

            # Clinical Findings
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(0, 102, 153)
            pdf.cell(0, 10, "CLINICAL FINDINGS", ln=True)
            pdf.set_text_color(0, 0, 0)

            diagnosis_fields = [
                ("Diagnosed Condition", data.get('diagnosed_disease', data.get('diagnosed_disease', 'Pending'))),
                ("Recommended Specialist", data.get('specialist_name', 'General Practitioner')),
                ("Recommended Treatments", data.get('recommended_treatments', data.get('recommended_treatments', 'Medical consultation')))
            ]

            for label, val in diagnosis_fields:
                pdf.set_font("Arial", "B", 10)
                pdf.cell(45, 8, f"{label}:", 0)
                pdf.set_font("Arial", "", 10)
                pdf.multi_cell(0, 8, str(val), border=0)

            # Appointment
            if data.get('appointment_time'):
                pdf.ln(5)
                pdf.set_font("Arial", "B", 12)
                pdf.set_text_color(0, 102, 153)
                pdf.cell(0, 10, "APPOINTMENT SCHEDULED", ln=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Arial", "", 10)
                pdf.cell(45, 8, "Time:", 0)
                pdf.multi_cell(0, 8, str(data.get('appointment_time')))

            # Detailed Analysis
            if data.get('detailed_analysis'):
                pdf.ln(5)
                pdf.set_font("Arial", "B", 12)
                pdf.set_text_color(0, 102, 153)
                pdf.cell(0, 10, "DETAILED ANALYSIS", ln=True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Arial", "", 9)
                pdf.multi_cell(0, 5, str(data.get('detailed_analysis')))

            # Disclaimer
            pdf.ln(10)
            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 6, "IMPORTANT DISCLAIMER", ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", "I", 8)
            pdf.multi_cell(0, 4,
                "This report is AI-generated and based on patient-provided information. "
                "It should NOT replace professional medical diagnosis. "
                "Please present this document to your healthcare specialist during your visit. "
                "Always consult a licensed medical professional for proper diagnosis and treatment."
            )

            # Footer
            pdf.ln(5)
            pdf.set_font("Arial", "I", 8)
            pdf.set_text_color(128, 128, 128)
            pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")

            filename = f"Report_{self.patient_data.get('name', 'Patient').replace(' ', '_')}_{int(time.time())}.pdf"
            pdf.output(filename)
            self.last_pdf = filename
            messagebox.showinfo("Report Ready", f"Professional Report saved as:\n{filename}\n\nPress OK to open for printing.")

            # Try to open the file for user convenience
            try:
                if os.name == 'nt':
                    os.startfile(filename)
                else:
                    subprocess.Popen(['xdg-open', filename])
            except Exception:
                pass

        except Exception as e:
            print(f"PDF Error: {e}")
            messagebox.showerror("Error", f"Could not generate professional PDF.\n\nError: {str(e)}")
            # Save text fallback
            txt_filename = f"Report_{int(time.time())}.txt"
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(raw_data)
            self.last_pdf = txt_filename

    def ai_reply(self, message):
        self.log("AI", message)
        self.speak(message)

    def generate_downloadable_report(self):
        self.patient_data['time'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        filename_base = self.patient_data['name'].strip().replace(' ', '_') or 'medinova'
        
        report_note = ""
        if self.urgency_level == "RED":
            report_note = "یہ صورتحال شدید خطرے کی جانب اشارہ کرتی ہے اور فوری طبی توجہ ضروری ہے۔"
        elif self.urgency_level == "YELLOW":
            report_note = "آپ کی صورتحال کچھ خطرناک سمت کی طرف اشارہ کرتی ہے۔"
        else:
            report_note = "آپ کی صورتحال زیادہ خطرناک نہیں معلوم ہوتی۔"

        lines = [
            ("نام", self.patient_data['name']),
            ("عمر", self.patient_data['age']),
            ("خلاصہ", self.patient_data['additional']),
            ("خطرے کی سطح", self.urgency_level),
            ("وقت", self.patient_data['time']),
            ("نوٹ", report_note)
        ]

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Medinova Health Report", ln=True, align="C")
        pdf.ln(8)
        pdf.set_font("Arial", "", 12)
        for label, value in lines:
            pdf.cell(0, 8, f"{label}: {value}", ln=True)
        
        path = f"{filename_base}_report_{int(time.time())}.pdf"
        try:
            pdf.output(path)
            self.last_pdf = path # Store for Print function
            messagebox.showinfo("Report Ready", f"Saved to {path}")
        except:
            path = path.replace(".pdf", ".txt")
            with open(path, "w", encoding="utf-8") as f:
                for label, value in lines: f.write(f"{label}: {value}\n")
            self.last_pdf = path
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
        if hasattr(self, 'last_pdf') and self.last_pdf and os.path.exists(self.last_pdf):
            try:
                if os.name == 'nt':
                    # Windows default print handler
                    os.startfile(self.last_pdf, "print")
                else:
                    # Linux/Mac fallback
                    subprocess.run(["lpr", self.last_pdf])
                messagebox.showinfo("Printing", "Report sent to the printer successfully.")
            except Exception as e:
                messagebox.showerror("Print Error", f"Could not print the report.\n\nDetails: {str(e)}")
        else:
            messagebox.showwarning("No Report", "No report available to print. Please complete a consultation first.")

if __name__ == "__main__":
    root = tk.Tk()
    app = MedinovaKiosk(root)
    root.mainloop()