"""Janela de legendas: pequena, semitransparente, sempre por cima das outras janelas.

Arraste pela barra superior. Controles: pausar/retomar, modo de exibição, histórico, fechar.
Atalhos: Espaço = pausar/retomar · T = alternar modo · H = histórico · Esc = fechar.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont

from .domain import Utterance
from .pipeline import Pipeline

BG = "#0f1115"
FG = "#f2f4f8"
DIM = "#8b93a7"
UNCERTAIN = "#ffb454"
LOW = "#ffb454"
ME = "#6cb6ff"
PARTNER = "#c39bff"
GREEN = "#3fb950"
AMBER = "#d29922"
GRAY = "#59606e"


def _font_family(root: tk.Tk) -> str:
    families = set(tkfont.families(root))
    for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans"):
        if f in families:
            return f
    return "TkDefaultFont"


class SubtitleWindow:
    def __init__(
        self,
        pipeline: Pipeline,
        source_labels: dict[str, str],
        show_original: bool = True,
        show_mine: bool = True,
        alpha: float = 0.90,
        max_lines: int = 2,
    ):
        self.p = pipeline
        self.source_labels = source_labels
        self.show_original = show_original
        self.show_mine = show_mine
        self.max_lines = max_lines
        self.events: queue.Queue = queue.Queue()
        self.finals: list[Utterance] = []
        self.partials: dict[str, Utterance] = {}

        self.root = tk.Tk()
        self.root.title("BRIDGE")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        self.root.overrideredirect(True)
        w = 760
        x = (self.root.winfo_screenwidth() - w) // 2
        self.root.geometry(f"{w}x260+{x}+40")
        self.family = _font_family(self.root)
        self._build()
        self._bind_keys()
        self.root.after(80, self._tick)

    # -- construção ---------------------------------------------------------------------
    def _build(self) -> None:
        f = self.family
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=12, pady=(8, 2))
        for widget in (bar,):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        title = tk.Label(bar, text="BRIDGE", bg=BG, fg=FG, font=(f, 10, "bold"))
        title.pack(side="left")
        title.bind("<ButtonPress-1>", self._drag_start)
        title.bind("<B1-Motion>", self._drag_move)

        self.status_dot = tk.Label(bar, text="●", bg=BG, fg=GREEN, font=(f, 10))
        self.status_dot.pack(side="left", padx=(8, 2))
        self.status_text = tk.Label(bar, text="ouvindo", bg=BG, fg=DIM, font=(f, 9))
        self.status_text.pack(side="left")

        self.level_labels: dict[str, tk.Label] = {}
        for sid, label in self.source_labels.items():
            lab = tk.Label(bar, text=f"{label} ▁▁▁▁", bg=BG, fg=DIM, font=(f, 9))
            lab.pack(side="left", padx=(12, 0))
            self.level_labels[sid] = lab

        def button(text, cmd):
            b = tk.Label(bar, text=text, bg="#1c2029", fg=FG, font=(f, 9), padx=8, pady=2, cursor="hand2")
            b.bind("<Button-1>", lambda e: cmd())
            b.pack(side="right", padx=(6, 0))
            return b

        button("✕", self.close)
        button("Histórico", self.open_history)
        self.mode_btn = button(self._mode_label(), self.toggle_mode)
        self.pause_btn = button("Pausar", self.toggle_pause)

        self.text = tk.Text(
            self.root,
            bg=BG,
            fg=FG,
            bd=0,
            highlightthickness=0,
            wrap="word",
            padx=14,
            pady=6,
            cursor="arrow",
        )
        self.text.pack(fill="both", expand=True)
        t = self.text
        t.tag_configure("hdr_me", foreground=ME, font=(f, 8, "bold"), spacing1=6)
        t.tag_configure("hdr_partner", foreground=PARTNER, font=(f, 8, "bold"), spacing1=6)
        t.tag_configure("hdr", foreground=DIM, font=(f, 8, "bold"), spacing1=2)
        t.tag_configure("orig", foreground=DIM, font=(f, 12))
        t.tag_configure("trans", foreground=FG, font=(f, 15, "bold"))
        t.tag_configure("uncertain", foreground=UNCERTAIN, underline=True)
        t.tag_configure("low", foreground=LOW, font=(f, 8))
        t.tag_configure("partial", foreground=DIM, font=(f, 12, "italic"))
        t.configure(state="disabled")

    def _bind_keys(self) -> None:
        self.root.bind("<space>", lambda e: self.toggle_pause())
        self.root.bind("<t>", lambda e: self.toggle_mode())
        self.root.bind("<h>", lambda e: self.open_history())
        self.root.bind("<Escape>", lambda e: self.close())

    def _drag_start(self, e) -> None:
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag_move(self, e) -> None:
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # -- ações --------------------------------------------------------------------------
    def _mode_label(self) -> str:
        return "Original + tradução" if self.show_original else "Só tradução"

    def toggle_mode(self) -> None:
        self.show_original = not self.show_original
        self.mode_btn.configure(text=self._mode_label())
        self._render()

    def toggle_pause(self) -> None:
        if self.p.paused:
            self.p.resume()
            self.pause_btn.configure(text="Pausar")
        else:
            self.p.pause()
            self.partials.clear()
            self.pause_btn.configure(text="Retomar")
            self._render()

    def close(self) -> None:
        self.root.quit()

    def open_history(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("BRIDGE — histórico (só na memória)")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.geometry("640x480")
        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=10, pady=6)
        enabled = tk.BooleanVar(value=self.p.history.enabled)
        info = tk.Label(top, bg=BG, fg=DIM, font=(self.family, 9))

        txt = tk.Text(win, bg=BG, fg=FG, bd=0, wrap="word", padx=10, font=(self.family, 11))
        txt.pack(fill="both", expand=True)

        def refresh():
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            items = self.p.history.items()
            for u in items:
                txt.insert("end", f"{u.speaker.name}: {u.transcript.text}\n", ())
                txt.insert("end", f"   → {u.translation}\n\n", ())
            txt.configure(state="disabled")
            info.configure(
                text=f"{len(items)} falas · nada é salvo em disco"
                if self.p.history.enabled
                else "Histórico desligado (padrão). Ligue para guardar falas enquanto o programa estiver aberto."
            )

        def toggle():
            self.p.history.set_enabled(enabled.get())
            refresh()

        def clear():
            self.p.history.clear()
            refresh()

        tk.Checkbutton(
            top, text="Guardar histórico", variable=enabled, command=toggle, bg=BG, fg=FG,
            selectcolor=BG, activebackground=BG, activeforeground=FG,
        ).pack(side="left")
        tk.Button(top, text="Apagar tudo", command=clear).pack(side="left", padx=8)
        info.pack(side="left", padx=8)
        refresh()

    # -- atualização --------------------------------------------------------------------
    def post(self, utt: Utterance) -> None:
        """Chamado pelo trabalhador do pipeline (outra thread)."""
        self.events.put(("utt", utt))

    def discard(self, source_id: str, segment_id: int) -> None:
        self.events.put(("discard", (source_id, segment_id)))

    def _tick(self) -> None:
        changed = False
        while True:
            try:
                kind, item = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if kind == "discard":
                sid, seg = item
                if sid in self.partials and self.partials[sid].segment_id == seg:
                    del self.partials[sid]
                continue
            utt: Utterance = item
            if utt.speaker.is_me and not self.show_mine:
                continue
            if utt.is_final:
                self.partials.pop(utt.source_id, None)
                self.finals.append(utt)
                self.finals = self.finals[-self.max_lines :]
            else:
                self.partials[utt.source_id] = utt
        self._update_status()
        if changed:
            self._render()
        self.root.after(80, self._tick)

    def _update_status(self) -> None:
        if self.p.paused:
            self.status_dot.configure(fg=GRAY)
            self.status_text.configure(text="pausado")
        elif self.p.busy:
            self.status_dot.configure(fg=AMBER)
            self.status_text.configure(text="processando")
        else:
            self.status_dot.configure(fg=GREEN)
            self.status_text.configure(text="ouvindo")
        bars = "▁▂▃▄▅▆▇█"
        for sid, lab in self.level_labels.items():
            lvl = self.p.levels.get(sid, 0.0)
            n = min(4, int(lvl * 40))
            meter = "".join(bars[min(7, 2 * i + 1)] if i < n else "▁" for i in range(4))
            active = self.p.segmenters[sid].in_speech and not self.p.paused
            lab.configure(text=f"{self.source_labels[sid]} {meter}", fg=FG if active else DIM)

    def _render(self) -> None:
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for u in self.finals:
            self._render_final(u)
        for u in self.partials.values():
            hdr = "hdr_me" if u.speaker.is_me else "hdr_partner"
            t.insert("end", f"{u.speaker.name.upper()} — falando…\n", hdr)
            t.insert("end", u.transcript.text.strip() + "\n", "partial")
        t.configure(state="disabled")
        t.see("end")

    def _render_final(self, u: Utterance) -> None:
        t = self.text
        hdr = "hdr_me" if u.speaker.is_me else "hdr_partner"
        if self.show_original:
            t.insert("end", f"{u.speaker.name.upper()} — ORIGINAL ({u.transcript.lang.label_pt})\n", hdr)
            for w in u.transcript.words:
                if w.uncertain:  # sublinha só a palavra, não o espaço antes dela
                    core = w.text.lstrip()
                    t.insert("end", w.text[: len(w.text) - len(core)], "orig")
                    t.insert("end", core, ("orig", "uncertain"))
                else:
                    t.insert("end", w.text, "orig")
            t.insert("end", "\n", "orig")
            label = u.target_lang.label_pt if u.target_lang else ""
            t.insert("end", f"TRADUÇÃO — {label}\n", "hdr")
        else:
            t.insert("end", f"{u.speaker.name.upper()}\n", hdr)
        prefix = "≈ " if u.low_confidence else ""
        t.insert("end", prefix + (u.translation or "") + "\n", "trans")
        if u.low_confidence:
            t.insert("end", "baixa confiança no reconhecimento — confirme se necessário\n", "low")

    def run(self) -> None:
        self.root.mainloop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
