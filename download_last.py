from authentication.token import start_session
import requests

BASE = "https://api.ksef.mf.gov.pl/v2"
# BASE = "https://api-test.ksef.mf.gov.pl/v2"

tokenfilename = "secret.json"
sessionFilename = "session.json"

def download_metadata(BASE, auth_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer "+str(auth_token),
    }
    body = {
        "subjectType": "Subject2",
        "dateRange": {
            "dateType": "PermanentStorage",
            "from": "2026-01-01T01:22:13+00:00",
            "to": "2026-03-01T01:24:13+00:00"
        },
    }
    meta_list = requests.post(
        BASE+"/invoices/query/metadata",    
        headers=headers,
        json=body
    )
    print("\nMetadata:")
    print("Status code:",meta_list.status_code)
    if meta_list.status_code != 200:
        print(meta_list.text)
        return []
    return meta_list.json().get("invoices")

def download_invoice(BASE, auth_token, ksef_number):
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
    save_path = f"invoices/invoice_{ksef_number}.xml"
    with open(save_path, "wb") as f:
        f.write(invoice.content)

if __name__ == "__main__":
    session = start_session(BASE, tokenfilename, sessionFilename)
    auth_token = session.get("accessToken")

    invoices = download_metadata(BASE, auth_token)

    print("\nInvoices:")
    for invoice in invoices:
        print(invoice.get("invoiceNumber"), invoice.get("ksefNumber"))
        download_invoice(BASE, auth_token, invoice.get("ksefNumber"))

