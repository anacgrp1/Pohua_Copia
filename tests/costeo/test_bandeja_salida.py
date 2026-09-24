"""La bandeja de salida: Render redacta, el escritorio despacha.

El caso real: la oferta la arma el proceso web en Render cuando el PM pulsa el
botón, pero el buzón de ISC se abre por el Outlook de una computadora. Antes
eso terminaba en excepción con el PDF ya generado: la oferta existía para todos
menos para el cliente.

Nada aquí toca la base ni Outlook: la conexión y el despacho se inyectan.
"""

import pytest

import app.email.bandeja_salida as bandeja


# --------------------------------------------------------------------------- #
# Una base de mentira, lo justo para esta tabla
# --------------------------------------------------------------------------- #

class _Cursor:
    def __init__(self, base):
        self.base = base

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        p = params or ()
        if s.startswith("INSERT INTO correos_salida ("):
            self.base["id"] += 1
            self.base["correos"].append({
                "id": self.base["id"], "rfq_id": p[0], "clase": p[1],
                "destinatario": p[2], "asunto": p[3], "cuerpo_html": p[4],
                "cuerpo_texto": p[5], "creado_por": p[6],
                "estado": "pendiente", "intentos": 0, "ultimo_error": None,
            })
            self._uno = (self.base["id"],)
        elif s.startswith("INSERT INTO correos_salida_adjuntos"):
            self.base["adjuntos"].append(
                {"salida_id": p[0], "nombre": p[1], "tipo": p[2],
                 "bytes": p[3], "contenido": bytes(p[4])})
            self._uno = None
        elif "SELECT id, rfq_id, clase" in s:
            vivos = [c for c in self.base["correos"]
                     if c["estado"] == "pendiente" and c["intentos"] < p[0]]
            self._filas = [(c["id"], c["rfq_id"], c["clase"], c["destinatario"],
                            c["asunto"], c["cuerpo_html"], c["cuerpo_texto"],
                            c["intentos"]) for c in vivos[:p[1]]]
        elif "SELECT nombre, tipo, contenido" in s:
            self._filas = [(a["nombre"], a["tipo"], a["contenido"])
                           for a in self.base["adjuntos"] if a["salida_id"] == p[0]]
        elif "SELECT COUNT(*) FROM correos_salida" in s:
            n = len([c for c in self.base["correos"]
                     if c["estado"] == "pendiente" and c["intentos"] < p[0]])
            self._uno = (n,)
        elif "SET estado = 'enviado'" in s:
            for c in self.base["correos"]:
                if c["id"] == p[0]:
                    c["estado"] = "enviado"
                    c["intentos"] += 1
        elif "SET intentos = intentos + 1" in s:
            for c in self.base["correos"]:
                if c["id"] == p[2]:
                    c["intentos"] += 1
                    c["ultimo_error"] = p[0]
                    c["estado"] = "fallo" if c["intentos"] >= p[1] else "pendiente"
        elif s.startswith("UPDATE rfqs"):
            self.base["apuntados"].append(p[0])
        else:
            raise AssertionError("consulta inesperada: " + s[:90])

    def fetchone(self):
        return self._uno

    def fetchall(self):
        return self._filas

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Conexion:
    def __init__(self, base):
        self.base = base

    def cursor(self):
        return _Cursor(self.base)


@pytest.fixture
def base(monkeypatch):
    datos = {"id": 0, "correos": [], "adjuntos": [], "apuntados": []}
    conn = _Conexion(datos)

    from contextlib import contextmanager

    @contextmanager
    def falsa(conexion=None):
        yield conn

    monkeypatch.setattr(bandeja, "_conexion", falsa)
    monkeypatch.setattr(bandeja, "psycopg_binario", lambda d: d)
    return datos


@pytest.fixture
def pdf(tmp_path):
    ruta = tmp_path / "CGR Mexico - INT-1.pdf"
    ruta.write_bytes(b"%PDF-1.7 la oferta")
    return ruta


def _correo(pdf):
    return {"destinatario": "ana.ramirez@cgr-international.com",
            "asunto": "Quote - spring 1060-022",
            "cuerpo_html": "<p>hola</p>", "cuerpo_texto": "hola",
            "adjuntos": [str(pdf)],
            # Las de la firma: NO deben viajar, son del repositorio.
            "imagenes": [{"ruta": "/app/frontend/img/firma.png", "cid": "firma"}]}


# --------------------------------------------------------------------------- #
# Encolar
# --------------------------------------------------------------------------- #

def test_el_pdf_viaja_en_bytes_no_como_ruta(base, pdf):
    """La ruta de Render no existe en la computadora que va a mandar."""
    bandeja.encolar(_correo(pdf), rfq_id="INT-1", por="pm@cgr.com")

    assert len(base["adjuntos"]) == 1
    guardado = base["adjuntos"][0]
    assert guardado["nombre"] == "CGR Mexico - INT-1.pdf"
    assert guardado["contenido"] == b"%PDF-1.7 la oferta"
    assert guardado["tipo"] == "application/pdf"


