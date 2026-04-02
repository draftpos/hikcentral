# Copyright (c) 2026, Ashley and contributors
# For license information, please see license.txt

import frappe
import psycopg2
from frappe.model.document import Document

def get_pg_connection():
    site_config = frappe.get_site_config()
    return psycopg2.connect(
        host=site_config.get("db_host", "194.163.155.17"),
        port=int(site_config.get("db_port", 5432)),
        dbname=site_config.get("db_name"),
        user=site_config.get("db_name"),
        password=site_config.get("db_password")
    )

class HikAttendanceLog(Document):
    def after_insert(self):
        self.sync_to_attendancelogs()

    def on_update(self):
        self.sync_to_attendancelogs()

    def sync_to_attendancelogs(self):
        conn = None
        try:
            conn = get_pg_connection()
            cur = conn.cursor()
            
            # NOTE: For 'ON CONFLICT' to work, public.attendancelogs must have a 
            # UNIQUE constraint on (employeeid, accessdatetime) or similar!
            cur.execute("""
                INSERT INTO public.attendancelogs (
                    employeeid, personname, firstname, lastname, persongroup,
                    cardnumber, accessdatetime, accessdate, accesstime,
                    logtimestamp, authenticationresult, authenticationtype,
                    devicename, deviceserialno, resourcename, readername,
                    capturedpictureurl, direction, maskwearingstatus,
                    attendancestatus, amended_from
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                ) ON CONFLICT DO NOTHING
            """, (
                self.employeeid, self.personname, self.firstname, self.lastname,
                self.persongroup, self.cardnumber, self.accessdatetime,
                self.accessdate, self.accesstime, self.logtimestamp,
                self.authenticationresult, self.authenticationtype,
                self.devicename, self.deviceserialno, self.resourcename,
                self.readername, self.capturedpictureurl, self.direction,
                self.maskwearingstatus, self.attendancestatus, self.amended_from
            ))
            conn.commit()
            cur.close()
        except Exception as e:
            frappe.log_error(f"HikCentral sync error: {str(e)}", "HikAttendanceLog Sync")
        finally:
            if conn:
                conn.close()


def sync_from_attendancelogs():
    """
    Cron job or manually triggered function to pull data from the 3rd party 
    attendancelogs table into Frappe.
    """
    conn = None
    synced_count = 0
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        
        # Added a LIMIT and ORDER BY to prevent memory overload. 
        # You should ideally track the last processed timestamp to avoid re-reading old logs!
        cur.execute("""
            SELECT 
                employeeid, personname, firstname, lastname, persongroup, 
                cardnumber, accessdatetime, accessdate, accesstime, 
                logtimestamp, authenticationresult, authenticationtype, 
                devicename, deviceserialno, resourcename, readername, 
                capturedpictureurl, direction, maskwearingstatus, attendancestatus 
            FROM public.attendancelogs 
            ORDER BY accessdatetime DESC 
            LIMIT 500
        """)
        
        rows = cur.fetchall()
        for row in rows:
            # Check if record already exists in Frappe
            if not frappe.db.exists("Hik Attendance Log", {"accessdatetime": str(row[6]), "employeeid": row[0]}):
                doc = frappe.get_doc({
                    "doctype": "Hik Attendance Log",
                    "employeeid": row[0],
                    "personname": row[1],
                    "firstname": row[2],
                    "lastname": row[3],
                    "persongroup": row[4],
                    "cardnumber": row[5],
                    "accessdatetime": str(row[6]),
                    "accessdate": row[7],
                    "accesstime": str(row[8]) if row[8] else None,
                    "logtimestamp": row[9],
                    "authenticationresult": row[10],
                    "authenticationtype": row[11],
                    "devicename": row[12],
                    "deviceserialno": row[13],
                    "resourcename": row[14],
                    "readername": row[15],
                    "capturedpictureurl": row[16],
                    "direction": row[17].capitalize() if row[17] else None,
                    "maskwearingstatus": row[18],
                    "attendancestatus": row[19]
                })
                doc.insert(ignore_permissions=True)
                synced_count += 1
                
        frappe.db.commit()
        cur.close()
        print(f"Successfully synced {synced_count} new records into Hik Attendance Log")
        
    except Exception as e:
        frappe.log_error(f"Pulling from attendancelogs failed: {str(e)}", "HikAttendanceLog Pull Sync")
    finally:
        if conn:
            conn.close()
