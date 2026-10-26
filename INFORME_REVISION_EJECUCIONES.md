# Informe de revisión y reingeniería del bot e-Konsulat

**Actualización:** 19 de octubre de 2026 (hora local, UTC-03)  
**Último registro observado:** 19 de octubre, 12:50:35  
**Alcance:** `ejecucion.log`, `monitor.py`, `run_cron.sh`, `.env.example`, `.gitignore` y configuración local `HEADLESS`.

> El log se vació después de la revisión original del 15 de octubre y volvió a acumular registros. Las métricas actuales cubren las 430 corridas desde el 15 de octubre a las 19:20 hasta el 19 de octubre a las 12:50. La sección histórica conserva el análisis anterior al vaciado; sus cifras no deben sumarse a las de esta actualización.

## Actualización: ejecuciones del 15 al 19 de octubre

| Fecha | Corridas | CAPTCHA OK | Cola llena | Lugar detectado | Sin confirmación | Excepciones | CAPTCHA agotado |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15 oct (desde 19:20) | 28 | 24 | 24 | 0 | 0 | 4 | 0 |
| 16 oct | 143 | 125 | 122 | 3 | 3 | 18 | 0 |
| 17 oct | 60 | 53 | 52 | 1 | 1 | 7 | 0 |
| 18 oct | 121 | 94 | 92 | 2 | 2 | 27 | 0 |
| 19 oct (hasta 12:50) | 78 | 64 | 64 | 0 | 0 | 12 | 2 |
| **Total** | **430** | **360** | **354** | **6** | **6** | **68** | **2** |

Las categorías no son excluyentes. Las 430 marcas de ejecución tienen horas únicas. Hubo 58 corridas con respuesta de 2Captcha `ERROR_CAPTCHA_UNSOLVABLE`; el 19 de octubre, 64 de 78 corridas superaron el CAPTCHA y las otras 14 no llegaron a completarlo. El log registra dos errores de navegación en esos días.

### Qué ocurrió cuando hubo un lugar

El log muestra seis oportunidades, y en las seis se completó la secuencia hasta el estado “registro no confirmado”. No hay ninguna línea que confirme el registro. Esto no prueba que e-Konsulat rechazara las solicitudes: el bot no reconoció una confirmación explícita. Las frases de confirmación configuradas no aparecen en estas ejecuciones y no han sido contrastadas con una confirmación real del sitio.

### Causas concretas del flujo actual

- Las respuestas `ERROR_CAPTCHA_UNSOLVABLE` de 2Captcha levantaban una excepción y abortaban la corrida; no se obtenía un CAPTCHA nuevo para aprovechar los intentos restantes.
- Si el sitio cambiaba los campos o un selector dejaba de funcionar, `escribir_campo()` devolvía `False`, pero el flujo ignoraba ese resultado y podía avanzar al botón de envío.
- El selector de entrada CAPTCHA terminaba en `input`, que podía seleccionar un campo no relacionado si los selectores específicos dejaban de coincidir.
- Telegram se llamaba con `curl -s` sin comprobar HTTP ni el indicador JSON `ok`, por lo que un rechazo podía pasar inadvertido.
- Las corridas observadas están separadas por unos diez minutos. El wrapper ejecuta una vez por invocación; la programación y su intervalo viven fuera de este repositorio. Una ventana de disponibilidad más breve que el intervalo podría pasar entre corridas. Reducir el intervalo incrementa las solicitudes a e-Konsulat y el gasto de 2Captcha.

### Cambios aplicados en esta reingeniería

- Los errores recuperables de 2Captcha renuevan el CAPTCHA y reintentan hasta ocho veces; errores de cuenta/configuración no se consumen como reintentos. El texto reconocido ya no se escribe en el log.
- Se eliminó el selector CAPTCHA genérico `input`. El rellenado de campos obligatorios se verifica leyendo el valor resultante, y el bot no envía si falla un campo obligatorio o un checkbox requerido.
- La detección de validación considera mensajes de texto y controles visibles marcados como inválidos, para parar reenvíos.
- Telegram se considera exitoso únicamente ante HTTP satisfactorio y `ok: true`; el wrapper también reporta fallo de inicio si Python termina con error.
- El wrapper ya no vuelve a enviar avisos de cupo, confirmación o intervención que ya notifica el monitor.
- En modo headless, los avisos aclaran que no existe intervención visual y no se mantiene una espera inútil con el navegador oculto.
- Se añadieron pruebas unitarias para los nuevos comportamientos y se actualizó el README.

Los cinco envíos máximos se mantienen según la preferencia indicada. Si el servidor aceptó una solicitud pero no mostró una confirmación reconocida, los reintentos pueden duplicarla. No se hizo ningún envío real en esta revisión.

El log ya existente conserva las respuestas de CAPTCHA registradas por versiones anteriores; el cambio solo impide que se sigan agregando respuestas nuevas. No se eliminó ni truncó el historial de ejecuciones.