def test_las_imagenes_de_la_firma_no_se_guardan(base, pdf):
    """Están en los dos lados; las rutas de Render romperían la firma."""
    bandeja.encolar(_correo(pdf), rfq_id="INT-1")

    nombres = [a["nombre"] for a in base["adjuntos"]]
    assert nombres == ["CGR Mexico - INT-1.pdf"]


def test_se_guarda_a_quien_va_y_quien_lo_mandó(base, pdf):
    bandeja.encolar(_correo(pdf), rfq_id="INT-1", por="pm@cgr.com")

    fila = base["correos"][0]
    assert fila["destinatario"] == "ana.ramirez@cgr-international.com"
    assert fila["rfq_id"] == "INT-1"
    assert fila["creado_por"] == "pm@cgr.com"
    assert fila["estado"] == "pendiente"


def test_un_adjunto_ilegible_no_cancela_el_correo(base, tmp_path):
    """Peor que salga sin PDF es que no salga."""
    correo = {"destinatario": "a@b.com", "asunto": "x", "cuerpo_texto": "y",
              "adjuntos": [str(tmp_path / "no-existe.pdf")]}
    bandeja.encolar(correo, rfq_id="INT-1")

    assert len(base["correos"]) == 1
    assert base["adjuntos"] == []


# --------------------------------------------------------------------------- #
# Drenar
# --------------------------------------------------------------------------- #

def test_se_manda_y_se_apunta_en_el_rfq(base, pdf):
    bandeja.encolar(_correo(pdf), rfq_id="INT-1")
    mandados = []
    resumen = bandeja.drenar(enviar=lambda c: mandados.append(c) or True)

    assert resumen["enviados"] == 1
    assert base["correos"][0]["estado"] == "enviado"
    # Y el RFQ queda marcado, o la pantalla seguiría diciendo "pendiente".
    assert base["apuntados"] == ["INT-1"]
    # El que se manda lleva el PDF recuperado de la base.
    assert mandados[0]["adjuntos"][0]["contenido"] == b"%PDF-1.7 la oferta"


def test_un_fallo_deja_el_correo_esperando_no_perdido(base, pdf):
    bandeja.encolar(_correo(pdf), rfq_id="INT-1")

    def revienta(_):
        raise RuntimeError("Outlook se estaba cerrando")

    resumen = bandeja.drenar(enviar=revienta)

    assert resumen["fallidos"] == 1
    fila = base["correos"][0]
    assert fila["estado"] == "pendiente"        # se reintenta
    assert fila["intentos"] == 1
    assert "Outlook" in fila["ultimo_error"]
    assert base["apuntados"] == []              # no se apunta lo que no salió


def test_tras_agotar_los_intentos_deja_de_tapar_la_cola(base, pdf):
    bandeja.encolar(_correo(pdf), rfq_id="INT-1")

    def revienta(_):
        raise RuntimeError("nada")

    for _ in range(bandeja.MAX_INTENTOS):
        bandeja.drenar(enviar=revienta)

    assert base["correos"][0]["estado"] == "fallo"
    # Y ya no vuelve a salir en la cola.
    assert bandeja.pendientes() == []


def test_lo_viejo_sale_primero(base, pdf):
    bandeja.encolar(dict(_correo(pdf), asunto="primera"), rfq_id="INT-1")
    bandeja.encolar(dict(_correo(pdf), asunto="segunda"), rfq_id="INT-2")

    orden = [c["asunto"] for c in bandeja.pendientes()]
    assert orden == ["primera", "segunda"]


def test_sin_cola_no_se_hace_nada(base):
    assert bandeja.drenar(enviar=lambda c: True) == {
        "enviados": 0, "fallidos": 0, "pendientes": 0, "omitidos": 0,
        "denegados": 0}


# --------------------------------------------------------------------------- #
# El guardia: no quemar los intentos por una variable sin poner
# --------------------------------------------------------------------------- #

def test_si_esta_computadora_tampoco_puede_mandar_no_toca_la_cola(base, pdf, monkeypatch):
    """Sin esto, los cinco intentos se gastan en segundos y el correo queda
    en 'fallo' para siempre por una configuración que se arregla en un minuto."""
    bandeja.encolar(_correo(pdf), rfq_id="INT-1")

    import app.email.outbound as outbound
    monkeypatch.setattr(outbound, "diagnostico_envio",
                        lambda: {"puede": False, "modo": "imap",
                                 "faltan": ["SMTP_USER (o IMAP_USER)"],
                                 "canal": "smtp", "nota": ""})

    resumen = bandeja.drenar()          # sin inyectar: pasa por el guardia

    assert resumen["omitidos"] == 1
    assert resumen["enviados"] == 0
    fila = base["correos"][0]
    assert fila["estado"] == "pendiente"
    assert fila["intentos"] == 0        # ni un intento gastado
