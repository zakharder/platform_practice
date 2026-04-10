import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
MATERIALS_FILE = DATA_DIR / "materials.json"

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "txt",
    "zip",
}


def ensure_storage() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOADS_DIR.mkdir(exist_ok=True)
    if not MATERIALS_FILE.exists():
        MATERIALS_FILE.write_text("[]", encoding="utf-8")


def load_materials():
    ensure_storage()
    try:
        return json.loads(MATERIALS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_materials(materials) -> None:
    MATERIALS_FILE.write_text(
        json.dumps(materials, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def is_api_request() -> bool:
    return request.path.startswith("/api/")


@app.route("/")
def index():
    return render_template("index.html", supported_formats=", ".join(sorted(ALLOWED_EXTENSIONS)).upper())


@app.get("/api/materials")
def get_materials():
    query = normalize_query(request.args.get("q", ""))
    materials = load_materials()

    if query:
        materials = [
            item
            for item in materials
            if query in normalize_query(item["title"])
            or query in normalize_query(item.get("description", ""))
            or any(query in normalize_query(tag) for tag in item.get("tags", []))
        ]

    materials.sort(key=lambda item: item["uploaded_at"], reverse=True)
    return jsonify(materials)


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    if is_api_request():
        return jsonify({"error": "Файл слишком большой. Максимальный размер: 50 МБ."}), 413
    return "Файл слишком большой. Максимальный размер: 50 МБ.", 413


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if is_api_request():
        return jsonify({"error": f"Ошибка сервера при загрузке файла: {error}"}), 500
    raise error


@app.post("/api/materials")
def upload_material():
    uploaded_file = request.files.get("file")
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    tags = [tag.strip() for tag in request.form.get("tags", "").split(",") if tag.strip()]

    if not uploaded_file or uploaded_file.filename == "":
        return jsonify({"error": "Выберите файл для загрузки."}), 400

    if not title:
        return jsonify({"error": "Укажите название материала."}), 400

    if not allowed_file(uploaded_file.filename):
        return jsonify({"error": "Неподдерживаемый формат файла."}), 400

    ensure_storage()

    safe_name = secure_filename(uploaded_file.filename)
    material_id = str(uuid.uuid4())
    extension = safe_name.rsplit(".", 1)[1].lower()
    stored_name = f"{material_id}.{extension}"
    uploaded_file.save(UPLOADS_DIR / stored_name)

    materials = load_materials()
    material = {
        "id": material_id,
        "title": title,
        "description": description,
        "tags": tags,
        "original_filename": safe_name,
        "stored_filename": stored_name,
        "extension": extension.upper(),
        "download_url": f"/downloads/{stored_name}",
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    materials.append(material)
    save_materials(materials)

    return jsonify(material), 201


@app.get("/downloads/<path:filename>")
def download_file(filename: str):
    return send_from_directory(UPLOADS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    ensure_storage()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
