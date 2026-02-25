from authentication.token import start_session, start_multi_session
from invoice.download import download_metadata, download_invoice
from db.sqlite import Database
from datetime import datetime, timedelta
import os
import json
import pandas as pd
import streamlit as st
from invoice.mock import generate_fake_invoices

DATA_FOLDER = "data"

BASE = "https://api.ksef.mf.gov.pl/v2"
START_DATE = "2026-01-01T00:00:00"
SUBJECTS = ["Subject1", "Subject2", "Subject3"]

# Display names for subjects (visual only)
SUBJECT_DISPLAY_NAMES = {
    "Subject1": "Sprzedawca",
    "Subject2": "Nabywca",
    "Subject3": "Podmiot 3"
} 

# For Debugging
USE_MOCK_DATA = True
RESET_DB_ON_START = False

# Default Streamlit page configuration for wide layout - must be in a function
def wide_space_default():
    st.set_page_config(layout="wide")
wide_space_default()

def data_path(filename):
    return os.path.join(DATA_FOLDER, filename)

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

def set_company(company):
    st.session_state.selected_company = company
    set_rerun_flag()

tokenPath = data_path("secret.json")
sessionPath = data_path("session.json")
downloadPath = data_path("downloads")

# last ksef extraction date
try:
    with open(sessionPath, 'r') as f:
        session_data = json.load(f)
        min_date = None
        for _, data in session_data.items():
            print("Checking token validUntil:", data.get("validUntil"))
            valid_until_str = data.get("validUntil")
            valid_until_date = datetime.fromisoformat(valid_until_str)
            if not min_date or valid_until_date < min_date:
                min_date = valid_until_date
            
        # Go back 30 days
        one_month_earlier = min_date - timedelta(days=31)
        begin_date = one_month_earlier.isoformat()

except (FileNotFoundError, json.JSONDecodeError):
    begin_date = START_DATE

end_date = (datetime.now() + timedelta(days=1)).isoformat()

# Load company names from secret file for sidebar filter
if "company_names" not in st.session_state:
    with open(tokenPath, 'r') as f:
        secret_data = json.load(f)
        st.session_state.company_names = list(secret_data.keys())

# initialize database (only once per Streamlit session)
if "db" not in st.session_state:
    # Do not drop tables on normal load
    st.session_state["db"] = Database(data_path("ksef.db"), drop_tables=RESET_DB_ON_START, table_names=st.session_state.company_names)
db = st.session_state["db"]

# ================
#region Streamlit sidebar
# UI and filtering logic
# ================
st.title("Faktury")

# Select company buttons, only if we have more than 1 company defined
if "selected_company" not in st.session_state:
    st.session_state.selected_company = st.session_state.company_names[0] if st.session_state.company_names else None

company = st.sidebar.segmented_control(label="Wybierz firmę", options=st.session_state.company_names, 
                                       default=st.session_state.selected_company, width="stretch", 
                                       key="company_selector", on_change=set_rerun_flag, format_func=lambda x: f"$\\textsf{{\\large {x}}}$")
if not company: company = st.session_state.selected_company
st.session_state.selected_company = company

# Sidebar with filters
st.sidebar.title("**Filtry**")
subject = st.sidebar.selectbox("Podmiot", SUBJECTS, index=1, key="subject_select", on_change=set_rerun_flag, format_func=lambda x: SUBJECT_DISPLAY_NAMES.get(x, x))

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
if company not in st.session_state[sellers_key]:
    st.session_state[sellers_key][company] = {}
if subject not in st.session_state[sellers_key][company]:
    # load sellers for this subject once and cache
    st.session_state[sellers_key][company][subject] = db.get_unique_sellers(subject, table=company)
sellers = st.session_state[sellers_key][company][subject]
sellers_with_all = ["Wszystkie"] + sellers
# use a subject-specific selectbox key to persist selection per subject
select_key = f"selected_seller_{subject}"
selected_seller = st.sidebar.selectbox("Wybierz nadawcę", sellers_with_all, index=0, key=select_key, on_change=set_rerun_flag)
seller_filter = None if selected_seller == "Wszystkie" else selected_seller

# st.sidebar.divider()

