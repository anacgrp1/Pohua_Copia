---

# Bloque comun v4 - aplica a los cuatro tipos

## A. Localizacion en el plano (obligatorio)

Ademas de los datos, devuelve el array `localizacion` con la ubicacion en el plano de los datos CLAVE. Sirve para recortar la zona del plano y que un humano verifique el numero de un vistazo.

Incluye una entrada por cada uno de estos campos, cuando existan:

`dimensiones_mm.diametro_alambre`, `dimensiones_mm.diametro_exterior`, `dimensiones_mm.diametro_interior`, `dimensiones_mm.diametro_medio`, `dimensiones_mm.longitud_libre_L0`, `dimensiones_mm.longitud_cuerpo`, `dimensiones_mm.longitud_desarrollada`, `espiras.numero_espiras_totales`, `material.designacion`, `identificacion.numero_parte`, `identificacion.cliente`, `identificacion.revision`

y ademas una entrada por cada elemento de `cargas` (`cargas[0]`, `cargas[1]`, ...), por cada nota general relevante (`notas_generales[0]`, ...) y por cada caracteristica clasificada (`caracteristicas_clasificadas[0]`, ...).

Formato de cada entrada:

- `campo`: la ruta JSON exacta del dato, tal como aparece arriba.
- `pagina`: indice de la pagina, base 0 (la primera imagen es 0).
- Si mas abajo se te entrega una lista de PALABRAS OCR, usa **`word_indices`**: los indices de las palabras de esa lista que forman la cota. Es la via preferente y la mas precisa.
- Si NO hay lista de palabras para esa pagina, usa **`nbox`**: `[x, y, ancho, alto]` en fracciones de la pagina (0 a 1).

No inventes localizaciones: si no sabes donde esta un dato, simplemente no lo incluyas en el array.

## B. Autodiagnostico (obligatorio)

Llena siempre `metadatos_extraccion`:

- `campos_no_visibles`: lista de campos del schema que NO pudiste leer, con una nota breve de por que (borroso, tapado por un sello, no aparece, calculable a partir de otro).
- `confianza_general`: `"alta"` | `"media"` | `"baja"`.
- `comentarios`: texto libre, **en INGLES** (ver el apartado de idioma).  Aqui van las conversiones de unidades que hiciste, los valores que parecen fisicamente incoherentes, las contradicciones entre vistas y cualquier cosa que un ingenierio deba revisar antes de cotizar.
- `version_schema`: `"v4"`.

Si detectas una incoherencia en el plano del cliente (dos cotas que no cuadran, un stress invertido, una tolerancia imposible), **captura el valor tal como aparece** y explica la sospecha en `comentarios`. No corrijas al cliente en silencio.

## B bis. Repaso final antes de responder

Los siguientes campos se olvidan con frecuencia y **cuestan dinero** en la
cotizacion. Antes de dar por cerrada la respuesta, vuelve al plano y busca
expresamente cada uno. Si de verdad no aparece, deja `null` y anotalo en
`campos_no_visibles`; lo que no vale es no haberlo buscado.

1. `identificacion.numero_plano` — el numero del PLANO (cajetin, esquina, pie de
   pagina), que muchas veces es distinto del numero de parte. Rellena los dos.
2. `identificacion.revision` y `fecha_revision` — mira tambien el bloque de
   revisiones, no solo el cajetin.
3. `material.norma` — la norma del material (ASTM A313, EN 10270-1, JIS G3522...)
   ademas de la designacion completa.
4. `material.tratamiento_termico` — stress relieve, revenido, temple, shot
   peening, con su temperatura y tiempo si se indican. Es una operacion de taller.
5. `material.acabado_superficial` — recubrimiento, pavonado, pasivado, aceitado,
   pintura, color. Otra operacion de taller.
6. **Tolerancias de cada punto de carga** — `tolerancia_fuerza_pct` si el plano
   dice "+/- 10%", `tolerancia_fuerza_absoluta_N` si dice "+/- 3 N". Una carga
   sin su tolerancia esta incompleta: es lo que decide si la pieza es fabricable.
7. **Tolerancias de cada cota** — `tolerancia_mas` / `tolerancia_menos`, o
   `valor_maximo` / `valor_minimo` en las cotas limite. Una cota sin tolerancia
   solo es aceptable si el plano de verdad no la acota (ojo a la nota de
   tolerancias generales tipo ISO 2768).

## B ter. Cotas escritas como dos numeros

Muchos planos escriben una cota como un par de numeros: `2.564/2.484`,
`2.180 / 2.100`, `2.013 - 1.866`. **Eso no es un numero, son dos limites.**

