from main import MedinovaKiosk
import tkinter as tk
root = tk.Tk(); root.withdraw()
app = MedinovaKiosk(root)
# Test dengue-like input
print('Loaded disease rules:', len(app.disease_rules))
if app.disease_rules:
	print('Sample rule keys:', list(app.disease_rules[0].keys()))
	print('Sample first rule disease:', app.disease_rules[0].get('disease'))

app.patient_data['symptom'] = 'بخار جسم میں درد آنکھوں کے پیچھے درد'
app.patient_data['location'] = ''
app.patient_data['duration'] = ''
app.patient_data['severity'] = ''
app.patient_data['associated'] = ''
print('Patient tokens:', app.tokenize('بخار جسم میں درد آنکھوں کے پیچھے درد'))
match = app.match_disease_rule()
print('Match:', match)
