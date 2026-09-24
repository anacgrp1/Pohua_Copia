/**
 * Quién es el responsable de los datos. LO LLENA EL ÁREA LEGAL, no el código.
 *
 * Los tres documentos (aviso de privacidad, cookies y términos) leen de aquí
 * la identidad de las empresas, el correo para ejercer derechos y la
 * jurisdicción. Nada de esto se puede inventar: un aviso de privacidad con una
 * razón social o un domicilio falsos no cumple, por muy bien redactado que
 * esté el resto.
 *
 * Mientras un dato esté en `null`, la página lo enseña marcado en rojo como
 * «por completar» y `python scripts/comprobar_flujo.py` avisa. No se publica
 * como definitivo con huecos.
 *
 * VERSION: cambiarla cuando cambie el CONTENIDO de los documentos (no una
 * errata). Pohua pide a cada usuario que vuelva a aceptar al entrar, y la
 * aceptación queda registrada con esta versión (tabla `aceptaciones_legales`).
 * Tiene que coincidir con `VERSION_LEGAL` de `app/legal.py`; una prueba lo
 * comprueba.
 */
window.POHUA_LEGAL = {
    VERSION: '2026-09-24',

    // Una entrada por empresa que trata los datos. Si en realidad es una sola
    // razón social, dejar una y borrar las demás.
    responsables: [
        {
            sede: 'Querétaro, México',
            razonSocial: null,          // p. ej. "CGR International, S.A. de C.V."
            domicilio: null,            // calle, número, colonia, C.P., municipio, estado
            rfcOIdentificador: null,    // RFC
        },
        {
            sede: 'Kansas City, Missouri, EE. UU.',
            razonSocial: null,
            domicilio: null,
            rfcOIdentificador: null,    // EIN, si se quiere mostrar
        },
        {
            sede: 'Sevran, Francia',
            razonSocial: null,
            domicilio: null,
            rfcOIdentificador: null,    // SIREN / SIRET
        },
    ],

    // El buzón al que se mandan las solicitudes de derechos (ARCO / RGPD).
    correoPrivacidad: null,             // p. ej. "privacidad@cgr-international.com"
    // Persona o departamento de datos personales (México, art. 29 LFPDPPP).
    departamentoDatos: null,
    // Delegado de protección de datos (RGPD). null si no se ha designado.
    delegadoProteccionDatos: null,
    // Ley y tribunales para los términos de uso de cada sede.
    jurisdiccion: null,                 // p. ej. "tribunales de Querétaro, Qro., México"
};