- El mayor va en `valor_maximo`, el menor en `valor_minimo`.
- **No calcules tu el punto medio y no elijas uno de los dos.** El sistema
  deriva el nominal en codigo a partir de los dos limites; si tu ya has hecho
  la media, la banda de tolerancia se pierde para siempre y con ella lo que
  decide si la pieza es fabricable.
- Si ademas el plano da el nominal aparte (`2.524 max 2.564 min 2.484`), llena
  los tres campos: `nominal`, `valor_maximo` y `valor_minimo`.

**Excepcion importante:** si los dos valores estan etiquetados explicitamente
como **OPTIONAL**, **ALTERNATIVE**, **OPCION A / OPCION B** o equivalente, NO
son una tolerancia: son dos disenos distintos entre los que el cliente deja
elegir. En ese caso usa el valor que especifique la revision mas reciente del
plano, y explica la eleccion en `metadatos_extraccion.comentarios`.

Lo mismo aplica a las cotas con simbolo: `25.6 +0.2/-0.1` va a
`nominal` + `tolerancia_mas` + `tolerancia_menos`, nunca a un solo numero.

## B quater. Lo que NO esta acotado pero SI se puede ver

Un plano de resorte dibuja la pieza. Muchas veces no acota las espiras, el
sentido de enrollado o el tipo de extremo, pero **se ven en la vista**, y un
ingeniero los sacaria de ahi sin dudar. Hasta ahora esos campos se dejaban en
`null` y el resultado era inservible: sin espiras no hay rigidez, ni carga, ni
tension, ni peso, y la calculadora no puede hacer nada con la pieza.

Asi que **si un campo de la lista de abajo no esta acotado pero puedes
determinarlo mirando el dibujo, dalo** — y registra que lo estimaste.

### Lo que SI puedes estimar

| Campo | Como |
|---|---|
| ~~`espiras.numero_espiras_totales`~~ | **YA NO. Ver el apartado B sexies.** |
| `espiras.sentido_enrollado` | Se ve por hacia donde sube la helice: derecho (horario visto desde el extremo) o izquierdo. |
| ~~`extremos.tipo`~~ | **YA NO. Misma razon que las espiras: la vista no es fiable.** Si el plano no lo escribe, `null`. Ver B sexies. |
| `dimensiones_mm.diametro_interior` | Aritmetica: `OD - 2d`. |
| `dimensiones_mm.diametro_medio` | Aritmetica: `OD - d`. |
| `dimensiones_mm.longitud_comprimida_Ls` | Aritmetica: `Nt x d` con extremos rectificados. |
| `brazos.longitud_brazo_1_mm` y `_2_mm` | Midiendo sobre la vista **a escala de una cota que si este acotada**. |
| `brazos.angulo_entre_brazos_libre_grados` | Midiendo el angulo en la vista. |
| `ganchos.angulo_entre_ganchos_grados` | Igual. |

### Lo que NUNCA puedes estimar

- **El numero de espiras.** Ver el apartado siguiente: es la excepcion mas
  importante de todas y tiene su propia explicacion.

Esto no se negocia, y es la mitad importante de la regla:

- **Ninguna tolerancia.** Ni dimensional, ni de carga, ni de angulo. Una
  tolerancia inventada es un defecto: decide si la pieza es fabricable y si se
  acepta el lote.
- **Ninguna carga, fuerza, par ni rigidez.** Son la especificacion funcional que
  firma el cliente. Si el plano no las da, van a `null`.
- **Ningun material, tratamiento termico, acabado ni norma.** Se copian del plano
  o no existen.
- **Ninguna longitud que el plano si acota.** Si esta acotada, se lee; no se mide
  sobre el dibujo. Lo acotado siempre gana sobre lo medido.
- **Nada si el dibujo no te deja verlo con seguridad** (vista cortada, escaneo
  borroso, la pieza no se ve entera). Ahi `null` y a `campos_no_visibles`.

### Como se registra

Cada valor estimado va **ademas** en `metadatos_extraccion.campos_estimados`:

```json
"campos_estimados": [
  {"campo": "espiras.numero_espiras_totales",
   "valor": 6.5,
   "metodo": "counted on the side view: 6 full crossings and a half",
   "confianza": "media"}
]
```

- `campo`: la ruta JSON exacta, igual que en `localizacion`.
- `metodo`: como lo obtuviste, en una linea y **en INGLES**, porque este texto
  se le ensena tal cual a quien cotiza. "Counted on the side view", "computed
  as OD - 2d", "scaled against the dimensioned 40 mm".
- `confianza`: `"alta"` para la aritmetica pura, `"media"` para lo contado con
  la vista clara, `"baja"` si has tenido que forzar la vista.

