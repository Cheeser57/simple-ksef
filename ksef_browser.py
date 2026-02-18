from authentication.token import start_session
from invoice.download import download_metadata, download_invoice
from db.sqlite import Database
from datetime import datetime, timezone, timedelta
import requests
import os
import json
import pandas as pd
import streamlit as st
from invoice.mock import generate_fake_invoices

DATA_FOLDER = "data"

BASE = "https://api.ksef.mf.gov.pl/v2"
START_DATE = "2026-01-01T00:00:00"
SUBJECTS = ["Subject1", "Subject2", "Subject3"] 
USE_MOCK_DATA = True

def data_path(filename):
    return os.path.join(DATA_FOLDER, filename)

def wide_space_default():
    st.set_page_config(layout="wide")
wide_space_default()

def set_rerun_flag():
    st.session_state["rerun_needed"] = True

def set_date_this_month():
    now = datetime.now()
    first_day_this_month = now.replace(day=1).date()
    last_day_this_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    st.session_state.date_from = first_day_this_month
    st.session_state.date_to = last_day_this_month
    set_rerun_flag()

def set_date_this_year():
    current_year = datetime.now().year
    st.session_state.date_from = datetime(current_year, 1, 1).date()
    st.session_state.date_to = datetime(current_year, 12, 31).date()
    set_rerun_flag()

tokenPath = data_path("secret.json")
sessionPath = data_path("session.json")

# ksef extraction date
try:
    with open(sessionPath, 'r') as f:
        session_data = json.load(f)
        valid_until_str = session_data.get("validUntil")
        valid_until_date = datetime.fromisoformat(valid_until_str)
            
        # Go back 30 days
        one_month_earlier = valid_until_date - timedelta(days=30)
        begin_date = one_month_earlier.isoformat()

except (FileNotFoundError, json.JSONDecodeError):
    begin_date = START_DATE

end_date = (datetime.now() + timedelta(days=1)).isoformat()

# initialize database (only once per Streamlit session)
if "db" not in st.session_state:
    # Do not drop tables on normal load
    st.session_state["db"] = Database(data_path("ksef.db"), drop_tables=False)
db = st.session_state["db"]

# Streamlit UI
st.title("Faktury")

# parametry wyboru
st.sidebar.title("**Filtry**")
subject = st.sidebar.selectbox("Podmiot", SUBJECTS, index=1, key="subject_select", on_change=set_rerun_flag)

# filtry dat z przyciskami szybkimi
st.sidebar.markdown("**Daty**")
col1, col2 = st.sidebar.columns(2)

# default to current month
now = datetime.now()
first_day_this_month = now.replace(day=1).date()
last_day_this_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)

if "date_from" not in st.session_state:
    st.session_state.date_from = first_day_this_month
if "date_to" not in st.session_state:
    st.session_state.date_to = last_day_this_month

with col1:
    st.date_input("Od", key="date_from", on_change=set_rerun_flag)
with col2:
    st.date_input("Do", key="date_to", on_change=set_rerun_flag)



# quick date buttons
col1, col2 = st.sidebar.columns(2)
with col1:
    st.button("Aktualny Miesiąc", use_container_width=True, on_click=set_date_this_month)
with col2:
    st.button("Aktualny Rok", use_container_width=True, on_click=set_date_this_year)


# st.sidebar.divider()

# filtr nadawcy (seller)
st.sidebar.markdown("**Nadawca (Nazwa Firmy)**")
sellers_key = "sellers_by_subject"
if sellers_key not in st.session_state:
    st.session_state[sellers_key] = {}
if subject not in st.session_state[sellers_key]:
    # load sellers for this subject once and cache
    st.session_state[sellers_key][subject] = db.get_unique_sellers(subject)
sellers = st.session_state[sellers_key][subject]
sellers_with_all = ["Wszystkie"] + sellers
# use a subject-specific selectbox key to persist selection per subject
select_key = f"selected_seller_{subject}"
selected_seller = st.sidebar.selectbox("Wybierz nadawcę", sellers_with_all, index=0, key=select_key, on_change=set_rerun_flag)
seller_filter = None if selected_seller == "Wszystkie" else selected_seller