# filtr zakresu cen
st.sidebar.markdown("**Zakres Cen**")
col1, col2 = st.sidebar.columns(2)
with col1:
    price_min = st.number_input("Cena Min", value=None, step=100.0, on_change=set_rerun_flag, key="price_min_input")
with col2:
    price_max = st.number_input("Cena Max", value=None, step=100.0, on_change=set_rerun_flag, key="price_max_input")

st.sidebar.markdown("**Status Płatności**")
paid_status_options = ["Tylko opłacone", "Tylko nie opłacone"]
paid_status_selected = st.sidebar.segmented_control("", paid_status_options, selection_mode="single", key="paid_status_select", on_change=set_rerun_flag, width="stretch", label_visibility="collapsed")
show_only_paid = (paid_status_selected == "Tylko opłacone")

# filtr typu faktury
st.sidebar.markdown("**Typ faktury**")
invoice_type_options = ["Wszystkie", "Vat", "Zal", "Kor", "Roz", "Upr"]

# Display names for invoice types
INVOICE_TYPE_DISPLAY = {
    "Vat": "Vat",
    "Kor": "Korygująca",
    "Roz": "Rozliczeniowa",
    "Zal": "Zaliczkowa",
    "Upr": "Upr",
    "Wszystkie": "Wszystkie"
}

def format_invoice_type_display(val):
    return INVOICE_TYPE_DISPLAY.get(val, val)

invoice_type_selected = st.sidebar.selectbox("Wybierz typ", invoice_type_options, index=0, key="invoice_type_select", label_visibility="collapsed",
                                             on_change=set_rerun_flag, format_func=format_invoice_type_display)
invoice_type_filter = None if invoice_type_selected == "Wszystkie" else invoice_type_selected


def get_invoices_df(db, subject, date_from=None, date_to=None, price_min=None, price_max=None, only_paid=False, only_unpaid=False, seller_name=None, invoice_type=None, table=None):
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
        table=table
    )
    # If only_unpaid is True, filter the results client-side
    if only_unpaid and rows:
        rows = [row for row in rows if not row.get('is_paid', False)]
    
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

    # Format invoice type display
    if 'type' in df.columns:
        df['type'] = df['type'].apply(lambda v: INVOICE_TYPE_DISPLAY.get(v, v) if pd.notna(v) else v)

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

            if db.update_paid_status(ksef_id, subject_val, new_status, table=company):
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
    # Determine which paid/unpaid filter to apply
    only_paid = (paid_status_selected == "Tylko opłacone")
    only_unpaid = (paid_status_selected == "Tylko nie opłacone")
    
    st.session_state["invoices_df"] = get_invoices_df(
        db, subject, st.session_state.date_from, st.session_state.date_to,
        price_min, price_max, only_paid=only_paid, only_unpaid=only_unpaid, seller_name=seller_filter, invoice_type=invoice_type_filter, table=company
    )

placeholder = st.empty()
if not st.session_state["invoices_df"].empty:
    event = placeholder.dataframe(
        st.session_state["invoices_df"],
        key="invoice_dataframe",
        column_config={
            "KSeF": None,
            "Podmiot": None,
            "Nabywca": None,
            "NIP Sprzedawcy": None,
            "Opłacona": st.column_config.CheckboxColumn(required=True),
        },
        height=600,
        hide_index=True,
        on_select="rerun",
    )
    st.session_state["invoice_event"] = event
else:
    placeholder.info("Brak faktur z wybranymi filtrami.")

# region download/paid

def get_selected_row_indices():
    ev = st.session_state.get("invoice_event") or {}
    sel = ev.get("selection") or {}
    rows = sel.get("rows") or []
    return rows

