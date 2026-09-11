# -*- coding: utf-8 -*-
"""Modern ISC / CGR customer quotation PDF generator.

Self-contained; uses PyMuPDF (fitz) which the companion app already ships.
Verdana is loaded from the Windows font folder; if unavailable (e.g. when
testing on Linux) it falls back to Helvetica so the layout still renders.

build_quote_pdf(data, out_path) -> out_path
"""
import os
import datetime
import fitz

BASE   = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")

# ---- palette (CGR brand) -------------------------------------------------
BLUE   = (0.137, 0.208, 0.420)
BLUED  = (0.090, 0.145, 0.310)
PINK   = (0.749, 0.220, 0.478)
INK    = (0.102, 0.133, 0.188)
GREY   = (0.420, 0.460, 0.520)
LIGHT  = (0.945, 0.957, 0.972)
PANEL  = (0.960, 0.968, 0.980)
GOLD   = (0.992, 0.945, 0.851)
GOLDLN = (0.851, 0.659, 0.318)
LINE   = (0.808, 0.835, 0.875)
WHITE  = (1, 1, 1)

WINF = r"C:\Windows\Fonts"


def _verdana():
    want = {"reg": "verdana.ttf", "bold": "verdanab.ttf", "ital": "verdanai.ttf"}
    out = {}
    for k, n in want.items():
        p = os.path.join(WINF, n)
        if os.path.exists(p):
            out[k] = p
    return out if len(out) == 3 else None


VERD = _verdana()
if VERD:
    _FREG = fitz.Font(fontfile=VERD["reg"])
    _FBLD = fitz.Font(fontfile=VERD["bold"])
else:
    _FREG = fitz.Font("helv")
    _FBLD = fitz.Font("hebo")


def _tw(s, size, bold=False):
    return (_FBLD if bold else _FREG).text_length(str(s), size)


def _wrap(text, width, size, bold=False):
    lines = []
    for para in str(text).split("\n"):
        words, cur = para.split(), ""
        for w in words:
            t = (cur + " " + w).strip()
            if _tw(t, size, bold) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines or [""]


def _money(v, dec=4):
    try:
        return "${:,.{d}f}".format(float(v), d=dec)
    except Exception:
        return "-"


def _qty(v):
    try:
        return "{:,}".format(int(round(float(v))))
    except Exception:
        return str(v)


def _safe(s):
    return "".join(c for c in str(s) if c not in '\\/:*?"<>|').strip() or "Quote"


