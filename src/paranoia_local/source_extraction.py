"""Trusted, resource-contained extraction worker; never executes document content.

Invoked by absolute filename with Python isolated mode, not through a repository
import path. Limits are installed before importing either document parser.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sys

MEMORY_BYTES = 512 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_PDF_STREAM_BYTES = 20_000_000


def contain() -> object:
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
        return None
    if os.name != "nt":
        raise RuntimeError("source extraction containment unavailable on this platform")
    import ctypes as c
    from ctypes import wintypes as w

    class Basic(c.Structure):
        _fields_ = [
            ("process_time", c.c_longlong), ("job_time", c.c_longlong),
            ("flags", w.DWORD), ("min_working_set", c.c_size_t),
            ("max_working_set", c.c_size_t), ("active_processes", w.DWORD),
            ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD),
        ]

    class Extended(c.Structure):
        _fields_ = [
            ("basic", Basic), ("io", c.c_ulonglong * 6),
            ("process_memory", c.c_size_t), ("job_memory", c.c_size_t),
            ("peak_process_memory", c.c_size_t), ("peak_job_memory", c.c_size_t),
        ]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.process_memory = MEMORY_BYTES
    if not job or not kernel.SetInformationJobObject(job, 9, c.byref(info), c.sizeof(info)):
        raise OSError(c.get_last_error(), "cannot establish extraction memory limit")
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise OSError(c.get_last_error(), "cannot assign extraction worker to memory job")
    # The worker retains this handle until process exit; no document can close it.
    return job


def edgar_payload(body: bytes) -> tuple[bytes, dict | None]:
    if not re.match(rb"(?:\xef\xbb\xbf)?\s*<DOCUMENT\b", body, re.I):
        return body, None
    documents = list(re.finditer(rb"</?DOCUMENT\s*>", body, re.I))
    texts = list(re.finditer(rb"</?TEXT\s*>", body, re.I))
    if (
        len(documents) != 2 or len(texts) != 2
        or documents[0].group().lower() != b"<document>"
        or documents[1].group().lower() != b"</document>"
        or texts[0].group().lower() != b"<text>"
        or texts[1].group().lower() != b"</text>"
        or not (documents[0].end() <= texts[0].start() < texts[1].start() < documents[1].start())
        or body[:documents[0].start()].removeprefix(b"\xef\xbb\xbf").strip()
        or body[documents[1].end():].strip()
        or body[texts[1].end():documents[1].start()].strip()
    ):
        raise ValueError("ambiguous or malformed EDGAR DOCUMENT/TEXT envelope")
    start, end = texts[0].end(), texts[1].start()
    payload = body[start:end]
    if not re.match(rb"\s*(?:<!DOCTYPE\s+html[^>]*>\s*)?<html\b", payload, re.I):
        raise ValueError("EDGAR TEXT payload is not an HTML document")
    if len(re.findall(rb"<html\b", payload, re.I)) != 1:
        raise ValueError("EDGAR TEXT contains multiple HTML documents")
    filename = re.search(rb"<FILENAME>([^\r\n<]*)", body[documents[0].end():texts[0].start()], re.I)
    name = filename[1].decode("utf-8", "replace").strip() if filename else None
    if name is not None and len(name) > 400:
        raise ValueError("EDGAR FILENAME exceeds 400 characters")
    return payload, {"kind": "edgar-single-document", "filename": name,
                     "start_byte": start, "end_byte": end}


def extract(body: bytes, content_type: str, max_chars: int) -> tuple[str, dict | None]:
    metadata = None
    if content_type == "application/pdf":
        from pypdf import PdfReader, apply_configuration

        apply_configuration(
            zlib_maximum_output_length=MAX_PDF_STREAM_BYTES,
            lzw_maximum_output_length=MAX_PDF_STREAM_BYTES,
            run_length_maximum_output_length=MAX_PDF_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_PDF_STREAM_BYTES,
            jbig2dec_binary=None,
        )
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted:
            raise ValueError("encrypted PDF is unsupported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds {MAX_PDF_PAGES} pages")
        pages, count = [], 0
        for number, page in enumerate(reader.pages, 1):
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > MAX_PDF_STREAM_BYTES:
                raise ValueError("PDF decoded page stream exceeds extraction limit")
            text = page.extract_text() or ""
            count += len(text) + (1 if pages else 0)
            if count > max_chars:
                raise ValueError(f"extracted page exceeds {max_chars} characters")
            pages.append(text)
        text = "\n".join(pages)
        metadata = {"kind": "pdf", "pages": len(reader.pages)}
    else:
        body, metadata = edgar_payload(body)
        if content_type == "text/plain" and metadata is None:
            text = body.decode("utf-8", errors="replace")
        else:
            import trafilatura

            options = dict(output_format="txt", include_comments=False, include_tables=True)
            text = trafilatura.extract(body, favor_precision=True, **options) or ""
            if not text.strip():
                text = trafilatura.extract(body, favor_recall=True, **options) or ""
            if not text.strip():
                text = trafilatura.html2txt(body, clean=True)
    text = text.strip()
    if not text:
        raise ValueError("page extraction produced no text")
    if len(text) > max_chars:
        raise ValueError(f"extracted page has {len(text)} characters; limit is {max_chars}")
    return text, metadata


def main() -> None:
    try:
        job = contain()
        logging.disable(logging.CRITICAL)
        content_type, limit = sys.argv[1:3]
        text, metadata = extract(sys.stdin.buffer.read(), content_type, int(limit))
        # ASCII JSON has a maximum of 12 bytes per Unicode scalar (surrogate pair).
        payload = json.dumps({"text": text, "metadata": metadata}, ensure_ascii=True)
        sys.stdout.buffer.write(payload.encode("ascii"))
        del job  # The OS owns and releases the job handle when this process exits.
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:1200]
        sys.stderr.buffer.write(message.encode("utf-8", "backslashreplace"))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