# Bulk download button for selected rows
def _download_selected(company_name):
    df = st.session_state.get("invoices_df")
    if df is None or df.empty:
        st.info("Brak faktur do pobrania.")
        return
    # Determine selected rows from the invoice_event selection if available
    selected_indices = get_selected_row_indices()
    if not selected_indices:
        return

    rows_to_download = selected_indices

    try:
        session = start_session(BASE, tokenPath, sessionPath, company_name)
    except Exception as e:
        st.error("Nie udało się otworzyć sesji KSEF")
        st.error(str(e))
        return

    auth_token = session.get("accessToken")
    if not auth_token:
        st.error(f"Brak tokenu dla {company_name}; nie można pobrać faktur.")
        return

    downloaded = 0
    for ridx in rows_to_download:
        row = df.iloc[ridx]

        ksef_id = row.get("KSeF")
        os.makedirs(downloadPath, exist_ok=True)
        download_invoice(BASE, auth_token, ksef_id, path=downloadPath)
        downloaded += 1

    st.success(f"Pobrano {downloaded} faktur.")

def set_selected_paid(company_name, paid=True):
    df = st.session_state.get("invoices_df")
    if df is None or df.empty:
        st.info("Brak faktur do aktualizacji.")
        return

    selected_indices = get_selected_row_indices()
    if not selected_indices:
        sel = df[df.get("Wybrane") == True]
        if sel.empty:
            st.info("Brak zaznaczonych faktur.")
            return
        rows_to_update = sel.index.tolist()
    else:
        rows_to_update = selected_indices

    updated = 0
    for ridx in rows_to_update:
        try:
            row = df.iloc[ridx]
        except Exception:
            try:
                row = df.loc[ridx]
            except Exception:
                st.error(f"Nie można odczytać wiersza: {ridx}")
                continue

        ksef_id = row.get("KSeF") or row.get("ksef")
        subject_val = row.get("Podmiot") or row.get("subject")
        invoice_number = row.get("Numer Faktury") or row.get("invoice_number")
        if not ksef_id or not subject_val:
            st.error(f"Nieprawidłowe dane w wierszu {ridx}; pomijam.")
            continue

        if db.update_paid_status(ksef_id, subject_val, paid, table=company_name):
            # Update the session DataFrame view
            try:
                st.session_state["invoices_df"].loc[df.index[ridx], "Opłacona"] = paid
            except Exception:
                # fallback if index alignment differs
                try:
                    st.session_state["invoices_df"].iloc[ridx, st.session_state["invoices_df"].columns.get_loc("Opłacona")] = paid
                except Exception:
                    pass
            updated += 1
        else:
            st.error(f"Błąd podczas aktualizacji faktury {invoice_number}")

    if updated:
        st.success(f"Zaktualizowano status dla {updated} faktur.")
        st.session_state["rerun_needed"] = True
        st.rerun()
    else:
        st.info("Nie zaktualizowano żadnej faktury.")


col1, col2 = st.columns(2)
# Render bulk download button
with col1:
    if st.button("Pobierz zaznaczone", use_container_width=True):
        _download_selected(company)
with col2:
    if st.button("Ustaw opłacone", use_container_width=True):
        set_selected_paid(company, paid=True)

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


#   region KSeF 
#   authorisation & update logic

# ensure we only auto-update once per session run
if "updated_once" not in st.session_state:
    st.session_state["updated_once"] = False

def run_update():
    sessions = start_multi_session(BASE, tokenPath, sessionPath)
    inserted = 0
    for comp_name in sessions:
        auth_token = sessions[comp_name].get("accessToken")
        if not auth_token and not USE_MOCK_DATA:
            st.error(f"Brak tokenu autoryzacji dla {comp_name}; nie można aktualizować z KSeF.")
            continue
        
        for sub in SUBJECTS:
            if USE_MOCK_DATA:
                invoices, error = generate_fake_invoices(subject=sub)
            else:
                invoices, error = download_metadata(BASE, auth_token, subject=sub, from_date=begin_date, to_date=end_date)
            
            if error:
                st.warning(f"Błąd podczas pobierania faktur z KSeF dla {comp_name} podmiotu {sub}: {error}")
                continue
            print(f"Pobrano {len(invoices)} faktur z KSeF.")
            for invoice in invoices:
                ksef_number = invoice.get('ksefNumber')
                # Check if invoice already exists before inserting
                if not db.invoice_exists(ksef_number, sub, table=comp_name):
                    try:
                        db.insert_invoice(invoice, sub, table=comp_name)
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
    st.session_state[sellers_key][company][subject] = db.get_unique_sellers(sub, table=company)
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