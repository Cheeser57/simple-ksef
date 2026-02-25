import sqlite3
import threading
import time

DEFULT_NAME = "invoices"

class Database:
    def __init__(self, file_path: str = "database.db", drop_tables: bool = False, table_names: str | list[str] | None = None):
        # allow using the connection from different threads (Streamlit may run callbacks)
        # set a generous timeout to wait for locks
        self.con = sqlite3.connect(file_path, check_same_thread=False, timeout=30.0)
        self.cur = self.con.cursor()
        # simple lock to serialize DB operations
        self.lock = threading.Lock()

        # normalize ids to list of strings
        if table_names is None:
            self.ids = [DEFULT_NAME]
        elif isinstance(table_names, str):
            self.ids = [self._table_name(table_names, allow_new=True)]
        else:
            self.ids = [self._table_name(id, allow_new=True) for id in table_names]

        if drop_tables: self.__drop_tables()
        self.__create_tables()

        # set WAL journal mode to reduce writer contention
        try:
            with self.lock:
                self.cur.execute("PRAGMA journal_mode=WAL;")
                self.cur.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass # non-fatal if pragmas can't be set


    def __create_tables(self):
        create_invoice_table = """
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ksef CHAR(35) NOT NULL,
            invoice_number VARCHAR(128) NOT NULL,
            invoice_date DATE NOT NULL,
            buyer_name VARCHAR(255) NOT NULL,
            buyer_id VARCHAR(50) NOT NULL,
            seller_name VARCHAR(255) NOT NULL,
            seller_nip CHAR(10) NOT NULL,
            net_amount DECIMAL(16, 2) NOT NULL,
            gross_amount DECIMAL(16, 2) NOT NULL,
            vat_amount DECIMAL(16, 2) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            subject VARCHAR(20) NOT NULL,
            type VARCHAR(10) NOT NULL,
            system_code VARCHAR(10),
            is_paid BOOLEAN DEFAULT FALSE
        );  
        """
        with self.lock:
            for id in self.ids:
                self.cur.execute(create_invoice_table.format(table=id))


    def __drop_tables(self):
        with self.lock:
            for id in self.ids:
                drop_invoice_table = f"DROP TABLE IF EXISTS {id};"
                self.cur.execute(drop_invoice_table)

    def _table_name(self, name: str, allow_new: bool = False) -> str:
        """Return a safe table name for given name. Raises ValueError if subject not configured."""
        if name is None:
            raise ValueError("subject must be provided to resolve table name")
        key = str(name)
        if not allow_new and key not in self.ids:
            raise ValueError(f"Unknown subject/table id: {key}")
   
        # sanitize: keep alnum and underscore
        safe = ''.join(c if (c.isalnum() or c == '_') else '_' for c in key)
        return f"{safe}"


    def insert_invoice(self, invoice_data, subject, table=DEFULT_NAME):
        table = self._table_name(table)
        insert_query = f"""
        INSERT INTO {table} (
            ksef, invoice_number, invoice_date, buyer_name, buyer_id,
            seller_name, seller_nip, net_amount, gross_amount, vat_amount,
            currency, subject, type, system_code, is_paid
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        buyer = invoice_data.get('buyer', {})
        seller = invoice_data.get('seller', {})

        # Safely extract buyer_id from nested dictionary
        buyer_id = None
        if buyer and buyer.get('identifier'):
            buyer_id = buyer['identifier'].get('value')

        # Safely extract system_code from nested dictionary
        system_code = None
        if invoice_data.get('formCode'):
            system_code = invoice_data['formCode'].get('systemCode')

        # try insert with retries on 'database is locked'
        attempts = 10
        delay = 0.1
        for attempt in range(attempts):
            try:
                with self.lock:
                    self.cur.execute(insert_query, (
                        invoice_data.get('ksefNumber'),
                        invoice_data.get('invoiceNumber'),
                        invoice_data.get('issueDate'),
                        buyer.get('name'),
                        buyer_id,
                        seller.get('name'),
                        seller.get('nip'),
                        invoice_data.get('netAmount'),
                        invoice_data.get('grossAmount'),
                        invoice_data.get('vatAmount'),
                        invoice_data.get('currency'),
                        subject,
                        invoice_data.get('invoiceType'),
                        system_code,
                        False,  # is_paid default to False
                    ))
                break
            except Exception as e:
                if 'database is locked' in str(e).lower() and attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        else:
            if attempt <= 0:
                raise Exception("Failed to insert invoice due to database locks.")

    def invoice_exists(self, ksef_number, subject, table=DEFULT_NAME):
        """Check if invoice with given ksef_number already exists in database."""
        table = self._table_name(table)
        query = f"SELECT 1 FROM {table} WHERE ksef = ? AND subject = ? LIMIT 1;"
        with self.lock:
            self.cur.execute(query, (ksef_number, subject))
            return self.cur.fetchone() is not None


    def commit(self):
        # commit with retry on lock
        attempts = 5
        delay = 0.1
        for attempt in range(attempts):
            try:
                with self.lock:
                    self.con.commit()
                break
            except sqlite3.OperationalError as e:
                if 'database is locked' in str(e).lower() and attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise


    def fetch(self, query, params=()):
        with self.lock:
            self.cur.execute(query, params)
            return self.cur.fetchall()


    def get_unique_sellers(self, subject, table=DEFULT_NAME):
        """Get list of unique seller names for given subject."""
        table = self._table_name(table)
        query = f"SELECT DISTINCT seller_name FROM {table} WHERE subject = ? ORDER BY seller_name ASC"
        with self.lock:
            self.cur.execute(query, (subject,))
            rows = self.cur.fetchall()
        return [row[0] for row in rows if row[0] is not None]

    def query_raw_with_filters(self, subject, date_from=None, date_to=None, price_min=None, price_max=None, only_paid=False, seller_name=None, invoice_type=None, table=DEFULT_NAME):
        """Return raw invoice rows (dicts) without formatting. Use when caller will format/present data."""
        table = self._table_name(table)
        query = f"""
        SELECT ksef, subject, invoice_date, invoice_number, buyer_name, seller_name, type, net_amount, gross_amount, currency, is_paid
        FROM {table}
        WHERE subject = ?
        """
        params = [subject]

        if date_from:
            query += " AND invoice_date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND invoice_date <= ?"
            params.append(date_to)
        if price_min is not None:
            query += " AND gross_amount >= ?"
            params.append(price_min)
        if price_max is not None:
            query += " AND gross_amount <= ?"
            params.append(price_max)
        if only_paid:
            query += " AND is_paid = 1"
        if seller_name:
            query += " AND seller_name = ?"
            params.append(seller_name)
        if invoice_type and invoice_type != "Wszystkie":
            query += " AND type = ?"
            params.append(invoice_type)

        query += " ORDER BY invoice_date ASC"

        with self.lock:
            self.cur.execute(query, params)
            rows = self.cur.fetchall()
            columns = [d[0] for d in self.cur.description] if self.cur.description else []
            result = [dict(zip(columns, r)) for r in rows]
        return result

    def update_paid_status(self, ksef_number, subject, is_paid, table=DEFULT_NAME):
        """Update the is_paid status for a given invoice."""
        table = self._table_name(table)
        query = f"UPDATE {table} SET is_paid = ? WHERE ksef = ? AND subject = ?;"
        try:
            with self.lock:
                self.cur.execute(query, (is_paid, ksef_number, subject))
                self.con.commit()
            return True
        except Exception as e:
            print(f"Error updating paid status for {ksef_number}: {e}")
            return False


