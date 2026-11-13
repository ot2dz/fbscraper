import pathlib

path = pathlib.Path("app/templates/settings.html")
source = path.read_text(encoding="utf-8")

marker = "{% endblock %}"
index = source.rfind(marker)
body = source[:index]

scripts = """<script>
document.getElementById('aiTestBtn').addEventListener('click', async () => {
  const out = document.getElementById('aiTestOut');
  out.style.display = 'block';
  out.textContent = 'جارٍ حفظ الإعدادات ثم التحليل...';
  try {
    const form = document.querySelector('form[action="/settings"]');
    if (form) {
      await fetch('/settings', { method: 'POST', body: new URLSearchParams(new FormData(form)) });
    }
    const response = await fetch('/api/ai/test', { method: 'POST' });
    const data = await response.json();
    out.textContent = data.text || JSON.stringify(data.analysis, null, 2);
  } catch (error) {
    out.textContent = 'خطأ في الاتصال: ' + error;
  }
});

document.getElementById('diagBtn').addEventListener('click', async () => {
  const out = document.getElementById('diagOut');
  out.style.display = 'block';
  out.textContent = 'جارٍ الفحص...';
  try {
    const response = await fetch('/api/bot/diagnostics');
    const data = await response.json();
    out.textContent = JSON.stringify(data, null, 2);
    if (data.webhook && data.webhook.url) {
      await fetch('/api/bot/restart', { method: 'POST' });
      out.textContent += '\\n\\nتم حذف webhook وإعادة تشغيل الاستقبال. أرسل /start الآن.';
    }
  } catch (error) {
    out.textContent = 'خطأ في الاتصال: ' + error;
  }
});
</script>

"""

path.write_text(body + scripts + marker + "\n", encoding="utf-8")
print("settings scripts moved inside block")
