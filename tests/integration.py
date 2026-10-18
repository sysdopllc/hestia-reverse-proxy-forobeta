#!/usr/bin/env python3
"""Real Nginx + HTTPS origin on loopback. Requires podman and openssl.
Artifacts are retained in --workdir; no production Hestia is used.
"""
import argparse
import base64
import hashlib
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
import ssl
import subprocess
import threading
import time

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('proxy', REPO / 'proxy.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def run(*args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True).stdout


class Origin(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == '/ws':
            assert self.headers.get('Upgrade', '').lower() == 'websocket'
            accept = base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key'] +
                                     '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            self.send_response(101)
            self.send_header('Upgrade', 'websocket')
            self.send_header('Connection', 'Upgrade')
            self.send_header('Sec-WebSocket-Accept', accept)
            self.end_headers()
            self.wfile.write(b'\x81\x02OK')
            self.wfile.flush()
            self.close_connection = True
            return
        if self.path == '/robots.txt':
            body = b'User-agent: *\nSitemap: https://site.test/sitemap.xml\n'
        elif self.path == '/sitemap.xml':
            body = b'<urlset><url><loc>https://site.test/</loc></url></urlset>'
        else:
            body = json.dumps(dict(self.headers)).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Set-Cookie', 'session=test; HttpOnly; Secure')
        self.send_header('Cache-Control', 'private, no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--image', default='docker.io/library/nginx:1.28-alpine')
    args = parser.parse_args()
    lab = args.workdir.resolve()
    lab.mkdir(parents=True, exist_ok=False, mode=0o700)
    run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-keyout', lab / 'key.pem', '-out', lab / 'cert.pem', '-subj', '/CN=site.test',
        '-addext', 'subjectAltName=DNS:site.test,DNS:www.site.test')
    (lab / 'key.pem').chmod(0o600)
    sni_names = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(lab / 'cert.pem', lab / 'key.pem')
    context.set_servername_callback(lambda _sock, name, _ctx: sni_names.append(name))
    origin = ThreadingHTTPServer(('127.0.0.1', 0), Origin)
    origin.socket = context.wrap_socket(origin.socket, server_side=True)
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    reservations = [socket.socket() for _ in range(2)]
    for reserve in reservations:
        reserve.bind(('127.0.0.1', 0))
    http_port, https_port = [r.getsockname()[1] for r in reservations]
    values = proxy.origin_values('192.0.2.10', origin.server_port, '$host')
    substitutions = {'192.0.2.10': '127.0.0.1', '%ip%': '127.0.0.1',
                     '%proxy_port%': str(http_port), '%proxy_ssl_port%': str(https_port),
                     '%domain_idn%': 'site.test', '%alias_idn%': 'www.site.test bad.test',
                     '%domain%': 'site.test', '%home%/%user%': '/lab',
                     '%ssl_pem%': '/lab/cert.pem', '%ssl_key%': '/lab/key.pem',
                     '/etc/ssl/certs/ca-certificates.crt': '/lab/cert.pem',
                     '/var/log/nginx/domains/': '/lab/'}
    for name, body in proxy.rendered(values).items():
        for key, value in substitutions.items():
            body = body.replace(key, value)
        (lab / name).write_text(body)
    includes = lab / 'conf/web/site.test'
    includes.mkdir(parents=True)
    challenge = 'location ~ "^/\\.well-known/acme-challenge/(.*)$" { default_type text/plain; return 200 "$1.TEST"; }\n'
    (includes / 'nginx.conf_letsencrypt').write_text(challenge)
    (includes / 'nginx.ssl.conf_letsencrypt').write_text(challenge)
    # A local robots.txt must never replace the upstream document.
    (lab / 'robots.txt').write_text('WRONG LOCAL ROBOTS')
    (lab / 'nginx.conf').write_text('pid /lab/nginx.pid;\nerror_log /lab/error.log info;\n'
        'events {}\nhttp {\nlog_format bytes "$bytes_sent";\n'
        'include /lab/rp-websocket.conf;\ninclude /lab/rp.tpl;\ninclude /lab/rp.stpl;\n}\n')
    name = 'hestia-rp-test-' + str(int(time.time()))
    for reserve in reservations:
        reserve.close()
    container = None
    checks = []
    try:
        container = run('podman', 'run', '-d', '--name', name, '--network=host',
                        '-v', str(lab) + ':/lab:Z', args.image,
                        'nginx', '-c', '/lab/nginx.conf', '-g', 'daemon off;').strip()
        for _ in range(50):
            try:
                with socket.create_connection(('127.0.0.1', http_port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.1)
        run('podman', 'exec', name, 'nginx', '-t', '-c', '/lab/nginx.conf')
        checks.append('nginx -t')

        def request(path, *, tls=False, host='site.test', method='GET', body=b'', headers=None):
            sock = socket.create_connection(('127.0.0.1', https_port if tls else http_port), timeout=5)
            if tls:
                client_context = ssl.create_default_context(cafile=str(lab / 'cert.pem'))
                sock = client_context.wrap_socket(sock, server_hostname='site.test')
            with sock:
                fields = {'Host': host, 'Connection': 'close', 'Content-Length': str(len(body))}
                fields.update(headers or {})
                data = f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in fields.items()) + '\r\n'
                sock.sendall(data.encode() + body)
                response = HTTPResponse(sock)
                response.begin()
                return response.status, dict(response.getheaders()), response.read()

        for tls in (False, True):
            for path, expected in (('/robots.txt', b'Sitemap:'), ('/sitemap.xml', b'<urlset>')):
                status, _, body = request(path, tls=tls)
                assert status == 200 and expected in body and b'WRONG LOCAL' not in body
                checks.append(('HTTPS' if tls else 'HTTP') + ' ' + path + ' from origin')
            status, headers, body = request('/', tls=tls, headers={
                'X-Forwarded-For': '6.6.6.6', 'X-Real-IP': '6.6.6.6',
                'CF-Connecting-IP': '6.6.6.6', 'Forwarded': 'for=6.6.6.6'})
            forwarded = json.loads(body)
            assert status == 200 and forwarded['Host'] == 'site.test'
            assert forwarded['X-Forwarded-Proto'] == ('https' if tls else 'http')
            assert forwarded['X-Forwarded-For'] == '127.0.0.1'
            assert forwarded['X-Real-IP'] == '127.0.0.1'
            assert forwarded['CF-Connecting-IP'] == '127.0.0.1'
            assert 'Forwarded' not in forwarded
            assert headers['Set-Cookie'].startswith('session=test')
            assert headers['Cache-Control'] == 'private, no-store'
            checks.append(('HTTPS' if tls else 'HTTP') + ' headers, cookies and spoof protection')
            assert request('/.env', tls=tls)[0] == 404
            assert request('/.well-known/acme-challenge/token', tls=tls)[2] == b'token.TEST'
            checks.append(('HTTPS' if tls else 'HTTP') + ' native Hestia challenge and dotfile rejection')
        payload = b'form-data=' + b'x' * 65536
        assert request('/upload', tls=True, method='POST', body=payload)[2] == payload
        checks.append('POST upload preserved')
        assert request('/', tls=True, host='www.site.test')[0] == 200
        assert 'site.test' in sni_names and 'www.site.test' in sni_names
        checks.append('SNI for main domain and www')
        assert request('/', tls=True, host='bad.test')[0] == 502
        checks.append('wrong upstream certificate name rejected')
        # Check the actual 101 response AND a WebSocket text frame through Nginx.
        with socket.create_connection(('127.0.0.1', http_port), timeout=5) as sock:
            sock.sendall(b'GET /ws HTTP/1.1\r\nHost: site.test\r\nUpgrade: websocket\r\n'
                         b'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
                         b'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n')  # gitleaks:allow Fixed protocol test nonce, not a credential.
            received = b''
            while b'\x81\x02OK' not in received:
                block = sock.recv(4096)
                if not block:
                    break
                received += block
            assert b'101 Switching Protocols' in received and b'\x81\x02OK' in received
        checks.append('WebSocket 101 plus text frame')
        run('podman', 'exec', name, 'nginx', '-s', 'reload', '-c', '/lab/nginx.conf')
        assert request('/robots.txt', tls=True)[0] == 200
        checks.append('Nginx reload and live HTTPS request')
        report = {'passed': len(checks), 'checks': checks, 'image': args.image,
                  'limits': 'No full Hestia installation, public ACME issuance or Hestia upgrade tested.'}
        (lab / 'result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        if container:
            run('podman', 'stop', '--time', '2', name)
        origin.shutdown()
        origin.server_close()


if __name__ == '__main__':
    main()
