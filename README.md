# Reverse proxy con HestiaCP para ForoBeta

Plantillas y preparación de un VPS dedicado al proxy. El contenido continúa en el servidor final; los visitantes se conectan a la IP del proxy.

```text
Visitante ── HTTPS ── [Cloudflare opcional] ── HTTPS ── VPS proxy ── HTTPS verificado ── Servidor final
```

Reemplazo del material del tutorial de 2024 cuyo repositorio original fue retirado. Este proyecto reconstruye su función; no es una copia recuperada del antiguo `default.pkg`.

**Alcance:** VPS nuevo con Ubuntu LTS admitido por Hestia y su esquema **Nginx como proxy + Apache/PHP-FPM**, como en la guía original. El instalador usa el canal estable oficial de Hestia, sin fijar una única versión. Las plantillas `rp` envían las peticiones directamente al servidor final. No desinstales paquetes base del panel.

**Validación:** 11 pruebas de seguridad/rollback del script y 14 comprobaciones contra Nginx real. No se ha probado una instalación completa de Hestia, su actualización ni una emisión/renovación pública de Let's Encrypt. Detalles en [VALIDATION.md](VALIDATION.md).

## 1. Antes de empezar

- Un VPS nuevo dedicado a este proxy, con acceso root y consola del proveedor.
- El dominio y `www` funcionando en el servidor final con un certificado HTTPS válido para ambos nombres. Si no usas `www`, no lo agregues.
- IP del proxy e IP del servidor final distintas. El origen debe aceptar conexiones desde el proxy.
- Un hostname propio para el panel, por ejemplo `proxy.tudominio.com`, cuyo DNS apunte al VPS proxy.
- Puertos 80/443 accesibles para las webs; SSH y 56464 según el acceso administrativo que necesites. La receta no instala firewall ni Fail2Ban.

Prueba el origen ANTES de cambiar DNS, sustituyendo dominio e IP:

```bash
curl --resolve ejemplo.com:443:203.0.113.10 https://ejemplo.com/ -I
curl --resolve www.ejemplo.com:443:203.0.113.10 https://www.ejemplo.com/ -I
```

Las direcciones `203.0.113.10` y los dominios de ejemplo se sustituyen por los tuyos. No uses `-k` para esconder un certificado incorrecto.

## 2. Instalar Hestia estable: un bloque

En un VPS Ubuntu LTS nuevo, como root:

```bash
apt-get update && apt-get install -y ca-certificates curl git python3 && \
git clone --branch v1.1.0 --depth 1 \
  https://github.com/sysdopllc/hestia-reverse-proxy-forobeta.git \
  /root/hestia-reverse-proxy && \
python3 /root/hestia-reverse-proxy/setup.py install
```

El asistente pregunta hostname, correo e IP del origen. Descarga el instalador estable oficial de Hestia sin fijar una versión del panel. Hestia valida el sistema operativo admitido. Se genera una contraseña y se guarda en `/root/hestia-reverse-proxy-setup.json`, accesible solo para root; se entrega al instalador por stdin, no como argumento del comando.

La receta conserva **`--iptables no --fail2ban no`**. No instala firewall ni Fail2Ban, ni desactiva protecciones existentes. Instala Nginx + Apache/PHP-FPM, sin DNS, correo ni bases de datos. El panel usa el puerto 56464. El asistente rechaza una instalación existente y no usa `--force`.

Cuando termine, reinicia con `reboot` y vuelve a entrar por SSH.

## 3. Barrido automático de vhosts, plantillas y paquetes

```bash
python3 /root/hestia-reverse-proxy/setup.py finish
```

Esta es la limpieza de la receta original, ahora con respaldo y registro:

1. Aparta los vhosts cuyo nombre completo es una IP (`/etc/nginx/conf.d/192.0.2.20.conf`, por ejemplo). No usa `0*`/`1*`, que también alcanzarían archivos como `0rtt-anti-replay.conf`.
2. Aparta plantillas de aplicaciones y paquetes sin usuarios, manteniendo las dependencias de Hestia (`default`, `suspended` y las referenciadas).
3. Genera e instala `rp.tpl`, `rp.stpl` y el mapa WebSocket; crea el paquete con la CLI oficial y lo asigna a admin para los dominios nuevos.
4. Valida Nginx y recarga. Muestra `BARRIDO 1/3`, `2/3`, `3/3`, los archivos movidos y la ruta del respaldo.

