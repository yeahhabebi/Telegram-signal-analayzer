import streamlit as st
import asyncio
import pandas as pd
import re
import json
import time
from datetime import datetime
import boto3
from botocore.config import Config
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
import threading
import queue
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Load environment variables
load_dotenv()

# Global variables
signal_queue = queue.Queue()
signals_data = []
latest_signals = []

class SignalProcessor:
    def __init__(self):
        self.signals = []
        self.load_existing_data()
    
    def parse_signal(self, message):
        try:
            signal_data = {
                'timestamp': datetime.now(),
                'period_id': None,
                'result': None,
                'trade': None,
                'quantity': None,
                'message': message
            }
            
            # Extract period ID
            period_match = re.search(r'period ID:\s*(\d+)', message)
            if period_match:
                signal_data['period_id'] = period_match.group(1)
            
            # Extract result
            if 'Result:Win' in message or 'Result🎉' in message:
                signal_data['result'] = 'Win'
            elif 'Result:Lose' in message or 'Lose💔' in message:
                signal_data['result'] = 'Lose'
            
            # Extract trade recommendation
            if '🟢✔️' in message:
                signal_data['trade'] = 'Green'
            elif '🔴✔️' in message:
                signal_data['trade'] = 'Red'
            
            # Extract quantity
            quantity_match = re.search(r'quantity:\s*x?([\d.]+)', message)
            if quantity_match:
                signal_data['quantity'] = float(quantity_match.group(1))
            
            # Only add if we have valid data
            if signal_data['period_id'] and signal_data['result']:
                return signal_data
            return None
            
        except Exception as e:
            print(f"Error parsing signal: {e}")
            return None
    
    def add_signal(self, signal_data):
        if signal_data and signal_data not in self.signals:
            self.signals.append(signal_data)
            # Keep only last 50 signals
            if len(self.signals) > 50:
                self.signals = self.signals[-50:]
            
            # Update latest signals for dashboard
            global latest_signals
            latest_signals = self.signals[-30:]  # Last 30 signals
            
            # Upload to R2
            self.upload_to_r2()
    
    def upload_to_r2(self):
        try:
            # Initialize R2 client
            s3 = boto3.client('s3',
                endpoint_url=os.getenv('R2_ENDPOINT'),
                aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
                config=Config(signature_version='s3v4')
            )
            
            # Prepare data for upload
            upload_data = {
                'signals': self.signals,
                'last_updated': datetime.now().isoformat(),
                'total_signals': len(self.signals),
                'wins': len([s for s in self.signals if s['result'] == 'Win']),
                'losses': len([s for s in self.signals if s['result'] == 'Lose'])
            }
            
            # Upload to R2
            s3.put_object(
                Bucket=os.getenv('R2_BUCKET'),
                Key='signals_data.json',
                Body=json.dumps(upload_data, default=str),
                ContentType='application/json'
            )
            print("Data uploaded to R2 successfully")
            
        except Exception as e:
            print(f"Error uploading to R2: {e}")
    
    def load_existing_data(self):
        try:
            s3 = boto3.client('s3',
                endpoint_url=os.getenv('R2_ENDPOINT'),
                aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
                config=Config(signature_version='s3v4')
            )
            
            response = s3.get_object(
                Bucket=os.getenv('R2_BUCKET'),
                Key='signals_data.json'
            )
            
            existing_data = json.loads(response['Body'].read())
            self.signals = existing_data.get('signals', [])
            global latest_signals
            latest_signals = self.signals[-30:]
            print("Existing data loaded from R2")
            
        except Exception as e:
            print(f"No existing data found or error loading: {e}")
    
    def get_stats(self):
        if not self.signals:
            return {'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'current_streak': 0}
        
        wins = len([s for s in self.signals if s['result'] == 'Win'])
        losses = len([s for s in self.signals if s['result'] == 'Lose'])
        total = len(self.signals)
        win_rate = (wins / total * 100) if total > 0 else 0
        
        # Calculate current streak
        current_streak = 0
        if self.signals:
            last_result = self.signals[-1]['result']
            for signal in reversed(self.signals):
                if signal['result'] == last_result:
                    current_streak += 1
                else:
                    break
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'current_streak': current_streak
        }

class TelegramMonitor:
    def __init__(self, processor):
        self.processor = processor
        self.client = None
        self.is_running = False
    
    async def start(self):
        try:
            # Create Telegram client
            self.client = TelegramClient(
                StringSession(os.getenv('SESSION_STRING')),
                int(os.getenv('API_ID')),
                os.getenv('API_HASH')
            )
            
            await self.client.start()
            print("Telegram client started successfully")
            
            # Get target chats
            target_chats = os.getenv('TARGET_CHATS', '').split(',')
            
            @self.client.on(self.client.NewMessage)
            async def handler(event):
                try:
                    chat = await event.get_chat()
                    if chat.username in target_chats or chat.id in target_chats:
                        message_text = event.message.text
                        if message_text:
                            signal_data = self.processor.parse_signal(message_text)
                            if signal_data:
                                self.processor.add_signal(signal_data)
                                signal_queue.put(signal_data)
                                print(f"New signal processed: {signal_data['period_id']}")
                except Exception as e:
                    print(f"Error handling message: {e}")
            
            self.is_running = True
            print("Monitoring started...")
            
            # Keep the client running
            await self.client.run_until_disconnected()
            
        except Exception as e:
            print(f"Error in Telegram monitor: {e}")
    
    def stop(self):
        self.is_running = False
        if self.client:
            self.client.disconnect()

