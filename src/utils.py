import io
import threading
from PIL import Image
from pynput import mouse
from typing import Optional, Tuple


def capture_single_click() -> Optional[Tuple[int, int]]:
    """
    Waits for the user to perform a single left mouse click and returns its screen coordinates.

    Returns:
        tuple(int, int) or None: (x, y) coordinates of the click, or None if interrupted.
    """
    position = None
    clicked = threading.Event()

    def on_click(x: int, y: int, button: mouse.Button, pressed: bool):
        nonlocal position
        if pressed and button == mouse.Button.left:
            position = (x, y)
            clicked.set()
            return False  # Stop listener

    with mouse.Listener(on_click=on_click) as listener:
        clicked.wait()  # Wait for click

    return position


def compress_for_api(
    img: Image.Image,
    max_width: int = 1280,
    quality: int = 85,
) -> Image.Image:
    """Resize and convert *img* to a smaller form before sending to Gemini.

    Full-resolution screenshots can be 2–5 MB. Gemini's vision models work
    well at 1280 px wide — sending anything larger just increases upload time
    and token cost with no accuracy benefit.

    The image is:
    1. Resized proportionally so the width is at most *max_width* pixels.
       Portrait images are left untouched if already narrower than *max_width*.
    2. Converted to RGB (drops any alpha channel that PNG may carry).
    3. Re-encoded as JPEG at *quality* and decoded back into a PIL Image so
       callers receive a standard Image object ready to pass to Gemini just
       like before — no change needed at the call site beyond swapping
       ``Image.open(path)`` for ``compress_for_api(Image.open(path))``.

    Parameters
    ----------
    img:
        Source PIL Image (any mode, any size).
    max_width:
        Maximum pixel width of the output image. Defaults to 1280.
    quality:
        JPEG compression quality (1–95). Defaults to 85 — good visual
        fidelity with ~60–80 % size reduction vs a full-res PNG.

    Returns
    -------
    PIL.Image.Image
        A resized, JPEG-compressed image ready to pass directly to Gemini.

    Examples
    --------
    Replace every ``Image.open(path)`` that feeds Gemini with:

        from utils import compress_for_api
        image = compress_for_api(Image.open(path))
        generate_content_with_fallback([prompt, image])
    """
    # Step 1 — resize if wider than max_width
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # Step 2 — drop alpha channel; JPEG does not support transparency
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Step 3 — encode as JPEG then decode back to a PIL Image
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return Image.open(buf)


def compress_for_classification(
    img: Image.Image,
    max_width: int = 800,
    quality: int = 50,
) -> Image.Image:
    """Aggressively compress *img* for the classification step only.

    Classification only needs to detect whether the content is code, SQL, or
    text — it doesn't need to read fine details.  Using 800 px / quality 50
    produces images ~85-90% smaller than raw PNGs, saving significant tokens
    on the cheapest call in the pipeline.

    Returns a PIL Image just like compress_for_api().
    """
    return compress_for_api(img, max_width=max_width, quality=quality)