from app.ai_analyzer import _extract_json

print(_extract_json('```json\n{"a":1,}\n```'))
print(_extract_json('نص قبل {"b":"x"} نص بعد'))
print(_extract_json('{"summary":"نص","criticisms":["a","b",]}'))
