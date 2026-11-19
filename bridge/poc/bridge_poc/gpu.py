"""Ajuda o CTranslate2 a encontrar as bibliotecas CUDA (cuBLAS/cuDNN) no Windows.

Instaladas via pip (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`), as DLLs ficam em
site-packages/nvidia/*/bin, fora do caminho de busca padrão do Windows.
"""

from __future__ import annotations

import glob
import os
import sys

_done = False


def prepare_cuda() -> list[str]:
    global _done
    if _done or sys.platform != "win32":
        return []
    _done = True
    added = []
    for sp in sys.path:
        for bin_dir in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            if os.path.isdir(bin_dir) and bin_dir not in added:
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                added.append(bin_dir)
    return added


def describe() -> str:
    prepare_cuda()
    try:
        import ctranslate2

        n = ctranslate2.get_cuda_device_count()
    except Exception as e:  # pragma: no cover - depende da máquina
        return f"CTranslate2 indisponível: {e}"
    if n == 0:
        return "Nenhuma GPU CUDA encontrada — usando CPU (mais lento)."
    types = ctranslate2.get_supported_compute_types("cuda")
    return f"GPU CUDA encontrada ({n}). Tipos suportados: {', '.join(sorted(types))}"
