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
from collections import deque

# Load environment variables
load_dotenv()

# Global variables
signal_queue = queue.Queue()
latest_signals = deque(maxlen=30)

class SignalProcessor:
    def __init__(self):
        self.signals = []
        self.load_existing_data()
    
    def parse_signal(self, message):
        try:
            signal_data = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'period_id': None,
                'result': None,
                'trade': None,
                'quantity': None,
                'message': message[:200]  # Limit message length
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
                try:
                    signal_data['quantity'] = float(quantity_match.group(1))
                except ValueError:
                    signal_data['quantity'] = None
            
            # Only add if we have valid data
            if signal_data['period_id'] and signal_data['result']:
                return signal_data
            return None
            
        except Exception as e:
            print(f"Error parsing signal: {e}")
            return None
    
    def add_signal(self, signal_data):
        if signal_data and not any(s.get('period_id') == signal_data['period_id'] for s in self.signals):
            self.signals.append(signal_data)
            # Keep only last 50 signals
            if len(self.signals) > 50:
                self.signals = self.signals[-50:]
            
            # Update latest signals for dashboard
            global latest_signals
            latest_signals.append(signal_data)
            
            # Upload to R2
            self.upload_to_r2()
            print(f"✅ Signal added: {signal_data['period_id']} - {signal_data['result']}")
    
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
            print("✅ Data uploaded to R2 successfully")
            
        except Exception as e:
            print(f"❌ Error uploading to R2: {e}")
    
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
            latest_signals.extend(self.signals[-30:])
            print(f"✅ Loaded {len(self.signals)} existing signals from R2")
            
        except Exception as e:
            print(f"ℹ️ No existing data found: {e}")
    
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
            print("✅ Telegram client started successfully")
            
            # Get target chats
            target_chats = [chat.strip() for chat in os.getenv('TARGET_CHATS', '').split(',') if chat.strip()]
            print(f"🎯 Monitoring channels: {target_chats}")
            
            @self.client.on(self.client.NewMessage)
            async def handler(event):
                try:
                    chat = await event.get_chat()
                    chat_username = getattr(chat, 'username', None)
                    
                    if chat_username in target_chats or str(chat.id) in target_chats:
                        message_text = event.message.text
                        if message_text:
                            print(f"📨 New message from {chat_username}: {message_text[:100]}...")
                            signal_data = self.processor.parse_signal(message_text)
                            if signal_data:
                                self.processor.add_signal(signal_data)
                                signal_queue.put(signal_data)
                except Exception as e:
                    print(f"❌ Error handling message: {e}")
            
            self.is_running = True
            print("🔍 Telegram monitoring started...")
            
            # Keep the client running
            await self.client.run_until_disconnected()
            
        except Exception as e:
            print(f"❌ Error in Telegram monitor: {e}")
    
    def stop(self):
        self.is_running = False
        if self.client:
            self.client.disconnect()

