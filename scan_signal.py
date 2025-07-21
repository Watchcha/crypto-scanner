import requests
import pandas as pd
import time
import os

# --- Configuration ---
# 1. ลิสต์ของเหรียญที่ต้องการ Monitor
SYMBOLS = [
    'ETHUSDT', 'BTCUSDT', 'XRPUSDT', 'DOGEUSDT', 'USDCUSDT', 
    'SOLUSDT', 'PEPEUSDT', 'CFXUSDT', 'FDUSDUSDT', 'ENAUSDT', 
    'LTCUSDT', 'SUIUSDT', 'XTZUSDT', 'ADAUSDT', 'BNBUSDT', 
    'WIFUSDT', 'TRXUSDT', 'LINKUSDT', 'BONKUSDT', 'UNIUSDT'
]

INTERVAL = "1d"
LIMIT = 100
API_URL = "https://api.binance.com/api/v3/klines"

# CDC Action Zone V2 Parameters
PRD_1 = 12
PRD_2 = 26

# --- Telegram Configuration ---
# แนะนำให้ตั้งค่า Environment Variables เพื่อความปลอดภัย
# For example: export TELEGRAM_BOT_TOKEN="your_token"
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram_message(message):
    """ส่งข้อความไปยัง Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token or chat_id is not set. Skipping notification.")
        return

    # Telegram's message character limit is 4096. We split if it's longer.
    max_len = 4096
    # Reserve some space for markdown and potential headers/footers
    chunk_size = 4000 
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Split message into chunks if it's too long
    if len(message) > max_len:
        message_parts = [message[i:i + chunk_size] for i in range(0, len(message), chunk_size)]
    else:
        message_parts = [message]

    for part in message_parts:
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': part,
            # Using 'MarkdownV2' is more strict, but 'Markdown' is more forgiving.
            # Using triple backticks for a code block is safe for both.
            'parse_mode': 'Markdown' 
        }
        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()
            print("Telegram notification part sent successfully!")
        except requests.exceptions.RequestException as e:
            print(f"Failed to send Telegram notification: {e}")
        except Exception as e:
            print(f"An error occurred while sending Telegram message: {e}")
        time.sleep(1) # Pause between sending parts

def get_klines_data(symbol, interval, limit):
    """ดึงข้อมูลแท่งเทียนจาก Binance API สำหรับเหรียญที่ระบุ"""
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {symbol} from Binance API: {e}")
        return None

def calculate_cdc_action_zone(df):
    """คำนวณ Indicator CDC Action Zone V2"""
    df['Open'] = df['Open'].astype(float)
    df['High'] = df['High'].astype(float)
    df['Low'] = df['Low'].astype(float)
    df['Close'] = df['Close'].astype(float)
    df['src'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    df['AP'] = df['src'].ewm(span=2, adjust=False).mean()
    df['Fast_MA'] = df['AP'].ewm(span=PRD_1, adjust=False).mean()
    df['Slow_MA'] = df['AP'].ewm(span=PRD_2, adjust=False).mean()
    df['Bullish'] = df['Fast_MA'] > df['Slow_MA']
    df['Bearish'] = df['Fast_MA'] < df['Slow_MA']
    df['Buy_Signal'] = (df['Bullish'] == True) & (df['Bullish'].shift(1) == False)
    df['Sell_Signal'] = (df['Bearish'] == True) & (df['Bearish'].shift(1) == False)
    return df

# 2. ปรับฟังก์ชันให้คืนค่าเป็น Dictionary ของผลลัพธ์
def get_symbol_status(symbol):
    """
    ตรวจสอบสถานะของเหรียญเดียวและคืนค่าเป็น Dictionary
    Returns: A dictionary with status info or None if data fetching fails.
    """
    print(f"--- Analyzing {symbol} ({INTERVAL}) ---")

    klines = get_klines_data(symbol, INTERVAL, LIMIT)
    if not klines:
        return None # คืนค่า None ถ้าดึงข้อมูลไม่สำเร็จ

    columns = ['Open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close_time', 'Quote_asset_volume', 'Number_of_trades', 'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore']
    df = pd.DataFrame(klines, columns=columns)
    df['Open_time'] = pd.to_datetime(df['Open_time'], unit='ms')

    df_with_signals = calculate_cdc_action_zone(df)
    latest_candle = df_with_signals.iloc[-1]
    
    # กำหนดค่า Status และ Signal
    if latest_candle['Bullish']:
        status_text = "Up Trend"
    else:
        status_text = "Down Trend"

    if latest_candle['Buy_Signal']:
        signal_text = "Buy"
    elif latest_candle['Sell_Signal']:
        signal_text = "Sell"
    else:
        signal_text = "No Signal"

    # สร้าง Dictionary ของผลลัพธ์
    result_data = {
        "Symbol": symbol,
        "Status": status_text,
        "Signal": signal_text,
        "Close": latest_candle['Close']
    }
    
    return result_data

if __name__ == "__main__":
    print(f"====== Starting Crypto Signal Monitor on {time.strftime('%Y-%m-%d %H:%M:%S')} ======")
    print(f"Monitoring {len(SYMBOLS)} symbols: {', '.join(SYMBOLS)}\n")
    
    # 3. สร้าง List ว่างเพื่อเก็บผลลัพธ์
    all_results = []
    
    for symbol in SYMBOLS:
        try:
            # เรียกฟังก์ชันและเก็บผลลัพธ์
            status = get_symbol_status(symbol)
            if status: # ตรวจสอบว่าได้ข้อมูลกลับมาหรือไม่
                all_results.append(status)
            
            # หน่วงเวลา 1 วินาที ก่อนไปเหรียญถัดไป
            time.sleep(1) 
        except Exception as e:
            print(f"An unexpected error occurred while processing {symbol}: {e}")
    
    # 4. สร้างข้อความสรุปหลังจากตรวจสอบครบทุกเหรียญ
    if not all_results:
        print("Could not retrieve data for any symbols. Exiting.")
    else:
        # สร้าง DataFrame จาก list of dictionaries
        results_df = pd.DataFrame(all_results)
        
        # จัดรูปแบบคอลัมน์ Close ให้สวยงาม
        results_df['Close'] = results_df['Close'].apply(lambda x: f"{x:,.4f}")

        # สร้างข้อความส่วนหัว
        header = f"📈 Crypto Signal Summary ({INTERVAL})\n"
        header += f"Checked at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # แปลง DataFrame เป็น String ในรูปแบบตารางที่ไม่มี index
        table_string = results_df.to_string(index=False)
        
        # รวมส่วนหัวกับตาราง และใช้ Markdown code block (```) เพื่อให้แสดงผลเป็นตารางใน Telegram
        final_message = f"{header}```\n{table_string}\n```"
        
        # 5. Print และส่ง Telegram ครั้งเดียว
        print("\n" + "="*10 + " FINAL SUMMARY " + "="*10)
        print(final_message)
        print("="*35 + "\n")

        send_telegram_message(final_message)
            
    print("====== Monitor run finished ======")