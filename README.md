📁 README.md (Copy-Paste Version)

```markdown
# 🎯 Coinryze Signal Analyzer

A real-time Telegram signal monitoring and analysis dashboard that automatically parses trading signals from Telegram channels, stores them in Cloudflare R2, and displays them in a beautiful Streamlit dashboard.

## 🌟 Features

- **🔐 Secure Telegram Login** - Using string session authentication
- **📡 Real-time Monitoring** - Auto-parses signals from multiple Telegram channels
- **☁️ Cloudflare R2 Storage** - Automatically backs up all signal data to cloud storage
- **📊 Live Dashboard** - Colorful, real-time Streamlit interface with auto-refresh
- **📈 Performance Analytics** - Win/loss tracking, streak counter, and statistics
- **🔄 Auto-Refresh** - Updates every 3 seconds with latest signals
- **🎯 Signal History** - Displays last 30 signals with detailed information

## 🚀 Quick Deployment on Render

### Prerequisites
- GitHub account
- Render.com account
- Telegram account with API credentials
- Cloudflare R2 bucket

### Step-by-Step Deployment

1. **📥 Download Files**
   - Download all files from this repository
   - `app.py` - Main application
   - `requirements.txt` - Python dependencies
   - `.env` - Environment variables template

2. **⚙️ Configure Environment**
   - Edit the `.env` file with your actual credentials:
     ```env
     API_ID=your_telegram_api_id
     API_HASH=your_telegram_api_hash
     SESSION_STRING=your_telegram_session_string
     R2_ACCESS_KEY_ID=your_r2_access_key
     R2_SECRET_ACCESS_KEY=your_r2_secret_key
     R2_BUCKET=your_bucket_name
     R2_ACCOUNT_ID=your_account_id
     R2_ENDPOINT=your_r2_endpoint
     TARGET_CHATS=@ETHGPT60s_bot,@ETHGPT260s_bot
     ```

```

1. 🌐 Deploy on Render
   · Go to Render.com
   · Click "New +" → "Web Service"
   · Connect your GitHub repository
   · Configure the service:
   Build Settings:
   · Build Command: pip install -r requirements.txt
   · Start Command: streamlit run app.py --server.port $PORT --server.address 0.0.0.0
   Environment Variables:
   · Add all variables from your .env file
2. ✅ Launch Service
   · Click "Create Web Service"
   · Wait for build to complete (5-10 minutes)
   · Access your dashboard via the provided URL

📋 File Structure

```
coinryze-analyzer/
├── app.py                 # Main Streamlit application
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables (create from template)
└── README.md            # This file
```

🔧 Configuration

Telegram Setup

1. Get your API credentials from my.telegram.org
2. Generate string session using Telethon
3. Add target channel usernames to TARGET_CHATS

Cloudflare R2 Setup

1. Create R2 bucket in Cloudflare dashboard
2. Generate API credentials
3. Update R2 configuration in .env file

🎮 Usage

Once deployed, the dashboard will automatically:

1. 🔄 Connect to Telegram and start monitoring specified channels
2. 📨 Parse incoming signal messages for period IDs, results, and trade recommendations
3. 💾 Store parsed data in Cloudflare R2 for persistence
4. 📊 Display real-time statistics and signal history
5. 🎯 Show win/loss streaks and performance metrics

📊 Dashboard Sections

· 📈 Live Stats - Total signals, wins, losses, win rate, current streak
· 📋 Signal History - Scrollable list of last 30 signals with colors
· 📊 Performance Chart - Visual timeline of win/loss results
· 🔧 System Status - Connection status and last signal info

Signal Parsing

The system automatically detects:

· ✅ Period IDs (e.g., 202510170352)
· ✅ Results (Win🎉/Lose💔)
· ✅ Trade recommendations (🟢 Green/🔴 Red)
· ✅ Quantity multipliers (x1, x2.5, x6.25)

📄 License

This project is for educational purposes as part of a learning project.

---

🎉 Happy Trading! May your signals be green! 🟢

```

📊 requirements.txt (Enhanced)

```

This README provides complete documentation for your learning project! It includes:

✅ Step-by-step deployment instructions
✅ Technical specifications
✅ Troubleshooting guide
✅ Feature overview
✅ Security information
✅ File structure explanation