No necesitas editar vhosts a mano ni hacer dos pasadas de simulación/aplicación. El hostname default que crea el instalador se conserva para el panel; se rechaza cualquier otra web existente. Lo apartado permanece bajo `/root/hestia-reverse-proxy-backups/FECHA/`. Ante un fallo se intenta restaurar la preparación; si el rollback también falla, se muestra el error. No se desinstalan librerías del panel.

`proxy.py prepare --origin IP` sigue disponible como simulación opcional para revisión técnica; `--apply` aplica los cambios. `setup.py finish` hace la aplicación directamente con los datos guardados y permite retomar la asignación del paquete tras una interrupción, comprobando los archivos registrados.

## 4. Usuario, dominio y DNS

1. Entra a Hestia: `https://IP_DEL_PROXY:56464`, usuario admin y contraseña mostrada al terminar. Comprueba la identidad del panel y configura su certificado.
2. El asistente ya asignó el paquete **reverse-proxy** a admin. El hostname que creó Hestia se conserva y no se transforma en proxy.
3. En Web agrega tu dominio. Agrega `www` como alias solo si lo usarás. No crees DNS ni correo en este VPS.
4. En opciones avanzadas confirma que la **plantilla de proxy es `rp`**; la plantilla web permanece en `default`.
5. En tu proveedor DNS, apunta los registros A del dominio y `www` a la IP del proxy. Revisa los AAAA: no deben conservar la IPv6 del servidor final. Esta receta configura el listener de la IP seleccionada por Hestia; no publiques AAAA hasta comprobar el servicio por IPv6.

Para un dominio existente en un usuario nuevo, la selección se puede hacer con la CLI nativa:

```bash
/usr/local/hestia/bin/v-change-web-domain-proxy-tpl USUARIO ejemplo.com rp "" no
nginx -t && systemctl reload nginx
```

Sustituye `USUARIO` y `ejemplo.com`. El argumento vacío de extensiones es intencional: `rp` reenvía todas las rutas al origen y no contiene una ubicación de estáticos separada. No cambies manualmente los archivos generados bajo `conf/web`: Hestia los reconstruye.

## 5. HTTPS y Cloudflare

Con el DNS apuntando al proxy y el puerto 80 accesible, edita el dominio en Hestia y activa **SSL** y **Let's Encrypt**. Comprueba que el certificado incluya todos los alias. Cuando HTTPS funcione, activa la redirección a HTTPS desde Hestia. Deja HSTS para después de validar el funcionamiento.

Cloudflare es opcional. Para la primera emisión puedes usar temporalmente **Solo DNS**; eso expone la IP del proxy, que es el destino publicado. Después activa la nube si la quieres y utiliza **Full (strict)** con un certificado válido en el proxy. No soluciones errores de certificados cambiando a Flexible.

La ruta de validación `/.well-known/acme-challenge/` la atiende Hestia mediante sus includes nativos. No se agrega otra regla que compita con ella. Para las renovaciones, esa ruta debe seguir accesible y sin challenge/bloqueo del WAF. No dependas de una excepción por User-Agent como autenticación de Let's Encrypt.

**Hay dos certificados distintos:** el del proxy y el del origen. Al cambiar DNS, el origen también necesita un método de renovación que siga funcionando. Usa DNS-01, un hostname de origen con renovación propia u otro mecanismo del proveedor. Esta plantilla no reenvía al origen los desafíos que Hestia atiende localmente.

Si el certificado del origen corresponde a un nombre diferente, usa `--tls-name origen.tudominio.com` al preparar. El `Host` HTTP continúa siendo el dominio visitado; SNI y validación TLS usan ese nombre fijo. El origen debe admitir esa combinación. Un certificado Cloudflare Origin CA requiere configurar su CA de confianza específicamente; no está incluido en el almacén público de esta receta.

## 6. Comprobar antes de darlo por listo

- Home, dominio y `www`, imágenes, login, formularios y subidas.
- `robots.txt` y sitemap deben ser los del servidor final, también por HTTPS.
- Certificado del proxy y del origen; sin bucles ni errores 502.
- IP del visitante en el origen: configura allí la confianza **solo en la IP del proxy**. Una lista blanca del firewall no configura por sí sola las cabeceras de IP real.
- WebSocket si tu aplicación lo utiliza. No se oculta la cabecera Upgrade.
- Regeneración de un dominio de prueba desde Hestia y comprobación posterior. La plantilla propia `rp` permanece; una actualización de Hestia puede reponer plantillas estándar que se apartaron. No programes purgas automáticas.
- Renovación real de certificados en tu entorno antes de dejarlo desatendido.

