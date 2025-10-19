import streamlit as st
import pandas as pd
import re
import json
import time
from datetime import datetime
import boto3
from botocore.config import Config
import os
from dotenv import load_dotenv
import plotly.graph_objects as go
from collections import deque

# Load environment variables
load_dotenv()

# Global variables
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
                'quantity': 1.0
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
                except:
                    signal_data['quantity'] = 1.0
            
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
            return True
        return False
    
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
            # Add sample data for demo
            self.add_sample_data()
    
    def add_sample_data(self):
        """Add sample data for demo purposes"""
        sample_data = [
            {'period_id': '202510170350', 'result': 'Win', 'trade': 'Red', 'timestamp': '2024-01-01 10:20:15', 'quantity': 1.0},
            {'period_id': '202510170351', 'result': 'Lose', 'trade': 'Green', 'timestamp': '2024-01-01 10:21:15', 'quantity': 2.5},
            {'period_id': '202510170352', 'result': 'Win', 'trade': 'Red', 'timestamp': '2024-01-01 10:22:15', 'quantity': 1.0},
            {'period_id': '202510170353', 'result': 'Win', 'trade': 'Green', 'timestamp': '2024-01-01 10:23:15', 'quantity': 1.0},
            {'period_id': '202510170354', 'result': 'Lose', 'trade': 'Red', 'timestamp': '2024-01-01 10:24:15', 'quantity': 3.0},
        ]
        for data in sample_data:
            self.signals.append(data)
            latest_signals.append(data)
        print("✅ Sample data loaded for demo")
    
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

# Initialize processor
processor = SignalProcessor()

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
    .win-signal {
        background-color: #d4edda;
        padding: 10px;
        border-radius: 8px;
        border-left: 5px solid #28a745;
        margin: 5px 0;
    }
    .loss-signal {
        background-color: #f8d7da;
        padding: 10px;
        border-radius: 8px;
        border-left: 5px solid #dc3545;
        margin: 5px 0;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 5px;
    }
    .status-connected {
        color: #28a745;
        font-weight: bold;
    }
    .status-disconnected {
        color: #dc3545;
        font-weight: bold;
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
        st.metric("✅ Wins", stats['wins'])
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("❌ Losses", stats['losses'])
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("📈 Win Rate", f"{stats['win_rate']}%")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col5:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("🔥 Current Streak", stats['current_streak'])
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Live Signals Section
    st.subheader("📋 Live Signals Dashboard")
    
    signals_list = list(latest_signals)
    if signals_list:
        # Display signals in reverse order (newest first)
        reversed_signals = signals_list[::-1]
        
        for signal in reversed_signals:
            if signal['result'] == 'Win':
                css_class = "win-signal"
                result_icon = "✅ WIN"
                result_color = "#28a745"
            else:
                css_class = "loss-signal"
                result_icon = "❌ LOSS"
                result_color = "#dc3545"
            
            trade_color = "#28a745" if signal['trade'] == 'Green' else "#dc3545"
            
            st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 2])
            
            with col1:
                st.write(f"**Period ID:** `{signal['period_id']}`")
            with col2:
                st.write(f"**Time:** `{signal['timestamp'].split(' ')[1]}`")
            with col3:
                st.markdown(f"<span style='color: {result_color}; font-weight: bold;'>{result_icon}</span>", unsafe_allow_html=True)
            with col4:
                if signal['trade']:
                    st.markdown(f"<span style='color: {trade_color}; font-weight: bold;'>{signal['trade'].upper()}</span>", unsafe_allow_html=True)
            with col5:
                st.write(f"**Quantity:** x{signal.get('quantity', 1.0)}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Performance Chart
        if len(signals_list) > 1:
            st.subheader("📈 Performance Trend")
            
            # Create simple chart data
            chart_data = []
            for i, signal in enumerate(signals_list):
                chart_data.append({
                    'index': i,
                    'result': 1 if signal['result'] == 'Win' else 0,
                    'period': signal['period_id'][-3:],  # Last 3 digits
                    'color': 'green' if signal['result'] == 'Win' else 'red'
                })
            
            df = pd.DataFrame(chart_data)
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['index'],
                y=df['result'],
                mode='lines+markers',
                line=dict(color='blue', width=2),
                marker=dict(
                    size=8,
                    color=df['color'],
                    symbol='circle'
                )
            ))
            
            fig.update_layout(
                title='Signal Results Trend (1=Win, 0=Loss)',
                xaxis_title='Signal Sequence',
                yaxis_title='Result',
                height=300,
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📡 Waiting for signals...")
        st.write("**System is ready to receive signals!**")
    
    # System Status Sidebar
    st.sidebar.title("🔧 System Status")
    
    # Check services
    r2_connected = all([
        os.getenv('R2_ACCESS_KEY_ID'),
        os.getenv('R2_SECRET_ACCESS_KEY'), 
        os.getenv('R2_BUCKET')
    ])
    
    telegram_connected = all([
        os.getenv('API_ID'),
        os.getenv('API_HASH'),
        os.getenv('SESSION_STRING')
    ])
    
    st.sidebar.subheader("📊 Connection Status")
    
    if r2_connected:
        st.sidebar.markdown('<p class="status-connected">✅ Cloudflare R2: Connected</p>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown('<p class="status-disconnected">❌ Cloudflare R2: Missing Credentials</p>', unsafe_allow_html=True)
    
    if telegram_connected:
        st.sidebar.markdown('<p class="status-connected">✅ Telegram: Ready</p>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown('<p class="status-disconnected">❌ Telegram: Setup Required</p>', unsafe_allow_html=True)
    
    st.sidebar.markdown('<p class="status-connected">✅ Dashboard: Active</p>', unsafe_allow_html=True)
    
    # Last Signal Info
    st.sidebar.subheader("📋 Last Signal")
    if signals_list:
        last_signal = signals_list[-1]
        st.sidebar.write(f"**Period:** `{last_signal['period_id']}`")
        st.sidebar.write(f"**Result:** `{last_signal['result']}`")
        st.sidebar.write(f"**Time:** `{last_signal['timestamp'].split(' ')[1]}`")
        if last_signal['trade']:
            st.sidebar.write(f"**Trade:** `{last_signal['trade']}`")
    else:
        st.sidebar.write("No signals received yet")
    
    # Manual Testing
    st.sidebar.subheader("🧪 Test Signal Input")
    test_signal = st.sidebar.text_area("Paste signal message:", height=100)
    if st.sidebar.button("Process Test Signal"):
        if test_signal:
            signal_data = processor.parse_signal(test_signal)
            if signal_data:
                processor.add_signal(signal_data)
                st.sidebar.success(f"✅ Signal processed: {signal_data['period_id']}")
            else:
                st.sidebar.error("❌ Invalid signal format")
        else:
            st.sidebar.warning("⚠️ Please enter a signal message")
    
    # Auto-refresh
    time.sleep(3)
    st.rerun()

if __name__ == "__main__":
    main()
