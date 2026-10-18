# Reverse proxy con HestiaCP para ForoBeta

Plantillas y preparación de un VPS dedicado al proxy. El contenido continúa en el servidor final; los visitantes se conectan a la IP del proxy.

```text
Visitante ── HTTPS ── [Cloudflare opcional] ── HTTPS ── VPS proxy ── HTTPS verificado ── Servidor final
```

Reemplazo del material del tutorial de 2024 cuyo repositorio original fue retirado. Este proyecto reconstruye su función; no es una copia recuperada del antiguo `default.pkg`.

**Alcance:** VPS nuevo con Ubuntu 24.04 LTS y HestiaCP en modo **Nginx + PHP-FPM, sin Apache**. Referencia revisada: HestiaCP 1.10.5. Hestia mantiene PHP-FPM como parte de esta modalidad; las plantillas `rp` no ejecutan PHP localmente. No desinstales paquetes base del panel.

**Validación:** 8 pruebas de seguridad/rollback del script y 14 comprobaciones contra Nginx real. No se ha probado una instalación completa de Hestia, su actualización ni una emisión/renovación pública de Let's Encrypt. Detalles en [VALIDATION.md](VALIDATION.md).

## 1. Antes de empezar

- Un VPS nuevo dedicado a este proxy, con acceso root y consola del proveedor.
- El dominio y `www` funcionando en el servidor final con un certificado HTTPS válido para ambos nombres. Si no usas `www`, no lo agregues.
- IP del proxy e IP del servidor final distintas. El origen debe aceptar conexiones desde el proxy.
- Un hostname propio para el panel, por ejemplo `proxy.tudominio.com`, cuyo DNS apunte al VPS proxy.
- Puertos 80/443 accesibles para las webs; SSH y 56464 según el acceso administrativo que necesites. Conserva firewall y Fail2Ban.

Prueba el origen ANTES de cambiar DNS, sustituyendo dominio e IP:

```bash
curl --resolve ejemplo.com:443:203.0.113.10 https://ejemplo.com/ -I
curl --resolve www.ejemplo.com:443:203.0.113.10 https://www.ejemplo.com/ -I
```

Las direcciones `203.0.113.10` y los dominios de ejemplo se sustituyen por los tuyos. No uses `-k` para esconder un certificado incorrecto.

## 2. Instalar Hestia

Ejecuta cada bloque solo si el anterior terminó bien. Este paso se hace en el VPS proxy, no en el servidor que aloja las webs.

```bash
apt-get update && apt-get install -y ca-certificates curl git python3
```

```bash
curl --proto '=https' --tlsv1.2 -fSL https://raw.githubusercontent.com/hestiacp/hestiacp/release/install/hst-install.sh -o hst-install.sh
```

Puedes revisar el instalador descargado antes de ejecutarlo. Los componentes elegidos son:

```bash
bash hst-install.sh --apache no --phpfpm yes --multiphp no \
  --vsftpd no --proftpd no --named no --mysql no --postgresql no \
  --exim no --dovecot no --clamav no --spamassassin no \
  --iptables yes --fail2ban yes --quota no --api no \
  --port 56464 --lang es
```

Sigue las preguntas del instalador, usa tu hostname real y guarda las credenciales. No se publica una contraseña universal ni se fuerza la instalación sobre un sistema ocupado. Si pide reiniciar, reinicia y vuelve a entrar por SSH.

El comando oficial descarga la versión estable disponible en ese momento. Antes de usar una versión posterior a la referencia revisada, consulta sus cambios y repite las comprobaciones de esta guía.

## 3. Descargar y preparar el proxy: incluye limpieza

Todavía no agregues dominios. Descarga esta versión del proyecto en una carpeta nueva:

```bash
git clone --branch v1.0.0 --depth 1 https://github.com/sysdopllc/hestia-reverse-proxy-forobeta.git /root/hestia-reverse-proxy
cd /root/hestia-reverse-proxy
```

Indica la IP del servidor final; no la IP del proxy:

```bash
read -r -p "IP del servidor final: " ORIGIN_IP
python3 proxy.py prepare --origin "$ORIGIN_IP"
```

Primero muestra el plan. Para aplicarlo:

```bash
python3 proxy.py prepare --origin "$ORIGIN_IP" --apply
```

**La limpieza sigue formando parte del tutorial.** Se apartan las plantillas web de aplicaciones y los paquetes de hosting que no estén en uso. Se conservan `default`, `suspended`, los paquetes de sistema y las dependencias de usuarios existentes. Se crean `rp.tpl`, `rp.stpl`, el mapa de WebSocket y el paquete `reverse-proxy` mediante la CLI de Hestia.

Todo lo retirado se mueve a `/root/hestia-reverse-proxy-backups/FECHA/`; no se borra. Se registra cada movimiento y los hashes de los archivos nuevos. Si falla la preparación, intenta restaurar los archivos y valida Nginx antes de recargarlo. Si también falla la restauración, el error queda visible y el respaldo permanece disponible.

Ya no se usan `rm -rf /etc/nginx/conf.d/0*` ni comodines similares: alcanzaban, entre otros, `0rtt-anti-replay.conf`, que contiene variables usadas por Hestia. Tampoco se elimina la línea global `Early-Data`. La plantilla HTTPS del proxy desactiva 0-RTT solo en sus propios dominios.

El script rechaza dominios existentes, destinos ocupados, enlaces simbólicos inesperados y una IP de origen que pertenezca al proxy según Hestia. No es un migrador de servidores de producción.

## 4. Usuario, dominio y DNS

1. Entra a Hestia: `https://IP_DEL_PROXY:56464`. Comprueba la identidad del panel mediante la consola/datos de tu proveedor; configura su hostname y certificado.
2. Como administrador, crea un usuario para tus webs y selecciona el paquete **reverse-proxy**. No alojes las webs en el usuario administrador.
3. Entra como ese usuario y agrega tu dominio. Agrega `www` como alias solo si lo usarás. No crees DNS ni correo en este VPS.
4. En opciones avanzadas confirma que la **plantilla web es `rp`**.
5. En tu proveedor DNS, apunta los registros A del dominio y `www` a la IP del proxy. Revisa los AAAA: no deben conservar la IPv6 del servidor final. Esta receta configura el listener de la IP seleccionada por Hestia; no publiques AAAA hasta comprobar el servicio por IPv6.

Para un dominio existente en un usuario nuevo, la selección se puede hacer con la CLI nativa:

```bash
/usr/local/hestia/bin/v-change-web-domain-tpl USUARIO ejemplo.com rp no
nginx -t && systemctl reload nginx
```

Sustituye `USUARIO` y `ejemplo.com`. No cambies manualmente los archivos generados bajo `conf/web`: Hestia los reconstruye.

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

Usa la ruta exacta mostrada al instalar. Si ya creaste un usuario con `reverse-proxy`, reasígnalo primero a un paquete compatible desde Hestia. La restauración rechaza cambios posteriores para no pisarlos y conserva los archivos retirados. Con dominios activos, se requiere una migración por dominio con respaldo; no ejecutes esta limpieza.

Para obtener plantillas sin instalar ni limpiar nada:

```bash
python3 proxy.py render --origin 203.0.113.10 --output ./generadas
```

El directorio debe ser nuevo. Para una instalación antigua con Apache, estas plantillas **no se copian directamente**: cambian los puertos, el directorio y la CLI de asignación. Prepara un proxy nuevo y migra DNS cuando lo hayas validado, o adapta y prueba una migración específica. No fuerces la preparación.

## Archivos y referencias

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
