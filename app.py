import os
import re
import time
import json
import tempfile
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
from gtts import gTTS
from pydub import AudioSegment
from vector_engine import MediNovaVectorEngine
from fpdf import FPDF

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Flask(__name__)
CORS(app)

# Configure Groq
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Initialize Vector Engine
CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "Diseases_Symptoms.csv")
vector_engine = MediNovaVectorEngine(CSV_PATH)

# Persistent JSON-based storage
DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "patients")
os.makedirs(DATA_DIR, exist_ok=True)

def save_patient_record(identifier, data):
    file_path = os.path.join(DATA_DIR, f"{identifier}.json")
    records = []
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
    records.append(data)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

def get_patient_history(identifier):
    file_path = os.path.join(DATA_DIR, f"{identifier}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def build_history_context(past_records):
    if not past_records:
        return ""
    lines = ["Patient History (Previous Visits):"]
    for i, rec in enumerate(past_records[-3:], 1):
        lines.append(f"Visit {i}:")
        lines.append(f"  Date: {rec.get('time', 'Unknown')}")
        lines.append(f"  Symptoms: {rec.get('symptom', 'Not recorded')}")
        lines.append(f"  Urgency: {rec.get('urgency', 'GREEN')}")
        if rec.get('additional'):
            lines.append(f"  Previous Assessment: {str(rec.get('additional'))[:300]}")
    lines.append("Compare previous symptoms, urgency, assessments, and recommendations with the current case when relevant.")
    return "\n".join(lines)

# In-memory session state
sessions = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/consultation')
def consultation():
    return render_template('consultation.html')

@app.route('/dashboard')
def dashboard():
    # Load all records for dashboard
    all_history = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(DATA_DIR, filename), 'r', encoding='utf-8') as f:
                all_history.extend(json.load(f))
    # Sort by date
    all_history.sort(key=lambda x: x.get('time', ''), reverse=True)
    return render_template('dashboard.html', history=all_history)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    session_id = data.get("session_id", "default")
    phone = data.get("phone")
    
    # Retrieve history using phone or session_id
    history = get_patient_history(phone if phone and phone != "Voice-Only" else session_id)
    
    sessions[session_id] = {
        "patient": data,
        "history": [],
        "past_records": history,
        "urgency": "GREEN",
        "state": "chatting"
    }
    
    return jsonify({
        "status": "success",
        "has_history": len(history) > 0,
        "last_visit": history[-1] if history else None
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_text = data.get("text", "").strip()
    session_id = data.get("session_id", "default")
    
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not initialized"}), 400
        
    session["history"].append({"role": "user", "content": user_text})
    
    # Context Construction (RAG + History)
    all_user_text = " ".join([m["content"] for m in session["history"] if m["role"] == "user"])
    valid_matches = vector_engine.get_valid_matches(all_user_text, top_n=5)
    history_context = build_history_context(session["past_records"])

    if not valid_matches:
        rag_context = "No relevant medical conditions found in the database."
        rag_guidance = (
            "CRITICAL: Symptoms were NOT found in the dataset. DO NOT HALLUCINATE any diagnosis or treatment. "
            "You MUST respond with the Urdu translation of exactly: "
            "'Sorry, I could not find sufficient information related to your symptoms in the available medical knowledge base. "
            "Please consult a qualified healthcare professional for proper medical advice.' "
            "Then continue the conversation professionally with only ONE follow-up question."
        )
    else:
        rag_context = vector_engine.format_for_llm(valid_matches)
        rag_guidance = (
            "CRITICAL: A dataset match WAS found. Use it as supporting evidence and include when diagnosing: "
            "matched condition, supporting symptoms from the dataset, possible treatment from the dataset, "
            "and recommendation from the dataset."
        )

    system_prompt = f"""# ROLE
AI Medical Assistant.

# STRICT RULES
1. **INTAKE:** Ensure Name/Age are captured first.
2. **ONE QUESTION:** Ask ONLY ONE short follow-up question per turn. Never ask multiple questions in one message.
3. **NO FILLER.**
4. **PURE URDU:** Clean Urdu script. No technical symbols in speech.
5. **DATA USAGE:** Use current symptoms, follow-up answers, dataset evidence, and patient history together for accuracy.
6. **HISTORY:** If previous visits exist, compare previous symptoms, urgency, assessments, and recommendations. Mention when relevant (e.g. similar symptoms in a prior visit).
7. **{rag_guidance}**

# CLINICAL ANALYSIS
{history_context}

# DATASET EVIDENCE (RAG)
{rag_context}

# FINAL RESPONSE FORMAT
If diagnosis is reached:
"آپ کو [Disease Name in English] کی علامات ہیں۔ [Specialist Name in English] سے رجوع کریں۔ کیا اپائنٹمنٹ بک کر دوں؟"

If user says yes:
"آپ کی اپائنٹمنٹ [Specialist Name in English] کے ساتھ [Time in English] پر بک ہو گئی ہے۔ بہتر تشخیص کے لیے براہِ مہربانی یہ رپورٹ ڈاکٹر کے پاس ضرور لے کر جائیں۔ شکریہ۔"

If a specialist referral is included in the final diagnosis, remind the patient in Urdu:
"براہِ مہربانی اس رپورٹ کو لے کر ماہر کے پاس ضرور جائیں۔"

# TECHNICAL (HIDDEN)
[TRIGGER_FINISH: TRUE]
--- REPORT DATA ---
{{
  "diagnosed_disease": "[Disease Name in English]",
  "specialist_name": "[Specialist Name in English]",
  "appointment_time": "[Time in English]",
  "patient_name": "[Name]",
  "patient_age": "[Age]"
}}
--- END REPORT DATA ---
[EXTRACTED_DATA: {{"name": "[Name]", "age": "[Age]"}}]
"""
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}] + session["history"],
            temperature=0.7,
            max_tokens=600
        )
        raw_reply = response.choices[0].message.content
        
        # UI CLEANUP: More aggressive filter to remove JSON/tags
        import re
        ui_display_reply = raw_reply
        # Remove technical tags
        ui_display_reply = re.sub(r'---.*?---', '', ui_display_reply, flags=re.DOTALL)
        ui_display_reply = re.sub(r'\[.*?\]', '', ui_display_reply)
        # Remove JSON-like curly brace blocks
        ui_display_reply = re.sub(r'\{.*?\}', '', ui_display_reply, flags=re.DOTALL)
        # Final Urdu/English script filter
        ui_display_reply = re.sub(r'[^\u0600-\u06FF\u0750-\u077F\ufb50-\ufdff\ufe70-\ufeffA-Za-z0-9\s.,!?:-]', '', ui_display_reply)
        ui_display_reply = ui_display_reply.strip()

        # Data Extraction logic (from raw_reply)
        ext_match = re.search(r'\[EXTRACTED_DATA: (\{.*?\})\]', raw_reply)
        if ext_match:
            try:
                ext_data = json.loads(ext_match.group(1))
                if ext_data.get("name") and "[Name]" not in ext_data["name"]:
                    session["patient"]["name"] = ext_data["name"]
                if ext_data.get("age") and "[Age]" not in ext_data["age"]:
                    session["patient"]["age"] = ext_data["age"]
            except: pass

        is_finished = "[TRIGGER_FINISH: TRUE]" in raw_reply or "--- REPORT DATA ---" in raw_reply
        
        session["history"].append({"role": "assistant", "content": ui_display_reply})
        
        if is_finished:
            session["patient"]["additional"] = raw_reply # Store raw for PDF
            session["patient"]["time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            session["patient"]["symptom"] = user_text
            save_patient_record(session["patient"].get("phone") or session_id, session["patient"])

        return jsonify({
            "reply": ui_display_reply,
            "is_finished": is_finished,
            "urgency": "GREEN"
        })
        
    except Exception as e:
        print(f"Groq Error: {e}")
        return jsonify({"error": "سرور کے ساتھ رابطہ کرنے میں مسئلہ پیش آیا۔"}), 500

@app.route('/api/report/<session_id>')
def generate_report(session_id):
    session = sessions.get(session_id)
    if not session:
        return "Session not found", 404
        
    p = session["patient"]
    raw_data = p.get('additional', '')
    
    pdf = FPDF()
    pdf.add_page()
    
    # Check for REPORT DATA JSON
    try:
        json_match = re.search(r'--- REPORT DATA ---\s*(\{.*?\})\s*--- END REPORT DATA ---', raw_data, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
            
            pdf.set_font("Arial", "B", 18)
            pdf.cell(0, 15, "MediNova Medical Consultation Summary", ln=True, align="C")
            pdf.ln(10)
            
            pdf.set_font("Arial", "B", 12)
            fields = [
                ("Patient Name", data.get('patient_name', p.get('name'))),
                ("Age", data.get('patient_age', p.get('age'))),
                ("Diagnosed Condition", data.get('diagnosed_disease')),
                ("Required Specialist", data.get('specialist_name')),
                ("Appointment Time", data.get('appointment_time'))
            ]
            
            for label, val in fields:
                pdf.set_text_color(50, 50, 50)
                pdf.cell(50, 10, f"{label}:", ln=False)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 10, str(val), ln=True)
            
            pdf.ln(20)
            pdf.set_font("Arial", "I", 10)
            pdf.multi_cell(0, 10, "Disclaimer: This is an AI-generated report and should be verified by a licensed medical professional. Please present this document to your specialist during your visit.")
        else:
            raise ValueError("No JSON found")
            
    except Exception as e:
        print(f"Report Generation Error: {e}")
        # Standard Fallback
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Medinova Health Report", ln=True, align="C")
        pdf.ln(10)
        pdf.set_font("Arial", "", 12)
        fields = [
            ("Name", p.get('name')),
            ("Age", p.get('age')),
            ("Date", p.get('time'))
        ]
        for label, val in fields:
            pdf.cell(0, 10, f"{label}: {val}", ln=True)
        pdf.ln(5)
        pdf.multi_cell(0, 10, "Summary: Please consult a specialist immediately.")
    
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp.name)
    inline = request.args.get('inline') == '1'
    return send_file(
        temp.name,
        mimetype='application/pdf',
        as_attachment=not inline,
        download_name=f"Medinova_Report_{p.get('name') or 'Patient'}.pdf"
    )

@app.route('/api/tts', methods=['POST'])
def tts():
    data = request.json
    text = data.get("text", "")
    try:
        tts = gTTS(text=text, lang='ur')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            mp3_path = fp.name
            tts.save(mp3_path)

        aud = AudioSegment.from_mp3(mp3_path)
        aud = aud._spawn(
            aud.raw_data,
            overrides={"frame_rate": int(aud.frame_rate * 1.2)}
        ).set_frame_rate(aud.frame_rate)

        wav_path = mp3_path.replace(".mp3", "_fast.mp3")
        aud.export(wav_path, format="mp3")
        try:
            os.remove(mp3_path)
        except OSError:
            pass
        return send_file(wav_path, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
