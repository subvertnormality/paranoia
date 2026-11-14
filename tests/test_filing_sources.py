import hashlib
import io
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from paranoia_local import arbitration_research as ar, external_sources as es, source_extraction as worker
from .test_external_sources import Response, candidate


def pdf_bytes(text="The API retries twice.", *, pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(600, 800)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 20 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("private-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def serve(monkeypatch, body, content_type="application/pdf", **kwargs):
    monkeypatch.setattr(es, "_validate_public_url", lambda url: None)
    return es.capture(candidate(), opener=lambda req, timeout: Response(body, content_type), **kwargs)


def test_pdf_capture_retains_complete_text_and_response_digests(monkeypatch):
    body = pdf_bytes(pages=2)
    got = serve(monkeypatch, body)
    assert got.usable, got.error
    assert got.text.count("The API retries twice.") == 2
    assert got.content_sha256 == hashlib.sha256(body).hexdigest()
    assert got.text_sha256 == hashlib.sha256(got.text.encode()).hexdigest()
    assert got.extraction_metadata == {"kind": "pdf", "pages": 2}


@pytest.mark.parametrize("body,expected", [
    (b"not a PDF", "extraction failed"),
    (pdf_bytes(text=""), "no text"),
    (pdf_bytes(encrypted=True), "encrypted"),
    (pdf_bytes(pages=501), "500 pages"),
])
def test_pdf_errors_are_source_local_with_response_provenance(monkeypatch, body, expected):
    got = serve(monkeypatch, body)
    assert not got.usable and expected in got.error
    assert got.status == 200 and got.content_type == "application/pdf"
    assert got.content_sha256 == hashlib.sha256(body).hexdigest()
    assert got.text_sha256 is None


HTML = b"<HTML><BODY><TABLE><TR><TD>The API retries twice.</TD></TR></TABLE></BODY></HTML>"
ENVELOPE = b"<DOCUMENT>\n<TYPE>10-K\n<FILENAME>filing.htm\n<TEXT>\n" + HTML + b"\n</TEXT>\n</DOCUMENT>"


@pytest.mark.parametrize("content_type", ["text/html", "text/plain"])
def test_single_edgar_document_has_exact_payload_identity(monkeypatch, content_type):
    got = serve(monkeypatch, ENVELOPE, content_type)
    assert got.usable, got.error
    assert got.text == es._extract(HTML, "text/html")
    assert "The API retries twice." in got.text
    assert "FILENAME" not in got.text and "<DOCUMENT>" not in got.text
    scope = got.extraction_metadata
    assert scope["filename"] == "filing.htm"
    assert ENVELOPE[scope["start_byte"]:scope["end_byte"]].strip() == HTML
    assert got.content_sha256 == hashlib.sha256(ENVELOPE).hexdigest()
    assert got.text_sha256 == hashlib.sha256(got.text.encode()).hexdigest()


@pytest.mark.parametrize("content_type", ["text/html", "text/plain"])
@pytest.mark.parametrize("body", [
    ENVELOPE + ENVELOPE.replace(b"twice", b"never"),
    ENVELOPE.replace(b"</TEXT>", b"</TEXT><TEXT>Conflicting passage</TEXT>"),
    ENVELOPE.replace(b"</TEXT>", b""),
    ENVELOPE.replace(b"<TEXT>", b"</TEXT>").replace(b"</TEXT>\n</DOCUMENT>", b"<TEXT>\n</DOCUMENT>"),
    ENVELOPE + b"unscoped text",
    ENVELOPE.replace(HTML, b"plain text instead of HTML"),
])
def test_ambiguous_edgar_envelopes_fail_closed(monkeypatch, content_type, body):
    got = serve(monkeypatch, body, content_type)
    assert not got.usable and "EDGAR" in got.error
    assert got.status == 200
    assert got.content_sha256 == hashlib.sha256(body).hexdigest()


def test_empty_precision_and_recall_use_clean_html_fallback(monkeypatch):
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda *args, **kwargs: "")
    body = b"<html><body><script>invented script evidence</script><!-- secret -->Actual table text</body></html>"
    text, _ = worker.extract(body, "text/html", 1000)
    assert "Actual table text" in text
    assert "invented" not in text and "secret" not in text


def test_arbitration_capture_profile_does_not_change_plan_limits(monkeypatch):
    # Padding exceeds the plan raw-byte limit without increasing extracted text.
    body = b"<html><body><p>The API retries twice.</p>" + b" " * 5_000_001 + b"</body></html>"
    plan = serve(monkeypatch, body, "text/html")
    research = serve(monkeypatch, body, "text/html", research=True)
    assert not plan.usable and "5000000 bytes" in plan.error
    assert research.usable, research.error
    large_text = b"x" * (es.MAX_EXTRACTED_CHARS + 1)
    assert not serve(monkeypatch, large_text, "text/plain").usable
    assert serve(monkeypatch, large_text, "text/plain", research=True).usable


def test_worker_memory_limit_is_enforced_in_a_real_child():
    code = "from paranoia_local.source_extraction import contain,MEMORY_BYTES; job=contain(); bytearray(2*MEMORY_BYTES)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=10)
    assert result.returncode != 0
    assert b"MemoryError" in result.stderr


def test_pdf_decoded_stream_limit_is_enforced_before_text_extraction(monkeypatch):
    import zlib
    from pypdf.generic import EncodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(600, 800)
    stream = EncodedStreamObject()
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    stream._data = zlib.compress(b" " * (worker.MAX_PDF_STREAM_BYTES + 1))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    got = serve(monkeypatch, output.getvalue())
    assert not got.usable and "limit" in got.error.lower()
    assert got.content_sha256


def test_containment_failure_becomes_a_source_local_capture_error(monkeypatch, tmp_path):
    script = tmp_path / "no_containment.py"
    script.write_text("import paranoia_local.source_extraction as w\n"
                      "def fail(): raise OSError('containment unavailable')\n"
                      "w.contain=fail\nw.main()\n")
    original = es.subprocess.Popen
    monkeypatch.setattr(es.subprocess, "Popen", lambda argv, **kwargs: original(
        [sys.executable, "-I", str(script), *argv[-2:]], **kwargs,
    ))
    got = serve(monkeypatch, b"<html><body>Must not be admitted</body></html>", "text/html")
    assert not got.usable and "containment unavailable" in got.error
    assert got.content_sha256 and got.status == 200


def test_slow_extraction_does_not_erase_completed_sibling(monkeypatch, tmp_path):
    script = tmp_path / "slow.py"
    script.write_text("import time; time.sleep(30)")
    original = es.subprocess.Popen
    children = []
    def spawn(argv, **kwargs):
        if argv[-2] == "text/html":
            argv = [sys.executable, "-I", str(script)]
        child = original(argv, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(es.subprocess, "Popen", spawn)
    monkeypatch.setattr(es, "_validate_public_url", lambda url: None)
    candidates = [candidate("https://example.com/slow"), candidate("https://example.com/good")]
    def one(item):
        slow = item == candidates[0]
        return es.capture(item, deadline=time.monotonic() + (0.5 if slow else 5),
                          opener=lambda request, timeout: Response(
                              b"captured sibling", "text/html" if slow else "text/plain", url=item.url))
    rows = es.capture_all(candidates, capture_one=one, workers=2)
    assert not rows[0].usable and "deadline" in rows[0].error
    assert rows[1].usable and rows[1].text == "captured sibling"
    assert all(child.poll() is not None for child in children)


@pytest.mark.parametrize("mode", ["deadline", "overflow"])
def test_parent_bounds_output_and_reaps_extraction_child(monkeypatch, tmp_path, mode):
    script = tmp_path / "worker.py"
    script.write_text("import time; time.sleep(30)" if mode == "deadline" else "print('x'*20000)")
    original_popen = es.subprocess.Popen
    children = []

    def spawn(argv, **kwargs):
        child = original_popen([sys.executable, "-I", str(script)], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(es.subprocess, "Popen", spawn)
    with pytest.raises(es.SourceError, match="deadline|output exceeds"):
        es._extract_bounded(b"", "text/html", deadline=time.monotonic() + 0.5,
                            clock=time.monotonic, max_chars=1)
    assert len(children) == 1 and children[0].poll() is not None


def test_scoped_binding_cannot_use_text_outside_the_supplied_window():
    quote = "The API retries twice."
    original = "Outside-only evidence.\n" + "x" * 450_000 + quote + "tail"
    claim = ar.DiscoveryClaim("behavior", quote, candidate(), quote)
    capture = es.Capture(claim.candidate, claim.candidate.url, 200, "text/plain", "a"*64,
                         hashlib.sha256(original.encode()).hexdigest(), original)
    prepared = ar.prepare_binding_input([claim], [capture])
    assert prepared.captures[0] is capture
    row = json.loads(prepared.rendered)["rows"][0]["capture"]
    start, end = prepared.scopes[0]
    assert row["window"]["mode"] == "quote-window"
    assert row["window"]["full_text_chars"] == len(original)
    assert row["window"]["text_sha256"] == hashlib.sha256(original[start:end].encode()).hexdigest()
    assert quote in row["line_numbered_text"] and "Outside-only evidence." not in row["line_numbered_text"]
    reply = lambda passage: ar.BINDING_MARKER + "\n" + json.dumps({"bindings": [{
        "claim_index": 0, "usable": True, "location": "section", "passage": passage,
    }]})
    with pytest.raises(ar.ResearchError, match="not in captured"):
        ar.parse_binding_result(reply("Outside-only evidence."), [claim], prepared.captures, prepared.scopes)
    bound, _ = ar.parse_binding_result(reply(quote), [claim], prepared.captures, prepared.scopes)
    assert bound[0].capture.text == original
    mismatched = ar.prepare_binding_input([replace(claim, quote="invented locator")], [capture])
    assert mismatched.captures[0].error == ar.BINDING_BUDGET_ERROR


def test_same_capture_different_quote_windows_never_share_text_reference():
    first, second = "First actual passage.", "Second actual passage."
    text = "x" * 100_000 + first + "y" * 300_000 + second + "z" * 100_000
    claims = [ar.DiscoveryClaim("fact", quote, candidate(), quote) for quote in (first, second)]
    captures = [es.Capture(c.candidate, c.candidate.url, 200, "text/plain", "a"*64, "b"*64, text) for c in claims]
    prepared = ar.prepare_binding_input(claims, captures)
    rows = json.loads(prepared.rendered)["rows"]
    assert all(row["capture"]["capture_ref"] is None for row in rows)
    assert prepared.scopes[0] != prepared.scopes[1]
    assert first not in rows[1]["capture"]["line_numbered_text"]


def test_binding_rejection_reason_is_bounded_and_legacy_is_explicit():
    claim = ar.DiscoveryClaim("fact", "Claim", candidate())
    capture = es.Capture(claim.candidate, claim.candidate.url, 200, "text/plain", "a"*64, "b"*64, "text")
    row = {"claim_index": 0, "usable": False, "location": None, "passage": None}
    reply = lambda: ar.BINDING_MARKER + "\n" + json.dumps({"bindings": [row]})
    bound, reasons = ar.parse_binding_result(reply(), [claim], [capture])
    assert ar.binding_diagnostics([claim], [capture], bound, reasons)[0]["reason"].endswith("no reason supplied")
    row["reason"] = "No information about this share class."
    bound, reasons = ar.parse_binding_result(reply(), [claim], [capture])
    assert reasons == (row["reason"],)
    row["reason"] = "x" * 601
    with pytest.raises(ar.ResearchError, match="reason exceeds"):
        ar.parse_binding_result(reply(), [claim], [capture])


def test_filing_research_native_receipt_retains_its_source_and_execution():
    root = Path(__file__).resolve().parents[1]
    receipt = json.loads((root / "docs/filing-research-146-acceptance.json").read_text(encoding="utf-8"))
    assert receipt["kind"] == "issue146-captured-filing-research" and receipt["qualified"]
    revision = receipt["source_revision"]
    inventory = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision, "--", "src/paranoia_local"], cwd=root, text=True)
    assert set(receipt["source_sha256"]) == {p for p in inventory.splitlines() if p.endswith(".py")}
    for name, digest in receipt["source_sha256"].items():
        assert hashlib.sha256(subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=root)).hexdigest() == digest
    sources = receipt["direct_capture"]["sources"]
    assert {source["extraction_metadata"]["kind"] for source in sources} == {"pdf", "edgar-single-document"}
    assert all(source["status"] == 200 and source["extracted_characters"] > 0 for source in sources)
    native = receipt["native_research"]
    assert native["engine"] == "codex" and native["model_calls"] == 2
    assert native["claims"] == native["bound_sources"] == 1
    assert [row["phase"] for row in native["attempts"]] == ["discovery", "binding"]
    for row in native["attempts"]:
        assert row["returncode"] == 0 and not row["execution_error"] and row["session_ref"]
        assert len(row["raw_sha256"]) == len(row["extracted_sha256"]) == 64
    assert "shares outstanding" in native["packet_text"]
    assert "latest practicable date" in native["packet_text"]
