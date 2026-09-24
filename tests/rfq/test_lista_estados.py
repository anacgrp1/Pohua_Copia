# -*- coding: utf-8 -*-
"""La lista de RFQ acepta varios estados de una vez.

Por qué existe
--------------
El apartado de RFQ ya dictaminadas los quiere JUNTOS —aprobados y
declinados—, en orden de fecha. Quien busca un caso viejo se acuerda del
cliente y de cuándo fue, no de en cuál de los dos acabó.

Con un solo estado por consulta habría que pedir dos listas, mezclarlas y
reordenarlas en el navegador, y paginar dos cosas a la vez. El filtro acepta
una lista separada por comas y lo resuelve en SQL.

Se prueba el armado de la consulta, no la base: lo que puede romperse aquí es
el SQL y sus parámetros.
"""

import pytest


def condicion(estado):
    """El mismo troceado que hace `list_rfqs`, aislado para poder probarlo."""
    conditions, params = [], []
    if estado:
        pedidos = [e.strip() for e in str(estado).split(",") if e.strip()]
        if len(pedidos) == 1:
            conditions.append("r.estado = %s")
            params.append(pedidos[0])
        elif pedidos:
            conditions.append("r.estado = ANY(%s)")
            params.append(pedidos)
    return conditions, params


class TestElFiltro:

    def test_un_estado_sigue_siendo_una_igualdad(self):
        # Lo que ya funcionaba no cambia de plan de consulta.
        cond, params = condicion("Approved")
        assert cond == ["r.estado = %s"]
        assert params == ["Approved"]

    def test_varios_estados_van_en_un_ANY(self):
        cond, params = condicion("Approved,Declined")
        assert cond == ["r.estado = ANY(%s)"]
        assert params == [["Approved", "Declined"]]

    def test_los_espacios_no_cuentan(self):
        _, params = condicion(" Approved , Declined ")
        assert params == [["Approved", "Declined"]]

    def test_las_comas_de_mas_no_crean_estados_vacios(self):
        # "Approved,,Declined," con un estado vacío dentro devolvería CERO
        # filas sin que nada avisara.
        _, params = condicion("Approved,,Declined,")
        assert params == [["Approved", "Declined"]]

    @pytest.mark.parametrize("vacio", ["", "   ", ",", ",,", None])
    def test_sin_estado_no_se_filtra_nada(self, vacio):
        cond, params = condicion(vacio)
        assert cond == [] and params == []

    def test_el_estado_nunca_se_pega_al_sql(self):
        # Va como parámetro, no interpolado: es texto que llega por la URL.
        cond, params = condicion("Approved'; DROP TABLE rfqs;--")
        assert "DROP" not in cond[0]
        assert params == ["Approved'; DROP TABLE rfqs;--"]


class TestLaRutaLoDeclara:

    def test_el_endpoint_dice_que_admite_varios(self):
        # Si alguien quita el soporte, que se caiga aquí y no en la pantalla.
        import inspect
        import api.routes.rfqs as rutas
        fuente = inspect.getsource(rutas.list_rfqs)
        assert "ANY(%s)" in fuente
        assert "split(\",\")" in fuente


class TestElNombreDelCliente:
    """Un RFQ sin cliente de la cartera salía en las listas como "—".

    El flujo deja en ``datos_json.customer`` quién es (la razón social o, si
    no se reconoció, lo que dijo el correo): la lista lo devuelve para que la
    pantalla no tenga que adivinarlo.
    """

    def test_la_lista_devuelve_el_nombre(self):
        import inspect
        import api.routes.rfqs as rutas
        fuente = inspect.getsource(rutas.list_rfqs)
        assert "datos_json->>'customer'" in fuente
        assert '"cliente_nombre"' in fuente

    def test_el_esquema_lo_acepta(self):
        from api.models.schemas import RFQSummary
        r = RFQSummary(id=1, rfq_id="INT-1", version=1, cliente_nombre="CGR México")
        assert r.cliente_nombre == "CGR México"
        assert RFQSummary(id=1, rfq_id="INT-1", version=1).cliente_nombre is None
