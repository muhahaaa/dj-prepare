"""PROTOTYPE -- throwaway. Wayfinder ticket "GUI layout prototype".

Question: what should the DJ Prepare GUI look like and how should it behave?
Three structurally different layouts of the main window, switchable from the
bottom bar (or the left/right arrow keys, or `--variant A|B|C`).

  A  Table + inspector   one row per Track, stage chips, inspector on the right
  B  Pipeline board      one column per Pipeline Stage, Tracks sit where they are stuck
  C  Stage-by-stage      sidebar of stages, Tag stage is a focused one-Track review

All data is stubbed in memory; nothing touches the disk. Run:
    pip install PySide6
    python prototypes/gui_layout/prototype.py [--variant A|B|C]
"""
import sys
import datetime
import types
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QObject, QEvent, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QLinearGradient, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QToolButton, QLineEdit, QComboBox, QTextEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QTableWidget, QTableWidgetItem, QListWidget,
    QListWidgetItem, QSplitter, QGroupBox, QTabWidget, QFrame, QStackedWidget,
    QDialog, QAbstractItemView, QHeaderView, QMessageBox,
)

NORMALIZABLE = {"mp3", "aac", "m4a"}
COVER_COLORS = ["#c0392b", "#2980b9", "#8e44ad", "#16a085", "#d35400", "#2c3e50"]

# state -> (glyph, background, foreground)
CHIP = {
    "done": ("\u2713", "#dff3e1", "#1e6b2b"),
    "pending": ("\u00b7", "#ececec", "#555555"),
    "skipped": ("\u2013", "#f6f6f6", "#999999"),
    "warn": ("\u26a0", "#fff1c2", "#7a5500"),
    "blocked": ("\u2715", "#fbdcdc", "#9b1c1c"),
    "failed": ("!", "#fbdcdc", "#9b1c1c"),
}
STAGE_NAMES = {"N": "Normalize", "T": "Tag", "R": "Rename", "F": "File"}


# --------------------------------------------------------------------------- data


@dataclass
class Track:
    file: str
    fmt: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    year: str = ""
    comment: str = ""
    pic: Optional[str] = None          # colour of the stub cover, None = no picture
    normalized: bool = False
    renamed: bool = False
    riff_only: bool = False            # wav tagged with RIFF INFO only
    always_fails_normalize: bool = False
    fail: Optional[tuple] = None       # (stage letter, reason)
    folder: str = ""                   # Inbox-relative folder ("" = Inbox root)


def stub_tracks():
    T = Track
    tracks = [
        T("glowed_up.mp3", "mp3", "Glowed Up", "Kaytranada", "99.9%", "House", "2016", "Peak", "#c0392b"),
        T("untitled_export_07.mp3", "mp3", "Untitled Export 07"),
        T("baby.flac", "flac", "Baby", "Four Tet", "Sixteen Oceans", "Deep House", "2020", "", "#2980b9"),
        T("glue.m4a", "m4a", "Glue", "Bicep", "Bicep", "Electronica", "2017", "Warmup", "#8e44ad", normalized=True),
        T("tentacles.wav", "wav", "Tentacles", "Noisia", "Split the Atom", "Drum & Bass", "2010", "Peak", None, riff_only=True),
        T("brown_paper_bag.ogg", "ogg", "Brown Paper Bag", "Roni Size", "New Forms", "Drum & Bass", "1997", "Closing"),
        T("digital_love.mp3", "mp3", "Digital Love", "Daft Punk", "Discovery", "House", "2001", "Warmup", "#16a085", normalized=True),
        T("shades_of_jae.aac", "aac", "Shades of Jae", "Moodymann", "Silentintroduction", "Techno", "1999", "Closing", "#d35400", always_fails_normalize=True),
        T("silhouettes.flac", "flac", "Silhouettes", "Floating Points", "Elaenia", "Deep House", "2099", "Warmup", "#2c3e50"),
        T("phat_trax.mp3", "mp3", "Phat Trax", "Carl Cox", "Phat Trax", "Techno", "1994", "Peak", "#c0392b", normalized=True, renamed=True),
        T("latch.m4a", "m4a", "Latch", "Disclosure", "Settle", "Deep House", "2012", "Peak", "#2980b9", normalized=True),
    ]
    for t, folder in zip(tracks, ["", "", "Bandcamp", "Beatport", "Beatport", "", "", "Beatport",
                                  "Bandcamp", "2026-10", ""]):
        t.folder = folder
    return tracks


