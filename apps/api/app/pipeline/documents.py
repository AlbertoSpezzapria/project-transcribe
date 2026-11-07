"""Estrazione del testo da documenti: PDF (con OCR per le pagine scansionate),
DOCX, ODT e testo semplice. Il risultato sono paragrafi citabili con la pagina.

Librerie con licenze permissive: pypdfium2 (Apache/BSD), python-docx (MIT);
l'OCR usa il binario tesseract (Apache 2.0) come processo separato.
"""

import logging
import re
import statistics
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

log = logging.getLogger(__name__)

MAX_PARAGRAPH = 1500  # caratteri: oltre si divide per frasi
MIN_PAGE_TEXT = 25  # sotto questa soglia una pagina PDF si considera scansionata
OCR_DPI = 300
_SENTENCE_END = (".", "?", "!", ":", ";", "…", "»", '"')


class ExtractionError(RuntimeError):
    pass


@dataclass
class Paragraph:
    text: str
    page: int | None = None


@dataclass
class Extracted:
    engine: str
    paragraphs: list[Paragraph]
    pages: int | None = None
    ocr_pages: int = 0


# --- Normalizzazione e divisione -------------------------------------------------


def _clean_line(line: str) -> str:
    return re.sub(r"[ \t ]+", " ", line).strip()


def _split_long(text: str) -> list[str]:
    """Divide un paragrafo troppo lungo ai confini di frase."""
    if len(text) <= MAX_PARAGRAPH:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.?!…])\s+", text):
        if current and len(current) + len(sentence) + 1 > MAX_PARAGRAPH:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    # Frasi singole lunghissime (tabelle, elenchi senza punteggiatura): taglio netto
    out: list[str] = []
    for p in parts:
        out.extend(p[i : i + MAX_PARAGRAPH * 2] for i in range(0, len(p), MAX_PARAGRAPH * 2))
    return out


def _is_noise(text: str) -> bool:
    """Numeri di pagina, righe di soli simboli."""
    t = text.strip()
    return (
        len(t) < 2
        or bool(re.fullmatch(r"[\d\W_]{1,8}", t))
        or bool(re.fullmatch(r"(pag(ina)?\.?\s*)?\d+(\s*(di|/)\s*\d+)?", t, re.IGNORECASE))
    )


def lines_to_paragraphs(lines: list[str]) -> list[str]:
    """Ricostruisce i paragrafi da righe di testo impaginato.

    Si va a capo quando c'è una riga vuota, oppure quando la riga precedente chiude
    una frase ed è più corta delle righe piene (ultima riga di un paragrafo).
    Le parole spezzate con il trattino a fine riga vengono riunite.
    """
    lines = [_clean_line(line) for line in lines]
    full = [len(line) for line in lines if line]
    typical = statistics.median(full) if full else 0
    paragraphs: list[str] = []
    current = ""
    for i, line in enumerate(lines):
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if current.endswith("-") and line[:1].islower():
            current = current[:-1] + line
        else:
            current = f"{current} {line}".strip() if current else line
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if line.endswith(_SENTENCE_END) and len(line) < 0.85 * typical and nxt[:1].isupper():
            paragraphs.append(current)
            current = ""
    if current:
        paragraphs.append(current)
    return paragraphs


def _paragraphs(blocks: list[str], page: int | None = None) -> list[Paragraph]:
    out: list[Paragraph] = []
    for block in blocks:
        for part in _split_long(block):
            if not _is_noise(part):
                out.append(Paragraph(part, page))
    return out


# --- PDF ---------------------------------------------------------------------------


def _ocr_image(image) -> str:
    with tempfile.TemporaryDirectory(prefix="ocr-") as tmp:
        img = Path(tmp) / "page.png"
        image.save(img)
        proc = subprocess.run(
            ["tesseract", str(img), "stdout", "-l", "ita+eng", "--psm", "3"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    if proc.returncode != 0:
        raise ExtractionError("OCR non riuscito")
    return proc.stdout


def extract_pdf(path: Path) -> Extracted:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        raise ExtractionError("PDF illeggibile o protetto da password") from exc
    paragraphs: list[Paragraph] = []
    ocr_pages = 0
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            text = page.get_textpage().get_text_range()
            if len(text.strip()) < MIN_PAGE_TEXT:
                # Pagina scansionata: si rende come immagine e si passa all'OCR
                image = page.render(scale=OCR_DPI / 72).to_pil()
                text = _ocr_image(image)
                ocr_pages += 1
            lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            paragraphs.extend(_paragraphs(lines_to_paragraphs(lines), page=i + 1))
        pages = len(pdf)
    finally:
        pdf.close()
    return Extracted("pdf+ocr" if ocr_pages else "pdf", paragraphs, pages=pages, ocr_pages=ocr_pages)


# --- DOCX / ODT / testo ------------------------------------------------------------


def extract_docx(path: Path) -> Extracted:
    import docx

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise ExtractionError("Documento Word illeggibile") from exc
    blocks: list[str] = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    # Tabelle: una riga per paragrafo, celle separate da " | "
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                blocks.append(" | ".join(dict.fromkeys(cells)))
    return Extracted("docx", _paragraphs(blocks))


_ODF_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def extract_odt(path: Path) -> Extracted:
    try:
        with zipfile.ZipFile(path) as z:
            root = ElementTree.fromstring(z.read("content.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ExtractionError("Documento ODT illeggibile") from exc
    blocks = []
    for el in root.iter():
        if el.tag in (f"{{{_ODF_TEXT}}}p", f"{{{_ODF_TEXT}}}h"):
            text = "".join(el.itertext()).strip()
            if text:
                blocks.append(text)
    return Extracted("odt", _paragraphs(blocks))


def text_to_paragraphs(text: str) -> list[Paragraph]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if b.strip()]
    return _paragraphs([re.sub(r"\s*\n\s*", " ", b) for b in blocks])


def _table_row(line: str) -> str:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return " — ".join(c for c in cells if c)


def web_text_to_paragraphs(text: str) -> list[Paragraph]:
    """Testo estratto da una pagina web: un paragrafo per riga; le tabelle (righe
    "| a | b |") diventano un unico paragrafo leggibile, senza separatori."""
    blocks: list[str] = []
    table: list[str] = []

    def flush() -> None:
        if table:
            blocks.append(" · ".join(table))
            table.clear()

    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("|"):
            if re.fullmatch(r"[|\s:\-]+", line):  # riga di separazione
                continue
            row = _table_row(line)
            if row:
                table.append(row)
            continue
        flush()
        if line:
            blocks.append(line)
    flush()
    return _paragraphs(blocks)


def extract_text(path: Path) -> Extracted:
    return Extracted("text", text_to_paragraphs(path.read_text("utf-8", errors="replace")))


EXTRACTORS = {
    "application/pdf": extract_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": extract_docx,
    "application/vnd.oasis.opendocument.text": extract_odt,
    "text/plain": extract_text,
}


def extract(path: Path, mime: str) -> Extracted:
    fn = EXTRACTORS.get(mime)
    if fn is None:
        raise ExtractionError("Estrazione del testo non disponibile per questo formato")
    return fn(path)
