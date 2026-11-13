import json
import os

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbai_test")
os.environ.setdefault("ADMIN_PASSWORD", "test123")

from app import db
from app.ai_analyzer import analysis_text, analyze_comments

db.init_db()

sample = [
    {"author": "أمينة", "text": "السعر 2500 دج؟ الجودة ممتازة لكن التوصيل تأخر", "likes": 4},
    {"author": "ياسين", "text": "غالي شوية مقارنة بغيركم", "likes": 1},
]

print("disabled:", analyze_comments(sample))

db.set_setting("ai_enabled", "1")
db.set_setting("ai_api_key", "sk-fake-key-for-test")
db.set_setting("ai_model", "gemini-3.8-flash")
print("fake key:", str(analyze_comments(sample))[:160])

fake_analysis = {
    "summary": "التعليقات تشير إلى إعجاب بالجودة مع تحفظ على السعر والتوصيل.",
    "sentiment": "مختلط",
    "price_mentioned": True,
    "price_details": ["2500 دج"],
    "criticisms": ["السعر مرتفع", "تأخر التوصيل"],
    "questions": ["هل يشمل التوصيل؟"],
    "praise": ["الجودة ممتازة"],
    "recommendations": ["إبراز القيمة مقابل السعر", "تحسين التوصيل"],
    "_meta": {"model": "gemini-3.8-flash", "analyzed": 2, "total": 2},
}
print("---- text ----")
print(analysis_text(fake_analysis))
print("---- json ----")
print(json.dumps(fake_analysis, ensure_ascii=False)[:120])
