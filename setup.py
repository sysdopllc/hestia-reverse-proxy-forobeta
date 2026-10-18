#!/usr/bin/env python3
"""Two-stage setup for a NEW dedicated VPS; the forum user pastes two commands."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

import proxy

HERE = Path(__file__).resolve().parent
PROFILE = Path('/root/hestia-reverse-proxy-setup.json')
OFFICIAL = 'https://raw.githubusercontent.com/hestiacp/hestiacp/release/install/hst-install.sh'


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def save(profile):
    with PROFILE.open('w') as stream:
        json.dump(profile, stream, indent=2)
    PROFILE.chmod(0o600)


def installer_arguments(script, hostname, email):
    return ['bash', str(script), '--interactive', 'no', '--username', 'admin',
            '--hostname', hostname, '--email', email, '--apache', 'yes',
            '--phpfpm', 'yes', '--multiphp', 'no', '--vsftpd', 'no', '--proftpd', 'no',
            '--named', 'no', '--mysql', 'no', '--postgresql', 'no', '--exim', 'no',
            '--dovecot', 'no', '--clamav', 'no', '--spamassassin', 'no',
            '--iptables', 'no', '--fail2ban', 'no', '--quota', 'no', '--api', 'no',
            '--port', '56464', '--lang', 'es']


def install():
    if Path('/usr/local/hestia').exists() or PROFILE.exists():
        raise RuntimeError('Ya existe Hestia o un registro de instalación. No se reinstala ni se fuerza.')
    os_release = Path('/etc/os-release').read_text()
    if not re.search(r'^ID=.?ubuntu.?$', os_release, re.M):
        raise RuntimeError('Esta receta usa un VPS Ubuntu LTS nuevo. Hestia valida qué versiones admite.')
    hostname = input('Hostname del proxy (ej. proxy.tudominio.com): ').strip().lower()
    email = input('Correo de administración: ').strip()
    origin = input('IP del servidor final: ').strip()
    proxy.origin_values(origin, 443, hostname)
    if hostname.count('.') < 2 or not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', email):
        raise RuntimeError('Hostname o correo no válido.')
    password = secrets.token_hex(20)
    profile = {'hostname': hostname, 'email': email, 'origin': origin,
               'admin_password': password, 'stage': 'installing'}
    save(profile)
    print('Instalando Hestia estable, SIN firewall ni Fail2Ban, como en la receta original.', flush=True)
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', NEEDRESTART_MODE='a')
    run('apt-get', 'update', env=env)
    run('apt-get', 'install', '-y', 'ca-certificates', 'curl', env=env)
    script = HERE / 'hst-install.sh'
    if script.exists():
        raise RuntimeError('Ya existe hst-install.sh; no se pisa un instalador anterior.')
    run('curl', '--proto', '=https', '--tlsv1.2', '-fSL', OFFICIAL, '-o', script)
    # Hestia asks for the omitted password via stdin even in noninteractive mode.
    # Keep it out of shell history and command arguments.
    run(*installer_arguments(script, hostname, email), input=password + '\n', text=True, env=env)
    profile['stage'] = 'installed'
    save(profile)
    print('\nInstalación completada. Reinicia el VPS como indica Hestia y reconecta por SSH.')
    print('Después ejecuta: python3 /root/hestia-reverse-proxy/setup.py finish')
    print('Usuario: admin. Datos de acceso guardados en ' + str(PROFILE) + ' (solo root).')


def finish():
    if PROFILE.is_symlink() or PROFILE.stat().st_uid != 0 or PROFILE.stat().st_mode & 0o077:
        raise RuntimeError('El registro de instalación debe pertenecer a root y tener modo 600.')
    profile = json.loads(PROFILE.read_text())
    if profile.get('stage') not in ('installed', 'prepared', 'ready'):
        raise RuntimeError('La instalación no terminó correctamente. Revisa su salida antes de continuar.')
    if profile['stage'] == 'installed':
        args = argparse.Namespace(origin=profile['origin'], port=443, tls_name='$host',
                                  apply=True, allow_setup_domain=profile['hostname'])
        # A completed preparation can survive an interruption before the profile is updated.
        marker = proxy.STATE / 'installed.json'
        if marker.exists():
            state = json.loads(marker.read_text())
            if not state.get('complete') or state.get('origin') != profile['origin']:
                raise RuntimeError('La preparación existente no coincide con esta instalación.')
            for path, expected in state.get('after_hashes', {}).items():
                if proxy.digest(Path(path)) != expected:
                    raise RuntimeError('Cambió un archivo de la preparación; revisa antes de continuar.')
        else:
            proxy.prepare(args)
        profile['stage'] = 'prepared'
        save(profile)
    if profile['stage'] == 'prepared':
        # This native command changes defaults for new domains; it does not rebuild existing ones.
        user_conf = proxy.HESTIA / 'data/users/admin/user.conf'
        backup = Path(json.loads((proxy.STATE / 'installed.json').read_text())['backup'])
        original_user = backup / 'admin-before-package.conf'
        if not original_user.exists():
            original_user.write_bytes(user_conf.read_bytes())
            original_user.chmod(0o600)
        if proxy.config(user_conf).get('PACKAGE') != 'reverse-proxy':
            run(proxy.HESTIA / 'bin/v-change-user-package', 'admin', 'reverse-proxy')
        profile['stage'] = 'ready'
        save(profile)
    run('nginx', '-t')
    print('\nBARRIDO TERMINADO. Plantillas y paquete configurados automáticamente.')
    print('Panel: https://' + profile['hostname'] + ':56464 | Usuario: admin')
    print('Contraseña del panel: ' + profile['admin_password'])
    print('Ahora entra a Web, agrega tu dominio, cambia DNS y emite SSL como muestra el tutorial.')
    print('El hostname de instalación se conserva para el panel; no es tu sitio final.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'finish'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Ejecuta este asistente como root en el VPS proxy nuevo.')
    os.umask(0o077)
    import fcntl
    with open('/run/lock/hestia-reverse-proxy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        install() if args.action == 'install' else finish()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
