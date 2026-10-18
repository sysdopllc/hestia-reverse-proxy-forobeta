# Extra: monta tu proxy con un agente de IA

Puedes encargar la ejecución al agente sin escribir comandos personalmente. Necesita herramientas y acceso SSH autorizado al VPS; un chat sin acceso al servidor solo puede orientarte. Configura el acceso por un canal privado, preferiblemente con llave SSH, y nunca publiques credenciales en el foro.

Para este trabajo recomiendo **ChatGPT Plus**, con un precio base anunciado de **US$20 al mes** y acceso a Codex incluido. Es una opción práctica para revisar el proyecto, ejecutar los pasos y contrastar los resultados. Tiene límites de uso; el importe final depende de la compra y los impuestos aplicables. No incluye el VPS ni consumo de API. [Planes oficiales](https://learn.chatgpt.com/docs/pricing).

Plus no es obligatorio para seguir la guía ni es el único plan con acceso a Codex. También puedes usar otro agente con herramientas equivalentes. La suscripción no configura SSH por sí sola.

Sustituye los campos entre corchetes y envía estos mensajes por separado.

## 1. Revisa antes de tocar

> Quiero montar un reverse proxy con https://github.com/sysdopllc/hestia-reverse-proxy-forobeta, versión v1.1.0. VPS proxy: [alias SSH o IP]. Origen: [IP]. Dominio y alias: [dominio, www si corresponde]. DNS: [proveedor; Cloudflare sí/no]. Usa el acceso privado que tengo configurado, sin mostrar secretos. Lee README, VALIDATION y el código. Comprueba sistema operativo, recursos, webs existentes, IP distintas y HTTPS del origen. Esta fase es solo lectura: dime si el VPS cumple y presenta el plan. No reinstales, borres ni modifiques DNS todavía; si algo no encaja, detente y explícalo.

## 2. Ejecuta lo revisado

> Autorizo el plan que acabamos de revisar para ese VPS dedicado. Haz tú la instalación y preparación; no me des comandos para copiarlos. Utiliza el instalador oficial de Hestia y la versión v1.1.0 del repo. Conserva la limpieza de plantillas y paquetes sobrantes, con respaldo y manifiesto, manteniendo las dependencias del panel. Usa sus CLI y plantillas nativas. Configura usuario, dominio, HTTPS y renovación de ambos certificados; verifica Nginx antes de recargar. Mantén --iptables no y --fail2ban no como en la receta, sin desactivar protecciones preexistentes ni la validación TLS. Antes de cambiar DNS, enséñame los registros exactos y espera mi confirmación. Si encuentras datos existentes, una reinstalación necesaria o un fallo, detente sin forzar.

## 3. Comprueba y entrega

> Verifica el resultado real: dominio y www, HTTPS hasta el origen, robots.txt, sitemap, login, formulario/subida, IP del visitante y WebSocket si se usa. Comprueba certificados, mecanismo de renovación y regeneración de un dominio de prueba desde Hestia. Si falla algo, conserva la evidencia y corrige solo dentro del alcance autorizado. Entrégame URL del panel, ubicación del respaldo, pruebas realizadas y pendientes. No declares terminado lo que no hayas probado. No publiques accesos ni cambies el servidor final sin autorización específica.

La idea es que el agente haga el trabajo y te muestre evidencia; tú conservas la decisión sobre cambios de DNS y acciones fuera del plan.
