"""BRIDGE — protótipo de legendas traduzidas pt-BR ⇄ uk-UA (100% local)."""

import os as _os

# No Windows, o CTranslate2 (Whisper/NLLB) e o PyTorch (Parakeet UK) trazem cada um a sua cópia
# do OpenMP (libiomp5md.dll). Carregadas juntas, o programa fecha com "OMP: Error #15".
# Esta variável permite as duas cópias convivendo; precisa ser definida antes de qualquer import.
_os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

__version__ = "0.2.0"