class Store(QObject):
    changed = Signal()
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self.tracks = stub_tracks()
        self.filed = []
        self.cfg = types.SimpleNamespace(
            inbox="C:/Users/dj/Downloads/Inbox",
            target_db=89.0,
            clipping_allowed=False,
            lists={
                "genre": ["House", "Deep House", "Techno", "Drum & Bass", "Electronica", "Hip-Hop"],
                "comment": ["Warmup", "Peak", "Closing"],
            },
            mapping=[
                ["Deep House", "D:/Music/House/Deep"],
                ["House", "D:/Music/House"],
                ["Drum*", "D:/Music/DnB"],
                ["Techno", "D:/Music/Techno"],
            ],
            template="{YYYY}-{MM}/{Artist} - {Title}",
            rules=[
                {"name": "Title required", "type": "Required", "field": "title", "sev": "Hard"},
                {"name": "Artist required", "type": "Required", "field": "artist", "sev": "Hard"},
                {"name": "Picture required", "type": "Required", "field": "pic", "sev": "Hard"},
                {"name": "Genre on Genre List", "type": "OneOf", "field": "genre", "sev": "Hard"},
                {"name": "Comment on Comment List", "type": "OneOf", "field": "comment", "sev": "Soft"},
                {"name": "Year in range", "type": "YearRange", "field": "year", "sev": "Soft", "min": 1990, "max": 2026},
                {"name": "WAV not RIFF-INFO only", "type": "RiffInfo", "field": "-", "sev": "Soft"},
            ],
        )

    # -- derived state ------------------------------------------------------

    def eval_rule(self, t, r):
        f = r["field"]
        if f == "pic" and t.fmt == "ogg":
            return "na"
        if r["type"] == "RiffInfo":
            if t.fmt != "wav":
                return "na"
            return "fail" if t.riff_only else "pass"
        v = getattr(t, f)
        if r["type"] == "Required":
            return "pass" if v else "fail"
        if r["type"] == "OneOf":
            return "pass" if v in self.cfg.lists[f] else "fail"
        if r["type"] == "YearRange":
            try:
                return "pass" if r["min"] <= int(v) <= r["max"] else "fail"
            except ValueError:
                return "fail"

    def results(self, t):
        return [(r, self.eval_rule(t, r)) for r in self.cfg.rules]

    def readiness(self, t):
        worst = "ok"
        for r, o in self.results(t):
            if o == "fail":
                if r["sev"] == "Hard":
                    return "blocked"
                worst = "warn"
        return worst

    def dest_folder(self, t):
        for pat, folder in self.cfg.mapping:
            if pat == t.genre:
                return folder
        for pat, folder in self.cfg.mapping:
            if pat.endswith("*") and t.genre.startswith(pat[:-1]):
                return folder
        return None

    def new_path(self, t):
        d = datetime.date.today()
        p = self.cfg.template
        for k, v in {"Title": t.title, "Artist": t.artist, "Album": t.album, "Genre": t.genre,
                     "Year": t.year, "Comment": t.comment, "YYYY": f"{d.year:04}",
                     "MM": f"{d.month:02}", "DD": f"{d.day:02}"}.items():
            p = p.replace("{" + k + "}", v or "?")
        return p + "." + t.fmt

    def needs_normalize(self, t):
        return t.fmt in NORMALIZABLE and not t.normalized and not t.fail

    def stages(self, t):
        s = {}
        if t.fmt not in NORMALIZABLE:
            s["N"] = ("skipped", f"{t.fmt} is not a Normalizable Format")
        elif t.fail and t.fail[0] == "N":
            s["N"] = ("failed", t.fail[1])
        elif t.normalized:
            s["N"] = ("done", "normalized")
        else:
            s["N"] = ("pending", "not normalized yet")
        rd = self.readiness(t)
        s["T"] = {"ok": ("done", "all rules pass"),
                  "warn": ("warn", "soft rule warning(s)"),
                  "blocked": ("blocked", "hard rule failing")}[rd]
        if t.renamed:
            s["R"] = ("done", "renamed")
        elif rd == "blocked":
            s["R"] = ("blocked", "blocked by failing hard rule")
        else:
            s["R"] = ("pending", "-> " + self.new_path(t))
        if rd == "blocked":
            s["F"] = ("blocked", "blocked by failing hard rule")
        elif self.dest_folder(t) is None:
            s["F"] = ("blocked", f"Genre '{t.genre}' has no Genre Folder Mapping")
        else:
            s["F"] = ("pending", "-> " + self.dest_folder(t))
        return s

    def column(self, t):
        """Where a Track is 'stuck' on a pipeline board: its next outstanding stage."""
        if t.fail:
            return "X"
        if self.needs_normalize(t):
            return "N"
        if self.readiness(t) == "blocked":
            return "T"
        return "F" if t.renamed else "R"

    # -- stubbed actions -----------------------------------------------------

    def by_files(self, files):
        return [t for t in self.tracks if t.file in set(files)]

    def run_normalize(self, files):
        ok = bad = skipped = 0
        for t in self.by_files(files):
            if t.fmt not in NORMALIZABLE or t.normalized:
                skipped += 1
            elif t.always_fails_normalize:
                t.fail = ("N", "mp3rgain exited 1: could not read MP4 container")
                bad += 1
            else:
                t.fail = None
                t.normalized = True
                ok += 1
        c = self.cfg
        flag = "" if c.clipping_allowed else " -k"
        self.message.emit(f"Normalize: {ok} done, {bad} failed & flagged, {skipped} skipped "
                          f"(mp3rgain -r -d {c.target_db - 89:+.1f}{flag})")
        self.changed.emit()

    def run_rename_file(self, files):
        filed = held = blocked = waiting = 0
        for t in self.by_files(files):
            if self.readiness(t) == "blocked":
                blocked += 1
            elif self.needs_normalize(t) or t.fail:
                waiting += 1
            else:
                t.renamed = True
                if self.dest_folder(t) is None:
                    held += 1
                else:
                    self.tracks.remove(t)
                    self.filed.append(t)
                    filed += 1
        self.message.emit(f"Rename & File: {filed} filed, {held} renamed but held (unmapped Genre), "
                          f"{blocked} blocked by hard rules, {waiting} waiting on Normalize")
        self.changed.emit()

    def retry(self, files):
        for t in self.by_files(files):
            t.fail = None
        self.message.emit("Cleared flags; they will be retried by the next Normalize run")
        self.changed.emit()


# --------------------------------------------------------------------------- shared bits


