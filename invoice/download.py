import requests
import os
def download_metadata(BASE, auth_token, subject="Subject1", from_date="2026-01-01T00:00:00", to_date="2026-03-01T00:00:00"):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer "+str(auth_token),
    }
    body = {
        "subjectType": subject,
        "dateRange": {
            "dateType": "Issue",
            "from": from_date,
            "to": to_date
        },
    }
    meta_list = requests.post(
        BASE+"/invoices/query/metadata",    
        headers=headers,
        json=body
    )
    # print("\nMetadata:")
    # print("Status code:",meta_list.status_code)
    if meta_list.status_code == 429:
        print(meta_list.text)
        return None, meta_list.json().get("status").get("details")[0]
    elif meta_list.status_code != 200:
        print(meta_list.text)
        return None, f"Błąd pobierania metadanych: {meta_list.status_code}"
    return meta_list.json().get("invoices"), None

def download_invoice(BASE, auth_token, ksef_number, path="invoices"):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer "+str(auth_token),
    }

    invoice = requests.get(
        BASE+"/invoices/ksef/"+str(ksef_number),
        headers=headers,
    )

    if invoice.status_code != 200:
        print(invoice.text)
        return
    
    save_path = os.path.join(path, f"invoice_{ksef_number}.xml") 
    with open(save_path, "wb") as f:
        f.write(invoice.content)