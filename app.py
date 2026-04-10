import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", str(BASE_DIR))).resolve()
DATA_DIR = STORAGE_DIR / "data"
UPLOADS_DIR = STORAGE_DIR / "uploads"
DATABASE_FILE = DATA_DIR / "materials.db"

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
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                extension TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_material(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "tags": json.loads(row["tags"]),
        "original_filename": row["original_filename"],
        "stored_filename": row["stored_filename"],
        "extension": row["extension"],
        "download_url": f"/downloads/{row['stored_filename']}",
        "uploaded_at": row["uploaded_at"],
    }


def load_materials(query: str = "") -> list[dict]:
    ensure_storage()
    sql = """
        SELECT
            id,
            title,
            description,
            tags,
            original_filename,
            stored_filename,
            extension,
            uploaded_at
        FROM materials
    """
    params: list[str] = []

    if query:
        like_query = f"%{query}%"
        sql += """
            WHERE lower(title) LIKE ?
            OR lower(description) LIKE ?
            OR lower(tags) LIKE ?
        """
        params.extend([like_query, like_query, like_query])

    sql += " ORDER BY uploaded_at DESC"

    with get_db_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    return [row_to_material(row) for row in rows]


def save_material(material: dict) -> None:
    ensure_storage()
    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO materials (
                id,
                title,
                description,
                tags,
                original_filename,
                stored_filename,
                extension,
                uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material["id"],
                material["title"],
                material["description"],
                json.dumps(material["tags"], ensure_ascii=False),
                material["original_filename"],
                material["stored_filename"],
                material["extension"],
                material["uploaded_at"],
            ),
        )
        connection.commit()


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
    return jsonify(load_materials(query))


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

    original_name = uploaded_file.filename.strip()
    extension = original_name.rsplit(".", 1)[1].lower()
    safe_name = secure_filename(original_name)
    display_name = safe_name or original_name
    material_id = str(uuid.uuid4())
    stored_name = f"{material_id}.{extension}"
    uploaded_file.save(UPLOADS_DIR / stored_name)

    material = {
        "id": material_id,
        "title": title,
        "description": description,
        "tags": tags,
        "original_filename": display_name,
        "stored_filename": stored_name,
        "extension": extension.upper(),
        "download_url": f"/downloads/{stored_name}",
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    save_material(material)

    return jsonify(material), 201


@app.get("/downloads/<path:filename>")
def download_file(filename: str):
    return send_from_directory(UPLOADS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    ensure_storage()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