En la revisión inicial, el cron de esta Mac se cambió de cada 10 minutos a cada 2 minutos (`*/2 * * * *`). El 20 de octubre de 2026, a pedido del usuario, se actualizó a cada 20 minutos (`*/20 * * * *`). El lock mantiene una sola instancia activa; si una corrida excede el intervalo, las siguientes invocaciones se omiten mientras continúe activa.

## Resumen histórico (revisión anterior al vaciado del log)

**Fecha de esa revisión:** 15 de octubre de 2026  
**Último registro observado entonces:** 15 de octubre, 19:10:40  

### Resumen ejecutivo

- El historial abarca del **7 al 15 de octubre de 2026**. Se encontraron 982 cabeceras de corrida; al normalizar el formato de fecha/hora hay **976 marcas de tiempo únicas** y 6 cabeceras repetidas.
- El **15 de octubre**, 86 corridas terminaron antes del CAPTCHA por un error CDP al consultar la ventana; otras 2 fallaron al navegar a e-Konsulat. La última corrida registrada, a las 19:10, sí superó el CAPTCHA y detectó la cola llena. El cambio que quitó CDP ya está en el código actual.
- En el historial hay **18 detecciones** de un lugar disponible. Se registró el inicio del envío en 13 corridas; 4 terminaron con “registro no confirmado”, 2 requirieron validación humana y al menos una falló al localizar el botón para continuar. Estos mensajes no permiten inferir que el trámite haya concluido.
- **Hallazgo urgente:** el log contiene valores con formato de credenciales en URLs de error históricas. También guarda las respuestas de CAPTCHA en texto. `.gitignore` excluye `*.log`, pero eso no elimina copias ya hechas ni protege el archivo local.
- El estado local actual es `HEADLESS=true`: el proceso no muestra una ventana de Chromium. Si se requiere intervención, el aviso llega por Telegram, pero la página no se puede revisar visualmente durante esa corrida.

## Métricas por día

Las cifras son por corrida con marca de tiempo única. Una corrida cuenta como “CAPTCHA OK”, “cola llena”, etc. si el bloque contiene ese marcador. Los tipos de resultado no son mutuamente excluyentes.

| Fecha | Corridas | CAPTCHA OK | Cola llena | Lugar detectado | Sin confirmación | Excepciones | CAPTCHA agotado |
|---|---:|---:|---:|---:|---:|---:|---:|
| 7 oct | 7 | 5 | 5 | 0 | 0 | 0 | 3 |
| 8 oct | 123 | 92 | 88 | 5 | 0 | 35 | 1 |
| 9 oct | 76 | 56 | 55 | 0 | 0 | 20 | 1 |
| 10 oct | 145 | 141 | 138 | 3 | 0 | 2 | 0 |
| 11 oct | 120 | 120 | 115 | 5 | 0 | 0 | 0 |
| 12 oct | 135 | 123 | 121 | 0 | 0 | 4 | 8 |
| 13 oct | 144 | 139 | 135 | 3 | 3 | 1 | 4 |
| 14 oct | 137 | 84 | 82 | 2 | 1 | 51 | 3 |
| 15 oct | 89 | 1 | 1 | 0 | 0 | 88 | 0 |
| **Total** | **976** | **761** | **740** | **18** | **4** | **201** | **20** |

Las cifras reflejan el contenido actual del log; las seis cabeceras duplicadas se excluyeron de los conteos por corrida. El historial mezcla formatos de fecha de versiones anteriores, así que los totales sirven como resumen operativo y no como telemetría transaccional.

## Hallazgos y acciones recomendadas

### 1. Credenciales incluidas en el log — prioridad urgente

Se identificaron al menos tres cadenas con formato de credencial en excepciones históricas: claves de servicio en URLs de error de 2Captcha y tokens de Telegram en trazas de conexión. No se reproducen sus valores en este documento.

La función de ocultamiento actual ayuda con errores nuevos, pero `run_cron.sh` copia el log anterior sin volver a sanearlo. Por eso, los valores de registros antiguos permanecen. El log también contiene las respuestas reconocidas por 2Captcha en texto.

**Acciones recomendadas:**

1. Rotar la API key de 2Captcha y el token del bot de Telegram, dado que sus valores aparecen en el historial.
2. Limpiar o reemplazar el log histórico por una copia saneada, después de conservar solo lo necesario y de forma segura.
3. Dejar de registrar el texto del CAPTCHA y sanear también el contenido histórico al conservar/rotar logs.
4. Verificar por separado si el log fue copiado o respaldado fuera de esta máquina. La regla `*.log` de `.gitignore` no demuestra que nunca se haya subido antes.

### 2. Fallo de control de ventana CDP — corregido en el código actual

El 14 y 15 de octubre se repitió `CDPSession.send: ... Browser.getWindowForTarget: No web contents in the target`: **49** corridas el 14 y **86** el 15. Eso detenía el flujo antes de buscar el CAPTCHA. En el código actual se eliminó esa consulta CDP; la corrida de las 19:10 del 15 de octubre llegó al CAPTCHA, lo resolvió en dos intentos y continuó hasta detectar la cola llena.