def cover_pixmap(t, size):
    pm = QPixmap(size, size)
    p = QPainter(pm)
    if t is not None and t.fmt == "ogg":
        pm.fill(QColor("#2b2b2b"))
        p.setPen(QColor("#999"))
        p.drawText(pm.rect(), Qt.AlignCenter, "Picture n/a\n(ogg)")
    elif t is None or not t.pic:
        pm.fill(QColor("#3a3a3a"))
        p.setPen(QColor("#bbb"))
        p.drawText(pm.rect(), Qt.AlignCenter, "no picture")
    else:
        g = QLinearGradient(0, 0, size, size)
        g.setColorAt(0, QColor(t.pic))
        g.setColorAt(1, QColor("#111"))
        p.fillRect(pm.rect(), QBrush(g))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 45))
        p.drawEllipse(int(size * .2), int(size * .2), int(size * .6), int(size * .6))
    p.end()
    return pm


def chip_item(state, tip=""):
    glyph, bg, fg = CHIP[state]
    it = QTableWidgetItem(glyph)
    it.setBackground(QColor(bg))
    it.setForeground(QColor(fg))
    it.setTextAlignment(Qt.AlignCenter)
    it.setToolTip(tip)
    return it


def rules_html(store, t, only_failures=False):
    if t is None:
        return ""
    rows = []
    for r, o in store.results(t):
        if only_failures and o != "fail":
            continue
        hard = r["sev"] == "Hard"
        g, col = {"pass": ("\u2713", "#2e9d4f"),
                  "fail": ("\u2715", "#d33") if hard else ("\u26a0", "#d99a00"),
                  "na": ("\u2013", "#888")}[o]
        extra = " <i>(not applicable)</i>" if o == "na" else ""
        rows.append(f'<span style="color:{col}">{g}</span> {r["name"]} '
                    f'<small>[{r["sev"].lower()}]</small>{extra}')
    if only_failures and not rows:
        return '<span style="color:#2e9d4f">✓</span> No failing rules'
    return "<br>".join(rows)


def stages_html(store, t):
    if t is None:
        return ""
    rows = []
    for k, (state, detail) in store.stages(t).items():
        g, bg, fg = CHIP[state]
        rows.append(f'<b>{STAGE_NAMES[k]}</b> <span style="color:{fg}">{g}</span> {detail}')
    return "<br>".join(rows)


def rich_label():
    lb = QLabel()
    lb.setTextFormat(Qt.RichText)
    lb.setWordWrap(True)
    lb.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    return lb


class TagForm(QWidget):
    """Edits the seven Tag Fields of one Track (edits apply to in-memory stub data)."""

    def __init__(self, store, cover_size=180, horizontal=False, show_apply=True):
        super().__init__()
        self.store, self.t, self.cover_size = store, None, cover_size
        self.cover = QLabel()
        self.cover.setFixedSize(cover_size, cover_size)
        self.btn_replace = QPushButton("Replace\u2026")
        self.btn_remove = QPushButton("Remove")
        self.title, self.artist, self.album, self.year = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.genre, self.comment = QComboBox(), QComboBox()
        for combo in (self.genre, self.comment):
            combo.setEditable(True)            # typing a new value prompts to add it to the list
            combo.setInsertPolicy(QComboBox.NoInsert)
        self.btn_apply = QPushButton("Apply tags")
        self.btn_apply.setVisible(show_apply)

        cbtn = QHBoxLayout()
        cbtn.addWidget(self.btn_replace)
        cbtn.addWidget(self.btn_remove)
        cbox = QVBoxLayout()
        cbox.addWidget(self.cover)
        cbox.addLayout(cbtn)
        cbox.addStretch()
        cw = QWidget()
        cw.setLayout(cbox)
        cw.setFixedWidth(cover_size + 4)

        form = QFormLayout()
        for lbl, w in (("Title", self.title), ("Artist", self.artist), ("Album", self.album),
                       ("Genre", self.genre), ("Year", self.year), ("Comment", self.comment)):
            form.addRow(lbl, w)
        form.addRow("", self.btn_apply)
        fw = QWidget()
        fw.setLayout(form)

        root = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(cw)
        root.addWidget(fw, 1)

        self.btn_apply.clicked.connect(self.apply)
        self.btn_replace.clicked.connect(self.replace_pic)
        self.btn_remove.clicked.connect(self.remove_pic)
        self.set_track(None)

    def set_track(self, t):
        self.t = t
        self.setEnabled(t is not None)
        self.cover.setPixmap(cover_pixmap(t, self.cover_size))
        self.title.setText(t.title if t else "")
        self.artist.setText(t.artist if t else "")
        self.album.setText(t.album if t else "")
        self.year.setText(t.year if t else "")
        for combo, key, cur in ((self.genre, "genre", t.genre if t else ""),
                                (self.comment, "comment", t.comment if t else "")):
            combo.clear()
            items = [""] + self.store.cfg.lists[key]
            if cur and cur not in items:
                items.append(cur)      # show an invalid value so the rule failure is visible
            combo.addItems(items)
            combo.setCurrentText(cur)
        pic_ok = t is not None and t.fmt != "ogg"
        self.btn_replace.setEnabled(pic_ok)
        self.btn_remove.setEnabled(pic_ok and bool(t.pic))

    def apply(self):
        t = self.t
        if t is None:
            return
        t.title, t.artist, t.album = self.title.text(), self.artist.text(), self.album.text()
        t.year = self.year.text()
        for key, combo in (("genre", self.genre), ("comment", self.comment)):
            v = combo.currentText().strip()
            if v and v not in self.store.cfg.lists[key]:
                if self.confirm_add(key, v):
                    self.store.cfg.lists[key].append(v)
                else:
                    v = getattr(t, key)    # declined: keep the previous value
            setattr(t, key, v)
        self.store.message.emit(f"Applied tags to {t.title or t.file}")
        self.store.changed.emit()

    def confirm_add(self, key, value):
        kind = "Genre" if key == "genre" else "Comment"
        return QMessageBox.question(self, f"New {kind}", f"“{value}” is not on the {kind} List. "
                                    f"Add it to the list?") == QMessageBox.Yes

    def replace_pic(self):
        if self.t:
            i = COVER_COLORS.index(self.t.pic) + 1 if self.t.pic in COVER_COLORS else 0
            self.t.pic = COVER_COLORS[i % len(COVER_COLORS)]
            self.store.changed.emit()

    def remove_pic(self):
        if self.t:
            self.t.pic = None
            self.store.changed.emit()