class _Sheet:
    """One PDF; helpers carry the current page + y cursor."""

    M = 40
    W = 612
    H = 792
    BOTTOM = 712

    def __init__(self, data):
        self.data = data
        self.doc = fitz.open()
        self.page = None
        self.F = None
        self.y = 0
        self._new_page(first=True)

    # -- fonts / primitives ------------------------------------------------
    def _fonts(self, page):
        if VERD:
            page.insert_font(fontname="vd", fontfile=VERD["reg"])
            page.insert_font(fontname="vb", fontfile=VERD["bold"])
            page.insert_font(fontname="vi", fontfile=VERD["ital"])
            return {"r": "vd", "b": "vb", "i": "vi"}
        return {"r": "helv", "b": "hebo", "i": "heit"}

    def txt(self, x, y, s, size, f="r", color=INK):
        self.page.insert_text((x, y), str(s), fontname=self.F[f],
                              fontsize=size, color=color)

    def rtxt(self, xr, y, s, size, f="r", color=INK):
        self.txt(xr - _tw(s, size, f == "b"), y, s, size, f, color)

    def ctxt(self, xc, y, s, size, f="r", color=INK):
        self.txt(xc - _tw(s, size, f == "b") / 2.0, y, s, size, f, color)

    def rect(self, x0, y0, x1, y1, fill=None, stroke=None, w=0.7):
        self.page.draw_rect(fitz.Rect(x0, y0, x1, y1),
                            color=stroke, fill=fill, width=w)

    def hline(self, x0, x1, y, color=LINE, w=0.7):
        self.page.draw_line((x0, y), (x1, y), color=color, width=w)

    # -- pages -------------------------------------------------------------
    def _new_page(self, first=False):
        self.page = self.doc.new_page(width=self.W, height=self.H)
        self.F = self._fonts(self.page)
        self._header(first)

    def _header(self, first):
        M = self.M
        isc = os.path.join(ASSETS, "isc_logo.png")
        cgr = os.path.join(ASSETS, "cgr_logo.png")
        if os.path.exists(isc):
            self.page.insert_image(fitz.Rect(M, 34, M + 27, 34 + 48), filename=isc)
        if os.path.exists(cgr):
            self.page.insert_image(fitz.Rect(self.W - M - 70, 40,
                                             self.W - M, 40 + 36), filename=cgr)
        self.ctxt(self.W / 2, 50, "INDUSTRIAL SPRING CORPORATION", 11.5, "b", BLUE)
        self.ctxt(self.W / 2, 62, "A CGR International Company", 8, "r", PINK)
        self.ctxt(self.W / 2, 74,
                  "1801 Bedford Rd  -  North Kansas City, MO 64116  -  "
                  "816-741-6073  -  www.isckc.com", 7.5, "r", GREY)
        self.rect(M, 88, self.W - M, 90.6, fill=BLUE)
        self.rect(M, 88, M + 150, 90.6, fill=PINK)
        if first:
            self.y = 108
        else:
            self.txt(M, 108, "Quotation " + str(self.data.get("quoteNo", "")) +
                     "  -  continued", 9, "i", GREY)
            self.y = 124

    def ensure(self, h):
        if self.y + h > self.BOTTOM:
            self._new_page(first=False)

    # -- page-1 blocks -----------------------------------------------------
    def title_block(self):
        M, W = self.M, self.W
        d = self.data
        self.txt(M, self.y + 20, "QUOTATION", 23, "b", BLUE)
        # meta panel (right)
        bx0, bx1 = 372, W - M
        rows = [("Quote No.", d.get("quoteNo", "")),
                ("Quote Date", d.get("date", "")),
                ("Valid Until", d.get("validUntil", "")),
                ("Payment Terms", d.get("paymentTerms", "")),
                ("Lead Time / PO", d.get("leadTime", ""))]
        bh = 12 + len(rows) * 15.5
        self.rect(bx0, self.y, bx1, self.y + bh, fill=PANEL, stroke=LINE, w=0.8)
        self.rect(bx0, self.y, bx0 + 3, self.y + bh, fill=PINK)
        ry = self.y + 16
        for k, v in rows:
            self.txt(bx0 + 12, ry, k.upper(), 7.2, "b", GREY)
            self.rtxt(bx1 - 10, ry, v if v else "-", 9, "b", BLUED)
            ry += 15.5
        # customer block (left)
        cy = self.y + 46
        self.txt(M, cy, "PREPARED FOR", 7.5, "b", PINK)
        self.txt(M, cy + 18, d.get("customer", ""), 14, "b", INK)
        self.y = max(self.y + bh, cy + 32) + 16
        self.txt(M, self.y, "We are pleased to quote the following:", 9, "i", GREY)
        self.y += 14

    # -- line item ---------------------------------------------------------
    def line_item(self, idx, ln):
        M, W = self.M, self.W
        cw = W - 2 * M
        tiers = ln.get("tiers") or []
        # height estimate for pagination
        remarks = _wrap(ln.get("remarks", ""), cw - 16, 8.2, False) if ln.get("remarks") else []
        need = 22 + 26 + 18 + (len(tiers) + 1) * 18 + (len(remarks) * 11 + 18 if remarks else 6) + 14
        self.ensure(need)
        # part header bar
        self.rect(M, self.y, M + cw, self.y + 21, fill=BLUE)
        self.txt(M + 9, self.y + 14, "ITEM " + str(idx), 8, "b", PINK)
        self.txt(M + 52, self.y + 14, "Part  " + str(ln.get("partNo", "-")),
                 10, "b", WHITE)
        self.y += 21
        # description + spec line
        self.txt(M + 2, self.y + 14, ln.get("description", ""), 9.5, "r", INK)
        spec = []
        if ln.get("material"):
            spec.append("Material: " + str(ln["material"]))
        if ln.get("finish"):
            spec.append("Finish: " + str(ln["finish"]))
        if ln.get("wireDia"):
            spec.append("Wire " + str(ln["wireDia"]))
        self.txt(M + 2, self.y + 26, "   -   ".join(spec), 8, "r", GREY)
        self.y += 34
        # price-ladder table
        c1, c2, c3 = M, M + cw * 0.40, M + cw * 0.70
        cend = M + cw
        self.rect(c1, self.y, cend, self.y + 17, fill=BLUED)
        self.txt(c1 + 9, self.y + 12, "ORDER QUANTITY", 7.6, "b", WHITE)
        self.rtxt(c3 - 12, self.y + 12, "UNIT PRICE (USD)", 7.6, "b", WHITE)
        self.rtxt(cend - 9, self.y + 12, "BATCH TOTAL", 7.6, "b", WHITE)
        self.y += 17
        rows = tiers if tiers else [{"qty": ln.get("quotedQty"),
                                     "price": ln.get("price")}]
        for i, t in enumerate(rows):
            q, pr = t.get("qty"), t.get("price")
            rh = 18
            if i % 2:
                self.rect(c1, self.y, cend, self.y + rh, fill=LIGHT)
            self.txt(c1 + 9, self.y + 12.6, _qty(q) + "  pcs", 9, "r", INK)
            self.rtxt(c3 - 12, self.y + 12.8, _money(pr, 4), 10.5, "b", INK)
            try:
                tot = float(q) * float(pr)
                self.rtxt(cend - 9, self.y + 12.6, _money(tot, 2), 9, "r", GREY)
            except Exception:
                pass
            self.hline(c1, cend, self.y + rh, LINE, 0.5)
            self.y += rh
        self.rect(c1, self.y - len(rows) * 18 - 17, cend, self.y,
                  fill=None, stroke=LINE, w=0.8)
        self.y += 6
        # remarks
        if remarks:
            self.rect(M, self.y, M + cw, self.y + len(remarks) * 11 + 14,
                      fill=PANEL, stroke=LINE, w=0.6)
            self.txt(M + 8, self.y + 12, "Feasibility remarks", 7.4, "b", PINK)
            ry = self.y + 12
            for r in remarks:
                ry += 11
                self.txt(M + 8, ry, r, 8.2, "i", GREY)
            self.y += len(remarks) * 11 + 14
        self.y += 12

    # -- closing -----------------------------------------------------------
    # -- multi-part horizontal price matrix --------------------------------
    def _ellip(self, s, maxw, size, bold):
        s = str(s or "")
        if _tw(s, size, bold) <= maxw:
            return s
        while s and _tw(s + "...", size, bold) > maxw:
            s = s[:-1]
        return (s + "...") if s else ""

    def line_matrix(self, lines):
        M, W = self.M, self.W
        cw = W - 2 * M
        qset = set()
        for ln in lines:
            ts = ln.get("tiers") or []
            if ts:
                for t in ts:
                    try:
                        qset.add(int(round(float(t.get("qty")))))
                    except Exception:
                        pass
            elif ln.get("quotedQty"):
                try:
                    qset.add(int(round(float(ln["quotedQty"]))))
                except Exception:
                    pass
        qtys = sorted(q for q in qset if q > 0)[:8]
        if not qtys:
            qtys = [0]
        xN, xP, xD, xM, xQ0 = M, M + 22, M + 100, M + 250, M + 320
        nQ = len(qtys)
        qw = (M + cw - xQ0) / nQ
        self.ensure(56 + len(lines) * 19)
        self.txt(M, self.y + 9,
                 "PRICE SCHEDULE  -  unit price (USD) by order quantity", 8, "b", BLUE)
        self.y += 14
        top = self.y
        hh = 26
        self.rect(M, self.y, M + cw, self.y + hh, fill=BLUED)
        self.txt(xN + 3, self.y + hh - 9, "#", 7.2, "b", WHITE)
        self.txt(xP + 2, self.y + hh - 9, "PART NUMBER", 7.2, "b", WHITE)
        self.txt(xD + 2, self.y + hh - 9, "DESCRIPTION", 7.2, "b", WHITE)
        self.txt(xM + 2, self.y + hh - 9, "MATERIAL", 7.2, "b", WHITE)
        for j, q in enumerate(qtys):
            cx = xQ0 + j * qw
            self.ctxt(cx + qw / 2, self.y + 12, _qty(q), 8.2, "b", WHITE)
            self.ctxt(cx + qw / 2, self.y + 21, "pcs", 6.4, "r", (0.72, 0.79, 0.91))
        self.y += hh
        for i, ln in enumerate(lines):
            rh = 18
            if i % 2:
                self.rect(M, self.y, M + cw, self.y + rh, fill=LIGHT)
            yb = self.y + 12.4
            self.txt(xN + 3, yb, str(i + 1), 8, "r", GREY)
            self.txt(xP + 2, yb, self._ellip(ln.get("partNo", "-"), xD - xP - 6, 8, True),
                     8, "b", INK)
            self.txt(xD + 2, yb, self._ellip(ln.get("description", ""), xM - xD - 6, 7.6, False),
                     7.6, "r", INK)
            self.txt(xM + 2, yb, self._ellip(ln.get("material", ""), xQ0 - xM - 6, 7.2, False),
                     7.2, "r", GREY)
            pmap = {}
            for t in (ln.get("tiers") or []):
                try:
                    pmap[int(round(float(t.get("qty"))))] = float(t.get("price"))
                except Exception:
                    pass
            if not pmap and ln.get("quotedQty"):
                try:
                    pmap[int(round(float(ln["quotedQty"])))] = float(ln.get("price") or 0)
                except Exception:
                    pass
            for j, q in enumerate(qtys):
                cx = xQ0 + j * qw
                v = pmap.get(q)
                self.ctxt(cx + qw / 2, yb, _money(v, 4) if v is not None else "-",
                          8.4, "b", BLUED if v is not None else GREY)
            self.hline(M, M + cw, self.y + rh, LINE, 0.5)
            self.y += rh
        self.rect(M, top, M + cw, self.y, fill=None, stroke=LINE, w=0.9)
        for j in range(1, nQ):
            gx = xQ0 + j * qw
            self.page.draw_line((gx, top), (gx, self.y), color=LINE, width=0.5)
        self.page.draw_line((xQ0, top), (xQ0, self.y), color=LINE, width=0.5)
        self.y += 12

    def remarks_block(self, lines):
        items = []
        for i, ln in enumerate(lines):
            r = str(ln.get("remarks", "")).strip()
            if r:
                items.append("Item %d  -  %s:  %s" % (i + 1, ln.get("partNo", "-"), r))
        if not items:
            return
        M, W = self.M, self.W
        cw = W - 2 * M
        wl = [_wrap(it, cw - 22, 7.6, False) for it in items]
        bh = sum(len(x) for x in wl) * 10 + 22
        self.ensure(bh + 8)
        self.rect(M, self.y, M + cw, self.y + bh, fill=PANEL, stroke=LINE, w=0.8)
        self.rect(M, self.y, M + 3, self.y + bh, fill=PINK)
        self.txt(M + 14, self.y + 14, "FEASIBILITY REMARKS", 7.6, "b", PINK)
        ry = self.y + 14
        for para in wl:
            for w in para:
                ry += 10
                self.txt(M + 14, ry, w, 7.6, "r", GREY)
        self.y += bh + 12

    def terms_block(self):
        M, W = self.M, self.W
        cw = W - 2 * M
        d = self.data
        terms = ("Lead time is %s after receipt of a firm purchase order, "
                 "subject to current workload.  Pricing is valid for %s days "
                 "from the quote date.  Terms are %s upon approval of credit.  "
                 "FOB our plant in North Kansas City, MO.  "
                 "Springs are manufactured to the dimensions specified on the "
                 "print; where no tolerances are given, the SMI Handbook of "
                 "Spring Design applies.  Standard shipment quantity variation "
                 "is " + chr(177) + "10%% unless otherwise negotiated."
                 ) % (d.get("leadTime", "-"), d.get("validDays", "30"),
                      d.get("paymentTerms", "Net 30"))
        wl = _wrap(terms, cw - 20, 7.8, False)
        bh = len(wl) * 10.5 + 26
        self.ensure(bh + 56)
        self.rect(M, self.y, M + cw, self.y + bh, fill=PANEL, stroke=LINE, w=0.8)
        self.rect(M, self.y, M + 3, self.y + bh, fill=BLUE)
        self.txt(M + 14, self.y + 15, "TERMS & CONDITIONS", 7.6, "b", BLUE)
        ry = self.y + 15
        for w in wl:
            ry += 10.5
            self.txt(M + 14, ry, w, 7.8, "r", GREY)
        self.y += bh + 14
        # footer
        fy = self.BOTTOM + 22
        self.hline(M, W - M, fy - 12, LINE, 0.7)
        self.ctxt(W / 2, fy, "Thank you for the opportunity to quote.  We "
                  "appreciate your business.", 8.5, "b", BLUE)
        self.ctxt(W / 2, fy + 12,
                  "This quotation is computer-generated and is valid without a "
                  "signature.", 7.2, "i", GREY)

    def build(self):
        self.title_block()
        lines = self.data.get("lines", [])
        if len(lines) > 1:
            self.line_matrix(lines)
            self.remarks_block(lines)
        else:
            for i, ln in enumerate(lines, 1):
                self.line_item(i, ln)
        self.terms_block()
        return self.doc


def build_quote_pdf(data, out_path):
    """Render the quote and save it. Returns the saved path."""
    try:
        base = datetime.datetime.strptime(str(data.get("date", ""))[:10], "%Y-%m-%d")
        data["date"] = base.strftime("%m/%d/%Y")
        if not data.get("validUntil"):
            days = int(data.get("validDays", 30) or 30)
            data["validUntil"] = (base + datetime.timedelta(days=days)).strftime("%m/%d/%Y")
    except Exception:
        pass
    doc = _Sheet(data).build()
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    return out_path


def quote_filename(customer, quote_no):
    return "%s - %s.pdf" % (_safe(customer), _safe(quote_no))
