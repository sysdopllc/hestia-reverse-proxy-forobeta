#!/usr/bin/env python3
"""Prepare a NEW, dedicated Hestia Nginx server. No downloads or shell eval."""
import argparse
import datetime
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
HESTIA = Path('/usr/local/hestia')
STATE = Path('/var/lib/hestia-reverse-proxy')
BACKUPS = Path('/root/hestia-reverse-proxy-backups')
TEMPLATES = HESTIA / 'data/templates/web/nginx/php-fpm'
PACKAGES = HESTIA / 'data/packages'
MAP = Path('/etc/nginx/conf.d/rp-websocket.conf')
VERSION = '1.0.0'


def fail(message):
    raise RuntimeError(message)


def run(*args):
    return subprocess.run([str(a) for a in args], check=True, text=True,
                          stdout=subprocess.PIPE).stdout


def config(path):
    """Read plain Hestia KEY='value' data, never source/execute it."""
    values = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"([A-Z_0-9]+)='([^'\n]*)'", line.strip())
        if match:
            values[match[1]] = match[2]
    return values


def digest(path):
    if path.is_symlink():
        return 'link:' + os.readlink(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def origin_values(origin, port, tls_name):
    ip = ipaddress.ip_address(origin)
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback or ip.is_link_local:
        fail('Usa la IP del servidor final, no loopback, multicast o link-local.')
    if not 1 <= port <= 65535:
        fail('Puerto fuera del rango 1..65535.')
    if tls_name != '$host' and not re.fullmatch(
            r'(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+'
            r'[a-zA-Z]{2,63}', tls_name):
        fail('tls-name debe ser un nombre DNS, o se omite para usar el dominio visitado.')
    return {'@@ORIGIN@@': '[' + str(ip) + ']' if ip.version == 6 else str(ip),
            '@@PORT@@': str(port), '@@TLS_NAME@@': tls_name}


def rendered(values):
    result = {}
    for name in ('rp.tpl', 'rp.stpl', 'rp-websocket.conf'):
        text = (HERE / 'templates' / name).read_text()
        for key, value in values.items():
            text = text.replace(key, value)
        if '@@' in text:
            fail('Plantilla incompleta: ' + name)
        result[name] = text
    return result


def inspect_server():
    if os.geteuid() != 0:
        fail('Ejecuta prepare/restore como root.')
    conf = config(HESTIA / 'conf/hestia.conf')
    if conf.get('WEB_SYSTEM') != 'nginx' or conf.get('PROXY_SYSTEM', ''):
        fail('Esta instalación requiere Hestia Nginx + PHP-FPM, sin Apache.')
    users = json.loads(run(HESTIA / 'bin/v-list-users', 'json'))
    if not isinstance(users, dict) or not users:
        fail('No se pudo validar la lista de usuarios de Hestia.')
    kept_packages = {'default', 'system', 'reverse-proxy'}
    kept_templates = {'default', 'suspended', 'rp'}
    for user in users:
        domains = json.loads(run(HESTIA / 'bin/v-list-web-domains', user, 'json'))
        if not isinstance(domains, dict) or domains:
            fail('Hay dominios existentes. La limpieza solo sirve ANTES de agregar webs.')
        data = config(HESTIA / 'data/users' / user / 'user.conf')
        if not data.get('PACKAGE') or not data.get('WEB_TEMPLATE'):
            fail('No se pudieron leer las dependencias del usuario ' + user)
        kept_packages.add(data['PACKAGE'])
        kept_templates.add(data['WEB_TEMPLATE'])
    if not TEMPLATES.is_dir() or not PACKAGES.is_dir():
        fail('No se encuentran los directorios de plantillas/paquetes.')
    if not Path('/etc/ssl/certs/ca-certificates.crt').is_file():
        fail('Falta el almacén de certificados CA del sistema.')
    run('nginx', '-t')
    return kept_packages, kept_templates


def package_text():
    values = config(PACKAGES / 'default.pkg')
    if not {'WEB_TEMPLATE', 'BACKEND_TEMPLATE', 'BACKUPS'} <= values.keys():
        fail('default.pkg no tiene el formato esperado; no se reemplazará.')
    values.update(WEB_TEMPLATE='rp', PROXY_TEMPLATE='', DNS_TEMPLATE='',
                  WEB_DOMAINS='unlimited', WEB_ALIASES='unlimited', DNS_DOMAINS='0',
                  MAIL_DOMAINS='0', MAIL_ACCOUNTS='0', DATABASES='0', NS='',
                  SHELL='nologin')
    return ''.join(f"{key}='{value}'\n" for key, value in values.items())


def check_owned(path):
    """Never traverse a directory symlink to perform cleanup."""
    for item in (path, *path.parents):
        if item.is_symlink():
            fail('Ruta con enlace simbólico inesperado: ' + str(item))


def write_new(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(text)
    path.chmod(0o644)


def rollback(backup, manifest):
    """Move newly created files aside and restore quarantined originals."""
    aside = backup / ('reverted-' + datetime.datetime.now().strftime('%H%M%S%f'))
    for item in reversed(manifest['created']):
        target = Path(item)
        if target.exists() or target.is_symlink():
            destination = aside / target.relative_to('/')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(destination))
    for item in reversed(manifest['moved']):
        target = Path(item)
        saved = backup / 'originals' / target.relative_to('/')
        if saved.exists() or saved.is_symlink():
            if target.exists() or target.is_symlink():
                fail('No se sobrescribe un archivo aparecido durante rollback: ' + item)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(saved), str(target))
    run('nginx', '-t')
    run('systemctl', 'reload', 'nginx')