class SettingsWidget(QTabWidget):
    """Editors for everything in the config file (lists, mapping, rules, template, normalize)."""

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.addTab(self._lists(), "Genre && Comment lists")
        self.addTab(self._mapping(), "Genre Folder Mapping")
        self.addTab(self._rules(), "Validation Rules")
        self.addTab(self._rename(), "Rename template")
        self.addTab(self._normalize(), "Normalize && Inbox")

    def _lists(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        for key, title in (("genre", "Genre List"), ("comment", "Comment List")):
            box = QGroupBox(title)
            lw, ed = QListWidget(), QLineEdit()
            add, rm = QPushButton("Add"), QPushButton("Remove selected")

            def reload(lw=lw, key=key):
                lw.clear()
                lw.addItems(self.store.cfg.lists[key])

            def do_add(ed=ed, key=key, reload=reload):
                if ed.text().strip():
                    self.store.cfg.lists[key].append(ed.text().strip())
                    ed.clear()
                    reload()
                    self.store.changed.emit()

            def do_rm(lw=lw, key=key, reload=reload):
                for it in lw.selectedItems():
                    self.store.cfg.lists[key].remove(it.text())
                reload()
                self.store.changed.emit()

            add.clicked.connect(do_add)
            rm.clicked.connect(do_rm)
            reload()
            v = QVBoxLayout(box)
            v.addWidget(lw)
            h = QHBoxLayout()
            h.addWidget(ed)
            h.addWidget(add)
            v.addLayout(h)
            v.addWidget(rm)
            lay.addWidget(box)
        return w

    def _mapping(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Genre (exact, or trailing-* wildcard) \u2192 destination folder. "
                           "Exact entries beat wildcards. Folders may use {YYYY}/{MM}/{DD}."))
        tb = QTableWidget(0, 2)
        tb.setHorizontalHeaderLabels(["Genre / pattern", "Destination folder"])
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        def load():
            tb.blockSignals(True)
            tb.setRowCount(0)
            for pat, folder in self.store.cfg.mapping:
                r = tb.rowCount()
                tb.insertRow(r)
                tb.setItem(r, 0, QTableWidgetItem(pat))
                tb.setItem(r, 1, QTableWidgetItem(folder))
            tb.blockSignals(False)

        def edited(r, c):
            self.store.cfg.mapping[r][c] = tb.item(r, c).text()
            self.store.changed.emit()

        def add():
            self.store.cfg.mapping.append(["New*", "D:/Music/"])
            load()
            self.store.changed.emit()

        def rm():
            for r in sorted({i.row() for i in tb.selectedIndexes()}, reverse=True):
                del self.store.cfg.mapping[r]
            load()
            self.store.changed.emit()

        tb.cellChanged.connect(edited)
        load()
        v.addWidget(tb)
        h = QHBoxLayout()
        for text, fn in (("Add mapping", add), ("Remove selected", rm)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        return w

    def _rules(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Rule Types: Required \u00b7 OneOf \u00b7 YearRange. Each rule is "
                           "independently Hard (blocks Rename & File) or Soft (warning)."))
        rules = self.store.cfg.rules
        tb = QTableWidget(len(rules), 5)
        tb.setHorizontalHeaderLabels(["Rule", "Type", "Field", "Params", "Severity"])
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i, r in enumerate(rules):
            params = {"OneOf": f"list: {r['field'].title()} List",
                      "YearRange": f"{r.get('min')} \u2013 {r.get('max')}"}.get(r["type"], "")
            for c, txt in enumerate((r["name"], r["type"], r["field"], params)):
                tb.setItem(i, c, QTableWidgetItem(txt))
            cb = QComboBox()
            cb.addItems(["Hard", "Soft"])
            cb.setCurrentText(r["sev"])

            def chg(txt, r=r):
                r["sev"] = txt
                self.store.changed.emit()

            cb.currentTextChanged.connect(chg)
            tb.setCellWidget(i, 4, cb)
        v.addWidget(tb)
        return w

    def _rename(self):
        w = QWidget()
        v = QVBoxLayout(w)
        ed = QLineEdit(self.store.cfg.template)
        pv = QLabel()
        v.addWidget(QLabel("Template (use / for nested subfolders)"))
        v.addWidget(ed)
        v.addWidget(QLabel("Tokens: {Title} {Artist} {Album} {Genre} {Year} {Comment}  \u00b7  "
                           "{YYYY} {MM} {DD} (processing date)"))
        v.addWidget(pv)
        v.addStretch()

        def upd(txt=None):
            if txt is not None:
                self.store.cfg.template = txt
                self.store.changed.emit()
            if self.store.tracks:
                pv.setText("Preview: " + self.store.new_path(self.store.tracks[0]))

        ed.textChanged.connect(upd)
        upd()
        return w

    def _normalize(self):
        w = QFormLayout()
        c = self.store.cfg
        db = QDoubleSpinBox()
        db.setRange(70, 100)
        db.setValue(c.target_db)
        clip = QCheckBox("Clipping allowed")
        clip.setChecked(c.clipping_allowed)
        inbox = QLineEdit(c.inbox)
        cmd = QLabel()

        def upd():
            c.target_db, c.clipping_allowed, c.inbox = db.value(), clip.isChecked(), inbox.text()
            cmd.setText(f"mp3rgain -r -d {c.target_db - 89:+.1f}" + ("" if c.clipping_allowed else " -k"))

        for sig in (db.valueChanged, clip.toggled, inbox.textChanged):
            sig.connect(upd)
        upd()
        w.addRow("Inbox folder", inbox)
        w.addRow("Target volume (dB)", db)
        w.addRow("", clip)
        w.addRow("Resulting command", cmd)
        box = QWidget()
        box.setLayout(w)
        return box


