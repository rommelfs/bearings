"""Upgrade only a legacy public lab CA certificate; retain its existing private key."""

import subprocess


def ensure_ca_usage(cert, key):
    usage = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-ext", "keyUsage"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if "Certificate Sign" in usage:
        return False
    subject = subprocess.check_output(
        ["openssl", "x509", "-in", str(cert), "-noout", "-subject", "-nameopt", "RFC2253"], text=True
    ).strip()
    if subject != "subject=CN=Bearings isolated development CA":
        raise RuntimeError("A custom legacy CA needs operator maintenance; its identity was not changed")
    # Python 3.14/OpenSSL strict verification requires CA key usage. No TLS checks are weakened.
    candidate = cert.with_name("ca-strict.crt")
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-x509",
            "-key",
            str(key),
            "-out",
            str(candidate),
            "-days",
            "3650",
            "-subj",
            "/CN=Bearings isolated development CA",
            "-sha256",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
        ],
        check=True,
        capture_output=True,
    )
    old_key = subprocess.check_output(["openssl", "x509", "-in", str(cert), "-noout", "-pubkey"])
    new_key = subprocess.check_output(["openssl", "x509", "-in", str(candidate), "-noout", "-pubkey"])
    if old_key != new_key:
        candidate.unlink()
        raise RuntimeError("Refusing to replace a lab CA identity")
    backup = cert.with_name("ca-before-strict.crt")
    if not backup.exists():
        backup.write_bytes(cert.read_bytes())
        backup.chmod(0o644)
    candidate.replace(cert)
    cert.chmod(0o644)
    return True
