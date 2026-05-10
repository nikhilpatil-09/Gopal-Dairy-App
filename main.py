import flet as ft
import sqlite3
import os
import urllib.parse
from datetime import datetime

# --- FIX FOR PYTHON SSL ERROR ---
import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass
# --------------------------------

def main(page: ft.Page):
    # --- App Window Settings ---
    page.title = "गोपाल डेअरी शेंदुर्णी"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 450  
    page.window_height = 850
    page.scroll = ft.ScrollMode.ADAPTIVE
    page.padding = 0

    # --- Database Setup ---
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "dairy_v3.db")
    conn = sqlite3.connect(db_path, check_same_thread=False) 
    c = conn.cursor()

    # Create ALL necessary tables
    c.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT UNIQUE, rate REAL, sort_order INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS workers (id INTEGER PRIMARY KEY, name TEXT UNIQUE, phone TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS bills (id INTEGER PRIMARY KEY AUTOINCREMENT, bill_date TEXT, worker_name TEXT, customer_name TEXT, total_amount REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS bill_items (id INTEGER PRIMARY KEY, bill_id INTEGER, product_name TEXT, qty REAL, rate REAL, amount REAL, bill_date TEXT, worker_name TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS credit_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, customer_name TEXT, type TEXT, product_name TEXT, qty REAL, rate REAL, amount REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS daily_stock (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, worker_name TEXT, product_name TEXT, opening_qty REAL, closing_qty REAL, received_qty REAL, UNIQUE(date, worker_name, product_name))")
    c.execute("CREATE TABLE IF NOT EXISTS daily_cash_summary (date TEXT, worker_name TEXT, op_cash REAL, other_inc REAL, expense REAL, deposit REAL, final_cash REAL, UNIQUE(date, worker_name))")
    conn.commit()

    # --- Global Application State ---
    state = {
        "cart_items": [],
        "current_bill_total": 0.0,
        "last_slip": "",
        "last_phone": ""
    }

    # ==========================================
    # 1. BILLING (बिलिंग)
    # ==========================================
    bill_date = ft.TextField(label="तारीख", value=datetime.now().strftime("%d-%m-%Y"), expand=1)
    bill_worker = ft.Dropdown(label="कर्मचारी", expand=1)
    bill_cust = ft.TextField(label="ग्राहक", value="Walk-in Customer", expand=1)
    bill_prod = ft.Dropdown(label="वस्तू", expand=2)
    bill_qty = ft.TextField(label="प्रमाण", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    cart_list_view = ft.ListView(height=200, spacing=5)
    lbl_total = ft.Text("एकूण: ₹ 0.00", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.RED)

    def load_billing_ui():
        bill_worker.options.clear()
        bill_prod.options.clear()
        c.execute("SELECT name FROM workers")
        for r in c.fetchall(): bill_worker.options.append(ft.dropdown.Option(r[0]))
        c.execute("SELECT name FROM products ORDER BY sort_order")
        for r in c.fetchall(): bill_prod.options.append(ft.dropdown.Option(r[0]))
        page.update()

    def delete_cart_item(index):
        state["cart_items"].pop(index)
        update_cart_ui()

    def update_cart_ui():
        cart_list_view.controls.clear()
        state["current_bill_total"] = 0.0
        for idx, item in enumerate(state["cart_items"]):
            cart_list_view.controls.append(
                ft.ListTile(
                    title=ft.Text(item[0], weight=ft.FontWeight.BOLD), 
                    subtitle=ft.Text(f"Qty: {item[1]} x ₹{item[2]}"), 
                    trailing=ft.Row([
                        ft.Text(f"₹{item[3]}", color=ft.Colors.GREEN, weight=ft.FontWeight.BOLD),
                        ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED, on_click=lambda e, i=idx: delete_cart_item(i))
                    ], alignment=ft.MainAxisAlignment.END, width=100)
                )
            )
            state["current_bill_total"] += item[3]
        lbl_total.value = f"एकूण: ₹ {state['current_bill_total']:.2f}"
        page.update()

    def btn_add_cart(e):
        prod, qty = bill_prod.value, bill_qty.value
        if not prod or not qty: return
        try:
            qty = float(qty)
            c.execute("SELECT rate FROM products WHERE name=?", (prod,))
            res = c.fetchone()
            rate = res[0] if res else 0.0
            amt = qty * rate
            state["cart_items"].append([prod, qty, rate, amt])
            bill_qty.value = ""
            update_cart_ui()
        except ValueError: pass

    def btn_clear_cart(e):
        state["cart_items"].clear()
        update_cart_ui()

    def save_bill_logic():
        worker = bill_worker.value
        if not worker or not state["cart_items"]: return False, "कर्मचारी निवडा आणि वस्तू ऍड करा!"
        cust, date_str = bill_cust.value, bill_date.value
        
        c.execute("SELECT phone FROM workers WHERE name=?", (worker,))
        w_res = c.fetchone()
        w_phone = w_res[0] if (w_res and w_res[0]) else ""
        
        c.execute("INSERT INTO bills (bill_date, worker_name, customer_name, total_amount) VALUES (?, ?, ?, ?)", (date_str, worker, cust, state["current_bill_total"]))
        bill_id = c.lastrowid
        slip = f"   गोपाल डेअरी शेंदुर्णी\n------------------------\nBill: {bill_id} | {date_str}\nWorker: {worker}\n------------------------\n"
        
        for p, q, r, a in state["cart_items"]:
            c.execute("INSERT INTO bill_items (bill_id, product_name, qty, rate, amount, bill_date, worker_name) VALUES (?, ?, ?, ?, ?, ?, ?)", (bill_id, p, q, r, a, date_str, worker))
            slip += f"{p} : {q} : Rs.{a}\n"
            
        conn.commit()
        slip += f"------------------------\nTOTAL : Rs. {state['current_bill_total']}\n------------------------"
        
        state["last_slip"] = slip
        state["last_phone"] = w_phone
        state["cart_items"].clear()
        update_cart_ui()
        return True, "बिल सेव्ह झाले!"

    def btn_save_only(e):
        if not state["cart_items"]: return
        success, msg = save_bill_logic()
        page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=ft.Colors.GREEN if success else ft.Colors.RED)
        page.snack_bar.open = True; page.update()

    def btn_whatsapp_only(e):
        if state["cart_items"]:
            success, msg = save_bill_logic()
            if not success: return
        if not state["last_slip"]: return
        phone = state["last_phone"]
        if phone and len(phone.strip()) >= 10:
            url = f"https://wa.me/91{phone.strip()[-10:]}?text={urllib.parse.quote(state['last_slip'])}"
            page.launch_url(url)

    view_billing = ft.Container(padding=15, visible=True, content=ft.Column([
        ft.Text("📦 नवीन बिलिंग", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
        ft.Row([bill_date, bill_worker]), bill_cust, ft.Divider(),
        ft.Row([bill_prod, bill_qty]),
        ft.Row([ft.ElevatedButton("➕ ऍड करा", on_click=btn_add_cart, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE, expand=True), ft.ElevatedButton("❌ क्लिअर", on_click=btn_clear_cart, bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE)]),
        ft.Divider(),
        ft.Container(content=cart_list_view, bgcolor=ft.Colors.GREY_200, border_radius=5, expand=True),
        ft.Row([lbl_total], alignment=ft.MainAxisAlignment.END),
        ft.Row([ft.ElevatedButton("💾 सेव्ह बिल", on_click=btn_save_only, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, expand=True, height=45), ft.ElevatedButton("💬 WhatsApp", on_click=btn_whatsapp_only, bgcolor=ft.Colors.TEAL, color=ft.Colors.WHITE, expand=True, height=45)])
    ], expand=True))


    # ==========================================
    # 2. DAILY REPORT (दिवसाचा हिशोब - PC STYLE)
    # ==========================================
    rep_date = ft.TextField(label="तारीख", value=datetime.now().strftime("%d-%m-%Y"), expand=1)
    rep_worker = ft.Dropdown(label="कर्मचारी", expand=1)
    
    report_list = ft.ListView(expand=True, spacing=10)
    
    # Cash Summary UI
    lbl_sales_total = ft.Text("₹ 0.00", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE)
    entry_op_cash = ft.TextField(label="+ शिल्लक", value="0", width=90, keyboard_type=ft.KeyboardType.NUMBER)
    entry_other_in = ft.TextField(label="+ जमा", value="0", width=90, keyboard_type=ft.KeyboardType.NUMBER)
    entry_exp = ft.TextField(label="- खर्च", value="0", width=90, keyboard_type=ft.KeyboardType.NUMBER)
    entry_dep = ft.TextField(label="- उधारी", value="0", width=90, keyboard_type=ft.KeyboardType.NUMBER)
    lbl_final_cash = ft.Text("अंतिम कॅश: ₹ 0.00", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800)

    report_data_refs = []

    def load_report_ui():
        rep_worker.options.clear()
        c.execute("SELECT name FROM workers")
        for r in c.fetchall(): rep_worker.options.append(ft.dropdown.Option(r[0]))
        page.update()

    def calculate_hishob_totals(e=None):
        grand_total = 0.0
        for ref in report_data_refs:
            try:
                op = float(ref["op"].value or 0)
                rec = float(ref["rec"].value or 0)
                cl = float(ref["cl"].value or 0)
                rate = ref["rate"]
                sold = (op + rec) - cl
                amt = sold * rate
                
                ref["lbl_sold"].value = f"खप: {sold:.2f}"
                ref["lbl_amt"].value = f"₹ {amt:.2f}"
                grand_total += amt
            except ValueError: pass

        lbl_sales_total.value = f"₹ {grand_total:.2f}"

        try:
            op_cash = float(entry_op_cash.value or 0)
            oth_in = float(entry_other_in.value or 0)
            exp = float(entry_exp.value or 0)
            dep = float(entry_dep.value or 0)
            final = (grand_total + op_cash + oth_in) - (exp + dep)
            lbl_final_cash.value = f"अंतिम कॅश: ₹ {final:.2f}"
        except ValueError: pass
        
        page.update()

    def btn_load_report(e):
        worker, date_val = rep_worker.value, rep_date.value
        if not worker or not date_val: return
        
        report_list.controls.clear()
        report_data_refs.clear()
        
        c.execute("SELECT op_cash, other_inc, expense, deposit FROM daily_cash_summary WHERE date=? AND worker_name=?", (date_val, worker))
        cash_res = c.fetchone()
        if cash_res:
            entry_op_cash.value, entry_other_in.value, entry_exp.value, entry_dep.value = str(cash_res[0]), str(cash_res[1]), str(cash_res[2]), str(cash_res[3])
        else:
            entry_op_cash.value, entry_other_in.value, entry_exp.value, entry_dep.value = "0", "0", "0", "0"

        c.execute("SELECT name, rate FROM products ORDER BY sort_order")
        products = c.fetchall()
        
        for prod_name, prod_rate in products:
            c.execute("SELECT opening_qty, received_qty, closing_qty FROM daily_stock WHERE date=? AND worker_name=? AND product_name=?", (date_val, worker, prod_name))
            stk = c.fetchone()
            
            if not stk:
                c.execute("SELECT SUM(qty) FROM bill_items WHERE bill_date=? AND worker_name=? AND product_name=?", (date_val, worker, prod_name))
                rec_sum = c.fetchone()[0] or 0.0
                op_val, rec_val, cl_val = 0.0, rec_sum, 0.0
            else:
                op_val, rec_val, cl_val = stk[0], stk[1], stk[2]

            tf_op = ft.TextField(label="सुरू (Op)", value=str(op_val), width=80, on_change=calculate_hishob_totals)
            tf_rec = ft.TextField(label="आले (In)", value=str(rec_val), width=80, on_change=calculate_hishob_totals)
            tf_cl = ft.TextField(label="शिल्लक (Cl)", value=str(cl_val), width=80, on_change=calculate_hishob_totals)
            
            l_sold = ft.Text("खप: 0.00", weight=ft.FontWeight.BOLD)
            l_amt = ft.Text("₹ 0.00", weight=ft.FontWeight.BOLD, color=ft.Colors.RED)
            
            report_data_refs.append({"name": prod_name, "rate": prod_rate, "op": tf_op, "rec": tf_rec, "cl": tf_cl, "lbl_sold": l_sold, "lbl_amt": l_amt})

            card = ft.Container(
                bgcolor=ft.Colors.BLUE_50, padding=10, border_radius=8,
                content=ft.Column([
                    ft.Text(f"{prod_name} (दर: ₹{prod_rate})", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                    ft.Row([tf_op, tf_rec, tf_cl], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([l_sold, l_amt], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ])
            )
            report_list.controls.append(card)
        
        calculate_hishob_totals()
        
    entry_op_cash.on_change = calculate_hishob_totals
    entry_other_in.on_change = calculate_hishob_totals
    entry_exp.on_change = calculate_hishob_totals
    entry_dep.on_change = calculate_hishob_totals

    def btn_save_hishob(e):
        worker, date_val = rep_worker.value, rep_date.value
        if not worker or not date_val: return
        
        for ref in report_data_refs:
            try:
                o, r, cl = float(ref["op"].value or 0), float(ref["rec"].value or 0), float(ref["cl"].value or 0)
                c.execute("""INSERT OR REPLACE INTO daily_stock (id, date, worker_name, product_name, opening_qty, received_qty, closing_qty) 
                             VALUES ((SELECT id FROM daily_stock WHERE date=? AND worker_name=? AND product_name=?), ?, ?, ?, ?, ?, ?)""",
                          (date_val, worker, ref["name"], date_val, worker, ref["name"], o, r, cl))
            except: pass
        
        try:
            opc, oti, ex, dp = float(entry_op_cash.value or 0), float(entry_other_in.value or 0), float(entry_exp.value or 0), float(entry_dep.value or 0)
            fin = float(lbl_final_cash.value.split("₹ ")[1])
            c.execute("""INSERT OR REPLACE INTO daily_cash_summary (date, worker_name, op_cash, other_inc, expense, deposit, final_cash)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""", (date_val, worker, opc, oti, ex, dp, fin))
            conn.commit()
            page.snack_bar = ft.SnackBar(ft.Text("हिशोब सेव्ह झाला!"), bgcolor=ft.Colors.GREEN); page.snack_bar.open = True; page.update()
        except: pass

    # --- FIX: Removed ft.border.all here and used bgcolor instead ---
    view_report = ft.Container(padding=10, visible=False, content=ft.Column([
        ft.Row([ft.Text("📊 हिशोब", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900), ft.ElevatedButton("लोड करा", on_click=btn_load_report, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Row([rep_date, rep_worker]),
        ft.Container(content=report_list, expand=True, bgcolor=ft.Colors.GREY_100, border_radius=5),
        ft.Container(bgcolor=ft.Colors.GREY_200, padding=10, border_radius=8, content=ft.Column([
            ft.Row([ft.Text("विक्री:", weight=ft.FontWeight.BOLD), lbl_sales_total], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([entry_op_cash, entry_other_in, entry_exp, entry_dep], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            ft.Row([lbl_final_cash, ft.ElevatedButton("💾 सेव्ह", on_click=btn_save_hishob, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        ]))
    ], expand=True))


    # ==========================================
    # 3. CREDIT (उधारी)
    # ==========================================
    cred_date = ft.TextField(label="तारीख", value=datetime.now().strftime("%d-%m-%Y"), expand=1)
    cred_cust = ft.TextField(label="ग्राहक नाव", expand=2)
    cred_amt = ft.TextField(label="रक्कम (₹)", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    cred_list = ft.ListView(expand=True, spacing=5)

    def delete_credit(record_id):
        c.execute("DELETE FROM credit_ledger WHERE id=?", (record_id,))
        conn.commit()
        load_credit_ui()

    def load_credit_ui():
        cred_list.controls.clear()
        c.execute("SELECT id, date, customer_name, amount FROM credit_ledger ORDER BY id DESC LIMIT 20")
        for r in c.fetchall():
            cred_list.controls.append(ft.ListTile(
                leading=ft.Icon(ft.Icons.PERSON), 
                title=ft.Text(r[2], weight=ft.FontWeight.BOLD), 
                subtitle=ft.Text(r[1]), 
                trailing=ft.Row([
                    ft.Text(f"₹ {r[3]}", color=ft.Colors.RED, weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED, on_click=lambda e, rid=r[0]: delete_credit(rid))
                ], alignment=ft.MainAxisAlignment.END, width=100), 
                bgcolor=ft.Colors.RED_50
            ))
        page.update()

    def btn_add_credit(e):
        if not cred_cust.value or not cred_amt.value: return
        try:
            amt = float(cred_amt.value)
            c.execute("INSERT INTO credit_ledger (date, customer_name, type, product_name, qty, rate, amount) VALUES (?, ?, 'Cash', 'रोख', 1, ?, ?)", (cred_date.value, cred_cust.value, amt, amt))
            conn.commit(); cred_amt.value = ""; cred_cust.value = ""; load_credit_ui()
        except: pass

    view_credit = ft.Container(padding=15, visible=False, content=ft.Column([
        ft.Text("📒 उधारी नोंद", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
        ft.Row([cred_date]), ft.Row([cred_cust, cred_amt]),
        ft.ElevatedButton("✅ सेव्ह करा", on_click=btn_add_credit, bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
        ft.Divider(), cred_list
    ], expand=True))


    # ==========================================
    # 4. SETTINGS & HISTORY + DELETE EVERYWHERE
    # ==========================================
    s_pname = ft.TextField(label="वस्तू नाव", expand=True)
    s_prate = ft.TextField(label="दर", width=80)
    p_list = ft.ListView(height=350)

    def delete_product(pid):
        c.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        load_settings_p()

    def load_settings_p():
        p_list.controls.clear()
        c.execute("SELECT id, name, rate FROM products ORDER BY sort_order")
        for r in c.fetchall():
            p_list.controls.append(
                ft.ListTile(
                    title=ft.Text(r[1], weight=ft.FontWeight.BOLD),
                    trailing=ft.Row([
                        ft.Text(f"₹ {r[2]}"),
                        ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED, on_click=lambda e, pid=r[0]: delete_product(pid))
                    ], width=100, alignment=ft.MainAxisAlignment.END)
                )
            )
        page.update()

    def btn_add_p(e):
        if s_pname.value and s_prate.value:
            c.execute("INSERT INTO products (name, rate, sort_order) VALUES (?, ?, 99)", (s_pname.value, float(s_prate.value)))
            conn.commit()
            s_pname.value = ""
            s_prate.value = ""
            load_settings_p()

    s_wname = ft.TextField(label="कर्मचारी नाव", expand=True)
    s_wphone = ft.TextField(label="मोबाईल", width=120)
    w_list = ft.ListView(height=350)

    def delete_worker(wid):
        c.execute("DELETE FROM workers WHERE id=?", (wid,))
        conn.commit()
        load_settings_w()

    def load_settings_w():
        w_list.controls.clear()
        c.execute("SELECT id, name, phone FROM workers")
        for r in c.fetchall():
            w_list.controls.append(
                ft.ListTile(
                    title=ft.Text(r[1], weight=ft.FontWeight.BOLD),
                    trailing=ft.Row([
                        ft.Text(r[2]),
                        ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED, on_click=lambda e, wid=r[0]: delete_worker(wid))
                    ], width=140, alignment=ft.MainAxisAlignment.END)
                )
            )
        page.update()

    def btn_add_w(e):
        if s_wname.value:
            c.execute("INSERT INTO workers (name, phone) VALUES (?, ?)", (s_wname.value, s_wphone.value))
            conn.commit()
            s_wname.value = ""
            s_wphone.value = ""
            load_settings_w()

    h_list = ft.ListView(expand=True)

    def delete_history_bill(bid):
        c.execute("DELETE FROM bills WHERE id=?", (bid,))
        c.execute("DELETE FROM bill_items WHERE bill_id=?", (bid,))
        conn.commit()
        load_history()

    def load_history():
        h_list.controls.clear()
        c.execute("SELECT id, bill_date, worker_name, total_amount FROM bills ORDER BY id DESC LIMIT 30")
        for r in c.fetchall():
            h_list.controls.append(
                ft.ListTile(
                    title=ft.Text(r[2], weight=ft.FontWeight.BOLD),
                    subtitle=ft.Text(r[1]),
                    trailing=ft.Row([
                        ft.Text(f"₹ {r[3]}", weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                        ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED, on_click=lambda e, bid=r[0]: delete_history_bill(bid))
                    ], width=120, alignment=ft.MainAxisAlignment.END)
                )
            )
        page.update()

    # Custom Tab Buttons
    tab_btn_p = ft.ElevatedButton("वस्तू", bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)
    tab_btn_w = ft.ElevatedButton("कर्मचारी")
    tab_btn_h = ft.ElevatedButton("जुने बिल")

    view_p = ft.Column([ft.Row([s_pname, s_prate]), ft.ElevatedButton("Add Product", on_click=btn_add_p, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE), p_list], visible=True, expand=True)
    view_w = ft.Column([ft.Row([s_wname, s_wphone]), ft.ElevatedButton("Add Worker", on_click=btn_add_w, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE), w_list], visible=False, expand=True)
    view_h = ft.Column([ft.ElevatedButton("🔄 रिफ्रेश करा", on_click=lambda e: load_history(), bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE), h_list], visible=False, expand=True)

    def set_tab(active_view, active_btn):
        for v in [view_p, view_w, view_h]: v.visible = False
        for b in [tab_btn_p, tab_btn_w, tab_btn_h]: b.bgcolor = None; b.color = None
        active_view.visible = True
        active_btn.bgcolor = ft.Colors.BLUE
        active_btn.color = ft.Colors.WHITE
        page.update()

    tab_btn_p.on_click = lambda e: set_tab(view_p, tab_btn_p)
    tab_btn_w.on_click = lambda e: set_tab(view_w, tab_btn_w)
    tab_btn_h.on_click = lambda e: set_tab(view_h, tab_btn_h)

    view_settings = ft.Container(padding=15, visible=False, content=ft.Column([
        ft.Text("⚙️ सेटिंग्ज व रेकॉर्ड", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
        ft.Row([tab_btn_p, tab_btn_w, tab_btn_h], alignment=ft.MainAxisAlignment.SPACE_AROUND),
        ft.Divider(),
        view_p, view_w, view_h
    ], expand=True))

    # ==========================================
    # APP NAVIGATION
    # ==========================================
    def on_nav_change(e):
        view_billing.visible = (e.control.selected_index == 0)
        view_report.visible = (e.control.selected_index == 1)
        view_credit.visible = (e.control.selected_index == 2)
        view_settings.visible = (e.control.selected_index == 3)
        
        if view_billing.visible: load_billing_ui()
        if view_report.visible: load_report_ui()
        if view_credit.visible: load_credit_ui()
        if view_settings.visible: load_settings_p(); load_settings_w(); load_history()
        page.update()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        on_change=on_nav_change,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.RECEIPT_LONG, label="बिलिंग"),
            ft.NavigationBarDestination(icon=ft.Icons.CALCULATE, label="हिशोब"),
            ft.NavigationBarDestination(icon=ft.Icons.MENU_BOOK, label="उधारी"),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="सेटिंग्ज"),
        ]
    )

    page.appbar = ft.AppBar(title=ft.Text("Gopal Dairy", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.BLUE_800)
    page.add(view_billing, view_report, view_credit, view_settings)
    load_billing_ui(); load_report_ui(); load_credit_ui(); load_settings_p(); load_settings_w(); load_history()

if __name__ == "__main__":
    ft.run(main)