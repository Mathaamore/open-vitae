"""Bounded HTTPS reads, with each redirect validated and DNS pinned at connection time."""
import http.client
import ipaddress
import json
import socket
import ssl
from urllib.parse import urljoin, urlsplit


def public_url(url):
    if not isinstance(url, str) or len(url) > 4096:
        raise ValueError('Adresse invalide.')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Une adresse HTTPS publique est nécessaire.')
    addresses = list(dict.fromkeys(result[4][0] for result in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError('Les adresses du réseau privé ne sont pas accessibles.')
    return parsed, addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=15, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def request(url, data=None, headers=None, limit=3_000_000):
    for _ in range(4):
        parsed, addresses = public_url(url)
        connection = PinnedHTTPS(parsed.hostname, addresses[0])
        try:
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            body = json.dumps(data).encode() if data is not None else None
            connection.request('POST' if body else 'GET', path, body=body,
                headers={'User-Agent': 'Open-Vitae/0.3.1 (local personal job search)', 'Accept': 'application/json,text/html',
                         **({'Content-Type': 'application/json'} if body else {}), **(headers or {})})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                if data is not None or headers:
                    raise ValueError('Redirection du fournisseur refusée.')
                url = urljoin(url, response.getheader('Location', ''))
                continue
            content = response.read(limit + 1)
            if len(content) > limit:
                raise ValueError('La réponse est trop volumineuse.')
            if response.status >= 400:
                if response.status in {401, 403}:
                    raise ValueError('Accès refusé. Vérifie la connexion ou la clé du fournisseur.')
                if response.status == 429:
                    raise ValueError('La limite du fournisseur est atteinte. Réessaie plus tard.')
                raise ValueError(f'Le service distant ne répond pas correctement ({response.status}).')
            return content, url
        finally:
            connection.close()
    raise ValueError('La page redirige trop de fois.')


def json_request(url, data=None, headers=None):
    try:
        return json.loads(request(url, data, headers)[0])
    except (OSError, http.client.HTTPException, UnicodeError, json.JSONDecodeError):
        raise ValueError('Le service distant est indisponible ou a renvoyé une réponse invalide.') from None