# --------------------------------------------------------------------------- variant A


class VariantA(QWidget):
    label = "Table + inspector"
    # "Show" filter: pick a state to see only the Tracks that are in it
    FILTERS = [
        ("All", lambda s, t: True),
        ("To normalize", lambda s, t: s.needs_normalize(t)),
        ("Needs tags", lambda s, t: s.readiness(t) != "ok"),
        ("Ready to Rename & File", lambda s, t: s.readiness(t) != "blocked" and not t.fail
         and not s.needs_normalize(t)),
        ("Flagged", lambda s, t: bool(t.fail)),
        ("Unmapped Genre", lambda s, t: s.dest_folder(t) is None),
    ]

    def __init__(self, store, open_settings):
        super().__init__()
        self.store, self.rows, self._busy = store, [], False
        self.btn_n = QPushButton("Normalize selected")
        self.btn_rf = QPushButton("Rename && File selected")
        self.filter = QComboBox()
        self.filter.addItems([name for name, _ in self.FILTERS])
        self.summary = QLabel()
        btn_set = QPushButton("Settings\u2026")

        top = QHBoxLayout()
        for w in (self.btn_n, self.btn_rf, QLabel("  Show:"), self.filter):
            top.addWidget(w)
        top.addStretch()
        top.addWidget(self.summary)
        top.addWidget(btn_set)

        # Columns are hardcoded here; they should later be user configurable.
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["#", "Path", "Filename", "Genre", "Year", "Comment",
                                              "Norm", "Tag", "Rename", "File"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        hh = self.table.horizontalHeader()
        for c in range(10):
            hh.setSectionResizeMode(c, QHeaderView.Stretch if c == 2 else QHeaderView.ResizeToContents)

        self.form = TagForm(store, cover_size=200)
        self.checks, self.where = rich_label(), rich_label()
        insp = QWidget()
        iv = QVBoxLayout(insp)
        iv.addWidget(self.form)
        g1 = QGroupBox("Rule checks")
        QVBoxLayout(g1).addWidget(self.checks)
        g2 = QGroupBox("Pipeline state")
        QVBoxLayout(g2).addWidget(self.where)
        iv.addWidget(g1)
        iv.addWidget(g2)
        iv.addStretch()

        sp = QSplitter()
        sp.addWidget(self.table)
        sp.addWidget(insp)
        sp.setSizes([620, 380])
        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(sp, 1)

        store.changed.connect(self.refresh)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self.on_select)
        self.btn_n.clicked.connect(lambda: store.run_normalize(self.selected()))
        self.btn_rf.clicked.connect(lambda: store.run_rename_file(self.selected()))
        btn_set.clicked.connect(open_settings)
        self.refresh()

    def selected(self):
        return [self.rows[i.row()].file for i in self.table.selectionModel().selectedRows()]

    def refresh(self):
        keep = set(self.selected())
        self._busy = True
        s = self.store
        for i, (name, pred) in enumerate(self.FILTERS):
            self.filter.setItemText(i, f"{name} ({sum(1 for t in s.tracks if pred(s, t))})")
        pred = self.FILTERS[self.filter.currentIndex()][1]
        self.rows = [t for t in s.tracks if pred(s, t)]
        self.table.setRowCount(len(self.rows))
        for r, t in enumerate(self.rows):
            num = QTableWidgetItem(str(r + 1))
            num.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, num)
            self.table.setItem(r, 1, QTableWidgetItem(t.folder or "/"))
            self.table.setItem(r, 2, QTableWidgetItem(t.file))
            self.table.setItem(r, 3, QTableWidgetItem(t.genre or "\u2014"))
            self.table.setItem(r, 4, QTableWidgetItem(t.year or "\u2014"))
            self.table.setItem(r, 5, QTableWidgetItem(t.comment or "\u2014"))
            st = s.stages(t)
            for c, k in enumerate("NTRF", start=6):
                tip = st[k][1]
                if k == "T":
                    tip = rules_html(s, t)
                self.table.setItem(r, c, chip_item(st[k][0], tip))
            if t.file in keep:
                self.table.selectRow(r)
        self._busy = False
        flagged = sum(1 for t in s.tracks if t.fail)
        unmapped = sum(1 for t in s.tracks if s.dest_folder(t) is None)
        self.summary.setText(f"Showing {len(self.rows)} of {len(s.tracks)} \u00b7 {flagged} flagged \u00b7 "
                             f"{unmapped} unmapped Genre   ")
        self.on_select()

    def on_select(self):
        if self._busy:
            return
        sel = self.store.by_files(self.selected())
        if len(sel) == 1:
            t = sel[0]
            self.form.set_track(t)
            self.checks.setText(rules_html(self.store, t, only_failures=True))
            self.where.setText(stages_html(self.store, t))
        else:
            self.form.set_track(None)
            self.checks.setText(f"{len(sel)} tracks selected" if sel else "Select a track")
            self.where.setText("")


# --------------------------------------------------------------------------- variant B


