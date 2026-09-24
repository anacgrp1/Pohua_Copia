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
            // De cgr-international.com/company/contact-us/ (Planta 1) y del
            // directorio de Dun & Bradstreet, consultados 2026-09-24. Confirmar
            // con contabilidad que este es el domicilio FISCAL (la Planta 2 está
            // en Libre a Celaya Km 7.9 Int 5, mismo parque). El RFC que publican
            // directorios de terceros es CME030424I94: verificarlo contra la
            // constancia antes de ponerlo aquí.
            sede: 'Corregidora, Querétaro, México',
            razonSocial: 'CGR de México, S.A. de C.V.',
            domicilio: 'Calle Sin Nombre # 7, Fracc. Industrial Balvanera, C.P. 76920, Corregidora, Querétaro, México',
            rfcOIdentificador: null,    // RFC
        },
        {
            // De isckc.com (portada y /contact-us/, consultado 2026-09-24).
            // La página «About» la llama "Industrial Spring Corporation of
            // Kansas City": confirmar cuál es la razón social registrada.
            sede: 'North Kansas City, Missouri, EE. UU.',
            razonSocial: 'Industrial Spring Corporation (a CGR company)',
            domicilio: '1801 Bedford Ave., North Kansas City, MO 64116, United States · Tel. +1 816 741 6073',
            rfcOIdentificador: null,    // EIN, si se quiere mostrar
        },
        {
            // De cgr-international.com/legal-notice/ (consultado 2026-09-24).
            sede: 'Sevran, Francia',
            razonSocial: 'CGR International SAS',
            domicilio: '2 rue Henri Poincaré, ZI Les Beaudottes, 93270 Sevran, France',
            rfcOIdentificador: 'RCS Bobigny 511 322 059',
        },
    ],

    // El buzón al que se mandan las solicitudes de derechos (ARCO / RGPD).
    // Elegido por Ana (2026-09-24). Quien lea este buzón tiene que contestar
    // las solicitudes en plazo: México 20 días, UE un mes.
    correoPrivacidad: 'info@isckc.com',
    // Persona o departamento de datos personales (México, art. 29 LFPDPPP).
    departamentoDatos: null,
    // Delegado de protección de datos (RGPD). null si no se ha designado.
    // El que declara el aviso legal de cgr-international.com para CGR
    // International SAS (consultado 2026-09-24).
    delegadoProteccionDatos: 'Philippe Tissot (CGR International SAS)',
    // Ley y tribunales para los términos de uso de cada sede.
    jurisdiccion: null,                 // p. ej. "tribunales de Querétaro, Qro., México"
};
