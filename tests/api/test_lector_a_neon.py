"""La lectura del plano se va entera a Neon y sale del disco (api/lector.py).

Desde 2026-10 el lector no deja planos ni recortes de clientes en el disco de
quien lo corre: nada más contestar `/api/parse`, los PNG van a
`lector_recortes`, el JSON de ingeniería a `lector_specs`, y los ficheros se
borran. Sin base no se borra nada.
"""
import json
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import api.lector as lector


class _Cursor:
    def __init__(self, registro, fallar):
        self.registro = registro
        self.fallar = fallar
        self._fila = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if self.fallar:
            raise RuntimeError("sin base")
        self.registro.append((" ".join(sql.split()), params))
        if sql.strip().startswith("SELECT spec"):
            self._fila = self.registro_spec

    def fetchone(self):
        return self._fila


class _Base:
    """Conexión falsa: apunta lo que se ejecuta."""

    def __init__(self, fallar=False, spec_guardado=None):
        self.ejecutado = []
        self.fallar = fallar
        self.spec_guardado = spec_guardado

    @contextmanager
    def conexion(self):
        base = self

        class _Conn:
            def cursor(self_inner):
                c = _Cursor(base.ejecutado, base.fallar)
                c.registro_spec = (base.spec_guardado,) if base.spec_guardado is not None else None
                return c
        yield _Conn()


