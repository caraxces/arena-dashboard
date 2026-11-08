#!/usr/bin/env python3
"""Mã hoá payload đầy đủ bằng AES-256-GCM, khoá dẫn xuất từ mã truy cập (PBKDF2)."""
import base64, hashlib, json, os, sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITER = 600000

def derive(code, salt):
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt, ITER, 32)

def encrypt(code, plaintext_bytes):
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(derive(code, salt)).encrypt(iv, plaintext_bytes, None)
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITER,
            "salt": base64.b64encode(salt).decode(),
            "iv": base64.b64encode(iv).decode(),
            "ct": base64.b64encode(ct).decode()}

if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("Dùng: python3 crypt.py <CODE> <data.json> <out.enc.json>")
    code, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    raw = open(src, "rb").read()
    blob = encrypt(code, raw)
    open(dst, "w").write(json.dumps(blob, separators=(",", ":")))
    print(f"→ {dst} ({os.path.getsize(dst)/1024:.0f} KB) · nguồn {len(raw)/1024:.0f} KB · PBKDF2 {ITER} vòng")
    # tự kiểm: giải mã lại
    b = json.load(open(dst))
    k = derive(code, base64.b64decode(b["salt"]))
    back = AESGCM(k).decrypt(base64.b64decode(b["iv"]), base64.b64decode(b["ct"]), None)
    assert back == raw, "giải mã không khớp"
    print("   tự kiểm giải mã: khớp")
    try:
        AESGCM(derive(code + "x", base64.b64decode(b["salt"]))).decrypt(
            base64.b64decode(b["iv"]), base64.b64decode(b["ct"]), None)
        print("   !! mã sai vẫn giải được — SAI")
    except Exception:
        print("   mã sai bị từ chối: đúng")