def run_telegram_monitor(processor):
    monitor = TelegramMonitor(processor)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(monitor.start())
    except Exception as e:
        print(f"❌ Telegram monitor crashed: {e}")
    finally:
        loop.close()

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
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
        font-weight: bold;
    }
    .win-box {
        background-color: #d4edda;
        padding: 8px;
        border-radius: 5px;
        border-left: 4px solid #28a745;
        margin: 2px 0;
    }
    .loss-box {
        background-color: #f8d7da;
        padding: 8px;
        border-radius: 5px;
        border-left: 4px solid #dc3545;
        margin: 2px 0;
    }
    .signal-card {
        padding: 8px;
        margin: 4px 0;
        border-radius: 5px;
        border-left: 4px solid;
        font-size: 0.9rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #007bff;
        margin: 5px;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Main Dashboard
    st.markdown('<div class="main-header">🎯 Coinryze Signal Analyzer</div>', unsafe_allow_html=True)
    
    # Stats Section
    col1, col2, col3, col4, col5 = st.columns(5)
    stats = processor.get_stats()
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("📊 Total Signals", stats['total'])
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("✅ Wins", stats['wins'], delta=f"{stats['wins']} wins")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("❌ Losses", stats['losses'], delta=f"-{stats['losses']} losses", delta_color="inverse")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("📈 Win Rate", f"{stats['win_rate']}%")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col5:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        streak_color = "normal" if stats['current_streak'] < 3 else "off"
        st.metric("🔥 Current Streak", stats['current_streak'], delta_color=streak_color)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Live Signals Section
    st.subheader("📋 Live Signals (Last 30)")
    
    if list(latest_signals):
        # Display signals in reverse order (newest first)
        reversed_signals = list(latest_signals)[::-1]
        
        for signal in reversed_signals:
            result_color = "#28a745" if signal['result'] == 'Win' else "#dc3545"
            trade_color = "#28a745" if signal['trade'] == 'Green' else "#dc3545"
            
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 2])
            
            with col1:
                st.write(f"**{signal['period_id']}**")
            with col2:
                st.write(f"`{signal['timestamp'].split(' ')[1]}`")
            with col3:
                if signal['result'] == 'Win':
                    st.markdown(f"<span style='color: {result_color}; font-weight: bold;'>✅ WIN</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color: {result_color}; font-weight: bold;'>❌ LOSS</span>", unsafe_allow_html=True)
            with col4:
                if signal['trade']:
                    st.markdown(f"<span style='color: {trade_color}; font-weight: bold;'>{signal['trade'].upper()}</span>", unsafe_allow_html=True)
            with col5:
                if signal['quantity']:
                    st.write(f"**x{signal['quantity']}**")
        
        # Performance Chart
        st.subheader("📈 Performance Trend")
        if len(reversed_signals) > 1:
            chart_data = reversed_signals[::-1]  # Reverse back for chronological order
            df = pd.DataFrame(chart_data)
            df['result_numeric'] = df['result'].apply(lambda x: 1 if x == 'Win' else 0)
            df['index'] = range(len(df))
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['index'],
                y=df['result_numeric'],
                mode='lines+markers',
                name='Win/Loss',
                line=dict(color='blue', width=2),
                marker=dict(
                    size=8,
                    color=df['result_numeric'].apply(lambda x: 'green' if x == 1 else 'red'),
                    symbol='circle'
                )
            ))
            
            fig.update_layout(
                title='Signal Results Trend',
                xaxis_title='Signal Sequence',
                yaxis_title='Result (1=Win, 0=Loss)',
                height=300,
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📡 Waiting for signals... Monitoring Telegram channels...")
        st.write("**Connected Channels:**")
        target_chats = [chat.strip() for chat in os.getenv('TARGET_CHATS', '').split(',') if chat.strip()]
        for chat in target_chats:
            st.write(f"- `{chat}`")
    
    # System Status
    st.sidebar.title("🔧 System Status")
    st.sidebar.info("""
    **Connected Services:**
    - ✅ Telegram Monitoring
    - ✅ Cloudflare R2 Storage  
    - ✅ Real-time Dashboard
    - 🔄 Auto-refresh: Every 3s
    """)
    
    st.sidebar.subheader("📋 Last Signal")
    if list(latest_signals):
        last_signal = list(latest_signals)[-1]
        st.sidebar.write(f"**Period:** `{last_signal['period_id']}`")
        st.sidebar.write(f"**Result:** `{last_signal['result']}`")
        st.sidebar.write(f"**Time:** `{last_signal['timestamp'].split(' ')[1]}`")
        if last_signal['trade']:
            st.sidebar.write(f"**Trade:** `{last_signal['trade']}`")
    else:
        st.sidebar.write("No signals received yet")
    
    st.sidebar.subheader("ℹ️ Info")
    st.sidebar.write(f"**Total Signals:** {stats['total']}")
    st.sidebar.write(f"**Last Update:** {datetime.now().strftime('%H:%M:%S')}")
    
    # Auto-refresh
    time.sleep(3)
    st.rerun()

if __name__ == "__main__":
    main()