class VariantB(QWidget):
    label = "Pipeline board"
    COLS = [("N", "\u2460 Normalize", "Normalize selected"),
            ("T", "\u2461 Tag", "Edit selected \u2193"),
            ("R", "\u2462 Rename", "Rename && File selected"),
            ("F", "\u2463 File", "Rename && File selected"),
            ("X", "\u2691 Flagged", "Clear flag && retry")]

    def __init__(self, store, open_settings):
        super().__init__()
        self.store, self._busy, self.lists, self.heads = store, False, {}, {}
        board = QHBoxLayout()
        for key, title, action in self.COLS:
            col = QVBoxLayout()
            head = QLabel()
            head.setStyleSheet("font-weight:bold; padding:4px;")
            lw = QListWidget()
            lw.setSelectionMode(QAbstractItemView.ExtendedSelection)
            lw.setWordWrap(True)
            btn = QPushButton(action)
            col.addWidget(head)
            col.addWidget(lw, 1)
            col.addWidget(btn)
            board.addLayout(col, 1)
            self.lists[key], self.heads[key] = lw, head
            lw.itemSelectionChanged.connect(lambda k=key: self.on_select(k))
            btn.clicked.connect(lambda _=False, k=key: self.act(k))
        btn_set = QPushButton("Settings\u2026")
        btn_set.clicked.connect(open_settings)
        top = QHBoxLayout()
        top.addWidget(QLabel("Each Track sits in the column of its next outstanding stage."))
        top.addStretch()
        top.addWidget(btn_set)

        self.form = TagForm(store, cover_size=130, horizontal=True)
        self.checks, self.where = rich_label(), rich_label()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.form, "Tags")
        self.tabs.addTab(self.checks, "Rule checks")
        self.tabs.addTab(self.where, "Pipeline state")
        self.tabs.setFixedHeight(250)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addLayout(board, 1)
        root.addWidget(self.tabs)
        store.changed.connect(self.refresh)
        self.refresh()

    def act(self, key):
        files = [i.data(Qt.UserRole) for i in self.lists[key].selectedItems()]
        if key == "N":
            self.store.run_normalize(files)
        elif key == "T":
            self.tabs.setCurrentIndex(0)
        elif key == "X":
            self.store.retry(files)
        else:
            self.store.run_rename_file(files)

    def on_select(self, key):
        if self._busy:
            return
        sel = self.lists[key].selectedItems()
        if sel:
            self._busy = True
            for k, lw in self.lists.items():
                if k != key:
                    lw.clearSelection()
            self._busy = False
        t = self.store.by_files([sel[0].data(Qt.UserRole)])[0] if len(sel) >= 1 else None
        self.form.set_track(t)
        self.checks.setText(rules_html(self.store, t))
        self.where.setText(stages_html(self.store, t))

    def refresh(self):
        keep = {i.data(Qt.UserRole) for lw in self.lists.values() for i in lw.selectedItems()}
        self._busy = True
        for lw in self.lists.values():
            lw.clear()
        for t in self.store.tracks:
            k = self.store.column(t)
            rd = self.store.readiness(t)
            st = self.store.stages(t)
            lines = [t.title or "(untitled)", f"{t.artist or '(no artist)'} \u00b7 {t.fmt}"]
            state = {"ok": "pending", "warn": "warn", "blocked": "blocked"}[rd]
            if k == "X":
                lines.append("! " + t.fail[1])
                state = "failed"
            elif k == "F" and st["F"][0] == "blocked":
                lines.append("\u2715 " + st["F"][1])
                state = "blocked"
            elif k == "R" and rd == "warn":
                lines.append("\u26a0 soft rule warning(s)")
            elif k == "T":
                n = sum(1 for r, o in self.store.results(t) if o == "fail" and r["sev"] == "Hard")
                lines.append(f"\u2715 {n} hard rule(s) failing")
            it = QListWidgetItem("\n".join(lines))
            it.setData(Qt.UserRole, t.file)
            it.setBackground(QColor(CHIP[state][1]))
            it.setForeground(QColor(CHIP[state][2]))
            self.lists[k].addItem(it)
            if t.file in keep:
                it.setSelected(True)
        for key, title, _ in self.COLS:
            self.heads[key].setText(f"{title}  ({self.lists[key].count()})")
        self._busy = False


# --------------------------------------------------------------------------- variant C


