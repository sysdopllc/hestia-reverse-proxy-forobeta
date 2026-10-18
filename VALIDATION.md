# Validación de v1.0.0

17 de octubre de 2026. Código de referencia de HestiaCP: 1.10.5. Pruebas ejecutadas en un entorno aislado; ningún servidor de producción fue modificado.

## Script: 8 pruebas aprobadas

- Rechazo de IP y nombre TLS no válidos.
- Simulación sin cambios en Hestia.
- Rechazo si ya existen dominios.
- Rechazo de origen igual a una IP del proxy.
- Preparación, preservación de `default`/`suspended`, paquete mediante CLI y restauración.
- Restauración automática tras un fallo de recarga simulado.
- Rechazo de restauración cuando los archivos cambiaron después.
- Rechazo de enlaces simbólicos inesperados.

Estas pruebas utilizan un árbol temporal y sustituyen las llamadas a Hestia/systemd; verifican las protecciones y transacciones del script, no el funcionamiento interno del panel.

```bash
sudo python3 -m unittest discover -s tests -v
```

## Tráfico real: 14 comprobaciones aprobadas

Nginx 1.28 en contenedor, origen HTTPS local con certificado de prueba, conexiones limitadas a loopback:

1. Sintaxis `nginx -t`.
2. `robots.txt` desde el origen por HTTP.
3. Sitemap desde el origen por HTTP.
4. Cabeceras, cookies y protección frente a IP falsificada por HTTP.
5. Ruta de challenge con la forma del include nativo de Hestia y bloqueo de `.env` por HTTP.
6. `robots.txt` desde el origen por HTTPS.
7. Sitemap desde el origen por HTTPS.
8. Cabeceras, cookies y protección frente a IP falsificada por HTTPS.
9. Challenge y bloqueo de `.env` por HTTPS.
10. Cuerpo POST conservado, superior a 64 KiB.
11. SNI del dominio y `www` observado en el origen.
12. Certificado de origen con nombre incorrecto rechazado con 502.
13. WebSocket: respuesta 101 y un frame de texto atravesando el proxy.
14. Recarga de Nginx y petición HTTPS posterior.

Requiere Podman, OpenSSL y Python 3. El contenedor se detiene al acabar; se conserva para inspección. No se monta ningún archivo de Hestia real.

```bash
python3 tests/integration.py --workdir ./lab-validacion
```

El directorio debe ser nuevo. Los certificados de prueba se generan localmente y no se publican.

## Límites pendientes de validar en un VPS de laboratorio

- Instalación completa de HestiaCP en Ubuntu 24.04.
- Crear usuario, dominio y asignar el paquete en el panel real.
- Emisión y renovación pública de Let's Encrypt.
- Regeneración y actualización de Hestia con dominios activos.
- Firewall del origen, Cloudflare, IPv6 público y aplicaciones específicas.

No se presentan las pruebas de contenedor como certificación de esos pasos. La guía incluye comprobaciones para cada instalación.
