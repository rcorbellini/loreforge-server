import base64
import hashlib
import hmac
import json
import time
import urllib.request
import urllib.error


def _b64url_encode(data: bytes) -> str:
    """Base64Url encoding without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(b64: str) -> bytes:
    """Base64Url decoding, automatically adding missing padding."""
    padding = b"=" * (4 - (len(b64) % 4))
    return base64.urlsafe_b64decode(b64 + padding.decode("ascii"))


def jwt_encode(payload: dict, secret: str) -> str:
    """Creates a JWT token with HS256 signature using Python stdlib.
    No expiration field ('exp') is added per spec 056 decisions.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    b64_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    b64_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    
    msg = f"{b64_header}.{b64_payload}".encode("utf-8")
    key = secret.encode("utf-8")
    
    sig = hmac.new(key, msg, hashlib.sha256).digest()
    b64_sig = _b64url_encode(sig)
    
    return f"{msg.decode('ascii')}.{b64_sig}"


def jwt_decode(token: str, secret: str) -> dict | None:
    """Decodes and verifies JWT signature. Returns payload dict or None if invalid."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
        
    b64_header, b64_payload, b64_sig = parts
    
    msg = f"{b64_header}.{b64_payload}".encode("utf-8")
    key = secret.encode("utf-8")
    
    expected_sig = hmac.new(key, msg, hashlib.sha256).digest()
    expected_b64_sig = _b64url_encode(expected_sig)
    
    # Constant-time comparison
    if not hmac.compare_digest(b64_sig, expected_b64_sig):
        return None
        
    try:
        payload_bytes = _b64url_decode(b64_payload)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None


def verify_google_token(id_token: str, client_id: str) -> dict | None:
    """Calls oauth2.googleapis.com/tokeninfo using urllib to verify Google token."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            
            # Check audience
            if data.get("aud") != client_id:
                return None
                
            return {
                "sub": f"google:{data.get('sub')}",
                "email": data.get("email"),
                "name": data.get("name"),
                "iat": int(time.time())
            }
    except Exception as e:
        return None


