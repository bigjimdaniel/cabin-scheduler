from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


ALLOWED_EXTENSIONS = (
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "pdf", "txt", "csv",
    "jpg", "jpeg", "png", "gif", "webp",
)
PREVIEW_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def validate_document_size(file):
    limit = settings.DOCUMENT_MAX_UPLOAD_BYTES
    if file.size > limit:
        raise ValidationError(
            "Files must be %(limit)s MB or smaller.",
            params={"limit": f"{limit / (1024 * 1024):g}"},
        )
    if file.size == 0:
        raise ValidationError("The file is empty. Choose a file with content.")


def preview_type(filename):
    return PREVIEW_TYPES.get(Path(filename).suffix.lower())
