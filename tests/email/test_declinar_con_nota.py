"""La nota del PM en el cuerpo del correo de declinación (2026-09-30)."""
from app.email.templates import construir_correo

BASE = {"destinatario": "buyer@cliente.com", "asunto_original": "RFQ SG0000142",
        "nombre_comprador": "Daniela"}


def test_la_nota_va_en_el_cuerpo_despues_del_machote():
    r = construir_correo("declinar_rfq", dict(
        BASE, nota="Wire Ø 15.875 mm exceeds our coilers.\n\nMax we coil is 9.5 mm."))
    texto = r["cuerpo_texto"]
    assert "Additional notes:" in texto
    assert "Wire Ø 15.875 mm exceeds our coilers." in texto
    assert "Max we coil is 9.5 mm." in texto
    # Después de "no podemos cotizar" y antes de la despedida del machote.
    assert texto.index("unable to quote") < texto.index("Additional notes:") \
        < texto.index("Thank you for considering us")
    assert "<p>Wire Ø 15.875 mm exceeds our coilers.</p>" in r["cuerpo_html"]


def test_sin_nota_el_correo_es_el_machote_de_siempre():
    for nota in (None, "", "   \n  "):
        r = construir_correo("declinar_rfq", dict(BASE, nota=nota))
        assert "Additional notes" not in r["cuerpo_texto"]
    assert "Additional notes" not in construir_correo("declinar_rfq", BASE)["cuerpo_texto"]


def test_la_nota_se_escapa_en_html():
    r = construir_correo("declinar_rfq", dict(BASE, nota="<b>ojo</b> & más"))
    assert "&lt;b&gt;ojo&lt;/b&gt; &amp; más" in r["cuerpo_html"]
    assert "<b>ojo</b>" not in r["cuerpo_html"]