def prepare(args):
    values = origin_values(args.origin, args.port, args.tls_name)
    kept_packages, kept_templates = inspect_server()
    addresses = json.loads(run(HESTIA / 'bin/v-list-sys-ips', 'json'))
    if not isinstance(addresses, dict) or not addresses:
        fail('No se pudieron comprobar las IP del proxy.')
    if ipaddress.ip_address(args.origin) in {ipaddress.ip_address(ip) for ip in addresses}:
        fail('La IP de origen pertenece al proxy: eso crearía un bucle.')
    for directory in (TEMPLATES, PACKAGES, MAP.parent, STATE, BACKUPS):
        check_owned(directory)
    if (STATE / 'installed.json').exists():
        fail('Ya existe una instalación registrada. No se repite la purga; consulta README.')
    outputs = {TEMPLATES / 'rp.tpl': rendered(values)['rp.tpl'],
               TEMPLATES / 'rp.stpl': rendered(values)['rp.stpl'],
               MAP: rendered(values)['rp-websocket.conf']}
    pkg = PACKAGES / 'reverse-proxy.pkg'
    for target in (*outputs, pkg):
        if target.exists() or target.is_symlink():
            fail('El destino ya existe; no se pisa: ' + str(target))
    unused = sorted(p for p in TEMPLATES.iterdir()
                    if p.suffix in ('.tpl', '.stpl', '.sh') and p.stem not in kept_templates)
    unused += sorted(p for p in PACKAGES.glob('*.pkg') if p.stem not in kept_packages)
    for path in unused:
        if not path.is_file() or path.is_symlink():
            fail('No se apartará una ruta irregular: ' + str(path))
    package = package_text()
    print(json.dumps({'version': VERSION, 'origin': args.origin, 'port': args.port,
                      'tls_name': args.tls_name, 'quarantine': [str(p) for p in unused],
                      'create': [str(p) for p in (*outputs, pkg)],
                      'keep_packages': sorted(kept_packages),
                      'keep_templates': sorted(kept_templates)}, indent=2))
    if not args.apply:
        print('SIMULACIÓN: no se ha modificado Hestia. Añade --apply para aplicar.')
        return
    backup = BACKUPS / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    BACKUPS.chmod(0o700)
    manifest = {'version': VERSION, 'created': [], 'moved': [], 'origin': args.origin}
    journal = backup / 'manifest.json'

    def save():
        journal.write_text(json.dumps(manifest, indent=2))

    save()
    try:
        for source in unused:
            destination = backup / 'originals' / source.relative_to('/')
            destination.parent.mkdir(parents=True, exist_ok=True)
            manifest['moved'].append(str(source))
            save()
            shutil.move(str(source), str(destination))
        for path, text in outputs.items():
            manifest['created'].append(str(path))
            save()
            write_new(path, text)
        package_input = backup / 'reverse-proxy.pkg'
        package_input.write_text(package)
        manifest['created'].append(str(pkg))
        save()
        run(HESTIA / 'bin/v-add-user-package', package_input, 'reverse-proxy')
        run('nginx', '-t')
        run('systemctl', 'reload', 'nginx')
        manifest['after_hashes'] = {str(p): digest(p) for p in (*outputs, pkg)}
        manifest['complete'] = True
        save()
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        (STATE / 'installed.json').write_text(json.dumps({'backup': str(backup), **manifest}, indent=2))
    except Exception:
        rollback(backup, manifest)
        raise
    print('Preparación terminada. Respaldo: ' + str(backup))
    print('Crea un usuario con el paquete reverse-proxy y agrega sus dominios.')
    print('Todavía debes comprobar el sitio y emitir su certificado desde Hestia.')