def run_telegram_monitor(processor):
    monitor = TelegramMonitor(processor)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(monitor.start())

# Initialize processor
processor = SignalProcessor()

# Start Telegram monitor in background thread
telegram_thread = threading.Thread(target=run_telegram_monitor, args=(processor,), daemon=True)
telegram_thread.start()

# Streamlit Dashboard
st.set_page_config(
    page_title="Coinryze Signal Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .win-box {
        background-color: #d4edda;
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #28a745;
    }
    .loss-box {
        background-color: #f8d7da;
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #dc3545;
    }
    .streak-box {
        background-color: #fff3cd;
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #ffc107;
    }
    .signal-card {
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
        border-left: 4px solid;
    }
</style>
""", unsafe_allow_html=True)

# Main Dashboard
st.markdown('<div class="main-header">🎯 Coinryze Signal Analyzer</div>', unsafe_allow_html=True)

# Auto-refresh every 3 seconds
st_autorefresh = st.empty()

# Stats Section
col1, col2, col3, col4, col5 = st.columns(5)

stats = processor.get_stats()

with col1:
    st.metric("Total Signals", stats['total'])
with col2:
    st.metric("Wins", stats['wins'], delta=f"{stats['wins']} wins")
with col3:
    st.metric("Losses", stats['losses'], delta=f"-{stats['losses']} losses", delta_color="inverse")
with col4:
    st.metric("Win Rate", f"{stats['win_rate']}%")
with col5:
    streak_color = "normal" if stats['current_streak'] < 3 else "off"
    st.metric("Current Streak", stats['current_streak'], delta_color=streak_color)

# Live Signals Section
st.subheader("📊 Live Signals Dashboard")

if latest_signals:
    # Create DataFrame for display
    df = pd.DataFrame(latest_signals)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp', ascending=False)
    
    # Display signals in cards
    for _, signal in df.iterrows():
        result_color = "#28a745" if signal['result'] == 'Win' else "#dc3545"
        trade_color = "#28a745" if signal['trade'] == 'Green' else "#dc3545"
        
        col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 2])
        
        with col1:
            st.write(f"**Period ID:** {signal['period_id']}")
        with col2:
            st.write(f"**Time:** {signal['timestamp'].strftime('%H:%M:%S')}")
        with col3:
            st.markdown(f"<div style='color: {result_color}; font-weight: bold;'>{signal['result']}</div>", unsafe_allow_html=True)
        with col4:
            if signal['trade']:
                st.markdown(f"<div style='color: {trade_color}; font-weight: bold;'>{signal['trade']}</div>", unsafe_allow_html=True)
        with col5:
            if signal['quantity']:
                st.write(f"**Qty:** x{signal['quantity']}")
    
    # Win/Loss Chart
    st.subheader("📈 Performance Chart")
    
    chart_data = df.copy()
    chart_data['result_numeric'] = chart_data['result'].apply(lambda x: 1 if x == 'Win' else 0)
    chart_data = chart_data.sort_values('timestamp')
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=chart_data['timestamp'],
        y=chart_data['result_numeric'],
        mode='lines+markers',
        name='Win/Loss',
        line=dict(color='blue'),
        marker=dict(
            size=8,
            color=chart_data['result_numeric'].apply(lambda x: 'green' if x == 1 else 'red'),
            symbol='circle'
        )
    ))
    
    fig.update_layout(
        title='Signal Results Over Time',
        xaxis_title='Time',
        yaxis_title='Result (1=Win, 0=Loss)',
        height=300
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
else:
    st.info("📡 Waiting for signals... Monitoring Telegram channels...")

# System Status
st.sidebar.title("🔧 System Status")
st.sidebar.info("""
**Connected Services:**
- ✅ Telegram Monitoring
- ✅ Cloudflare R2 Storage
- ✅ Real-time Dashboard
""")

st.sidebar.subheader("📋 Last Signal")
if latest_signals:
    last_signal = latest_signals[-1]
    st.sidebar.write(f"**Period:** {last_signal['period_id']}")
    st.sidebar.write(f"**Result:** {last_signal['result']}")
    st.sidebar.write(f"**Time:** {last_signal['timestamp'].strftime('%H:%M:%S')}")
else:
    st.sidebar.write("No signals yet")

# Auto-refresh
time.sleep(3)
st_autorefresh.empty()
st.rerun()
