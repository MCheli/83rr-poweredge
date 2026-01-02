#!/usr/bin/env python3
"""
Test CSR generation to ensure it's valid
"""

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def test_csr_generation():
    """Test CSR generation and validate the output"""
    print("🔑 Testing CSR Generation")
    print("=" * 40)

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Create certificate subject
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Personal Infrastructure"),
        x509.NameAttribute(NameOID.COMMON_NAME, "*.markcheli.com"),
    ])

    # Create SAN extension
    hostnames = ["*.markcheli.com", "markcheli.com"]
    san_list = []
    for hostname in hostnames:
        san_list.append(x509.DNSName(hostname))

    # Generate CSR
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        subject
    ).add_extension(
        x509.SubjectAlternativeName(san_list),
        critical=False,
    ).sign(private_key, hashes.SHA256())

    # Serialize to PEM format
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    print("✅ CSR Generated Successfully")
    print(f"📏 CSR Length: {len(csr_pem)} characters")
    print(f"📏 Private Key Length: {len(private_key_pem)} characters")
    print()
    print("📄 CSR Content (first 200 chars):")
    print(csr_pem[:200] + "...")
    print()
    print("🔍 CSR Validation:")

    # Validate CSR
    try:
        # Try to parse it back
        csr_obj = x509.load_pem_x509_csr(csr_pem.encode('utf-8'))
        print("✅ CSR parses correctly")

        # Check subject
        subject_cn = None
        for attribute in csr_obj.subject:
            if attribute.oid == NameOID.COMMON_NAME:
                subject_cn = attribute.value
                break
        print(f"✅ Common Name: {subject_cn}")

        # Check SAN
        try:
            san_ext = csr_obj.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            san_names = [name.value for name in san_ext.value]
            print(f"✅ SAN Names: {', '.join(san_names)}")
        except x509.ExtensionNotFound:
            print("❌ No SAN extension found")

        print(f"✅ CSR is valid and ready for Cloudflare API")
        return csr_pem

    except Exception as e:
        print(f"❌ CSR validation failed: {str(e)}")
        return None

if __name__ == '__main__':
    test_csr_generation()