def restore(args):
    inspect_server()
    backup = args.backup.resolve()
    if backup.parent != BACKUPS or not (backup / 'manifest.json').is_file():
        fail('El respaldo debe ser un directorio directo de ' + str(BACKUPS))
    manifest = json.loads((backup / 'manifest.json').read_text())
    state_file = STATE / 'installed.json'
    if not state_file.is_file() or json.loads(state_file.read_text()).get('backup') != str(backup):
        fail('El respaldo no corresponde a la instalación registrada.')
    for user in json.loads(run(HESTIA / 'bin/v-list-users', 'json')):
        data = config(HESTIA / 'data/users' / user / 'user.conf')
        if data.get('PACKAGE') == 'reverse-proxy' or data.get('WEB_TEMPLATE') == 'rp':
            fail('El usuario ' + user + ' usa reverse-proxy. Reasigna su paquete antes de restaurar.')
    for path, expected in manifest.get('after_hashes', {}).items():
        if digest(Path(path)) != expected:
            fail('Hay cambios posteriores en ' + path + '; requiere revisión manual.')
    if not manifest.get('complete') or not manifest.get('after_hashes'):
        fail('Instalación incompleta: revisa el manifiesto manualmente.')
    for item in manifest['moved']:
        target = Path(item)
        saved = backup / 'originals' / target.relative_to('/')
        if target.exists() or target.is_symlink() or not saved.is_file():
            fail('El respaldo o el destino cambió: ' + item)
    print('Restaurar: ' + str(backup))
    if args.apply:
        rollback(backup, manifest)
        shutil.move(str(state_file), str(backup / 'installed-restored.json'))
        print('Restaurado; archivos nuevos conservados dentro del respaldo.')
    else:
        print('SIMULACIÓN. Añade --apply para restaurar.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('render', 'prepare'):
        item = sub.add_parser(name)
        item.add_argument('--origin', required=True, help='IP del servidor final')
        item.add_argument('--port', type=int, default=443)
        item.add_argument('--tls-name', default='$host')
        if name == 'render':
            item.add_argument('--output', type=Path, required=True)
        else:
            item.add_argument('--apply', action='store_true')
    item = sub.add_parser('restore')
    item.add_argument('backup', type=Path)
    item.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.command == 'render':
        values = origin_values(args.origin, args.port, args.tls_name)
        if args.output.exists():
            fail('Usa un directorio de salida nuevo para no sobrescribir archivos.')
        args.output.mkdir(parents=True)
        for name, text in rendered(values).items():
            write_new(args.output / name, text)
        print('Plantillas generadas: ' + str(args.output))
    else:
        if os.geteuid() != 0:
            fail('Se requiere root.')
        with open('/run/lock/hestia-reverse-proxy.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            prepare(args) if args.command == 'prepare' else restore(args)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
