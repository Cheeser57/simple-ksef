import requests

DEBUG = False



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
    status = auth.json().get("status")
    if(DEBUG): print("\nAuthorisation:")
    if(DEBUG): print(status.get("description"))
    if(DEBUG and status.get("details")): print(status.get("details"))
    return auth.status_code == 200

def get_access_token(BASE, auth_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer "+str(auth_token),
    }
    tokens = requests.post(f"{BASE}/auth/token/redeem", headers=headers)
    if(DEBUG): print("\nAccessToken:")
    if(DEBUG): print("Status code:",tokens.status_code)

    if(tokens.status_code != 200):
        print(tokens.text)
        return None, None, None
    
    accessToken = tokens.json().get("accessToken").get("token")
    refreshToken = tokens.json().get("refreshToken").get("token")
    validUntil = tokens.json().get("accessToken").get("validUntil")

    print("validUntil:", validUntil)
    return accessToken, refreshToken, validUntil

# pass
def refresh_access_token(BASE, refresh_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {refresh_token}"
    }
    tokens = requests.post(f"{BASE}/auth/token/refresh", headers=headers)
    if(DEBUG): print("\nRefreshed AccessToken:")
    if(DEBUG): print("Status code:",tokens.status_code)

    if(tokens.status_code != 200):
        print(tokens.text)
        return None, None, None
    
    accessToken = tokens.json().get("accessToken").get("token")
    refreshToken = tokens.json().get("refreshToken").get("token")
    validUntil = tokens.json().get("accessToken").get("validUntil")

    print("validUntil:", validUntil)
    return accessToken, refreshToken, validUntil