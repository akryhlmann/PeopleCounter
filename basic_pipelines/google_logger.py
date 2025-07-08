import csv
import os
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

class GoogleSheetLogger:
    def __init__(self, sheet_name="Hovedindgang", worksheet_name="Log", credentials_path='/home/anders/python/hailo-rpi5-examples/basic_pipelines/credentials.json', reconnect_interval=60):
        self.sheet_name = sheet_name
        self.worksheet_name = worksheet_name
        self.credentials_path = credentials_path
        self.sheet_client = None
        self.last_logged_time = None
        self.reconnect_interval = 120 # antal sekunder mellem forsoeg paa genforbindelse
        self.last_reconnect_attempt = None
        self.connect_to_sheet()

    def connect_to_sheet(self):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_path, scope)
            client = gspread.authorize(creds)
            self.sheet_client = client.open(self.sheet_name).worksheet(self.worksheet_name)
            print("Forbundet til Google Sheet")
        except Exception as e:
            print("Kunne ikke oprette forbindelse til Google Sheet:", e)
            self.sheet_client = None
            self.last_reconnect_attempt = datetime.datetime.now()

    def maybe_reconnect(self):
        # Forsoeger automatisk genforbindelse hvis forbindelsen er mistet
        if self.sheet_client is not None:
            return

        now = datetime.datetime.now()
        if (self.last_reconnect_attempt is None or 
            (now - self.last_reconnect_attempt).total_seconds() >= self.reconnect_interval):
            print("Proever at genoprette forbindelsen til Google Sheet")
            self.connect_to_sheet()
            self.last_reconnect_attempt = now

    def log(self, total_in, total_out):
        now = datetime.datetime.now()
        if self.last_logged_time is None or (now - self.last_logged_time).total_seconds() >= 60:
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            row = [timestamp, total_in, total_out]

            # Forsoeg at genforbinde hvis sheet_client er None
            if self.sheet_client is None:
                self.maybe_reconnect()

            if self.sheet_client:
                try:
                    self.sheet_client.append_row(row)
                    self.last_logged_time = now
                    print(f"Loggede til Google Sheet: {row}")
                    self.flush_local_buffer()
                except Exception as e:
                    print("Fejl ved upload gemmer lokalt:", e)
                    self.sheet_client = None
                    self.last_reconnect_attempt = now
                    self.append_to_local_buffer(row)
            else:
                print("Ikke forbundet gemmer lokalt")
                self.append_to_local_buffer(row)

    def append_to_local_buffer(self, row):
        with open("buffer.csv", mode="a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)

    def flush_local_buffer(self):
        if not os.path.exists("buffer.csv"):
            return

        new_lines = []
        with open("buffer.csv", mode="r", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                try:
                    if self.sheet_client is None:
                        self.maybe_reconnect()
                        if self.sheet_client is None:
                            new_lines.append(row)
                            continue
                    self.sheet_client.append_row(row)
                    print(f"Sendte buffered raekke: {row}")
                except Exception as e:
                    print("Kunne ikke sende buffered raekke:", e)
                    self.sheet_client = None
                    self.last_reconnect_attempt = datetime.datetime.now()
                    new_lines.append(row)

        # Overskriver bufferfilen med de raekker der stadig fejlede
        with open("buffer.csv", mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(new_lines)
