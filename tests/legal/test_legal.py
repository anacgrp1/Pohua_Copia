# -*- coding: utf-8 -*-
"""Lo legal: los documentos públicos, su versión y la constancia de aceptación.

Nada de esto hace el texto legalmente correcto —eso lo revisa un abogado—,
pero sí evita los fallos que lo dejarían sin efecto sin que nadie lo note: una
versión que no coincide (nadie vuelve a aceptar), un idioma al que le falta
una sección, una fuente pedida a un tercero sin avisar, o una aceptación de
la que no queda constancia.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app import legal

RAIZ = Path(__file__).resolve().parents[2]
LEGAL = RAIZ / "frontend" / "legal"


class TestLaVersion:

    def test_la_pagina_y_el_servidor_dicen_la_misma(self):
        texto = (LEGAL / "responsable.js").read_text(encoding="utf-8")
        version = re.search(r"VERSION:\s*'([^']+)'", texto).group(1)
        assert version == legal.VERSION_LEGAL


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
class TestLosTresIdiomas:

    def test_tienen_las_mismas_secciones_y_marcadores(self):
        js = """
        const vm = require('vm'); const fs = require('fs');
        const ctx = { window: {} }; vm.createContext(ctx);
        for (const l of ['es', 'en', 'fr'])
            vm.runInContext(
                fs.readFileSync(process.argv[1] + '/contenido.' + l + '.js', 'utf8'), ctx);
        const T = ctx.window.POHUA_LEGAL_TEXTOS;
        const forma = (o) => JSON.stringify(o, (k, v) =>
            typeof v === 'string' ? (v.match(/\\{\\{\\w+\\}\\}/g) || []).join('') : v);
        process.stdout.write(JSON.stringify(['es', 'en', 'fr'].map(l => forma(T[l]))));
        """
        salida = subprocess.run(["node", "-e", js, str(LEGAL)], capture_output=True,
                                text=True, check=True, timeout=30).stdout
        es, en, fr = json.loads(salida)
        assert es == en == fr


class TestSinTerceros:

    def test_la_aplicacion_no_pide_nada_a_google(self):
        # Mandaba la IP de cada visitante a Google sin avisar.
        for ruta in (RAIZ / "frontend" / "index.html", LEGAL / "index.html",
                     RAIZ / "frontend" / "css" / "style.css", LEGAL / "legal.css"):
            texto = ruta.read_text(encoding="utf-8")
            assert "googleapis" not in texto and "gstatic" not in texto, ruta

    def test_la_fuente_esta_en_casa(self):
        assert (RAIZ / "frontend" / "assets" / "fonts" / "inter-latin-wght-normal.woff2").is_file()


class TestSeSirvenSinSesion:

    def test_legal_barra_es_su_pagina_y_no_la_spa(self):
        from api import server
        assert server._ruta_segura("legal/") == (LEGAL / "index.html").resolve()
        assert server._ruta_segura("legal") == (LEGAL / "index.html").resolve()

    def test_no_se_sale_de_frontend(self):
        from api import server
        assert server._ruta_segura("../.env") is None


# --------------------------------------------------------------------------- #
# La constancia
# --------------------------------------------------------------------------- #

class Cursor:
    def __init__(self, filas):
        self.filas = filas
        self.ejecutado = []

    def execute(self, sql, params=None):
        self.ejecutado.append((sql, params))

    def fetchone(self):
        return self.filas.pop(0) if self.filas else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Conexion:
    autocommit = True

    def __init__(self, filas=None):
        self.cur = Cursor(list(filas or []))

    def cursor(self):
        return self.cur


class TestLaAceptacion:

    def test_sin_aceptar_se_pide_la_version_vigente(self):
        assert legal.pendiente(7, conexion=Conexion([])) == legal.VERSION_LEGAL

    def test_aceptada_no_se_vuelve_a_pedir(self):
        assert legal.pendiente(7, conexion=Conexion([(1,)])) is None

    def test_si_la_base_falla_no_deja_a_nadie_fuera(self):
        class Rota:
            def cursor(self):
                raise RuntimeError("sin base")
        assert legal.pendiente(7, conexion=Rota()) is None

    def test_queda_constancia_de_quien_y_que_version(self):
        con = Conexion()
        legal.aceptar(7, legal.VERSION_LEGAL, conexion=con)
        sql, params = con.cur.ejecutado[-1]
        assert "INSERT INTO aceptaciones_legales" in sql
        assert params == (7, legal.VERSION_LEGAL)

    def test_no_se_acepta_una_version_que_no_es_la_publicada(self):
        with pytest.raises(ValueError):
            legal.aceptar(7, "2020-01-01", conexion=Conexion())

    def test_la_migracion_crea_la_tabla(self):
        ruta = RAIZ / "sql" / "migrations" / "027_aceptaciones_legales.sql"
        sql = ruta.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS aceptaciones_legales" in sql
        assert "UNIQUE (usuario_id, version)" in sql


class TestElAvisoDeFaltantes:

    def test_preflight_dice_que_faltan_los_datos_del_responsable(self):
        from app.core import preflight
        inf = preflight._Informe()
        preflight._legal(inf)
        titulos = [p["titulo"] for p in inf.puntos]
        assert any("responsable" in t for t in titulos)
        assert not any(p["estado"] == "falta" for p in inf.puntos)
