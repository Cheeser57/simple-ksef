import random
from datetime import datetime, timedelta
import uuid

INVOICE_TYPES = ["Vat", "Zal", "Kor", "Roz", "Upr"]
SELLERS = [
    {"name": "Tech Fakers Inc.", "nip": "1234567890"},
    {"name": "Mock Data Solutions", "nip": "0987654321"},
    {"name": "Phantom Goods Co.", "nip": "1122334455"},
    {"name": "TestCorp Ltd.", "nip": "5544332211"},
]
BUYERS = [
    {"name": "Real Client LLC", "identifier": {"value": "9876543210"}},
    {"name": "Sample Customer", "identifier": {"value": "0123456789"}},
    {"name": "Generic Buyer", "identifier": {"value": "5432109876"}},
]

def generate_fake_invoices(subject, num_invoices=50):
    """Generates a list of fake invoice dictionaries for a given subject."""
    invoices = []
    today = datetime.now()
    for _ in range(num_invoices):
        invoice_type = random.choice(INVOICE_TYPES)
        net = round(random.uniform(10, 2000), 2)
        vat_rate = 0.23
        
        # Corrections ('Kor') can have 0 or negative values
        if invoice_type == "Kor":
            if random.random() < 0.5: # 50% chance of being negative
                net = -net
            else: # Sometimes a correction is just to zero
                if random.random() < 0.2:
                    net = 0

        vat = round(net * vat_rate, 2)
        gross = net + vat

        invoice = {
            "ksefNumber": f"FAKE-{uuid.uuid4()}",
            "invoiceNumber": f"FV/{random.randint(1, 100)}/{today.year}",
            "issueDate": (today - timedelta(days=random.randint(0, 30))).date(),
            "buyer": random.choice(BUYERS),
            "seller": random.choice(SELLERS),
            "netAmount": str(net),
            "grossAmount": str(gross),
            "vatAmount": str(vat),
            "currency": "PLN",
            "invoiceType": invoice_type,
            "formCode": {"systemCode": "FA (2)"},
        }
        invoices.append(invoice)
    
    return invoices, None
