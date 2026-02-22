# 🚀 Quick Start Guide - Quant Engine Pro

## ⚡ 3-Minute Setup

### Step 1: Setup Environment
```bash
# Navigate to project directory
cd "e:\IV\terry bot"

# Install dependencies (one-time only)
pip install -r requirements.txt
```

### Step 2: Start Server
```bash
python terryquant.py
```

You should see:
```
INFO:     Started server process [14076]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Step 3: Open Dashboard
Open browser and go to:
```
http://localhost:8000/dashboard
```

---

## 🎯 API Quick Reference

### Check Server Status
```bash
curl http://localhost:8000/health
```

### Get Available Symbols
```bash
curl http://localhost:8000/symbols
```

### Get Analysis for Bitcoin
```bash
curl http://localhost:8000/snapshot/BTCUSDT
```

### Get Analysis for All Symbols
```bash
curl http://localhost:8000/snapshot
```

---

## 🔗 Important URLs

| Feature | URL |
|---------|-----|
| Dashboard | http://localhost:8000/dashboard |
| Health Check | http://localhost:8000/health |
| Symbols List | http://localhost:8000/symbols |
| Root API | http://localhost:8000/ |
| WebSocket | ws://localhost:8000/ws |

---

## 📊 Understanding the Signal Types

### Reading the Dashboard Gauge

The gauge shows signal score from -100 to +100:

```
        WEAK      STRONG
RED ←→ YELLOW ←→ GREEN
SELL    NEUTRAL   BUY
```

- **Green (>60):** STRONG BUY - Very bullish
- **Light Green (20-60):** BUY - Moderately bullish
- **Yellow (-20 to 20):** NEUTRAL - No clear direction
- **Orange (-60 to -20):** SELL - Moderately bearish
- **Red (<-60):** STRONG SELL - Very bearish

---

## 💡 Reading the Analysis

### Factors
Each factor shows:
- **Name:** What's being measured
- **Impact:** Numeric score (-50 to +50)
- **Direction:** Bullish or bearish
- **Description:** Specific details

### Risk Profile
- **Volatility State:** low, normal, high, extreme
- **ATR %:** Average True Range as % of price
- **Position Size:** Recommended size (0-100%)
- **Stop Loss Distance:** How much to risk per trade

### Market Regime
- **Trending Up/Down:** Clear trend direction
- **Ranging:** Consolidating pricesRange
- **Breakout:** Moving out of range
- **Reversal:** Potential trend change

---

## ⚙️ Configuration

### Using Environment Variables

**Windows PowerShell:**
```powershell
$env:PORT=3000
python terryquant.py
```

**Windows CMD:**
```cmd
set PORT=3000
python terryquant.py
```

**Linux/Mac:**
```bash
export PORT=3000
python terryquant.py
```

### Available Variables
```
PORT=8000              # Server port
HOST=0.0.0.0           # Server host
RELOAD=false           # Auto-reload on code changes
```

---

## 📱 Accessing from Another Computer

### Step 1: Find Your IP Address

**Windows:**
```bash
ipconfig
# Look for "IPv4 Address"
```

**Linux/Mac:**
```bash
ifconfig
# Look for "inet"
```

### Step 2: Access from Remote

Replace `YOUR_IP` with your computer's IP:
```
http://YOUR_IP:8000/dashboard
```

**Note:** Make sure firewall allows port 8000

---

## 🐛 Troubleshooting

### Error: "Port 8000 already in use"
```bash
# Kill all Python processes
taskkill /f /im python.exe

# Or check what's using the port
netstat -ano | findstr "8000"
```

### WebSocket Won't Connect
- Check if server is running
- Verify port is correct
- Ensure firewall allows connections
- Check browser console for errors

### No Data Appearing
- Wait 30-45 seconds for initial data fetch
- Check `/health` endpoint
- Verify internet connection
- Check server logs in terminal

---

## 📈 Example Use Cases

### 1. Monitor Bitcoin in Real-time
```
Open: http://localhost:8000/dashboard
(Auto-updates every 5 seconds)
```

### 2. Programmatic Analysis
```python
import asyncio
import aiohttp
import json

async def get_analysis():
    async with aiohttp.ClientSession() as session:
        async with session.get('http://localhost:8000/snapshot/BTCUSDT') as resp:
            data = await resp.json()
            print(f"Signal: {data['signal']['label']}")
            print(f"Score: {data['signal']['score']}")
            print(f"Recommendation: {data['recommendation']}")

asyncio.run(get_analysis())
```

### 3. Monitor Multiple Symbols
```javascript
const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'];

async function monitorAll() {
  const data = await fetch('http://localhost:8000/snapshot').then(r => r.json());
  data.data.forEach(asset => {
    console.log(`${asset.symbol}: ${asset.signal.label}`);
  });
}

// Check every 5 seconds
setInterval(monitorAll, 5000);
```

---

## ❓ FAQ

**Q: Can I change the update frequency?**
A: Currently set to 5 seconds. Edit `_analysis_loop()` in terryquant.py

**Q: Does it work with live trading?**
A: No, this is for analysis only. Integrate with broker API separately

**Q: What exchanges are supported?**
A: Currently Binance. Can add others in DataFeed class

**Q: Can I add more symbols?**
A: Yes, edit `self.symbols` in DataFeed.__init__()

**Q: Is the data real-time?**
A: Yes, updates every 5 seconds from Binance API

---

## ✅ You're Ready!

- Dashboard: http://localhost:8000/dashboard
- API Docs: http://localhost:8000/docs (if Swagger enabled)
- Stop Server: Ctrl+C in terminal

Happy analyzing! 📊🚀
