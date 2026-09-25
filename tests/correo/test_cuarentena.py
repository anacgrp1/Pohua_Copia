"""Cuarentena: el correo que puede ser malware no se abre ni se contesta.

Las comprobaciones propias (extensión, extensión doble, cabecera del archivo,
contenido activo del PDF) no dependen de Windows ni de Defender: se prueban
aquí en cualquier máquina. Defender sólo se comprueba en que su ausencia no
inventa un veredicto.
"""
import os
import unittest
from unittest import mock

import app.email.cuarentena as cuarentena

PDF_LIMPIO = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
EXE = b"MZ\x90\x00" + b"\x00" * 60


def adjunto(nombre, contenido=b""):
    return {"nombre": nombre, "contenido": contenido, "content_type": "", "en_linea": False}


class TestAdjuntos(unittest.TestCase):

    def test_un_plano_y_una_imagen_pasan(self):
        self.assertEqual(cuarentena.motivos_del_adjunto(adjunto("plano.pdf", PDF_LIMPIO)), [])
        self.assertEqual(cuarentena.motivos_del_adjunto(adjunto("foto.PNG", PNG)), [])
        self.assertEqual(
            cuarentena.motivos_del_adjunto(adjunto("pieza.step", b"ISO-10303-21;")), [])

    def test_ejecutables_y_scripts_no(self):
        for nombre in ("factura.exe", "abrir.bat", "macro.docm", "todo.zip", "enlace.lnk",
                       "pagina.html", "script.js"):
            motivos = cuarentena.motivos_del_adjunto(adjunto(nombre, b"x"))
            self.assertTrue(motivos, nombre)
            self.assertIn("peligroso", motivos[0])

    def test_extension_doble(self):
        motivos = cuarentena.motivos_del_adjunto(adjunto("plano.pdf.exe", EXE))
        self.assertTrue(any("extensión doble" in m for m in motivos), motivos)

    def test_un_exe_con_nombre_de_pdf(self):
        motivos = cuarentena.motivos_del_adjunto(adjunto("plano.pdf", EXE))
        self.assertTrue(any("ejecutable" in m for m in motivos), motivos)

    def test_png_y_pdf_se_aceptan_aunque_la_cabecera_sea_rara(self):
        # Outlook guarda las imágenes pegadas en el cuerpo como objetos OLE:
        # «image.png» no empieza por la cabecera PNG y sigue siendo inocente.
        # Regla de ventas: el sistema acepta .png y .pdf. Sólo un ejecutable
        # disfrazado se para.
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16
        self.assertEqual(cuarentena.motivos_del_adjunto(adjunto("image.png", ole)), [])
        self.assertEqual(
            cuarentena.motivos_del_adjunto(adjunto("plano.pdf", b"<html>hola</html>")), [])

    def test_pdf_con_javascript(self):
        malo = b"%PDF-1.7\n1 0 obj << /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>"
        motivos = cuarentena.motivos_del_adjunto(adjunto("plano.pdf", malo))
        self.assertTrue(any("contenido activo" in m for m in motivos), motivos)

    def test_tipo_desconocido_no_se_abre(self):
        motivos = cuarentena.motivos_del_adjunto(adjunto("datos.xyz", b"???"))
        self.assertTrue(any("no admitido" in m for m in motivos), motivos)

    def test_sin_extension_pasa_si_parece_imagen(self):
        # Un logo incrustado sin nombre: se ve que es un PNG y se deja.
        self.assertEqual(cuarentena.motivos_del_adjunto(adjunto("image001", PNG)), [])
        self.assertTrue(cuarentena.motivos_del_adjunto(adjunto("image001", EXE)))


class TestRevisar(unittest.TestCase):

    def test_un_correo_limpio_no_da_motivos(self):
        correo = {"adjuntos": [adjunto("plano.pdf", PDF_LIMPIO), adjunto("logo.png", PNG)]}
        with mock.patch.object(cuarentena, "analizar_con_defender", return_value=""):
            self.assertEqual(cuarentena.revisar(correo), [])

    def test_sin_adjuntos_no_hay_nada_que_mirar(self):
        self.assertEqual(cuarentena.revisar({"adjuntos": []}), [])
        self.assertEqual(cuarentena.revisar({}), [])

    def test_junta_los_motivos_de_todos_los_adjuntos(self):
        correo = {"adjuntos": [adjunto("plano.pdf", PDF_LIMPIO), adjunto("virus.exe", EXE)]}
        motivos = cuarentena.revisar(correo, con_antivirus=False)
        self.assertEqual(len(motivos), 2, motivos)     # peligroso + ejecutable

    def test_defender_solo_se_consulta_si_lo_propio_no_vio_nada(self):
        correo = {"adjuntos": [adjunto("virus.exe", EXE)]}
        with mock.patch.object(cuarentena, "analizar_con_defender") as defender:
            cuarentena.revisar(correo)
        defender.assert_not_called()

    def test_lo_que_diga_defender_cuenta(self):
        correo = {"adjuntos": [adjunto("plano.pdf", PDF_LIMPIO)]}
        with mock.patch.object(cuarentena, "analizar_con_defender",
                               return_value="Windows Defender detectó una amenaza en «plano.pdf»"):
            motivos = cuarentena.revisar(correo)
        self.assertEqual(len(motivos), 1)
        self.assertIn("Defender", motivos[0])


class TestDefender(unittest.TestCase):

    def test_sin_defender_no_se_inventa_veredicto(self):
        with mock.patch.object(cuarentena, "_mpcmdrun", return_value=""):
            self.assertEqual(cuarentena.analizar_con_defender(adjunto("plano.pdf", PDF_LIMPIO)), "")

    @unittest.skipIf(os.name == "nt", "en Windows puede estar de verdad")
    def test_fuera_de_windows_no_se_busca(self):
        self.assertEqual(cuarentena._mpcmdrun(), "")

    def test_codigo_2_es_amenaza_y_el_temporal_se_borra(self):
        borrados = []
        salida = mock.Mock(returncode=2)
        with mock.patch.object(cuarentena, "_mpcmdrun", return_value=r"C:\MpCmdRun.exe"), \
             mock.patch.object(cuarentena.subprocess, "run", return_value=salida) as run, \
             mock.patch.object(cuarentena.os, "remove", side_effect=borrados.append):
            motivo = cuarentena.analizar_con_defender(adjunto("plano.pdf", PDF_LIMPIO))
        self.assertIn("Defender", motivo)
        self.assertEqual(len(borrados), 1)
        self.assertIn("-File", run.call_args[0][0])

    def test_codigo_0_es_limpio(self):
        with mock.patch.object(cuarentena, "_mpcmdrun", return_value=r"C:\MpCmdRun.exe"), \
             mock.patch.object(cuarentena.subprocess, "run", return_value=mock.Mock(returncode=0)):
            self.assertEqual(cuarentena.analizar_con_defender(adjunto("plano.pdf", PDF_LIMPIO)), "")


if __name__ == "__main__":
    unittest.main()