class VariantC(QWidget):
    label = "Stage-by-stage"

    def __init__(self, store):
        super().__init__()
        self.store, self._busy, self.queue_files = store, False, []
        self.nav = QListWidget()
        self.nav.setFixedWidth(190)
        self.pages = QStackedWidget()
        self.banner = QLabel()
        self.banner.setStyleSheet("background:#fbdcdc; color:#9b1c1c; padding:6px;")

        # Normalize page
        self.n_table = QTableWidget(0, 3)
        self.n_table.setHorizontalHeaderLabels(["Track", "Format", "Status"])
        self._style_table(self.n_table)
        self.n_info = QLabel()
        n_btn = QPushButton("Normalize selected")
        n_btn.clicked.connect(lambda: store.run_normalize(self._files(self.n_table, self.n_files)))
        self.pages.addWidget(self._page("Normalize", self.n_info, self.n_table, n_btn))

        # Tag page
        self.queue = QListWidget()
        self.queue.setFixedWidth(250)
        self.show_all = QCheckBox("Include Tracks that already pass")
        self.form = TagForm(store, cover_size=260, horizontal=True, show_apply=False)
        self.checks = rich_label()
        prev, apply_, nxt = QPushButton("\u25c0 Previous"), QPushButton("Apply"), QPushButton("Apply && next \u25b6")
        prev.clicked.connect(lambda: self.step(-1, False))
        apply_.clicked.connect(lambda: self.step(0, True))
        nxt.clicked.connect(lambda: self.step(1, True))
        right = QVBoxLayout()
        right.addWidget(self.form)
        g = QGroupBox("Rule checks")
        QVBoxLayout(g).addWidget(self.checks)
        right.addWidget(g)
        bl = QHBoxLayout()
        for b in (prev, apply_, nxt):
            bl.addWidget(b)
        right.addLayout(bl)
        left = QVBoxLayout()
        left.addWidget(QLabel("Review queue"))
        left.addWidget(self.queue, 1)
        left.addWidget(self.show_all)
        tag = QWidget()
        h = QHBoxLayout(tag)
        h.addLayout(left)
        h.addLayout(right, 1)
        self.pages.addWidget(self._page("Tag", None, tag, None))

        # Rename & File page
        self.rf_table = QTableWidget(0, 4)
        self.rf_table.setHorizontalHeaderLabels(["Track", "New name (Rename)", "Destination (File)", "Status"])
        self._style_table(self.rf_table)
        rf_btn = QPushButton("Rename && File selected")
        rf_btn.clicked.connect(lambda: store.run_rename_file(self._files(self.rf_table, self.rf_files)))
        self.pages.addWidget(self._page("Rename & File", None, self.rf_table, rf_btn))

        # Flagged page
        self.x_table = QTableWidget(0, 3)
        self.x_table.setHorizontalHeaderLabels(["Track", "Stage", "Reason"])
        self._style_table(self.x_table)
        x_btn = QPushButton("Clear flag && retry")
        x_btn.clicked.connect(lambda: store.retry(self._files(self.x_table, self.x_files)))
        self.pages.addWidget(self._page("Flagged", None, self.x_table, x_btn))

        # Settings page
        self.pages.addWidget(self._page("Settings", None, SettingsWidget(store), None))

        right_col = QVBoxLayout()
        right_col.addWidget(self.banner)
        right_col.addWidget(self.pages, 1)
        root = QHBoxLayout(self)
        root.addWidget(self.nav)
        root.addLayout(right_col, 1)

        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.queue.currentRowChanged.connect(self.on_queue)
        self.show_all.toggled.connect(self.refresh)
        store.changed.connect(self.refresh)
        self.nav.addItems(["Normalize", "Tag", "Rename & File", "Flagged", "Settings"])
        self.nav.setCurrentRow(1)
        self.refresh()

    def _style_table(self, tb):
        tb.setSelectionBehavior(QAbstractItemView.SelectRows)
        tb.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.verticalHeader().hide()
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def _page(self, title, info, body, button):
        w = QWidget()
        v = QVBoxLayout(w)
        h = QLabel(title)
        h.setStyleSheet("font-size:18px; font-weight:bold;")
        v.addWidget(h)
        if info:
            v.addWidget(info)
        v.addWidget(body, 1)
        if button:
            v.addWidget(button, alignment=Qt.AlignRight)
        return w

    def _files(self, table, files):
        return [files[i.row()] for i in table.selectionModel().selectedRows()]

    def refresh(self):
        s, c = self.store, self.store.cfg
        tracks = s.tracks
        self._busy = True

        # Normalize
        self.n_files = [t.file for t in tracks]
        self.n_table.setRowCount(len(tracks))
        for r, t in enumerate(tracks):
            self.n_table.setItem(r, 0, QTableWidgetItem(f"{t.artist or '?'} \u2014 {t.title or '(untitled)'}"))
            self.n_table.setItem(r, 1, QTableWidgetItem(t.fmt))
            state, detail = s.stages(t)["N"]
            it = QTableWidgetItem(f"{CHIP[state][0]} {detail}")
            it.setForeground(QColor(CHIP[state][2]))
            self.n_table.setItem(r, 2, it)
        self.n_info.setText(f"Target {c.target_db:.0f} dB \u00b7 clipping "
                            f"{'allowed' if c.clipping_allowed else 'not allowed'} (change under Settings). "
                            "wav, flac and ogg skip this stage.")

        # Tag queue
        cur = self.queue_files[self.queue.currentRow()] if 0 <= self.queue.currentRow() < len(self.queue_files) else None
        q = [t for t in tracks if self.show_all.isChecked() or s.readiness(t) != "ok"]
        self.queue_files = [t.file for t in q]
        self.queue.clear()
        for t in q:
            rd = s.readiness(t)
            it = QListWidgetItem(f"{CHIP[{'ok': 'done', 'warn': 'warn', 'blocked': 'blocked'}[rd]][0]}  "
                                 f"{t.title or '(untitled)'} \u2014 {t.artist or '?'}")
            it.setForeground(QColor(CHIP[{'ok': 'done', 'warn': 'warn', 'blocked': 'blocked'}[rd]][2]))
            self.queue.addItem(it)
        self._busy = False
        if cur in self.queue_files:
            self.queue.setCurrentRow(self.queue_files.index(cur))
        elif q:
            self.queue.setCurrentRow(0)
        else:
            self.on_queue(-1)

        # Rename & File
        self.rf_files = [t.file for t in tracks]
        self.rf_table.setRowCount(len(tracks))
        for r, t in enumerate(tracks):
            st = s.stages(t)
            self.rf_table.setItem(r, 0, QTableWidgetItem(f"{t.artist or '?'} \u2014 {t.title or '(untitled)'}"))
            self.rf_table.setItem(r, 1, QTableWidgetItem("(renamed)" if t.renamed else s.new_path(t)))
            self.rf_table.setItem(r, 2, QTableWidgetItem(s.dest_folder(t) or "\u2014 no mapping \u2014"))
            if st["R"][0] == "blocked" or st["F"][0] == "blocked" or s.needs_normalize(t):
                reason = st["R"][1] if st["R"][0] == "blocked" else (
                    st["F"][1] if st["F"][0] == "blocked" else "Normalize first")
                txt, col = "\u2715 " + reason, CHIP["blocked"][2]
            else:
                txt, col = "\u2713 ready" + (" (soft warnings)" if s.readiness(t) == "warn" else ""), CHIP["done"][2]
            it = QTableWidgetItem(txt)
            it.setForeground(QColor(col))
            self.rf_table.setItem(r, 3, it)

        # Flagged
        fl = [t for t in tracks if t.fail]
        self.x_files = [t.file for t in fl]
        self.x_table.setRowCount(len(fl))
        for r, t in enumerate(fl):
            self.x_table.setItem(r, 0, QTableWidgetItem(f"{t.artist or '?'} \u2014 {t.title}"))
            self.x_table.setItem(r, 1, QTableWidgetItem(STAGE_NAMES[t.fail[0]]))
            self.x_table.setItem(r, 2, QTableWidgetItem(t.fail[1]))

        # nav counts + banner
        counts = [sum(1 for t in tracks if s.needs_normalize(t)),
                  sum(1 for t in tracks if s.readiness(t) != "ok"),
                  sum(1 for t in tracks if s.readiness(t) != "blocked" and not t.fail and not s.needs_normalize(t)),
                  len(fl), None]
        names = ["Normalize", "Tag", "Rename & File", "Flagged", "Settings"]
        row = self.nav.currentRow()
        self.nav.blockSignals(True)
        for i, n in enumerate(names):
            self.nav.item(i).setText(n if counts[i] is None else f"{n}   ({counts[i]})")
        self.nav.blockSignals(False)
        unmapped = [t for t in tracks if s.dest_folder(t) is None]
        msgs = []
        if fl:
            msgs.append(f"{len(fl)} Track(s) flagged")
        if unmapped:
            msgs.append(f"{len(unmapped)} Track(s) have a Genre with no folder mapping and cannot be Filed")
        self.banner.setVisible(bool(msgs))
        self.banner.setText("  \u00b7  ".join(msgs))

    def on_queue(self, row):
        if self._busy:
            return
        t = self.store.by_files([self.queue_files[row]])[0] if 0 <= row < len(self.queue_files) else None
        self.form.set_track(t)
        self.checks.setText(rules_html(self.store, t) if t else "Nothing left to review.")

    def step(self, delta, apply):
        row = self.queue.currentRow()
        nxt = self.queue_files[min(max(row + delta, 0), len(self.queue_files) - 1)] if self.queue_files else None
        if apply:
            self.form.apply()
        if nxt in self.queue_files:
            self.queue.setCurrentRow(self.queue_files.index(nxt))


