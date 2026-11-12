"""Bounded image decoding and private filesystem storage."""
from io import BytesIO
from pathlib import Path
from threading import Lock
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False, depth_images=False, aux_images=False, decode_threads=1)
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
_processing_lock = Lock()


def optimize_photo(stream):
    with _processing_lock, warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(stream, formats=["JPEG", "PNG", "WEBP", "HEIF"]) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("La foto supera 16 megapíxeles. Usa la resolución normal de la cámara.")
                if source.width < 100 or source.height < 100:
                    raise ValueError("La foto es demasiado pequeña para leer una orden médica.")
                if source.format != "HEIF" and getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Selecciona una foto estática, no una imagen animada.")
                # JPEG draft decoding avoids allocating full-size phone photos unnecessarily.
                source.draft("RGB", (2500, 2500))
                oriented = ImageOps.exif_transpose(source)
                image = oriented.convert("RGBA") if "A" in oriented.getbands() else oriented.convert("RGB")
                if image.mode == "RGBA":
                    white = Image.new("RGB", image.size, "white")
                    white.paste(image, mask=image.getchannel("A"))
                    image.close()
                    image = white
                if oriented is not source:
                    oriented.close()
                try:
                    image.thumbnail((2500, 2500), Image.Resampling.LANCZOS)
                    image.info.clear()  # no GPS, EXIF, XMP or camera metadata is retained
                    full = BytesIO()
                    image.save(full, "WEBP", quality=88, method=4)
                    width, height = image.size
                    image.thumbnail((360, 460), Image.Resampling.LANCZOS)
                    thumb = BytesIO()
                    image.save(thumb, "WEBP", quality=78, method=3)
                    return full.getvalue(), thumb.getvalue(), width, height
                finally:
                    image.close()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("No se pudo leer la foto. Usa una imagen JPG, PNG, WebP o HEIC válida.") from exc


def private_path(root: Path, storage_key: str, thumbnail=False):
    suffix = ".thumb.webp" if thumbnail else ".webp"
    base = root.resolve()
    path = (base / (storage_key + suffix)).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Ruta de archivo inválida")
    return path