El registro contiene además fallos de navegación (`Page.goto`) en distintos días, incluidos dos el 15 de octubre. Cambiar `wait_until` a `domcontentloaded` reduce la espera por red inactiva, pero no corrige fallas de DNS, conectividad o indisponibilidad del sitio.

### 3. CAPTCHA — inestabilidad externa e intentos agotados

Se registran **20 corridas** que agotaron ocho intentos. En días anteriores también aparecen respuestas de 2Captcha malformadas, errores de conexión y timeouts. Hubo 761 corridas con CAPTCHA superado; por tanto, el mecanismo no estuvo totalmente caído, pero la tasa de rechazo/intermitencia fue relevante.

El log confirma que 2Captcha devolvió respuestas y que e-Konsulat rechazó varios intentos; no permite determinar si los rechazos se deben a la calidad de la imagen, a cambios del CAPTCHA o a la validación del sitio. El código actual mejora el diagnóstico de respuestas que no son JSON, pero el resultado sigue dependiendo de ambos servicios.

### 4. Envío del formulario y confirmación no demostrada

El registro contiene 18 alertas de lugar disponible. En 13 bloques aparece el inicio del envío; cuatro registran explícitamente que no se encontró confirmación y dos muestran errores de validación que requieren intervención. El caso del 14 de octubre a las 00:42 encontró lugar pero agotó el tiempo al desplazar el botón `Dalej`; el de las 11:50 completó los campos y pulsó el botón, pero no encontró confirmación.

El mensaje “registro no confirmado” significa que el bot **no pudo probar el resultado**, no que e-Konsulat necesariamente haya rechazado la solicitud. El texto de éxito que busca el código debe verificarse contra una confirmación real del sitio: no hay evidencia en el log de una corrida actual que haya coincidido con uno de esos textos.

El código actual reintenta el envío hasta cinco veces si no detecta confirmación ni errores de validación. Como el primer envío podría haber sido aceptado aunque la página no lo haya confirmado de forma reconocible, esos reintentos pueden crear duplicados. Esto concuerda con la preferencia indicada por el usuario, pero el sistema debe seguir diferenciando “confirmado” de “sin confirmación”.

### 5. Validación de campos y disponibilidad de intervención

`escribir_campo` devuelve `False` si no encuentra o no completa un campo, pero varias llamadas ignoran ese resultado y el flujo puede continuar hasta buscar `Dalej`. El historial del 14 de octubre a las 00:42 muestra que no aparecen los mensajes de campos completados y luego falla la búsqueda del botón.

Se recomienda detener el envío si no se completaron todos los campos obligatorios y comunicar cuáles faltan, sin incluir sus valores. También conviene validar el prefijo y la descripción, cuyos fallos se registran parcialmente o se ignoran.

Con `HEADLESS=true`, Chromium no tiene ventana visible y `mostrar_ventana_navegador` solo emite un aviso; no puede convertir una sesión headless en una ventana. El proceso espera cuatro minutos, pero la intervención visual no es posible. Si se necesita actuar manualmente, debe configurarse una ejecución no headless y comprobar que la ventana se restaure correctamente.

### 6. Fiabilidad de notificaciones de Telegram

El historial contiene fallos de resolución DNS al enviar mensajes. Además, `enviar_telegram` no comprueba el estado HTTP ni el campo `ok` de la respuesta de Telegram; un error HTTP de la API podría no generar una excepción y pasar inadvertido.

Se recomienda comprobar explícitamente la respuesta de Telegram y registrar el fallo con datos saneados. No incluir el token, el cuerpo completo de la URL ni datos personales en el error.

## Estado del código revisado

- El control CDP que impedía alcanzar el CAPTCHA fue retirado.
- La navegación usa `domcontentloaded`.
- La API de 2Captcha convierte respuestas no JSON en errores diagnósticos sin imprimir el cuerpo de la respuesta.
- El CAPTCHA ya no se anuncia por audio; el mecanismo de audio fue retirado.
- La configuración local actual es `HEADLESS=true`; Chromium funciona sin ventana visible.
- El código permite hasta cinco envíos ante falta de confirmación reconocida. Esa lógica no está validada contra una confirmación real del sitio y aún no hay evidencia en el log de una corrida que ejercite esta versión.
- El análisis estático de `monitor.py` y `run_cron.sh` no reportó errores. No se ejecutó el bot contra e-Konsulat ni se probaron envíos reales.

## Límites de este informe

El log registra mensajes de ejecución, no respuestas HTTP completas ni el estado persistente de la lista de espera. Por ello no permite certificar que alguna solicitud haya quedado registrada, atribuir todos los rechazos de CAPTCHA a una causa concreta ni reconstruir el contenido visual exacto de cada página. Para confirmar un registro se requiere una señal verificable de e-Konsulat o revisar el correo/estado del solicitante.
