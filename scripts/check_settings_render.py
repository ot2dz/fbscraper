import os

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbsettings_render")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app.main import app

with TestClient(app) as client:
    client.post("/login", data={"password": "test123"})
    html = client.get("/settings").text
    print("ai script:", "/api/ai/test" in html)
    print("save before test:", "new FormData(form)" in html)
    print("diag script:", "/api/bot/diagnostics" in html)
    print("script after endblock:", html.rfind("</script>") > html.find("{% endblock %}"))
