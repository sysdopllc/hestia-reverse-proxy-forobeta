# Validación de v1.2.0

17 de Octubre de 2026. Se utilizó Ubuntu 24.04 LTS y el canal estable oficial de HestiaCP. El panel instalado mostró 1.10.5: es un dato del ejercicio, no una versión exigida por el tutorial.

## Ejercicio real en un VPS temporal

Se preparó un VPS SYSDOP Cloud One de 4 CPU, 4 GB de RAM y 128 GB, y un sitio temporal autorizado en un hosting cPanel externo. Los archivos de la aplicación permanecieron en ese hosting. Las capturas corresponden al ejercicio; las IP y credenciales están ocultas. La cuenta de demostración se activó para el laboratorio: las capturas no prueban un cobro ni una transacción Square.

Comprobaciones realizadas:

1. Instalación de Hestia mediante su Bash oficial, con Nginx + Apache/PHP-FPM y sin instalar firewall ni Fail2Ban. Reinicio real y servicios activos.
2. Barrido y restauración reales: 132 archivos comparados antes y después, sin diferencias; `nginx -t` correcto.
3. Preparación v1.2.0 y asignación nativa del paquete a admin. Alta del dominio en la interfaz de Hestia: `rp` apareció como plantilla de proxy automáticamente.
4. Emisión pública de Let's Encrypt para el panel, el dominio y su alias `www`.
5. Once comprobaciones de tráfico aprobadas inicialmente, después de reconstruir el dominio y después de reemitir su certificado frontal mediante la función nativa usada por la renovación:
   - Origen directo con certificado público válido.
   - Página real entregada a través del proxy.
   - HTTPS para dominio y `www`, también hasta el origen.
   - `robots.txt` y sitemap idénticos a los archivos del origen.
   - Sustitución de cabeceras de IP y protocolo falsificadas.
   - Formulario POST, atributos de cookie y recepción de la cookie en la siguiente petición.
   - Subida multipart de 64000 bytes con SHA256 idéntico.
   - HTTP frontal hacia HTTPS de origen antes de activar Force SSL; después, redirección HTTP a HTTPS sin bucle.
6. `v-rebuild-web-domain` conservó la plantilla y el sitio siguió pasando las pruebas. La reemisión nativa cambió realmente el certificado frontal y pasó nuevamente las pruebas.
7. Reinicio final por la API del proveedor: nuevo arranque, Hestia/Nginx/Apache activos y sintaxis Nginx correcta. La batería de tráfico anterior se ejecutó antes de este último reinicio.

Se verificaron ambos extremos HTTPS con confianza pública, sin omitir la validación del cliente ni la del upstream de Nginx. Para el vhost temporal del hosting externo se instaló una copia privada de un certificado nuevo del propio laboratorio. Esto no demuestra renovación automática en ese hosting: el tutorial exige conservar un mecanismo independiente para el certificado de origen.

## Script: 13 pruebas aprobadas

Las pruebas usan un árbol temporal y sustituyen las llamadas a Hestia/systemd. Comprueban validación de IP/SNI, simulación sin escrituras, rechazo de webs existentes, preservación de dependencias, barrido por nombre IP completo, transacción y rollback, cambios posteriores, enlaces simbólicos, excepción del hostname inicial y preparación después de una instalación oficial independiente del asistente antiguo.

```bash
sudo python3 -m unittest discover -s tests -v
```

No se presentan como prueba del comportamiento interno de Hestia.

## Nginx real: 14 comprobaciones en contenedor

Las plantillas se comprobaron con Nginx 1.28, origen HTTPS local y puertos limitados a loopback. Las pruebas cubren sintaxis, `robots.txt`, sitemap, cabeceras/cookies, challenge nativo, bloqueo de dotfiles, HTTP/HTTPS, POST superior a 64 KiB, SNI de dominio y alias, rechazo de certificado con nombre incorrecto, WebSocket con respuesta 101 y un frame de texto, recarga y petición posterior.

```bash
python3 tests/integration.py --workdir ./lab-validacion
```

Requiere Podman, OpenSSL y Python 3. El directorio debe ser nuevo. El contenedor se detiene al acabar; quedan artefactos locales para inspección.

## Límites

- No se probó una actualización futura de Hestia con sitios activos. Puede reponer plantillas estándar; no se recomienda programar purgas automáticas.
- No se probó Cloudflare con nube activa, IPv6 público, un firewall de origen ni una aplicación WebSocket en el hosting externo. La prueba WebSocket corresponde al contenedor.
- No se certificó inicio de sesión de un CMS concreto, tráfico elevado, streaming prolongado ni tamaños de subida distintos de los indicados.
- Reemitir el certificado frontal valida ese recorrido de ACME, pero no simula el paso de meses ni certifica una renovación futura. Revisa cron, DNS y acceso al challenge en tu entorno.
- Los hostnames de las capturas son temporales y se retiran al cerrar el laboratorio. No son servicios de demostración permanentes.

Los resultados corresponden a este ejercicio y a esta revisión. Cada instalación necesita comprobar su aplicación, DNS y mecanismo de renovación.
