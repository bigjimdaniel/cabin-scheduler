from pathlib import Path
import warnings

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError


PHOTO_TYPES = {".jpg": ("JPEG", "image/jpeg"), ".jpeg": ("JPEG", "image/jpeg"), ".png": ("PNG", "image/png"), ".webp": ("WEBP", "image/webp")}


def validate_carousel_image(file):
    expected = PHOTO_TYPES.get(Path(file.name).suffix.lower())
    if not expected:
        raise ValidationError("Choose a JPG, PNG, or WebP photo.")
    if file.size > settings.CAROUSEL_MAX_UPLOAD_BYTES:
        raise ValidationError("Photo must be %(limit)s MB or smaller.", params={"limit": f"{settings.CAROUSEL_MAX_UPLOAD_BYTES / 1048576:g}"})
    try:
        file.open("rb")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file) as image:
                if image.format != expected[0]:
                    raise ValidationError("The photo contents do not match its filename extension.")
                if image.width * image.height > 40_000_000:
                    raise ValidationError("Choose a photo with at most 40 megapixels.")
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("Upload a valid, undamaged JPG, PNG, or WebP photo.")
    finally:
        file.seek(0)
