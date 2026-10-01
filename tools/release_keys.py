"""Create a local release signing identity once; private material never enters a build."""
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
folder = Path(os.environ["LOCALAPPDATA"]) / "SmartFlowReleaseKeys"
folder.mkdir(exist_ok=True)
key_file = folder / "publisher.ed25519"
if key_file.exists():
    key = Ed25519PrivateKey.from_private_bytes(key_file.read_bytes())
else:
    key = Ed25519PrivateKey.generate()
    with key_file.open("xb") as stream:
        stream.write(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
(ROOT / "assets/update-public-key.txt").write_text(public, encoding="ascii")
print("Release public key prepared; private key excluded from project")