# st.sidebar.divider()

# filtr zakresu cen
st.sidebar.markdown("**Zakres Cen**")
price_min = st.sidebar.number_input("Cena Min", value=None, step=100.0, on_change=set_rerun_flag, key="price_min_input")
price_max = st.sidebar.number_input("Cena Max", value=None, step=100.0, on_change=set_rerun_flag, key="price_max_input")

show_only_paid = st.sidebar.checkbox("Pokaż tylko opłacone faktury", value=False, on_change=set_rerun_flag, key="paid_checkbox")

# filtr typu faktury
st.sidebar.markdown("**Typ faktury**")
invoice_type_options = ["Wszystkie", "Vat", "Zal", "Kor", "Roz", "Upr"]
invoice_type_selected = st.sidebar.selectbox("Wybierz typ", invoice_type_options, index=0, key="invoice_type_select", on_change=set_rerun_flag)
invoice_type_filter = None if invoice_type_selected == "Wszystkie" else invoice_type_selected


def get_invoices_df(db, subject, date_from=None, date_to=None, price_min=None, price_max=None, only_paid=False, seller_name=None, invoice_type=None):
    """Fetch invoices from DB, format fields for display and return a DataFrame.

    - `header_map` is an optional dict mapping raw column names to desired display names.
    """
    rows = db.query_raw_with_filters(
        subject,
        date_from=date_from,
        date_to=date_to,
        price_min=price_min,
        price_max=price_max,
        only_paid=only_paid,
        seller_name=seller_name,
        invoice_type=invoice_type,
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Normalize/format fields similar to previous DB formatting
    if 'is_paid' in df.columns:
        df['is_paid'] = df['is_paid'].astype(bool)

    for amount_field in ['net_amount', 'gross_amount', 'vat_amount']:
        if amount_field in df.columns:
            # keep numeric for filtering, but create a formatted string column for display
            df[amount_field] = pd.to_numeric(df[amount_field], errors='coerce')
            df[amount_field] = df[amount_field].apply(lambda v: (f"{v:,.2f}".replace(',', ' ').replace('.', ',')) if pd.notna(v) else v)

    # Apply header rename if provided
    header_map = {
        "ksef": "KSeF",
        "subject": "Podmiot",
        "invoice_number": "Numer Faktury",
        "invoice_date": "Data Wystawienia",
        "buyer_name": "Nabywca",
        "buyer_id": "NIP Nabywcy",
        "seller_name": "Sprzedawca",
        "seller_nip": "NIP Sprzedawcy",
        "net_amount": "Kwota Netto",
        "gross_amount": "Kwota Brutto",
        "vat_amount": "Kwota VAT",
        "is_paid": "Opłacona",
        "type": "Typ",
        "currency": "Waluta",
    }
    df = df.rename(columns=header_map)

    return df


def process_edits():
    """Callback function to process edits from the data_editor."""
    # The data_editor state is a dictionary of changes, not a dataframe
    changes = st.session_state["invoice_editor"]
    original_df = st.session_state["invoices_df"]

    if not changes.get('edited_rows'):
        return

    for row_index, changed_columns in changes['edited_rows'].items():
        if "Opłacona" in changed_columns:
            new_status = changed_columns["Opłacona"]
            
            # Get the original row from the dataframe to find the ksef number and invoice number
            original_row = original_df.iloc[row_index] 
            
            ksef_id = original_row["KSeF"]
            subject_val = original_row["Podmiot"]
            invoice_number = original_row["Numer Faktury"]

            if db.update_paid_status(ksef_id, subject_val, new_status):
                st.toast(f"Zaktualizowano status faktury {invoice_number}")
                # Update the main dataframe in the session state to reflect the successful change
                # Use .loc with the actual index label to be safe
                st.session_state["invoices_df"].loc[original_df.index[row_index], "Opłacona"] = new_status
            else:
                st.toast(f"Błąd podczas aktualizacji faktury {invoice_number}")


# Corrected Data Loading and Display Logic
# =======================================
if "invoices_df" not in st.session_state or st.session_state.get("rerun_needed"):
    st.session_state["rerun_needed"] = False
    st.session_state["invoices_df"] = get_invoices_df(
        db, subject, st.session_state.date_from, st.session_state.date_to,
        price_min, price_max, show_only_paid, seller_filter, invoice_type_filter
    )

placeholder = st.empty()
if not st.session_state["invoices_df"].empty:
    placeholder.data_editor(
        st.session_state["invoices_df"],
        key="invoice_editor",
        on_change=process_edits,
        column_config={"KSeF": None, "Podmiot": None, "Opłacona": st.column_config.CheckboxColumn(required=True)},
        disabled=st.session_state["invoices_df"].columns.drop("Opłacona"),
        height=600
    )
else:
    placeholder.info("Brak faktur z wybranymi filtrami.")

# Status container - always visible
status_container = st.empty()

# Display the update status message if it exists from the last run
if "last_update_inserted_count" in st.session_state:
    inserted = st.session_state["last_update_inserted_count"]
    if inserted > 0:
        status_container.success(f"Aktualizacja zakończona, dodano {inserted} nowych faktur.")
    else:
        status_container.info("Brak nowych faktur do wstawienia.")
    # Clear the value so the message doesn't persist on the next rerun
    del st.session_state["last_update_inserted_count"]


#   KSeF
#   authorisation & update logic

# ensure we only auto-update once per session run
if "updated_once" not in st.session_state:
    st.session_state["updated_once"] = False

def run_update():
    session = start_session(BASE, tokenPath, sessionPath)
    auth_token = session.get("accessToken")
    if not auth_token and not USE_MOCK_DATA:
        st.error("Brak tokenu autoryzacji; nie można aktualizować z KSeF.")
        return 0
    inserted = 0
    for sub in SUBJECTS:
        if USE_MOCK_DATA:
            invoices, error = generate_fake_invoices(subject=sub)
        else:
            invoices, error = download_metadata(BASE, auth_token, subject=sub, from_date=begin_date, to_date=end_date)
        
        if error:
            st.warning(f"Błąd podczas pobierania faktur z KSeF dla podmiotu {sub}: {error}")
            continue
        print(f"Pobrano {len(invoices)} faktur z KSeF.")
        for invoice in invoices:
            ksef_number = invoice.get('ksefNumber')
            # Check if invoice already exists before inserting
            if not db.invoice_exists(ksef_number, sub):
                try:
                    db.insert_invoice(invoice, sub)
                    inserted += 1
                except Exception as e:
                    print(f"Błąd przy wstawianiu faktury {ksef_number}: {e}")
                    # Also print the problematic invoice data for debugging
                    print(f"Dane faktury powodującej błąd: {invoice}")
                    continue
        # commit after each subject to reduce lock contention
        try:
            db.commit()
        except Exception as e:
            print(f"Błąd przy komitowaniu po podmiocie {sub}: {e}")

        # update seller list
        st.session_state[sellers_key][sub] = db.get_unique_sellers(sub)
        # if we updated sellers for the currently selected subject, recreate the selectbox widget


    print(f"Wstawiono {inserted} nowych faktur do bazy.")
    return inserted

should_run = (not st.session_state["updated_once"])
if should_run:
    with st.spinner("Aktualizowanie z KSeF..."):
        inserted = run_update()
        
        # Store the number of inserted invoices to show a message after the rerun
        st.session_state["last_update_inserted_count"] = inserted

        # Flag that a refresh is needed after the KSeF update
        st.session_state["rerun_needed"] = True
        st.session_state["updated_once"] = True
        
        # Rerun to reload the dataframe with the new data and refresh the UI
        st.rerun()
