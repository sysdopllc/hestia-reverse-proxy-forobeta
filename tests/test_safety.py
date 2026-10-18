import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('proxy', Path(__file__).resolve().parents[1] / 'proxy.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class Safety(unittest.TestCase):
    def setUp(self):
        # Keep temporary fixtures for inspection; no recursive deletion.
        self.root = Path(tempfile.mkdtemp(prefix='hestia-rp-test-'))
        self.hestia = self.root / 'hestia'
        self.templates = self.hestia / 'data/templates/web/nginx/php-fpm'
        self.packages = self.hestia / 'data/packages'
        self.state = self.root / 'state'
        self.backups = self.root / 'backups'
        self.map = self.root / 'nginx/rp-websocket.conf'
        self.patch = patch.multiple(proxy, HESTIA=self.hestia, TEMPLATES=self.templates,
                                    PACKAGES=self.packages, STATE=self.state,
                                    BACKUPS=self.backups, MAP=self.map)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        for path in (self.templates, self.packages, self.map.parent,
                     self.hestia / 'conf', self.hestia / 'data/users/admin'):
            path.mkdir(parents=True)
        (self.hestia / 'conf/hestia.conf').write_text("WEB_SYSTEM='nginx'\nPROXY_SYSTEM=''\n")
        (self.hestia / 'data/users/admin/user.conf').write_text(
            "PACKAGE='default'\nWEB_TEMPLATE='default'\n")
        for name in ('default.tpl', 'default.stpl', 'suspended.tpl', 'wordpress.tpl'):
            (self.templates / name).write_text('original ' + name)
        (self.packages / 'default.pkg').write_text(
            "WEB_TEMPLATE='default'\nBACKEND_TEMPLATE='default'\nBACKUPS='1'\n")
        (self.packages / 'unused.pkg').write_text('unused')
        self.domains = {}
        self.calls = []
        self.fail_reload = False
        self.runner = patch.object(proxy, 'run', self.run_command)
        self.runner.start()
        self.addCleanup(self.runner.stop)
        self.args = argparse.Namespace(origin='192.0.2.10', port=443, tls_name='$host', apply=False)

    def run_command(self, *args):
        args = [str(a) for a in args]
        self.calls.append(args)
        name = Path(args[0]).name
        if name == 'v-list-users':
            return json.dumps({'admin': {}})
        if name == 'v-list-web-domains':
            return json.dumps(self.domains)
        if name == 'v-list-sys-ips':
            return json.dumps({'192.0.2.20': {}})
        if name == 'v-add-user-package':
            (self.packages / 'reverse-proxy.pkg').write_text(Path(args[1]).read_text())
        if name == 'systemctl' and self.fail_reload:
            self.fail_reload = False
            raise RuntimeError('simulated reload failure')
        return ''

    def test_invalid_inputs(self):
        for value in ('127.0.0.1', '0.0.0.0', '169.254.1.1', '1.2.3.4;reboot', 'example.org'):
            with self.subTest(value=value), self.assertRaises((RuntimeError, ValueError)):
                proxy.origin_values(value, 443, '$host')
        with self.assertRaises(RuntimeError):
            proxy.origin_values('192.0.2.10', 443, 'host;bad')

    def test_dry_run_preserves_files(self):
        proxy.prepare(self.args)
        self.assertTrue((self.templates / 'wordpress.tpl').exists())
        self.assertFalse(self.map.exists())
        self.assertFalse(self.backups.exists())

    def test_existing_domain_blocks_all_changes(self):
        self.domains = {'live.example': {}}
        self.args.apply = True
        with self.assertRaisesRegex(RuntimeError, 'dominios existentes'):
            proxy.prepare(self.args)
        self.assertTrue((self.templates / 'wordpress.tpl').exists())
        self.assertFalse(self.map.exists())

    def test_loop_blocks_all_changes(self):
        self.args.origin = '192.0.2.20'
        self.args.apply = True
        with self.assertRaisesRegex(RuntimeError, 'bucle'):
            proxy.prepare(self.args)
        self.assertFalse(self.backups.exists())

    def test_apply_restore_and_native_package(self):
        self.args.apply = True
        proxy.prepare(self.args)
        state = json.loads((self.state / 'installed.json').read_text())
        backup = Path(state['backup'])
        self.assertFalse((self.templates / 'wordpress.tpl').exists())
        self.assertTrue((self.templates / 'suspended.tpl').exists())
        self.assertTrue((self.templates / 'default.tpl').exists())
        self.assertTrue(any(Path(c[0]).name == 'v-add-user-package' for c in self.calls))
        self.assertIn('proxy_ssl_verify on;', (self.templates / 'rp.stpl').read_text())
        with self.assertRaisesRegex(RuntimeError, 'Ya existe'):
            proxy.prepare(self.args)
        proxy.restore(argparse.Namespace(backup=backup, apply=True))
        self.assertEqual((self.templates / 'wordpress.tpl').read_text(), 'original wordpress.tpl')
        self.assertTrue((self.packages / 'unused.pkg').exists())
        self.assertFalse(self.map.exists())
        self.assertFalse((self.state / 'installed.json').exists())

    def test_failed_reload_rolls_back(self):
        self.args.apply = True
        self.fail_reload = True
        with self.assertRaisesRegex(RuntimeError, 'simulated reload failure'):
            proxy.prepare(self.args)
        self.assertTrue((self.templates / 'wordpress.tpl').exists())
        self.assertTrue((self.packages / 'unused.pkg').exists())
        self.assertFalse(self.map.exists())
        self.assertFalse((self.packages / 'reverse-proxy.pkg').exists())

    def test_restore_refuses_modified_files(self):
        self.args.apply = True
        proxy.prepare(self.args)
        state = json.loads((self.state / 'installed.json').read_text())
        self.map.write_text('a later legitimate change')
        with self.assertRaisesRegex(RuntimeError, 'cambios posteriores'):
            proxy.restore(argparse.Namespace(backup=Path(state['backup']), apply=True))
        self.assertEqual(self.map.read_text(), 'a later legitimate change')

    def test_symlink_blocks_cleanup(self):
        (self.templates / 'wordpress.tpl').rename(self.root / 'original.tpl')
        (self.templates / 'wordpress.tpl').symlink_to(self.root / 'original.tpl')
        self.args.apply = True
        with self.assertRaisesRegex(RuntimeError, 'ruta irregular'):
            proxy.prepare(self.args)
        self.assertFalse(self.backups.exists())


if __name__ == '__main__':
    unittest.main()
