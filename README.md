# Quant Engine Pro - Real-time Quantitative Analysis Engine

**Status: ✅ FULLY OPERATIONAL**

แอปพลิเคชันวิเคราะห์ข้อมูลเชิงปริมาณ (Quant) ในเวลาจริง พร้อม API และ Dashboard แบบ Interactive

---

## 🚀 การเริ่มต้นใช้งาน

### 1. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

### 2. รันเซิร์ฟเวอร์

```bash
python terryquant.py
```

**Server จะรันที่:** `http://localhost:8000`

---

## 🌐 Web Dashboard

เข้าดู Dashboard แบบ Interactive ได้ที่:

```
http://localhost:8000/dashboard
```

**Features:**
- 📊 Real-time signal gauge
- 💹 Live price updates
- 📈 Technical indicators
- 🎯 Trade recommendations
- 🛡️ Risk management metrics

---

## 📡 API Endpoints

### 1. **Root Endpoint**
```
GET /
```
ส่งคืนข้อมูล API และ endpoints ที่มี

**Response:**
```json
{
  "service": "Quant Engine Pro",
  "version": "2.0.0",
  "status": "running",
  "endpoints": {
    "websocket": "/ws",
    "health": "/health",
    "snapshot": "/snapshot/{symbol}"
  }
}
```

---

### 2. **Health Check**
```
GET /health
```
ตรวจสอบสถานะเซิร์ฟเวอร์

**Response:**
```json
{
  "status": "healthy",
  "active_connections": 0,
  "timestamp": "2026-02-22T17:07:39.648652+00:00",
  "server": "Quant Engine Pro v2.0.0"
}
```

---

### 3. **Get Symbols**
```
GET /symbols
```
ดูรายชื่อสัญลักษณ์ที่สนับสนุน

**Response:**
```json
{
  "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
  "count": 3
}
```

---

### 4. **Get Single Symbol Analysis**
```
GET /snapshot/{symbol}
```
ดึงข้อมูลวิเคราะห์ปัจจุบันของสัญลักษณ์เดียว

**Example:**
```
GET /snapshot/BTCUSDT
```

**Response:**
```json
{
  "symbol": "BTCUSDT",
  "timestamp": "2026-02-22T17:07:39.648652+00:00",
  "market_data": {
    "price": 45230.50,
    "change_24h": 1250.25,
    "change_percent_24h": 2.84,
    "high_24h": 46100.00,
    "low_24h": 44500.00,
    "volume_24h": 850000.00
  },
  "signal": {
    "type": "strong_buy",
    "score": 75,
    "confidence": 85,
    "label": "STRONG BUY"
  },
  "factors": [
    {
      "name": "Trend Strength",
      "impact": 30,
      "description": "EMA20 above EMA50, ADX 35.2",
      "direction": "bullish"
    },
    {
      "name": "Momentum",
      "impact": 25,
      "description": "RSI 68.5, MACD bullish",
      "direction": "bullish"
    },
    {
      "name": "Volatility Position",
      "impact": -5,
      "description": "Price at 65% of BB range",
      "direction": "bearish"
    },
    {
      "name": "Volume Confirmation",
      "impact": 30,
      "description": "Volume 2.5x average",
      "direction": "bullish"
    },
    {
      "name": "Market Structure",
      "impact": 25,
      "description": "Price above VWAP",
      "direction": "bullish"
    }
  ],
  "risk": {
    "volatility_state": "normal",
    "atr_percent": 1.85,
    "recommended_position_size": 0.85,
    "stop_loss_distance": 1250.50
  },
  "regime": "trending_up",
  "active_session": "london",
  "next_event": "NY Open / London-NY Overlap in 1h",
  "recommendation": "Consider LONG at $45000.00 (limit order). Stop loss $43749.50 (1250.50 below). Target $46501.00 (1:2 RRR). Use 85% of normal size due to normal volatility."
}
```

---

### 5. **Get All Symbols Analysis**
```
GET /snapshot
```
ดึงข้อมูลวิเคราะห์สำหรับทุกสัญลักษณ์

