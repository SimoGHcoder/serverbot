# modules/alea.py
import datetime
import json
import os
import logging

logger = logging.getLogger("ServerBot")
# Salva il file nella stessa cartella del modulo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config_alea.json")

FIXED_HOLIDAYS = [
    (1, 1),   # 1 Gennaio
    (5, 1),   # 1 Maggio
    (6, 2),   # 2 Giugno
    (8, 15),  # 15 Agosto
    (10, 4),  # 4 Ottobre
    (11, 1),  # 1 Novembre
    (12, 8),  # 8 Dicembre
    (12, 25), # 25 Dicembre
]

def get_easter_monday(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    easter_date = datetime.date(year, month, day)
    return easter_date + datetime.timedelta(days=1)

def is_holiday(date):
    if (date.month, date.day) in FIXED_HOLIDAYS:
        return True
    if date == get_easter_monday(date.year):
        return True
    return False

def get_week_of_month(date):
    dom = date.day
    return (dom - 1) // 7 + 1

def get_base_collection(date):
    weekday = date.weekday() # 0=Lun, 1=Mar, 2=Mer, 3=Gio, 4=Ven, 5=Sab, 6=Dom
    if weekday == 0:
        return ["Umido", "Carta"]
    elif weekday == 1:
        if get_week_of_month(date) in [2, 4]:
            return ["Secco"]
    elif weekday == 2:
        return []
    elif weekday == 3:
        return ["Umido", "Secco/Vegetale"]
    elif weekday == 4:
        return ["Plastica"]
    elif weekday == 5:
        return []
    return []

def get_collection_for_date(target_date):
    if is_holiday(target_date):
        return []
        
    weekday = target_date.weekday()
    rifiuti = get_base_collection(target_date)
    
    if weekday == 5: # Sabato
        for i in range(1, 4):
            d_prev = target_date - datetime.timedelta(days=i)
            if is_holiday(d_prev):
                rifiuti.extend(get_base_collection(d_prev))
        for i in range(1, 3):
            d_prev = target_date - datetime.timedelta(days=i)
            if d_prev.weekday() in [3, 4] and is_holiday(d_prev):
                rifiuti.extend(get_base_collection(d_prev))
                
    return list(set(rifiuti))

def get_collection_for_tomorrow_str():
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    rifiuti = get_collection_for_date(tomorrow)
    date_str = tomorrow.strftime("%d/%m/%Y")
    return date_str, rifiuti

def get_notification_time():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("alea_time", "20:00")
    except FileNotFoundError:
        logger.exception("Config file not found")
    except json.JSONDecodeError:
        logger.exception("Config file is not valid JSON")
    except Exception as e:
        logger.exception("Unexpected error reading Alea time")
    return "20:00"

def set_notification_time(time_str):
    try:
        data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
        data["alea_time"] = time_str
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
        logger.info(f"Orario notifica Alea impostato su: {time_str}")
    except Exception:
        logger.exception("Errore salvataggio orario alea")