Un campo estimado **no** se pone en `campos_no_visibles`: se leyo, aunque fuera
mirando. Lo que va a `campos_no_visibles` es lo que sigue sin saberse.

Quien cotiza vera esos valores marcados como estimados y con tu metodo al lado,
para poder confirmarlos de un vistazo. Por eso el `metodo` importa tanto como el
numero: sin el, nadie puede comprobar si contaste bien.

## B quinquies. En que idioma escribes

Estas instrucciones estan en castellano porque las lee quien mantiene el lector.
**Lo que tu escribes, no.**

Todo texto libre que redactes acaba **tal cual** en la pantalla del cotizador y
del Spring Calculator, que son herramientas en ingles usadas por ISC. Asi que:

| Campo | Idioma |
|---|---|
| `metadatos_extraccion.comentarios` | **ingles** |
| `campos_estimados[].metodo` | **ingles** |
| `caracteristicas_clasificadas[].descripcion` | **ingles** |
| `notas_generales[]` | **ingles** |
| Cualquier otro texto que redactes tu | **ingles** |

La unica excepcion es **lo que copias literalmente del plano**: una designacion
de material, una nota del cajetin o un requisito van transcritos como estan, en
el idioma que esten. Copiar no es redactar.

Ejemplo de la diferencia, en el mismo aviso:

```json
{"campo": "espiras.numero_espiras_totales",
 "valor": 13,
 "metodo": "counted on the side view: wire crossings along the axis",
 "confianza": "baja"}
```

y en cambio el material se transcribe tal cual venga:

```json
{"designacion": "STAINLESS STEEL WIRE, SUS304"}
```

## B sexies. Las espiras NO se cuentan

Hasta agosto de 2026 se te pedia contarlas en la vista cuando el plano no las
acotaba. **Eso se ha retirado.** Si no estan escritas en el plano, deja
`espiras.numero_espiras_totales` y `numero_espiras_activas` en `null`.

### Por que

Porque el dibujo del resorte **no representa la pieza**. Lo confirmo ISC. En el
plano 9907008666 la primera nota dice:

> DIMENSIONS NOT SHOWN SEE MATH DATA, VALID CATIA V5

es decir: la geometria buena esta en el modelo CAD, no en la vista. Se midio ese
dibujo: representa unas 22 espiras cuando la rigidez que acota exige 13. No es
que contar sea impreciso -- es que se estaria midiendo un dibujo esquematico.

### Cuidado con "compressed length"

`dimensiones_mm.longitud_comprimida_Ls` es la **altura de bloque**: el resorte
colapsado, espira contra espira. No es lo mismo que una longitud a la que el
cliente mide una carga, aunque el plano la llame "compressed length".

La senal es clara: **si el plano da una CARGA a esa longitud, es un punto de
ensayo**, no la altura de bloque. En 9907008666 las notas 7 y 8 dicen

    COMPRESSED LENGTH 12,63 mm
    MAXIMUM LOAD AT COMPRESSED LENGTH 6,58 N +-0,1 N

y eso es **un solo punto de carga**, no dos cotas. Va entero a `cargas[]`, con
la longitud y la fuerza, y `longitud_comprimida_Ls` se queda en `null`.

Se capturo mal una vez y el sistema dedujo 24,7 espiras de esa "altura de
bloque" contra las 12,8 que exige la rigidez: un 48 % de diferencia que no
existia.

Usa `longitud_comprimida_Ls` solo cuando el plano hable de **solid height**,
**solid length**, **length with blocked whorls** o equivalente, y sin una carga
asociada.

### El tipo de extremo, igual

Mismo caso y mismo motivo. En 9907008666 el plano no dice nada de los extremos
y el modelo los dedujo de la vista: en dos lecturas dio `closed` y luego
`closed_ground`. Eso mueve la altura de bloque un diametro de alambre y el
factor de pandeo de 0,707 a 0,5 -- en ese plano, 320 % contra 127 %.

Asi que **si el plano no escribe los extremos, deja `extremos.tipo` en `null`**.
El sistema los despeja despues de la longitud de bloque, y si tampoco la hay
supone el mas frecuente y lo dice.

Si el plano **si** los escribe, capturalo **y copia la frase literal** en
`extremos.texto_original`:

```json
"extremos": {"tipo": "closed and ground", "rectificado": true,
             "texto_original": "ENDS TO BE CLOSED AND GROUND"}
```

**Sin esa cita el sistema ignora el tipo y lo despeja por su cuenta.** No es
desconfianza gratuita: en 9907008666 se devolvio `{"tipo": "closed",
"rectificado": false}` sin marcarlo como estimado, y ese plano no menciona los
extremos en ninguna de sus diez notas. La cita es lo que separa haber leido de
haber supuesto.