class TestLlevarLecturaANeon(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lector_"))
        self.carpetas = {k: self.tmp / k.lower() for k in ("CROPS", "UPLOADS", "SPECS")}
        for d in self.carpetas.values():
            d.mkdir()
        (self.carpetas["CROPS"] / "ab12cd34_p0.png").write_bytes(b"\x89PNG pagina")
        (self.carpetas["CROPS"] / "ab12cd34_c1.png").write_bytes(b"\x89PNG cota")
        (self.carpetas["CROPS"] / "otro_job.png").write_bytes(b"\x89PNG ajeno")
        (self.carpetas["UPLOADS"] / "ab12cd34.pdf").write_bytes(b"%PDF plano del cliente")
        (self.carpetas["UPLOADS"] / "zz99zz99.pdf").write_bytes(b"%PDF otro")
        (self.carpetas["SPECS"] / "ab12cd34.json").write_text('{"od": 1}', encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _llevar(self, base, spec={"od": 1}):
        with mock.patch("app.persistence.duplicates.conexion_bd", base.conexion):
            return lector.llevar_lectura_a_neon(
                "ab12cd34", spec, ["ab12cd34_p0.png", "ab12cd34_c1.png"], self.carpetas)

    def _quedan(self):
        return sorted(p.name for d in self.carpetas.values() for p in d.iterdir())

    def test_guarda_imagenes_y_spec_y_borra_lo_suyo_del_disco(self):
        base = _Base()
        r = self._llevar(base)
        self.assertEqual(r["recortes"], 2)
        self.assertTrue(r["spec"])
        self.assertEqual(r["borrados"], 4)          # 2 PNG + spec + plano subido
        # Lo de otras lecturas no se toca.
        self.assertEqual(self._quedan(), ["otro_job.png", "zz99zz99.pdf"])
        sqls = [s for s, _ in base.ejecutado]
        self.assertEqual(sum("INSERT INTO lector_recortes" in s for s in sqls), 2)
        self.assertEqual(sum("INSERT INTO lector_specs" in s for s in sqls), 1)
        spec_param = [p for s, p in base.ejecutado if "lector_specs" in s][0]
        self.assertEqual(json.loads(spec_param[1]), {"od": 1})

    def test_sin_base_no_borra_nada(self):
        r = self._llevar(_Base(fallar=True))
        self.assertIsNotNone(r["error"])
        self.assertEqual(r["borrados"], 0)
        self.assertEqual(len(self._quedan()), 6)

    def test_sin_spec_en_la_respuesta_lo_toma_del_disco(self):
        base = _Base()
        r = self._llevar(base, spec=None)
        self.assertTrue(r["spec"])
        self.assertFalse((self.carpetas["SPECS"] / "ab12cd34.json").exists())

    def test_job_raro_no_toca_el_disco(self):
        with mock.patch("app.persistence.duplicates.conexion_bd", _Base().conexion):
            r = lector.llevar_lectura_a_neon("../../etc", {}, [], self.carpetas)
        self.assertEqual(r["error"], "sin lector")
        self.assertEqual(len(self._quedan()), 6)


class TestRecortesDeLaRespuesta(unittest.TestCase):

    def test_recoge_paginas_y_cotas_sin_repetir_ni_salirse(self):
        datos = {
            "page": "/api/crop/j_p0.png",
            "pages": ["/api/crop/j_p0.png", "/api/crop/j_p1.png"],
            "fields": [{"crop": "/api/crop/j_c1.png"}, {"crop": None}, {}],
            "feasibility": [{"crop": "/api/crop/..%2Fsecreto"}, {"crop": "/api/crop/j_c2.png?v=1"}],
        }
        self.assertEqual(lector.recortes_de(datos),
                         ["j_p0.png", "j_p1.png", "j_c1.png", "j_c2.png"])


class TestServirSpecDesdeNeon(unittest.TestCase):

    def test_si_el_disco_ya_no_lo_tiene_sale_de_la_base(self):
        base = _Base(spec_guardado={"od": 2.5})
        with mock.patch("app.persistence.duplicates.conexion_bd", base.conexion):
            cuerpo, captura = lector._spec({"PATH_INFO": "/api/spec/ab12cd34"},
                                           {"estado": "404 NOT FOUND", "cabeceras": []}, b"")
        self.assertEqual(captura["estado"], "200 OK")
        self.assertEqual(json.loads(cuerpo), {"od": 2.5})

    def test_si_el_disco_lo_tiene_no_pregunta_a_la_base(self):
        base = _Base()
        with mock.patch("app.persistence.duplicates.conexion_bd", base.conexion):
            cuerpo, captura = lector._spec({"PATH_INFO": "/api/spec/ab12cd34"},
                                           {"estado": "200 OK", "cabeceras": []}, b"{}")
        self.assertEqual(base.ejecutado, [])
        self.assertEqual(cuerpo, b"{}")


class TestTrasLectura(unittest.TestCase):

    def _respuesta(self, **extra):
        datos = {"ok": True, "job": "ab12cd34", "spec": {"od": 1},
                 "page": "/api/crop/ab12cd34_p0.png", "pages": []}
        datos.update(extra)
        return json.dumps(datos).encode()

    def test_lanza_el_hilo_solo_tras_un_parse_bueno(self):
        with mock.patch.object(lector.threading, "Thread") as hilo:
            lector._tras_lectura({"PATH_INFO": "/api/parse", "REQUEST_METHOD": "POST"},
                                 {"estado": "200 OK"}, self._respuesta())
            hilo.assert_called_once()
            args = hilo.call_args.kwargs["args"]
            self.assertEqual(args[0], "ab12cd34")
            self.assertEqual(args[2], ["ab12cd34_p0.png"])

    def test_no_hace_nada_con_otras_rutas_ni_errores(self):
        with mock.patch.object(lector.threading, "Thread") as hilo:
            lector._tras_lectura({"PATH_INFO": "/api/crop/x.png", "REQUEST_METHOD": "GET"},
                                 {"estado": "200 OK"}, b"")
            lector._tras_lectura({"PATH_INFO": "/api/parse", "REQUEST_METHOD": "POST"},
                                 {"estado": "500 INTERNAL SERVER ERROR"}, b"{}")
            lector._tras_lectura({"PATH_INFO": "/api/parse", "REQUEST_METHOD": "POST"},
                                 {"estado": "200 OK"}, self._respuesta(ok=False))
            lector._tras_lectura({"PATH_INFO": "/api/parse", "REQUEST_METHOD": "POST"},
                                 {"estado": "200 OK"}, self._respuesta(job="../x"))
            hilo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
