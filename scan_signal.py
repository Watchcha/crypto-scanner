import requests
import pandas as pd
import time
import os

# --- Configuration ---
SYMBOLS = [
    'ETHUSDT', 'BTCUSDT', 'XRPUSDT', 'DOGEUSDT', 'SOLUSDT', 
    'PEPEUSDT', 'CFXUSDT', 'ENAUSDT', 'LTCUSDT', 'SUIUSDT', 
    'XTZUSDT', 'ADAUSDT', 'BNBUSDT', 'WIFUSDT', 'TRXUSDT', 
    'LINKUSDT', 'BONKUSDT', 'UNIUSDT'
]
INTERVAL = "1d"
LIMIT = 100
API_URL = "https://api.binance.com/api/v3/klines"

# CDC Action Zone V2 Parameters
PRD_1 = 12
PRD_2 = 26

# --- Telegram & Proxy Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
HTTP_PROXY = os.getenv('HTTP_PROXY')

def send_telegram_message(message):
    """ส่งข้อความไปยัง Telegram และจัดการข้อความยาว"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token or chat_id is not set. Skipping notification.")
        return
    max_len, chunk_size = 4096, 4000
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    message_parts = [message[i:i + chunk_size] for i in range(0, len(message), chunk_size)] if len(message) > max_len else [message]
    for part in message_parts:
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': part, 'parse_mode': 'Markdown'}
        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()
            print("Telegram notification part sent successfully!")
        except requests.exceptions.RequestException as e:
            print(f"Failed to send Telegram notification: {e.response.text}")
        except Exception as e:
            print(f"An error occurred while sending Telegram message: {e}")
        time.sleep(1)

def get_klines_data(symbol, interval, limit):
    """ดึงข้อมูลแท่งเทียนจาก Binance API โดยใช้ Proxy ถ้ามี"""
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    proxies = {"http": HTTP_PROXY, "https": HTTP_PROXY} if HTTP_PROXY else None
    try:
        if proxies: print(f"Fetching data for {symbol} via proxy...")
        response = requests.get(API_URL, params=params, proxies=proxies, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ProxyError as e:
        print(f"Proxy Error while fetching data for {symbol}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {symbol} from Binance API: {e}")
        return None

# --- ฟังก์ชันที่แก้ไข (สำคัญ) ---
def calculate_cdc_action_zone(df):
    """คำนวณ Indicator CDC Action Zone V2"""
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df['src'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    df['AP'] = df['src'].ewm(span=2, adjust=False).mean()
    df['Fast_MA'] = df['AP'].ewm(span=PRD_1, adjust=False).mean()
    df['Slow_MA'] = df['AP'].ewm(span=PRD_2, adjust=False).mean()
    df['Bullish'] = df['Fast_MA'] > df['Slow_MA']
    
    # *** นี่คือบรรทัดที่เพิ่มกลับเข้ามา ***
    df['Bearish'] = df['Fast_MA'] < df['Slow_MA'] 
    
    df['Buy_Signal'] = (df['Bullish'] == True) & (df['Bullish'].shift(1) == False)
    df['Sell_Signal'] = (df['Bearish'] == True) & (df['Bearish'].shift(1) == False)
    return df

def get_symbol_status(symbol):
    """ตรวจสอบสถานะของเหรียญเดียวและคืนค่าเป็น Dictionary"""
    print(f"--- Analyzing {symbol} ({INTERVAL}) ---")
    klines = get_klines_data(symbol, INTERVAL, LIMIT)
    if not klines:
        return None

    columns = ['Open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close_time', 'Quote_asset_volume', 'Number_of_trades', 'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore']
    df = pd.DataFrame(klines, columns=columns)
    
    df_with_signals = calculate_cdc_action_zone(df)
    latest_candle = df_with_signals.iloc[-1]
    
    status_text = "Up Trend" if latest_candle['Bullish'] else "Down Trend"
    signal_text = "Buy" if latest_candle['Buy_Signal'] else "Sell" if latest_candle['Sell_Signal'] else "No Signal"

    return {"Symbol": symbol, "Status": status_text, "Signal": signal_text, "Close": latest_candle['Close']}

if __name__ == "__main__":
    print(f"====== Starting Crypto Signal Monitor on {time.strftime('%Y-%m-%d %H:%M:%S')} ======")
    print(f"Monitoring {len(SYMBOLS)} symbols: {', '.join(SYMBOLS)}\n")
    if HTTP_PROXY: print("Proxy is configured and will be used for API requests.")
    else: print("No proxy configured. Running directly.")
        
    all_results = []
    for symbol in SYMBOLS:
        try:
            status = get_symbol_status(symbol)
            if status: all_results.append(status)
            time.sleep(1) 
        except Exception as e:
            print(f"An unexpected error occurred while processing {symbol}: {e}")
    
    if not all_results:
        print("Could not retrieve data for any symbols. Exiting.")
    else:
        results_df = pd.DataFrame(all_results)
        signals_df = results_df[results_df['Signal'].isin(['Buy', 'Sell'])].copy()
        header = f"📈 *Crypto Signal Summary ({INTERVAL})*\n"
        header += f"Checked at: {time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
        final_message = header
        if not signals_df.empty:
            signals_df['Close'] = signals_df['Close'].apply(lambda x: f"{x:,.4f}")
            signal_table = signals_df.to_string(index=False)
            final_message += "‼️ *Actionable Signals Detected* ‼️\n"
            final_message += f"```\n{signal_table}\n```\n\n"
        else:
            final_message += "✅ *No new signals detected.*\n\n"
        summary_df = results_df.copy()
        summary_df['Close'] = summary_df['Close'].apply(lambda x: f"{x:,.4f}")
        summary_table = summary_df.to_string(index=False)
        final_message += "--- *Full Market Overview* ---\n"
        final_message += f"```\n{summary_table}\n```"
        print("\n" + "="*10 + " FINAL SUMMARY " + "="*10)
        print(final_message)
        print("="*35 + "\n")
        send_telegram_message(final_message)
            
    print("====== Monitor run finished ======")
