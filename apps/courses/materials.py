"""Checking and converting the files tutors upload.

Files are identified by their contents, not just their name, so a renamed
program is refused. Word and PowerPoint files get a readable HTML copy that
students can study in the browser on any phone, and the original stays
available for download if the tutor allows it.
"""
import html
import io
import zipfile

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.core.utils import sanitize_html

from .models import CourseMaterial

ACCEPTED = '.pdf,.docx,.pptx,.xlsx,.html,.htm,.jpg,.jpeg,.png,.webp'
LEGACY = {'doc': 'Word 97-2003 (.doc)', 'ppt': 'PowerPoint 97-2003 (.ppt)', 'xls': 'Excel 97-2003 (.xls)'}


def _ext(name):
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


def detect_kind(upload):
    """Return the CourseMaterial.Kind for an uploaded file, or raise
    ValidationError with a message a tutor can act on."""
    ext = _ext(upload.name)
    if ext in LEGACY:
        raise ValidationError(f'{LEGACY[ext]} files are not supported. Open the file and use '
                              f'"Save as" to save it in the newer format (.{ext}x), then upload that.')
    if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f'This file is larger than {settings.MAX_UPLOAD_MB} MB. Try compressing it.')
    upload.seek(0)
    head = upload.read(8)
    upload.seek(0)

    if ext == 'pdf':
        if not head.startswith(b'%PDF-'):
            raise ValidationError('This does not look like a real PDF file.')
        return CourseMaterial.Kind.PDF
    if ext in ('docx', 'pptx', 'xlsx'):
        if not head.startswith(b'PK'):
            raise ValidationError('This file is damaged or is not really an Office document.')
        try:
            with zipfile.ZipFile(upload) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            raise ValidationError('This file is damaged or is not really an Office document.')
        finally:
            upload.seek(0)
        marker = {'docx': 'word/document.xml', 'pptx': 'ppt/presentation.xml', 'xlsx': 'xl/workbook.xml'}[ext]
        if marker not in names:
            raise ValidationError(f'This file is not a valid .{ext} document.')
        return {'docx': CourseMaterial.Kind.WORD, 'pptx': CourseMaterial.Kind.SLIDES,
                'xlsx': CourseMaterial.Kind.SHEET}[ext]
    if ext in ('html', 'htm'):
        try:
            upload.read().decode('utf-8')
        except UnicodeDecodeError:
            raise ValidationError('Save the HTML file with UTF-8 encoding and upload it again.')
        finally:
            upload.seek(0)
        return CourseMaterial.Kind.HTML
    if ext in ('jpg', 'jpeg', 'png', 'webp'):
        from PIL import Image
        try:
            Image.open(upload).verify()
        except Exception:  # noqa: BLE001
            raise ValidationError('This image could not be read.')
        finally:
            upload.seek(0)
        return CourseMaterial.Kind.IMAGE
    raise ValidationError('Upload a PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML or image file.')


def readable_html(upload, kind):
    """A cleaned HTML copy for reading in the browser. Never raises: if a
    conversion fails, students can still download the original."""
    upload.seek(0)
    try:
        if kind == CourseMaterial.Kind.WORD:
            import mammoth
            result = mammoth.convert_to_html(upload)
            return sanitize_html(result.value)
        if kind == CourseMaterial.Kind.SLIDES:
            return sanitize_html(_pptx_to_html(upload))
        if kind == CourseMaterial.Kind.HTML:
            return sanitize_html(upload.read().decode('utf-8'))
    except Exception:  # noqa: BLE001
        return ''
    finally:
        upload.seek(0)
    return ''


def _pptx_to_html(upload):
    from pptx import Presentation
    deck = Presentation(io.BytesIO(upload.read()))
    parts = []
    for n, slide in enumerate(deck.slides, start=1):
        title = ''
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            title = slide.shapes.title.text_frame.text.strip()
        bullets = []
        for shape in slide.shapes:
            if shape == slide.shapes.title or not getattr(shape, 'has_text_frame', False):
                continue
            for para in shape.text_frame.paragraphs:
                text = ''.join(run.text for run in para.runs).strip()
                if text:
                    bullets.append(f'<li>{html.escape(text)}</li>')
        notes = ''
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            note_text = slide.notes_slide.notes_text_frame.text.strip()
            if note_text:
                notes = f'<p class="slide-notes"><strong>Notes:</strong> {html.escape(note_text)}</p>'
        parts.append(f'<section class="slide"><div class="slide-no">Slide {n}</div>'
                     f'<h3>{html.escape(title) or "Untitled slide"}</h3>'
                     f'{"<ul>" + "".join(bullets) + "</ul>" if bullets else ""}{notes}</section>')
    return ''.join(parts)
