"""Testa o cliente da IA local contra um servidor HTTP falso (sem modelo)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bridge_poc.domain import Lang
from bridge_poc.translate import LlmTranslator, clean_output, translategemma_prompt


class _Handler(BaseHTTPRequestHandler):
    received: list = []
    reply = "Привіт, кохана!"

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.received.append((self.path, body))
        if self.path == "/api/generate":
            data = {"response": _Handler.reply + "<end_of_turn>"}
        else:
            data = {"choices": [{"text": _Handler.reply}]}
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Handler.received = []
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


class _Fallback:
    def translate(self, text, src, tgt):
        return "NLLB"


def test_prompt_matches_official_template():
    p = translategemma_prompt(" Olá ", Lang.PT, Lang.UK)
    assert p.startswith("<start_of_turn>user\nYou are a professional Portuguese (pt-BR) to Ukrainian (uk-UA)")
    assert p.endswith("into Ukrainian:\n\n\nOlá<end_of_turn>\n<start_of_turn>model\n")


@pytest.mark.parametrize("backend,path", [("ollama", "/api/generate"), ("openai", "/v1/completions")])
def test_backends(server, backend, path):
    t = LlmTranslator("m", url=server, backend=backend, fallback=_Fallback())
    assert t.translate("Oi, amor!", Lang.PT, Lang.UK) == "Привіт, кохана!"
    assert t.last_engine == "ia"
    sent_path, body = _Handler.received[-1]
    assert sent_path == path and body["model"] == "m" and "Oi, amor!" in body["prompt"]
    assert body.get("raw", True) is True


def test_falls_back_to_nllb_when_server_is_down():
    t = LlmTranslator("m", url="http://127.0.0.1:9", fallback=_Fallback(), timeout_s=0.5)
    assert t.translate("Oi", Lang.PT, Lang.UK) == "NLLB"
    assert t.last_engine == "nllb" and t.failures == 1
    t.translate("Oi", Lang.PT, Lang.UK)
    assert t.failures == 1  # não tenta de novo imediatamente (evita atraso a cada frase)


def test_refuses_remote_server():
    with pytest.raises(ValueError):
        LlmTranslator("m", url="https://api.exemplo.com")


def test_clean_output():
    assert clean_output('"Olá, amor!"<end_of_turn>lixo') == "Olá, amor!"