**Response:**
```json
{
  "count": 3,
  "timestamp": "2026-02-22T17:07:39.648652+00:00",
  "data": [
    { /* BTCUSDT snapshot */ },
    { /* ETHUSDT snapshot */ },
    { /* BNBUSDT snapshot */ }
  ]
}
```

---

### 6. **WebSocket Real-time Updates**
```
WS ws://localhost:8000/ws
```

เชื่อมต่อ WebSocket เพื่อรับข้อมูลอัปเดตในเวลาจริง

**ตัวอย่าง JavaScript:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Updated signal:', data.signal);
};

// Keep connection alive
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({action: 'ping'}));
  }
}, 30000);
```

---

## 📊 Supported Symbols

| Symbol | Market | Type |
|--------|--------|------|
| BTCUSDT | Binance | Crypto |
| ETHUSDT | Binance | Crypto |
| BNBUSDT | Binance | Crypto |

---

## 🔧 Configuration

### Environment Variables

```bash
# Port (default: 8000)
set PORT=8000

# Host (default: 0.0.0.0)
set HOST=0.0.0.0

# Reload on file changes (default: false)
set RELOAD=false
```

**Example:**
```bash
$env:PORT=3000
python terryquant.py
```

---

## 📈 Signal Types

| Signal | Score | Meaning |
|--------|-------|---------|
| STRONG BUY | 60-100 | Strong uptrend signal |
| BUY | 20-59 | Moderate uptrend signal |
| NEUTRAL | -20-19 | No clear direction |
| SELL | -60--21 | Moderate downtrend signal |
| STRONG SELL | -100--61 | Strong downtrend signal |

---

## 🔍 Technical Indicators Used

- **Trend:** EMA(20, 50), ADX
- **Momentum:** RSI(14), MACD(12, 26, 9)
- **Volatility:** Bollinger Bands(20, 2), ATR(14)
- **Volume:** SMA(20), Volume Profile
- **Structure:** VWAP

---

## 💡 How It Works

### Analysis Loop
1. **Data Collection** → ดึงข้อมูล OHLCV จาก Binance API
2. **Technical Analysis** → คำนวณตัวชี้วัดทางเทคนิค
3. **Signal Generation** → สร้างสัญญาณจากปัจจัยหลายตัว
4. **Risk Assessment** → ประเมินความเสี่ยงและขนาดตำแหน่ง
5. **Broadcasting** → ส่งผลลัพธ์ไปยังไคลเอนต์ที่เชื่อมต่อ

**Update Frequency:** Every 5 seconds

---

## ⚠️ Risk Disclaimer

⚠️ **ข้อมูลนี้เป็นเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน**

- ทำการทดสอบ backtesting ก่อนใช้ในจริง
- ตรวจสอบกับผู้เชี่ยวชาญการเงินเสมอ
- เริ่มจากจำนวนเงินน้อย เพื่อวัดความสามารถ
- ใช้ stop loss เสมอในทุกการเทรด

---

## 🛠️ Troubleshooting

### Port 8000 already in use
```bash
# Kill all Python processes
Get-Process python | Stop-Process -Force
```

### Not enough historical data
- ให้เวลาพอสำหรับการดึงข้อมูล
- ค่าเริ่มต้นใช้เวลา ~30 วินาที

### WebSocket connection failed
- ตรวจสอบ CORS configuration
- ใช้ `ws://` ไม่ใช่ `wss://`

---

## 📝 Requirements

- Python 3.10+
- FastAPI 0.128.0+
- TA-Lib (หรือ pandas-ta)
- aiohttp for async HTTP requests

ดูรายละเอียดเต็ม: [`requirements.txt`](requirements.txt)

---

## 📧 Support

ถ้ามีปัญหา:
1. ตรวจสอบ logs ในเทอร์มินัล
2. ทดสอบ health endpoint: `http://localhost:8000/health`
3. ตรวจสอบ port availability: `netstat -ano | findstr "8000"`

---

## 📄 License

Educational & Research Use Only

---

**Version:** 2.0.0 | **Last Updated:** February 2026
