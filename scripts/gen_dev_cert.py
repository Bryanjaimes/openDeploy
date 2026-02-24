"""Generate a self-signed TLS certificate for local/LAN development.

Creates certs/key.pem + certs/cert.pem with SANs for localhost and
the machine's LAN IPs so mobile devices accept the camera API.
"""
import datetime
import ipaddress
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Generate RSA key
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "OpenDeploy Dev"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenDeploy"),
])

# SANs — add your LAN IPs here
sans = [
    x509.DNSName("localhost"),
    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    x509.IPAddress(ipaddress.IPv4Address("192.168.1.154")),
    x509.IPAddress(ipaddress.IPv4Address("192.168.1.153")),
]

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
    .add_extension(x509.SubjectAlternativeName(sans), critical=False)
    .sign(key, hashes.SHA256())
)

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "certs")
os.makedirs(out_dir, exist_ok=True)

key_path = os.path.join(out_dir, "key.pem")
cert_path = os.path.join(out_dir, "cert.pem")

with open(key_path, "wb") as f:
    f.write(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )

with open(cert_path, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print(f"✅ Created {key_path}")
print(f"✅ Created {cert_path}")
print(f"   Valid for 365 days, SANs: localhost, 127.0.0.1, 192.168.1.154, 192.168.1.153")