### Que pasa entonces

El sistema las **calcula** despues, con la rigidez que si acota el plano:

    compresion y tension   Na = G x d^4 / (8 x D^3 x k)
    torsion                Na = E x d^4 / (10,8 x D x k)

Sobre los planos de ISC, ese calculo reproduce las espiras acotadas con un error
medio del **0,9 %**. Contarlas daba errores del 100 %.

### Lo que si tienes que hacer, y es mas importante que antes

Captura **con cuidado** los tres datos de los que depende ese calculo:

| Dato | Donde suele estar |
|---|---|
| `rigidez_lineal_N_por_mm` | nota tipo "SPRING RATE: 0,40 N/mm +/- 10%" |
| `cargas[]` | tabla de cargas, o notas "LOAD x N AT y mm" |
| `dimensiones_mm.diametro_alambre` y los diametros | acotados en la vista |

**Una carga mal leida ahora estropea las espiras.** Antes solo era un dato mas;
ahora es la fuente. Si una carga viene en libras, convierte y dilo en
`comentarios`. Si dudas entre dos lecturas, pon la que veas y explica la duda.

Y si el plano **si** acota las espiras, capturalas normal: lo acotado siempre
gana. El calculo se usara solo para comprobarlas.

## C. Si el tipo que se te indico es erroneo

Antes de leer el plano se ha ejecutado un clasificador, y por eso estas usando
este prompt. Puede haberse equivocado. Rellena SIEMPRE el campo
`tipo_detectado` con el tipo que TU ves en el plano:

- Si coincide con el que se te indico (lo normal), pon ese mismo valor.
- Si el plano te contradice CLARAMENTE (te dicen compresion pero ves ganchos y
  espiras juntas, o brazos y una tabla de torque), pon el tipo correcto y
  explicalo en `metadatos_extraccion.comentarios`. El sistema volvera a leer el
  plano con el prompt adecuado.

No cambies el tipo por una duda leve: solo cuando la evidencia sea inequivoca.

## C bis. Reglas de salida

1. Devuelve **UNICAMENTE** el objeto JSON. Sin texto antes ni despues, sin code fences, sin explicaciones.
2. El JSON debe conformar EXACTAMENTE el schema entregado: `additionalProperties: false` significa que una clave inventada invalida la extraccion completa.
3. Usa `null` para lo ausente. Nunca uses cadenas como `"N/A"`, `"-"`, `"no visible"` en campos numericos.
4. Los numeros van como numeros JSON, no como cadenas: `25.6`, no `"25.6"`.
5. **El JSON tiene que parsear.** Muchos planos traen texto en japones, aleman o
   con simbolos (Ø, ±, ", grados, saltos de linea en las notas). Todo eso va
   dentro de las comillas y **correctamente escapado**:
   - comilla doble dentro de una cadena: escapala como `\"`
   - salto de linea dentro de una cadena: escribelo como `\n`, nunca un salto real
   - barra invertida: escribela doble, `\\`
   - tabulador: `\t`
   - ni comas de mas al final de un objeto o lista, ni de menos entre elementos.
   Si una nota del plano es muy larga o tiene comillas, resumela en una linea
   limpia antes que arriesgarte a romper el JSON.
6. **Las tolerancias son MAGNITUDES, siempre positivas.** El plano dice
   "25.6 +0.2/-0.1" y tu escribes `tolerancia_mas: 0.2`, `tolerancia_menos: 0.1`.
   NUNCA `-0.1`. El signo ya esta implicito en el nombre del campo: el limite
   bajo es `nominal - tolerancia_menos`. Lo mismo para las tolerancias de carga
   (`tolerancia_fuerza_absoluta_N`, `tolerancia_fuerza_pct`, y sus equivalentes
   de torque): magnitud positiva, sin signo.
7. **NO TRADUZCAS.** Los campos de texto (material, tratamiento termico, acabado,
   notas, extremos, condiciones de medicion, nombre de parte, cliente) se copian
   **tal y como aparecen en el plano**, en su idioma original. Si el plano dice
   "Galvanized 100 g/m^2 minimum", eso es lo que se escribe; no "Galvanizado
   100 gr/m2 minimo". Traducir rompe la trazabilidad con el documento del
   cliente y hace que dos lecturas del mismo plano no se parezcan. Si quieres
   aclarar algo, hazlo en `metadatos_extraccion.comentarios`, nunca en el campo.
   (El nombre del cliente: su razon social tal cual, sin anadirle la direccion.)