El proxy no añade caché de páginas ni reemplaza archivos estáticos del origen. Respeta sus cookies y sus cabeceras de caché. Los tiempos de espera actuales son 10 segundos al conectar y 300 segundos de lectura/escritura; adapta los límites de subida y streaming a tu aplicación.

## Diagnóstico rápido

| Síntoma | Qué revisar |
| --- | --- |
| 502 | Acceso del proxy al origen, puerto, certificado, SNI y `/var/log/nginx/domains/DOMINIO.error.log`. |
| Cloudflare 521 | Que el proxy escuche en 80/443, firewall y A/AAAA correctos. |
| Cloudflare 526 | Certificado del proxy válido para el nombre visitado y cadena correcta. |
| Let's Encrypt 403/404 | DNS/AAAA, puerto 80, WAF y ruta de validación. No activar Force SSL antes de tener HTTPS funcional. |
| Bucle de redirecciones | Full (strict), URL HTTPS de la aplicación y confianza de `X-Forwarded-Proto` en el origen. |
| robots.txt incorrecto | Plantilla `rp` seleccionada, archivo del origen y caché externa de Cloudflare. |
| Todos tienen la IP del proxy | Configuración de proxies confiables en el servidor final. |

## Proteger el origen

Si administras el servidor final, restringe los puertos web para aceptar al proxy y a los servicios expresamente necesarios. Conserva acceso administrativo y una vía de renovación de certificados. En hosting compartido solicita al proveedor las restricciones y la configuración de IP real que permita.

Un reverse proxy no elimina el historial DNS ni las filtraciones por correo, subdominios, IPv6 o la propia aplicación; tampoco añade por sí mismo protección DDoS. Cambiar el puerto del origen no reemplaza el firewall. Una VPN entre servidores puede añadirse en una guía avanzada.

## Restaurar o actualizar

Para revertir una preparación **antes de agregar dominios**:

```bash
python3 proxy.py restore /root/hestia-reverse-proxy-backups/FECHA
python3 proxy.py restore /root/hestia-reverse-proxy-backups/FECHA --apply
```

Usa la ruta exacta mostrada al instalar. Antes de restaurar, reasigna admin al paquete default desde Hestia. Si solo existe el hostname inicial, añade `--allow-setup-domain proxy.tudominio.com` a restore (sustituye ese nombre). La restauración rechaza cambios posteriores para no pisarlos y conserva los archivos retirados. Con dominios activos, se requiere una migración por dominio con respaldo; no ejecutes esta limpieza.

Para obtener plantillas sin instalar ni limpiar nada:

```bash
python3 proxy.py render --origin 203.0.113.10 --output ./generadas
```

El directorio debe ser nuevo. Las plantillas de esta revisión usan `%proxy_port%` y `%proxy_ssl_port%` en `data/templates/web/nginx/`, con `PROXY_TEMPLATE=rp` y `WEB_TEMPLATE=default`. El barrido sigue siendo exclusivamente para un VPS nuevo. En instalaciones existentes, revisa y prueba una migración por dominio; no fuerces la preparación.

La revisión v1.0.0 utilizaba la modalidad Nginx sin Apache. No mezcles sus rutas ni paquetes con v1.1.0 y no ejecutes el barrido para actualizar un proxy con webs.

## Archivos y referencias

- `setup.py`: instalación asistida y barrido automático, en dos fases.
- `proxy.py`: simulación, preparación con limpieza y restauración.
- `templates/rp.tpl`, `templates/rp.stpl`: HTTP y HTTPS, con marcadores `@@...@@` que sustituye el script.
- `templates/rp-websocket.conf`: mapa utilizado por ambas plantillas.
- `tests/`: pruebas del script y del tráfico real de Nginx.
- [Extra: hacerlo con tu agente de IA](AI-PROMPTS.md), con tres prompts para revisar, ejecutar y comprobar.
- [Guía original de ForoBeta](https://forobeta.com/temas/crea-tu-propio-reverse-proxy-para-ocultar-la-ip-del-servidor-final-version-2024.1019680/).
- [Instalación oficial de Hestia](https://hestiacp.com/docs/introduction/getting-started).
- [Plantillas de Hestia](https://hestiacp.com/docs/server-administration/web-templates).
- [Proxy y TLS en Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
- [Cloudflare Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/).

Proyecto comunitario independiente para ForoBeta; no es un componente oficial de HestiaCP ni de ForoBeta. GPL-3.0-or-later.
