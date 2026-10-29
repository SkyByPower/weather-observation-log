import os
import uuid
from functools import wraps

from flask import abort, current_app
from flask_login import current_user
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from . import login_manager
from .i18n import gettext as _

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "csv", "txt"}

# Файлдың алғашқы байттары кеңейтіміне сәйкес келуі керек (атын ауыстырып жіберуден қорғау)
FILE_SIGNATURES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "webp": (b"RIFF",),
    "pdf": (b"%PDF",),
}


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def has_file(storage):
    return isinstance(storage, FileStorage) and bool(storage.filename)


def file_extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def allowed_file(filename, allowed_extensions):
    return file_extension(filename) in allowed_extensions


def save_upload(storage, subfolder, allowed_extensions):
    """Файлды қауіпсіз атпен сақтап, uploads/ ішіндегі салыстырмалы жолын қайтарады."""
    filename = secure_filename(storage.filename or "")
    if not filename or not allowed_file(filename, allowed_extensions):
        raise ValueError(_("Рұқсат етілмеген файл түрі: {types}", types=", ".join(sorted(allowed_extensions))))

    ext = file_extension(filename)
    signatures = FILE_SIGNATURES.get(ext)
    if signatures:
        head = storage.stream.read(16)
        storage.stream.seek(0)
        if not head.startswith(signatures):
            raise ValueError(_("Файл мазмұны кеңейтіміне сәйкес келмейді."))

    new_name = f"{uuid.uuid4().hex}.{ext}"
    storage.save(os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder, new_name))
    return f"{subfolder}/{new_name}"


def delete_upload(relative_path):
    if not relative_path:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], *relative_path.split("/"))
    if os.path.isfile(path):
        os.remove(path)
