/**
 * Textos legales de Pohua, en español (versión de referencia).
 *
 * Cada documento es una lista de secciones; cada sección, un título y bloques:
 * un texto es un párrafo y una lista es una lista con viñetas. Los textos
 * pueden llevar <b> y enlaces; los escribe el equipo, no los usuarios.
 *
 * Marcadores que rellena la página con `responsable.js`:
 *   {{responsables}}  la lista de empresas con su domicilio
 *   {{correo}}        el buzón de privacidad
 *   {{departamento}}  la persona o departamento de datos personales
 *   {{dpo}}           el delegado de protección de datos (RGPD)
 *   {{jurisdiccion}}  ley y tribunales de los términos de uso
 *   {{version}}       la versión de los documentos
 *
 * ESTE TEXTO LO TIENE QUE REVISAR UN ABOGADO de cada país donde opera la
 * empresa (México, Estados Unidos y Francia) antes de darlo por definitivo.
 */
window.POHUA_LEGAL_TEXTOS = window.POHUA_LEGAL_TEXTOS || {};
window.POHUA_LEGAL_TEXTOS.es = {
    ui: {
        titulo: 'Información legal',
        privacidad: 'Aviso de privacidad',
        cookies: 'Cookies y almacenamiento',
        terminos: 'Términos de uso',
        version: 'Versión',
        imprimir: 'Imprimir',
        volver: 'Volver a Pohua',
        pendiente: 'por completar',
        avisoPendiente: 'Este documento tiene datos del responsable sin completar. No es definitivo hasta que el área legal los llene y lo revise.',
        borrarPreferencias: 'Borrar las preferencias de este navegador',
        borradas: 'Listo: se borraron las preferencias de este navegador.',
        tablaNombre: 'Nombre',
        tablaTipo: 'Tipo',
        tablaPara: 'Para qué sirve',
        tablaDura: 'Duración',
    },

    privacidad: {
        titulo: 'Aviso de privacidad integral',
        intro: 'Este aviso explica qué datos personales trata Pohua (el cotizador de solicitudes de cotización, RFQ), para qué, con quién se comparten y cómo puede ejercer sus derechos. Se emite conforme a la Ley Federal de Protección de Datos Personales en Posesión de los Particulares de México (LFPDPPP), al Reglamento General de Protección de Datos de la Unión Europea (RGPD) y a la ley francesa Informatique et Libertés, y a las leyes de Estados Unidos que resulten aplicables.',
        secciones: [
            { t: '1. Responsable del tratamiento', b: [
                'Son responsables de sus datos personales las siguientes empresas del grupo, cada una respecto de los datos que trata en su sede:',
                '{{responsables}}',
                'Para cualquier asunto de privacidad: {{correo}}. Persona o departamento de datos personales: {{departamento}}. Delegado de protección de datos (UE): {{dpo}}.',
            ]},
            { t: '2. A quién se aplica', b: [[
                '<b>Usuarios de Pohua</b>: personal de la empresa y colaboradores a quienes se les dio una cuenta.',
                '<b>Contactos de clientes y proveedores</b>: las personas que nos envían una solicitud de cotización por correo o cuyos datos de contacto figuran en ella, y las que reciben nuestras ofertas.',
            ]]},
            { t: '3. Datos personales que tratamos', b: [
                '<b>De los usuarios:</b>',
                [
                    'Identificación y contacto: nombre, correo corporativo, puesto o rol en la aplicación.',
                    'Autenticación: la contraseña, guardada sólo como huella cifrada (PBKDF2); nunca se guarda ni se ve en claro.',
                    'Foto de perfil, sólo si el usuario decide subirla.',
                    'Actividad: fecha del último acceso y registro de las acciones hechas en la aplicación (por ejemplo, quién aprobó, declinó o modificó una cotización y cuándo).',
                    'Preferencias de pantalla (tema, idioma, sonido, reloj) y, si el usuario las activa, la suscripción a notificaciones del dispositivo.',
                ],
                '<b>De los contactos de clientes y proveedores:</b>',
                [
                    'Nombre, cargo, correo, teléfono, empresa y domicilio de la empresa.',
                    'El contenido de los correos de solicitud y sus archivos adjuntos (planos técnicos), las cotizaciones y ofertas emitidas y las condiciones comerciales pactadas.',
                ],
                '<b>Datos técnicos:</b> los servidores pueden registrar la fecha, la ruta solicitada y la dirección IP de cada acceso, con fines de seguridad y diagnóstico.',
                '<b>No tratamos datos personales sensibles</b> (salud, origen étnico, creencias, etc.). Le pedimos no incluirlos en correos ni planos; si llegaran, se eliminan.',
            ]},
            { t: '4. Para qué usamos sus datos', b: [
                'Finalidades necesarias para la relación con usted:',
                [
                    'Recibir, registrar y atender las solicitudes de cotización.',
                    'Evaluar la factibilidad técnica, calcular costos y preparar y enviar las ofertas.',
                    'Comunicarnos con usted sobre su solicitud, su oferta y el pedido que resulte.',
                    'Dar de alta y administrar las cuentas de usuario, sus permisos y su acceso.',
                    'Mantener la seguridad de la aplicación y un registro de quién hizo qué, para poder auditar las decisiones comerciales.',
                    'Cumplir obligaciones legales, fiscales y mercantiles.',
                ],
                '<b>No hay finalidades secundarias.</b> Pohua no usa sus datos para mercadotecnia, publicidad, venta de datos ni elaboración de perfiles.',
            ]},
            { t: '5. Fundamento legal', b: [[
                '<b>México (LFPDPPP):</b> los tratamientos anteriores son necesarios para cumplir la relación jurídica o comercial que usted inicia al pedir una cotización o que tiene con la empresa como usuario, por lo que no requieren consentimiento (art. 9). En lo demás, el consentimiento es tácito si, puesto a su disposición este aviso, no manifiesta su oposición (art. 7).',
                '<b>Unión Europea (RGPD):</b> ejecución de un contrato o de medidas precontractuales a petición del interesado (art. 6.1.b); interés legítimo en gestionar la relación comercial con empresas, la seguridad y la auditoría (art. 6.1.f); cumplimiento de obligaciones legales (art. 6.1.c). Para el personal, la relación laboral.',
            ]]},
            { t: '6. Uso de inteligencia artificial', b: [
                'Para leer los correos y los planos técnicos y extraer los datos de la pieza (material, medidas, cantidades), Pohua envía su contenido a un modelo de inteligencia artificial de un proveedor externo (Anthropic, PBC, Estados Unidos), que actúa como encargado y sólo trata los datos para prestarnos ese servicio, conforme al contrato con él.',
                '<b>Ninguna decisión se toma sólo de forma automatizada.</b> La factibilidad, el precio y el envío de cada oferta los revisa y decide una persona. Usted puede pedir que su solicitud se atienda sin este procesamiento escribiendo a {{correo}}.',
            ]},
            { t: '7. Con quién compartimos sus datos', b: [
                'Con <b>proveedores que actúan por nuestra cuenta</b> (encargados), sólo para prestarnos su servicio y bajo obligación de confidencialidad:',
                [
                    'Alojamiento de la aplicación (Render) y base de datos (Neon).',
                    'Correo electrónico (el proveedor del buzón corporativo, p. ej. Microsoft 365).',
                    'Almacenamiento de planos en la nube (Microsoft Azure), cuando está activado.',
                    'Lectura de correos y planos con inteligencia artificial (Anthropic).',
                    'Entrega de notificaciones al teléfono o al navegador (el servicio de avisos del propio navegador: Google, Apple, Mozilla o Microsoft), sólo si el usuario las activa.',
                ],
                'Entre las <b>empresas del mismo grupo</b> en México, Estados Unidos y Francia, que operan con los mismos procesos y políticas (art. 36 fr. III LFPDPPP).',
                'Con <b>autoridades</b>, cuando una ley o una orden judicial lo exija.',
                '<b>No vendemos ni cedemos sus datos</b> a terceros para sus propios fines.',
            ]},
            { t: '8. Transferencias internacionales', b: [
                'Los servidores de los proveedores anteriores están principalmente en Estados Unidos, y los datos circulan entre las sedes de México, Estados Unidos y Francia. Cuando salen de la Unión Europea, se protegen con las cláusulas contractuales tipo aprobadas por la Comisión Europea o con la adhesión del proveedor al Marco de Privacidad de Datos UE-EE. UU., según el caso. Puede pedir una copia de esas garantías en {{correo}}.',
            ]},
            { t: '9. Cuánto tiempo los conservamos', b: [[
                'Cuentas de usuario: mientras la cuenta esté activa; después se desactivan y se conserva el registro de actividad por el plazo que exija la ley o la defensa de derechos.',
                'Solicitudes, planos, cotizaciones y ofertas: mientras dure la relación comercial y, después, durante los plazos de conservación que imponen las leyes fiscales y mercantiles (en México, en general cinco años).',
                'Registros técnicos del servidor: el tiempo que los guarde el proveedor de alojamiento para seguridad y diagnóstico.',
                'Al terminar el plazo, los datos se bloquean y se eliminan de forma segura.',
            ]]},
            { t: '10. Sus derechos', b: [
                'Usted puede, en cualquier momento y de forma gratuita:',
                [
                    '<b>Acceder</b> a sus datos, <b>rectificarlos</b> si son inexactos, <b>cancelarlos</b> u <b>oponerse</b> a su tratamiento (derechos ARCO, México).',
                    'En la Unión Europea, además: pedir la <b>supresión</b>, la <b>limitación</b> del tratamiento y la <b>portabilidad</b> de sus datos, y dar instrucciones sobre su destino después de su fallecimiento (Francia).',
                    '<b>Revocar</b> el consentimiento que haya dado, sin efectos retroactivos, y <b>limitar</b> el uso o la divulgación de sus datos.',
                ],
                '<b>Cómo:</b> envíe un correo a {{correo}} con su nombre, un medio para responderle, un documento que acredite su identidad (o la de su representante), la descripción clara de lo que pide y, si pide una rectificación, el dato correcto.',
                '<b>Plazos:</b> en México le comunicaremos la respuesta en un máximo de 20 días y, si procede, la haremos efectiva en los 15 días siguientes (art. 31 LFPDPPP). En la Unión Europea, en un mes, ampliable dos meses más en casos complejos (art. 12 RGPD).',
                '<b>Si no está conforme</b>, puede acudir a la autoridad: en México, la Secretaría Anticorrupción y Buen Gobierno; en Francia, la CNIL (cnil.fr); o a la autoridad de protección de datos de su país de residencia en la UE. Si reside en un estado de EE. UU. con ley de privacidad aplicable, tiene los derechos que esa ley le otorgue.',
            ]},
            { t: '11. Seguridad', b: [
                'Aplicamos medidas administrativas, técnicas y físicas para proteger sus datos: conexión cifrada (HTTPS), contraseñas guardadas sólo como huella cifrada, sesiones que caducan, acceso por roles y permisos, y registro de las acciones. Si ocurriera una vulneración de seguridad que afecte de forma significativa sus derechos, se lo informaremos sin demora y avisaremos a la autoridad cuando la ley lo exija.',
            ]},
            { t: '12. Cookies y almacenamiento en el navegador', b: [
                'Pohua sólo usa una cookie técnica y almacenamiento local necesarios para funcionar y para recordar las preferencias que el propio usuario elige. No usa cookies de publicidad, de analítica ni de terceros. El detalle, y cómo borrarlas, está en la <a href="?doc=cookies">política de cookies y almacenamiento</a>.',
            ]},
            { t: '13. Menores de edad', b: [
                'Pohua es una herramienta de uso profesional y no está dirigida a menores de edad. No tratamos a sabiendas datos de menores.',
            ]},
            { t: '14. Cambios a este aviso', b: [
                'Cualquier cambio se publicará en esta misma página, con una nueva versión y fecha. Si el cambio afecta a lo que tratamos o para qué, Pohua pedirá a cada usuario que lo lea y lo acepte de nuevo al entrar.',
                'Versión {{version}}.',
            ]},
        ],
    },

    cookies: {
        titulo: 'Política de cookies y almacenamiento local',
        intro: 'Esta política explica qué guarda Pohua en su navegador, para qué y cómo puede borrarlo. Se informa en el momento del primer acceso, como exigen el artículo 14 del Reglamento de la LFPDPPP (México) y el artículo 82 de la ley Informatique et Libertés (Francia).',
        secciones: [
            { t: '1. Qué usamos, en resumen', b: [[
                '<b>Sólo lo estrictamente necesario</b> para que la aplicación funcione (iniciar sesión, abrir las calculadoras) y para recordar las <b>preferencias que usted mismo elige</b> (tema, idioma, sonido, reloj).',
                '<b>Ninguna</b> cookie de publicidad, de analítica, de redes sociales ni de terceros. No hay rastreo entre sitios.',
                'La fuente tipográfica se sirve desde el propio Pohua: su navegador no se conecta a Google ni a ningún otro tercero al abrir la aplicación.',
            ]]},
            { t: '2. Por qué no le pedimos consentimiento', b: [
                'Las cookies y el almacenamiento estrictamente necesarios para prestar un servicio que el usuario pidió, o para recordar una preferencia que él mismo fijó, están exentos de consentimiento previo (art. 82 de la ley Informatique et Libertés y directrices de la CNIL; art. 5.3 de la Directiva 2002/58/CE). Por eso sólo le informamos. Si algún día Pohua incorporara cualquier otra tecnología, no se activará hasta que usted la acepte expresamente, y podrá retirar esa aceptación desde esta página.',
            ]},
            { t: '3. El detalle', b: ['{{tabla}}'] },
            { t: '4. Cómo borrarlas o impedirlas', b: [
                'Puede borrar las preferencias guardadas por Pohua con el botón de abajo, o borrar todo desde la configuración de su navegador (sección de privacidad, «cookies y datos de sitios»). También puede bloquearlas allí.',
                'Tenga en cuenta que sin la cookie técnica y el almacenamiento de sesión <b>no se puede iniciar sesión ni abrir las calculadoras</b>, y que borrar la copia local de la calculadora elimina el trabajo que todavía no se haya guardado en Pohua.',
                '{{botonBorrar}}',
            ]},
            { t: '5. Más información', b: [
                'Lo que hacemos con los datos personales está en el <a href="?doc=privacidad">aviso de privacidad</a>. Dudas: {{correo}}. Versión {{version}}.',
            ]},
        ],
        tabla: [
            ['cgr_lector', 'Cookie técnica (HttpOnly)', 'Da acceso a las calculadoras y al lector de planos con la sesión ya iniciada.', 'Hasta cerrar el navegador'],
            ['cgr_token, cgr_token_caduca, cgr_usuario', 'Almacenamiento de sesión', 'Mantiene la sesión iniciada en esa pestaña.', 'Hasta cerrar la pestaña o 8 horas'],
            ['cgr_correo', 'Almacenamiento local', 'Recuerda el correo del último acceso para no teclearlo otra vez.', 'Hasta que se borre'],
            ['cgr-tema, cgr-idioma, cgr-sonido, cgr-reloj, cgr-instalar-oculto', 'Almacenamiento local', 'Preferencias elegidas por el usuario: tema claro u oscuro, idioma, sonido de avisos, huso del reloj y si se ocultó la sugerencia de instalar la aplicación.', 'Hasta que se borre'],
            ['cgr-legal', 'Almacenamiento local', 'Recuerda que ya se le informó de esta política, para no repetir el aviso.', 'Hasta que se borre o cambie la versión'],
            ['iscv4_local, iscv4_sharedlocal', 'Almacenamiento local', 'La calculadora guarda aquí el borrador en curso y una copia de trabajo, para no perder lo escrito si se corta la conexión. Puede contener datos de la cotización.', 'Hasta que se borre'],
            ['Caché de la aplicación', 'Service worker', 'Guarda los archivos de la aplicación (no datos de cotizaciones) para que abra más rápido y sin conexión.', 'Hasta la siguiente versión'],
            ['Notificaciones', 'Permiso del navegador', 'Sólo si el usuario las activa: permite recibir los avisos de Pohua en el teléfono o el escritorio.', 'Hasta que se desactiven'],
        ],
    },

    terminos: {
        titulo: 'Términos de uso de Pohua',
        intro: 'Pohua es una herramienta interna de la empresa para recibir, evaluar y cotizar solicitudes de clientes. Al entrar con su cuenta, usted acepta estas condiciones.',
        secciones: [
            { t: '1. Quién puede usarla', b: [
                'Sólo el personal y los colaboradores a quienes la empresa les dio una cuenta. Las credenciales son personales e intransferibles: no las comparta ni deje la sesión abierta en equipos ajenos. Si sospecha que alguien más las conoce, cambie su contraseña y avise al administrador.',
            ]},
            { t: '2. Confidencialidad', b: [
                'La información de Pohua —datos de clientes, planos, precios, costos, márgenes, proveedores y condiciones comerciales— es confidencial y puede constituir secreto industrial o comercial. Úsela sólo para su trabajo, no la copie fuera de los sistemas de la empresa ni la comparta con terceros sin autorización. Esta obligación continúa después de terminar su relación con la empresa.',
            ]},
            { t: '3. Uso aceptable', b: [[
                'No intente acceder a funciones o datos para los que su rol no tiene permiso.',
                'No extraiga datos de forma masiva ni automatizada, ni interfiera con el funcionamiento de la aplicación.',
                'No suba datos personales sensibles ni información ajena a la cotización.',
                'Respete los derechos de los clientes sobre sus planos y documentos.',
            ]]},
            { t: '4. Resultados automáticos', b: [
                'Los datos que la inteligencia artificial extrae de correos y planos, y los precios que calcula el motor de costos, son una ayuda: pueden contener errores. <b>Antes de enviar una oferta, una persona autorizada debe revisar</b> las cotas, el material, las cantidades y el precio. La responsabilidad de lo que se envía al cliente es de quien lo aprueba.',
            ]},
            { t: '5. Registro de actividad', b: [
                'Pohua registra quién hace cada acción relevante (aprobar, declinar, modificar, enviar) y cuándo, para la trazabilidad de las decisiones comerciales y la seguridad. Ese registro puede ser consultado por los administradores. Lo que se trata y por cuánto tiempo está en el <a href="?doc=privacidad">aviso de privacidad</a>.',
            ]},
            { t: '6. Disponibilidad', b: [
                'La empresa procura que Pohua funcione de forma continua, pero puede interrumpirlo para mantenimiento o por causas ajenas. Guarde su trabajo en la aplicación; no dependa de copias locales.',
            ]},
            { t: '7. Propiedad', b: [
                'Pohua, sus calculadoras, el motor de costos y su contenido son propiedad de la empresa o de sus licenciantes. Su cuenta le da permiso de uso para su trabajo, no ningún otro derecho.',
            ]},
            { t: '8. Suspensión', b: [
                'La empresa puede suspender o cancelar una cuenta si se incumplen estos términos, al terminar la relación laboral o de colaboración, o por seguridad.',
            ]},
            { t: '9. Cambios, ley aplicable', b: [
                'Estos términos pueden cambiar; la nueva versión se publicará aquí y Pohua le pedirá aceptarla al entrar. Se rigen por la ley y los tribunales siguientes: {{jurisdiccion}}, sin perjuicio de los derechos que la legislación laboral y de protección de datos del país de cada usuario le reconozca. Versión {{version}}.',
            ]},
        ],
    },
};
