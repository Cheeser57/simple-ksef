from authentication.token import start_session
from invoice.download import download_metadata, download_invoice
import requests
from db.sqlite import Database
BASE = "https://api.ksef.mf.gov.pl/v2"
# BASE = "https://api-test.ksef.mf.gov.pl/v2"

tokenfilename = "data/secret.json"
sessionFilename = "data/session.json"

if __name__ == "__main__":
    session = start_session(BASE, tokenfilename, sessionFilename)
    auth_token = session.get("accessToken")

    invoices, error = download_metadata(BASE, auth_token, subject="Subject3")

    if error:
        print(f"Error: {error}")
        exit(1)

    # db = Database("data/ksef.db", drop_tables=True)
    # print("\nInvoices:")
    for invoice in invoices:
        print(invoice.get("ksefNumber"), invoice.get("invoiceNumber"), invoice.get("issueDate"), invoice.get("invoiceType"))

    #     db.insert_invoice(invoice, subject="Subject3")
    # print(db.fetch("SELECT ksef, type FROM invoices"))