# --------------------------------------------------------------------------- shell


class Main(QMainWindow):
    def __init__(self, start=0):
        super().__init__()
        self.store = Store()
        self.stack = QStackedWidget()

        def open_settings():
            d = QDialog(self)
            d.setWindowTitle("Settings")
            QVBoxLayout(d).addWidget(SettingsWidget(self.store))
            d.resize(820, 480)
            d.exec()

        self.views = [VariantA(self.store, open_settings),
                      VariantB(self.store, open_settings),
                      VariantC(self.store)]
        for v in self.views:
            self.stack.addWidget(v)

        self.prev, self.nextb = QToolButton(), QToolButton()
        self.prev.setText("\u25c0")
        self.nextb.setText("\u25b6")
        self.lbl = QLabel()
        pill = QFrame()
        pill.setStyleSheet("QFrame{background:#1f1f1f; border-radius:16px;} "
                           "QLabel{color:white; font-weight:bold; padding:0 10px;} "
                           "QToolButton{color:white; border:none; padding:4px 10px; background:transparent;}")
        ph = QHBoxLayout(pill)
        ph.setContentsMargins(6, 4, 6, 4)
        for w in (self.prev, self.lbl, self.nextb):
            ph.addWidget(w)
        bar = QHBoxLayout()
        bar.addStretch()
        bar.addWidget(pill)
        bar.addStretch()

        central = QWidget()
        v = QVBoxLayout(central)
        v.addWidget(self.stack, 1)
        v.addLayout(bar)
        self.setCentralWidget(central)
        self.resize(1280, 800)
        self.prev.clicked.connect(lambda: self.cycle(-1))
        self.nextb.clicked.connect(lambda: self.cycle(1))
        self.store.message.connect(lambda m: self.statusBar().showMessage(m, 8000))
        self.show_variant(start)

    def show_variant(self, i):
        self.cur = i % len(self.views)
        self.stack.setCurrentIndex(self.cur)
        name = f"{'ABC'[self.cur]} ({self.views[self.cur].label})"
        self.lbl.setText(name)
        self.setWindowTitle(f"PROTOTYPE \u2014 DJ Prepare GUI layout \u2014 {name}")

    def cycle(self, d):
        self.show_variant(self.cur + d)


class ArrowKeys(QObject):
    def __init__(self, win):
        super().__init__()
        self.win = win

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress and ev.key() in (Qt.Key_Left, Qt.Key_Right):
            fw = QApplication.focusWidget()
            if not isinstance(fw, (QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox)):
                self.win.cycle(-1 if ev.key() == Qt.Key_Left else 1)
                return True
        return False


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    start = 0
    if "--variant" in sys.argv:
        start = "ABC".index(sys.argv[sys.argv.index("--variant") + 1].upper())
    win = Main(start)
    app.installEventFilter(ArrowKeys(win))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
