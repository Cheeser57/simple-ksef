import requests
import json
import re
import base64
from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import PKCS1_OAEP
from datetime import datetime, timezone
import os

def start_session(BASE, secret_file, session_file):
    if not os.path.exists(secret_file):
        raise Exception(f"Nie znaleziono pliku {secret_file}")

    with open(secret_file, "r") as f:
        secret = json.load(f)
    
    if not os.path.exists(session_file):
        return authenticate_session(BASE, secret, session_file)
    
    with open(session_file, "r") as f:
        session = json.load(f)

        ts = datetime.fromisoformat(session.get("validUntil"))
        now = datetime.now(timezone.utc)
        if ts < now:
            print("Token wygasł. Uzyskiwanie nowego tokena...")
            return authenticate_session(BASE, secret, session_file)
            
        else:
            print("Token jest nadal ważny.")
            return session



def authenticate_session(BASE, secret, session_file):
    reference, auth_token = authenticate(BASE, secret)
    if(auth_check(BASE,reference, auth_token)):
        accessToken, refreshToken, validUntil  = getAccessToken(BASE, auth_token)
        new_session = {
            "accessToken": accessToken,
            "refreshToken": refreshToken,
            "validUntil": validUntil
        }
        with open(session_file, "w") as f:
            json.dump(new_session, f)
        return new_session

def authenticate(BASE, secret):
    # 1) Pobierz challenge
    r = requests.post(f"{BASE}/auth/challenge")
    print("Challenge status:", r.status_code)
    data = r.json()
    challenge_id = data.get("challenge")
    print("Challenge:", challenge_id)
    timestamp = data.get("timestampMs")

    # 2) Pobierz certyfikaty publiczne
    certs_resp = requests.get(f"{BASE}/security/public-key-certificates")
    certs_resp.raise_for_status()
    certs_data = certs_resp.json()

    # Znajdź certyfikat z usage KsefTokenEncryption
    pub_pem = None
    for cert in certs_data:
        usage = cert.get("usage", [])
        if "KsefTokenEncryption" in usage:
            pub_pem = cert.get("certificate")  # PEM w wersji base64 lub PEM
            break

    if not pub_pem:
        raise Exception("Nie znaleziono certyfikatu typu KsefTokenEncryption")

    # Jeśli certyfikat jest zakodowany w Base64 bez nagłówków PEM, dodaj nagłówki:
    if "BEGIN CERTIFICATE" not in pub_pem:
        # Dodaj nagłówki PEM
        pub_pem = "-----BEGIN CERTIFICATE-----\n" + pub_pem + "\n-----END CERTIFICATE-----"

    # print("Wybrany certyfikat KSeF:\n", pub_pem)


    # 3) Wyodrębnij klucz publiczny i szyfruj challenge
    pem_body = re.sub(r"-----.*?-----", "", pub_pem, flags=re.S)
    der_bytes = base64.b64decode(pem_body)

    key = RSA.import_key(der_bytes)
    cipher = PKCS1_OAEP.new(key, hashAlgo=SHA256)

    token_time = secret.get("token")+'|'+str(timestamp)

    encrypted = cipher.encrypt(token_time.encode("utf-8"))
    encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

    # print("Encrypted (base64):", encrypted_b64)

    # 3) Poprawne uwierzytelnienie
    body = {
        "challenge": challenge_id,
        "contextIdentifier": {
            "type": "Nip",
            "value": secret.get("NIP")
        },
        "encryptedToken": encrypted_b64
    }

    auth = requests.post(
        f"{BASE}/auth/ksef-token",
        json=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    )

    if auth.status_code != 202:
        raise Exception("Blad uwierzytelnienia")

    auth_token = auth.json().get("authenticationToken").get("token")
    reference = auth.json().get("referenceNumber")
    # print("AccessToken:", auth_token)
    
    return reference, auth_token

def auth_check(BASE, reference, auth_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer "+str(auth_token),
    }
    body = {
        "subjectType": "Subject1",
    }

    auth = requests.get(
        BASE+"/auth/"+str(reference),
        headers=headers,
        data=body
    )
    print("\nAuthorisation:")
    status = auth.json().get("status")
    print(status.get("description"))
    if(status.get("details")): print(status.get("details"))
    return auth.status_code == 200

def getAccessToken(BASE, auth_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer "+str(auth_token),
    }
    tokens = requests.post(f"{BASE}/auth/token/redeem", headers=headers)
    print("\nAccessToken:")
    print("Status code:",tokens.status_code)

    if(tokens.status_code != 200):
        print(tokens.text)
        return None, None
    
    accessToken = tokens.json().get("accessToken").get("token")
    refreshToken = tokens.json().get("refreshToken").get("token")
    validUntil = tokens.json().get("accessToken").get("validUntil")

    print("validUntil:", validUntil)
    return accessToken, refreshToken, validUntil