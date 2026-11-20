"""Real Nginx dual-stack SNI/ACME checks in an owned network-none container.

Reproduces a fallback IPv6 certificate with the old IPv4-only vhosts. No public
DNS/service, host listener, certificate issuance or operational credentials.
"""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native", ROOT / "deploy/ubuntu24/ecosystem.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def run(args):
    return subprocess.run([str(arg) for arg in args], capture_output=True, check=True)


def main():
    name = "bearings-native-ipv6-" + uuid.uuid4().hex[:10]
    created = False
    with tempfile.TemporaryDirectory(prefix="bearings-native-ipv6-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        conf, cert, acme = root / "conf", root / "cert", root / "acme"
        for folder in (conf, cert, acme):
            folder.mkdir(mode=0o755)
            folder.chmod(0o755)
        challenge = acme / ".well-known/acme-challenge"
        challenge.mkdir(parents=True)
        (challenge / "probe").write_text("synthetic-dual-stack-readiness")
        (acme / ".well-known").chmod(0o755)
        challenge.chmod(0o755)
        (challenge / "probe").chmod(0o644)
        now = datetime.now(timezone.utc)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic native dual-stack CA")])
        ca = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        (cert / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        for prefix, hosts in (
            ("fullchain", list(native.HOSTS.values())),
            ("wrong", ["wrong.example.invalid"]),
        ):
            leafkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            leaf = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
                .issuer_name(subject)
                .public_key(leafkey.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1))
                .not_valid_after(now + timedelta(days=1))
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(host) for host in hosts]), critical=False
                )
                .sign(key, hashes.SHA256())
            )
            (cert / (prefix + ".pem")).write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
            filename = "privkey.pem" if prefix == "fullchain" else "wrong.key"
            (cert / filename).write_bytes(
                leafkey.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        (conf / "00-fallback.conf").write_text(
            "server { listen 443 ssl default_server; listen [::]:443 ssl default_server; "
            "server_name wrong.example.invalid; ssl_certificate /cert/wrong.pem; ssl_certificate_key /cert/wrong.key; return 421; }\n"
        )
        for service in native.HOSTS:
            legacy = (
                native.nginx(service, tls=True)
                .replace("listen [::]:80;", "")
                .replace("listen [::]:443 ssl;", "")
            )
            (conf / (service + ".conf")).write_text(legacy)
        try:
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--network",
                    "none",
                    "--sysctl",
                    "net.ipv6.conf.all.disable_ipv6=0",
                    "-v",
                    f"{conf}:/etc/nginx/conf.d:ro",
                    "-v",
                    f"{cert}:/cert:ro",
                    "-v",
                    f"{cert}:/etc/letsencrypt/live/bearings-ecosystem:ro",
                    "-v",
                    f"{acme}:/var/lib/letsencrypt:ro",
                    "nginx:1.28-alpine",
                ]
            )
            created = True

            def fetch(service, address, scheme="https"):
                port = "443" if scheme == "https" else "80"
                host = native.HOSTS[service]
                return subprocess.run(
                    [
                        "docker",
                        "exec",
                        name,
                        "curl",
                        "--noproxy",
                        "*",
                        "--cacert",
                        "/cert/ca.pem",
                        "--connect-timeout",
                        "2",
                        "--max-time",
                        "3",
                        "--fail",
                        "--silent",
                        "--show-error",
                        "--resolve",
                        f"{host}:{port}:{address}",
                        f"{scheme}://{host}/.well-known/acme-challenge/probe",
                    ],
                    capture_output=True,
                )

            for _ in range(60):
                legacy = fetch("sso", "[::1]")
                if legacy.returncode == 60:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Old IPv4-only vhosts did not reproduce IPv6 certificate failure")
            for service in native.HOSTS:
                (conf / (service + ".conf")).write_text(native.nginx(service, tls=True))
            run(["docker", "exec", name, "nginx", "-t"])
            run(["docker", "exec", name, "nginx", "-s", "reload"])
            for _ in range(60):
                if fetch("sso", "[::1]").returncode == 0:
                    break
                time.sleep(0.1)
            for service in native.HOSTS:
                for address in ("127.0.0.1", "[::1]"):
                    for scheme in ("https", "http"):
                        response = fetch(service, address, scheme)
                        assert response.returncode == 0, (
                            f"{service} {address} {scheme}: " + response.stderr.decode(errors="replace")
                        )
                        assert response.stdout == b"synthetic-dual-stack-readiness"
            print(
                "Reproduced IPv6 certificate mismatch; all three corrected vhosts pass verified IPv4/IPv6 TLS and HTTP ACME"
            )
        finally:
            if created:
                subprocess.run(["docker", "rm", "-fv", name], capture_output=True)


if __name__ == "__main__":
    main()
